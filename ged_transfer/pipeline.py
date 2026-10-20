"""Process each origin file.

DB lookup on: run the SQL file; the returned value is the destiny file name.
DB lookup off: move every file and keep its name.

ALWAYS_LISTENING on: after that pass, stay open and repeat for new files.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ged_transfer.config import always_listening, lookup_enabled, resolve_sql_file
from ged_transfer.db import connect, lookup_new_name, read_lookup_sql
from ged_transfer.paths import (
    destination_name,
    ensure_dest_access,
    ensure_origin_access,
    list_origin_files,
    move_to_dest,
)

# Poll instead of a directory watch. Origin is often a UNC share, and Windows
# change notifications are not reliable there.
LISTEN_POLL_SECONDS = 2

_Signature = tuple[int, int]


@dataclass
class _Batch:
    moved: int = 0
    ignored: int = 0
    errors: int = 0
    ignored_signatures: dict[str, _Signature] = field(default_factory=dict)
    failed_keys: set[str] = field(default_factory=set)


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a) == str(b)


def _track_key(path: Path) -> str:
    return path.name.casefold()


def _signature(path: Path) -> _Signature | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


def _ready_files(
    files: list[Path],
    pending: dict[str, _Signature],
    ignored: dict[str, _Signature],
) -> list[Path]:
    """Return files whose size and mtime are unchanged since the last look.

    The first look only records the file, so a copy that is still arriving
    is not moved. A file already ignored is skipped until its signature
    changes. Names that disappeared are dropped from both maps.
    """
    ready: list[Path] = []
    present: set[str] = set()
    for path in files:
        key = _track_key(path)
        present.add(key)
        signature = _signature(path)
        if signature is None:
            continue
        if ignored.get(key) == signature:
            pending.pop(key, None)
            continue
        previous = pending.get(key)
        if previous != signature:
            pending[key] = signature
            continue
        ready.append(path)

    for key in [key for key in pending if key not in present]:
        del pending[key]
    for key in [key for key in ignored if key not in present]:
        del ignored[key]
    return ready


def _close_connection(conn: Any | None) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except Exception:
        pass


def _connection_alive(conn: Any) -> bool:
    ping = getattr(conn, "ping", None)
    if not callable(ping):
        return True
    try:
        ping()
        return True
    except Exception:
        return False


def _open_connection(conn: Any | None) -> Any:
    if conn is not None and _connection_alive(conn):
        return conn
    had_connection = conn is not None
    _close_connection(conn)
    if had_connection:
        print("   DB connection dropped. Reconnecting...")
    return connect()


def _is_db_error(exc: Exception) -> bool:
    return type(exc).__module__.startswith("oracledb")


def _remember_ignore(batch: _Batch, key: str, signature: _Signature | None) -> None:
    if signature is not None:
        batch.ignored_signatures[key] = signature


def _handle_file(
    path: Path,
    dest: Path,
    lookup: bool,
    sql_text: str,
    conn: Any | None,
    batch: _Batch,
    signature: _Signature | None,
    key: str,
) -> None:
    if not lookup:
        target = move_to_dest(path, dest)
        print(f"   Move: {path.name} -> {target.name}")
        batch.moved += 1
        return

    queried = lookup_new_name(conn, path.name, sql_text)
    if not queried:
        print(f"   Ignore (no name from SQL): {path.name}")
        batch.ignored += 1
        _remember_ignore(batch, key, signature)
        return

    new_name = destination_name(queried)
    if not new_name:
        print(f"   Ignore (empty name from SQL): {path.name}")
        batch.ignored += 1
        _remember_ignore(batch, key, signature)
        return

    target = move_to_dest(path, dest, new_name)
    print(f"   Move: {path.name} -> {target.name}")
    batch.moved += 1


def _process_files(
    files: list[Path],
    dest: Path,
    lookup: bool,
    sql_text: str,
    conn_box: list[Any | None],
    *,
    retry_db: bool,
) -> _Batch:
    batch = _Batch()
    if lookup:
        conn_box[0] = _open_connection(conn_box[0])

    for path in files:
        key = _track_key(path)
        signature = _signature(path)
        retried = False
        while True:
            try:
                if lookup and conn_box[0] is None:
                    conn_box[0] = _open_connection(None)
                _handle_file(
                    path,
                    dest,
                    lookup,
                    sql_text,
                    conn_box[0],
                    batch,
                    signature,
                    key,
                )
                break
            except SystemExit:
                raise
            except Exception as e:
                if lookup and retry_db and not retried and _is_db_error(e):
                    retried = True
                    print(f"   DB error on {path.name}. Reconnecting...")
                    _close_connection(conn_box[0])
                    conn_box[0] = None
                    continue
                print(f"   Error on {path.name}: {e}")
                batch.errors += 1
                batch.failed_keys.add(key)
                break
    return batch


def _print_summary(lookup: bool, batch: _Batch) -> None:
    print()
    if lookup:
        print(
            f"Done. lookup=on  moved={batch.moved}  "
            f"ignored={batch.ignored}  errors={batch.errors}"
        )
    else:
        print(f"Done. lookup=off  moved={batch.moved}  errors={batch.errors}")


def _seed_watch_state(
    files: list[Path],
    batch: _Batch,
    pending: dict[str, _Signature],
    ignored: dict[str, _Signature],
) -> None:
    """Remember ignored and failed files so the next poll does not repeat them.

    A failed file stays pending with its current signature, so the next look
    retries it once the file is stable. A successful move drops that name.
    """
    ignored.update(batch.ignored_signatures)
    for path in files:
        key = _track_key(path)
        if key in batch.failed_keys:
            signature = _signature(path)
            if signature is not None:
                pending[key] = signature
            continue
        pending.pop(key, None)
        if key not in batch.ignored_signatures:
            ignored.pop(key, None)


def _listen(
    origin: Path,
    dest: Path,
    lookup: bool,
    sql_text: str,
    conn_box: list[Any | None],
    pending: dict[str, _Signature],
    ignored: dict[str, _Signature],
) -> None:
    print("   Waiting for new files. Press Ctrl+C to stop.")
    while True:
        time.sleep(LISTEN_POLL_SECONDS)
        try:
            files = list_origin_files(origin, dest)
        except OSError as e:
            print(f"   Cannot list origin: {e}")
            continue

        ready = _ready_files(files, pending, ignored)
        if not ready:
            continue

        print(f"   New files: {len(ready)}")
        try:
            batch = _process_files(
                ready,
                dest,
                lookup,
                sql_text,
                conn_box,
                retry_db=True,
            )
        except SystemExit:
            raise
        except Exception as e:
            print(f"   Cannot connect to the database: {e}")
            _close_connection(conn_box[0])
            conn_box[0] = None
            continue

        _print_summary(lookup, batch)
        _seed_watch_state(ready, batch, pending, ignored)


def _execute(conn_box: list[Any | None]) -> None:
    print("GED file transfer")
    listening = always_listening()
    lookup = lookup_enabled()
    sql_text = ""
    if lookup:
        sql_path = resolve_sql_file()
        sql_text = read_lookup_sql(sql_path)
        print("   DB lookup: on")
        print(f"   SQL file:  {sql_path}")
    else:
        print("   DB lookup: off")
        print("   Action: move every file and keep its name")
    if listening:
        print(f"   Always listening: on, poll {LISTEN_POLL_SECONDS:g}s")

    origin = ensure_origin_access()
    dest = ensure_dest_access()
    if _same_dir(origin, dest):
        raise SystemExit(
            "DOWNLOAD_DIR and DEST_DIR resolve to the same folder. "
            "Set two different paths in .env."
        )

    files = list_origin_files(origin, dest)
    print(f"   Files in origin: {len(files)}")

    pending: dict[str, _Signature] = {}
    ignored: dict[str, _Signature] = {}
    if files:
        try:
            batch = _process_files(
                files,
                dest,
                lookup,
                sql_text,
                conn_box,
                retry_db=listening,
            )
        except SystemExit:
            raise
        except Exception as e:
            if not listening:
                raise
            print(f"   Cannot connect to the database: {e}")
            _close_connection(conn_box[0])
            conn_box[0] = None
            batch = _Batch(
                errors=len(files),
                failed_keys={_track_key(path) for path in files},
            )
        _print_summary(lookup, batch)
        if not listening:
            if batch.errors:
                raise SystemExit(1)
            return
        _seed_watch_state(files, batch, pending, ignored)
    else:
        print("Nothing to do.")
        if not listening:
            return

    _listen(origin, dest, lookup, sql_text, conn_box, pending, ignored)


def main() -> None:
    conn_box: list[Any | None] = [None]
    try:
        _execute(conn_box)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        _close_connection(conn_box[0])
        conn_box[0] = None
