"""Oracle lookup: the SQL file returns the destiny file name."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ged_transfer.config import load_db_config

_BIND = re.compile(r":file_name\b", re.IGNORECASE)


def connect() -> Any:
    cfg = load_db_config()
    try:
        import oracledb
    except ImportError as e:
        raise SystemExit(
            "Package 'oracledb' is required for the GED lookup.\n"
            "  pip install oracledb\n"
            f"  ({e})"
        ) from e

    print(f"   DB host: {cfg['host']}:{cfg['port']}/{cfg['service']}")
    print(f"   DB user: {cfg['user']}")
    return oracledb.connect(
        user=cfg["user"],
        password=cfg["password"],
        host=cfg["host"],
        port=int(cfg["port"]),
        service_name=cfg["service"],
    )


def read_lookup_sql(path: Path) -> str:
    """Read the lookup statement. A single trailing semicolon is removed."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as e:
        raise SystemExit(f"Cannot read SQL file: {path}\n  {e}") from e

    sql = text.strip()
    if sql.endswith(";"):
        sql = sql[:-1].rstrip()
    if not sql:
        raise SystemExit(f"SQL file is empty: {path}")
    if _BIND.search(sql) is None:
        raise SystemExit(
            "The SQL file must bind the current file name as :file_name.\n"
            f"  File: {path}"
        )
    return sql


def lookup_new_name(conn: Any, file_name: str, sql: str) -> str | None:
    """
    Return the first non-empty queried name for this file, or None to ignore it.
    """
    with conn.cursor() as cur:
        cur.execute(sql, file_name=file_name)
        for row in cur:
            if not row:
                continue
            value = row[0]
            if value is None:
                continue
            name = str(value).strip()
            if name:
                return name
    return None
