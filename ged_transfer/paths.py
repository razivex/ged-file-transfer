"""Origin / destiny directory resolution (local / UNC) and file moves."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

from ged_transfer.config import load_dir_config

_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_ILLEGAL_NAME_CHARS = '<>:"/\\|?*'
_authenticated_shares: set[str] = set()


def _collapse_dup_seps(s: str, sep: str = "\\") -> str:
    if not s:
        return s
    doubled = sep + sep
    while doubled in s:
        s = s.replace(doubled, sep)
    return s


def is_unc_path(path: Path | str) -> bool:
    s = str(path)
    if s.startswith("\\\\?\\UNC\\") or s.startswith("//?/UNC/"):
        return True
    s = s.replace("/", "\\")
    if s.startswith("\\\\?\\"):
        return False
    return s.startswith("\\\\")


def unc_share_root(path: Path | str) -> str:
    s = str(path).replace("/", "\\")
    if s.startswith("\\\\?\\UNC\\"):
        s = "\\\\" + s[8:]
    if not s.startswith("\\\\"):
        raise ValueError(f"Not a UNC path: {path}")
    bits = [b for b in s[2:].split("\\") if b]
    if len(bits) < 2:
        raise ValueError(f"UNC path must include server and share: {path}")
    return f"\\\\{bits[0]}\\{bits[1]}"


def normalize_dir_path(raw: str, key: str) -> Path:
    """Accept common directory forms and return a usable Path."""
    s = (raw or "").strip().strip("\ufeff")
    if (len(s) >= 2) and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()

    if s.lower().startswith("file:"):
        parsed = urlparse(s)
        if parsed.netloc and parsed.netloc not in (".", "localhost"):
            tail = unquote(parsed.path or "").lstrip("/").replace("/", "\\")
            s = f"\\\\{parsed.netloc}\\{tail}"
        else:
            path_part = unquote(parsed.path or "")
            if os.name == "nt" and re.match(r"^/[A-Za-z]:", path_part):
                path_part = path_part[1:]
            s = path_part

    s = os.path.expandvars(os.path.expanduser(s)).strip()
    if not s:
        raise ValueError(f"{key} is empty after expansion")

    unc_lead = re.match(r"^[\\/]{2,}", s)
    if unc_lead:
        body = s[unc_lead.end() :]
        body = body.replace("/", "\\")
        body = _collapse_dup_seps(body, "\\")
        body = body.strip("\\")
        if not body:
            raise ValueError(f"Invalid UNC {key} (missing server/share): {raw!r}")
        s = "\\\\" + body
    else:
        if os.name == "nt":
            s = s.replace("/", "\\")
            if re.match(r"^[A-Za-z]:", s):
                drive, rest = s[:2], s[2:]
                rest = _collapse_dup_seps(rest.lstrip("\\"), "\\")
                s = drive + "\\" + rest if rest else drive + "\\"
            else:
                s = _collapse_dup_seps(s, "\\")

    if os.name == "nt":
        if s.startswith("\\\\"):
            bits = [b for b in s[2:].split("\\") if b]
            if len(bits) < 2:
                raise ValueError(
                    f"UNC {key} must be \\\\server\\share\\... got: {raw!r}"
                )
            s = "\\\\" + "\\".join(bits)
        else:
            while len(s) > 3 and s.endswith("\\"):
                s = s[:-1]
            if re.fullmatch(r"[A-Za-z]:", s):
                s = s + "\\"

    path = Path(s)
    if not is_unc_path(path) and not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _can_list(path: Path) -> bool:
    try:
        if not path.is_dir():
            return False
        next(path.iterdir(), None)
        return True
    except OSError:
        return False


def _can_write_under(path: Path) -> bool:
    try:
        path = Path(path)
        if path.exists():
            if not path.is_dir():
                return False
            probe_parent = path
        else:
            cur = path
            while not cur.exists():
                parent = cur.parent
                if parent == cur:
                    return False
                cur = parent
            if not cur.is_dir():
                return False
            probe_parent = cur

        probe = probe_parent / ".ged_transfer_write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass
            return False
    except OSError:
        return False


def _net_use_connect(share: str, user: str, password: str) -> None:
    """Authenticate to a Windows share via `net use`. Never logs the password."""
    if share in _authenticated_shares:
        return
    subprocess.run(
        ["net", "use", share, "/delete", "/y"],
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    result = subprocess.run(
        ["net", "use", share, password, f"/user:{user}"],
        capture_output=True,
        text=True,
        creationflags=_CREATE_NO_WINDOW,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise SystemExit(
            f"Failed to authenticate to share {share} as {user}.\n"
            f"  Windows said: {detail or f'exit code {result.returncode}'}\n"
            "  Check directory paths and DOWNLOAD_DIR_USER / DOWNLOAD_DIR_PASSWORD "
            "(or DEST_DIR_USER / DEST_DIR_PASSWORD) in .env.\n"
            "  User may be HOST\\user or DOMAIN\\user."
        )
    _authenticated_shares.add(share)


def _auth_if_needed(
    path: Path,
    user: str | None,
    password: str | None,
    key: str,
    accessible: bool,
) -> None:
    """Connect to the UNC share only when the path is not already usable."""
    if accessible or not is_unc_path(path):
        return
    try:
        share = unc_share_root(path)
    except ValueError as e:
        raise SystemExit(str(e)) from e
    if not user or not password:
        raise SystemExit(
            f"Cannot access UNC {key} path: {path}\n"
            f"  Share: {share}\n"
            "  Path is not accessible with the current Windows session.\n"
            "  Set DOWNLOAD_DIR_USER and DOWNLOAD_DIR_PASSWORD in .env "
            "(used only when needed)."
        )
    print(f"   UNC path not accessible yet — authenticating to {share} as {user}...")
    _net_use_connect(share, user, password)


def ensure_origin_access() -> Path:
    cfg = load_dir_config()
    try:
        origin = normalize_dir_path(str(cfg["origin"]), "DOWNLOAD_DIR")
    except ValueError as e:
        raise SystemExit(f"Invalid DOWNLOAD_DIR in .env: {e}") from e

    _auth_if_needed(
        origin,
        cfg["origin_user"],
        cfg["origin_password"],
        "DOWNLOAD_DIR",
        accessible=_can_list(origin) and _can_write_under(origin),
    )

    if not origin.exists():
        raise SystemExit(f"Origin folder does not exist: {origin}")
    if not origin.is_dir():
        raise SystemExit(f"Origin path is not a folder: {origin}")
    if not _can_list(origin):
        raise SystemExit(f"Cannot list files in origin folder: {origin}")
    if not _can_write_under(origin):
        raise SystemExit(
            f"Cannot move files out of origin folder (no write/delete): {origin}"
        )
    print(f"   Origin:  {origin}")
    return origin


def ensure_dest_access() -> Path:
    cfg = load_dir_config()
    try:
        dest = normalize_dir_path(str(cfg["dest"]), "DEST_DIR")
    except ValueError as e:
        raise SystemExit(f"Invalid DEST_DIR in .env: {e}") from e

    _auth_if_needed(
        dest,
        cfg["dest_user"],
        cfg["dest_password"],
        "DEST_DIR",
        accessible=_can_write_under(dest),
    )

    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Cannot create destiny folder: {dest}\n  Error: {e}") from e
    if not _can_write_under(dest):
        raise SystemExit(f"Cannot write to destiny folder: {dest}")
    print(f"   Destiny: {dest}")
    return dest


def unique_path(path: Path) -> Path:
    """If path exists, append _1, _2, ... before the extension."""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 1
    candidate = path.with_name(f"{stem}_{i}{suffix}")
    while candidate.exists():
        i += 1
        candidate = path.with_name(f"{stem}_{i}{suffix}")
    return candidate


def sanitize_filename(name: str) -> str:
    cleaned = "".join(
        "_" if (c in _ILLEGAL_NAME_CHARS or ord(c) < 32) else c for c in name
    )
    return cleaned.rstrip(" .")


def dest_filename(original: Path, queried_name: str) -> str | None:
    """
    Build the destiny file name as ``{queried}_{original_name}``.

    The query result is the prefix. The original file name (including
    extension) is appended after an underscore. If the query result already
    ends with the same extension as the original, that extension is stripped
    so it is not duplicated in the prefix.

    Returns None when the query result is empty after sanitizing.
    """
    prefix = sanitize_filename(queried_name.strip())
    if not prefix:
        return None
    queried_path = Path(prefix)
    if (
        queried_path.suffix
        and queried_path.suffix.casefold() == original.suffix.casefold()
    ):
        prefix = queried_path.stem
        if not prefix:
            return None
    original_name = sanitize_filename(original.name)
    if not original_name:
        return None
    return f"{prefix}_{original_name}"


def starts_with_003(path: Path) -> bool:
    return path.name.startswith("003")


def list_origin_files(origin: Path, dest: Path) -> list[Path]:
    """Non-recursive files in origin, excluding anything already under dest."""
    try:
        dest_resolved = dest.resolve()
    except OSError:
        dest_resolved = dest

    files: list[Path] = []
    for item in origin.iterdir():
        if not item.is_file():
            continue
        try:
            resolved = item.resolve()
        except OSError:
            resolved = item
        try:
            resolved.relative_to(dest_resolved)
            continue
        except ValueError:
            pass
        files.append(item)
    files.sort(key=lambda p: p.name.casefold())
    return files


def move_to_dest(source: Path, dest_dir: Path, new_name: str | None = None) -> Path:
    """Move source into dest_dir, optionally renaming. Never overwrites."""
    name = new_name if new_name else source.name
    target = unique_path(dest_dir / name)
    shutil.move(str(source), str(target))
    return target
