"""Process each origin file.

DB lookup on: run the SQL file; the returned value is the destiny file name.
DB lookup off: move every file and keep its name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ged_transfer.config import lookup_enabled, resolve_sql_file
from ged_transfer.db import connect, lookup_new_name, read_lookup_sql
from ged_transfer.paths import (
    destination_name,
    ensure_dest_access,
    ensure_origin_access,
    list_origin_files,
    move_to_dest,
)


def _same_dir(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:
        return str(a) == str(b)


def main() -> None:
    print("GED file transfer")
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

    origin = ensure_origin_access()
    dest = ensure_dest_access()
    if _same_dir(origin, dest):
        raise SystemExit(
            "DOWNLOAD_DIR and DEST_DIR resolve to the same folder. "
            "Set two different paths in .env."
        )

    files = list_origin_files(origin, dest)
    print(f"   Files in origin: {len(files)}")
    if not files:
        print("Nothing to do.")
        return

    conn: Any | None = None
    moved = 0
    ignored = 0
    errors = 0

    try:
        if lookup:
            conn = connect()

        for path in files:
            try:
                if not lookup:
                    target = move_to_dest(path, dest)
                    print(f"   Move: {path.name} -> {target.name}")
                    moved += 1
                    continue

                queried = lookup_new_name(conn, path.name, sql_text)
                if not queried:
                    print(f"   Ignore (no name from SQL): {path.name}")
                    ignored += 1
                    continue

                new_name = destination_name(queried)
                if not new_name:
                    print(f"   Ignore (empty name from SQL): {path.name}")
                    ignored += 1
                    continue

                target = move_to_dest(path, dest, new_name)
                print(f"   Move: {path.name} -> {target.name}")
                moved += 1
            except SystemExit:
                raise
            except Exception as e:
                print(f"   Error on {path.name}: {e}")
                errors += 1
    finally:
        if conn is not None:
            conn.close()

    print()
    if lookup:
        print(f"Done. lookup=on  moved={moved}  ignored={ignored}  errors={errors}")
    else:
        print(f"Done. lookup=off  moved={moved}  errors={errors}")
    if errors:
        raise SystemExit(1)
