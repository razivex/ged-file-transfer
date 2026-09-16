"""Env loading and directory / DB settings. Never log secret values."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _env_search_paths(path: Path | None = None) -> list[Path]:
    if path is not None:
        return [path]
    env_path = PROJECT_ROOT / ".env"
    return [env_path] if env_path.is_file() else []


def load_dotenv(path: Path | None = None) -> None:
    """
    Minimal .env loader (no extra dependency). Does not override existing env vars.

    Path-friendly: keeps backslashes as written (no escape decoding).
    """
    for env_path in _env_search_paths(path):
        if not env_path.is_file():
            continue
        text = env_path.read_text(encoding="utf-8-sig")
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            else:
                if " #" in value:
                    value = value.split(" #", 1)[0].rstrip()
                elif "\t#" in value:
                    value = value.split("\t#", 1)[0].rstrip()
            if key and key not in os.environ:
                os.environ[key] = value


def _raw(key: str) -> str:
    return (os.environ.get(key) or "").strip()


def _configured(value: str) -> bool:
    if not value:
        return False
    return value.lower() not in {"none", "default", "local", "-", ".", "null"}


def load_dir_config() -> dict[str, str | None]:
    """Origin / destiny paths and optional share credentials. Never log passwords."""
    load_dotenv()
    origin = _raw("DOWNLOAD_DIR")
    dest = _raw("DEST_DIR")
    if not _configured(origin):
        raise SystemExit(
            "Missing DOWNLOAD_DIR (origin) in .env.\n"
            f"  Copy .env.example to .env in {PROJECT_ROOT}\n"
            "  and set DOWNLOAD_DIR to the folder that holds the files."
        )
    if not _configured(dest):
        raise SystemExit(
            "Missing DEST_DIR (destiny) in .env.\n"
            f"  Copy .env.example to .env in {PROJECT_ROOT}\n"
            "  and set DEST_DIR to the folder that should receive the files."
        )
    origin_user = _raw("DOWNLOAD_DIR_USER") or None
    origin_password = _raw("DOWNLOAD_DIR_PASSWORD") or None
    dest_user = _raw("DEST_DIR_USER") or origin_user
    dest_password = _raw("DEST_DIR_PASSWORD") or origin_password
    return {
        "origin": origin,
        "dest": dest,
        "origin_user": origin_user,
        "origin_password": origin_password,
        "dest_user": dest_user,
        "dest_password": dest_password,
    }


def load_db_config() -> dict[str, str]:
    """
    Oracle connection settings.

    Requires DB_USER, DB_PASSWORD, DB_HOST, and DB_SERVICE.
    DB_PORT defaults to 1521.
    """
    load_dotenv()
    user = _raw("DB_USER")
    password = _raw("DB_PASSWORD")
    host = _raw("DB_HOST")
    port = _raw("DB_PORT") or "1521"
    service = _raw("DB_SERVICE")

    if not user or not password:
        raise SystemExit(
            "Missing DB credentials.\n"
            f"  Set DB_USER and DB_PASSWORD in {PROJECT_ROOT / '.env'}\n"
            "  Plus DB_HOST and DB_SERVICE."
        )
    if not host or not service:
        raise SystemExit(
            "Missing DB_HOST or DB_SERVICE in .env.\n"
            "  Example: DB_HOST=hostname  DB_PORT=1521  DB_SERVICE=SERVICE_NAME"
        )
    return {
        "user": user,
        "password": password,
        "host": host,
        "port": port,
        "service": service,
    }
