"""Oracle lookup: map a GED file name to 003-{atendimento}-{pessoa}."""

from __future__ import annotations

from typing import Any

from ged_transfer.config import load_db_config

SQL_LOOKUP = """
select '003-'|| nvl(nr_atendimento,tasy.obter_ultimo_atendimento(cd_pessoa_fisica)) ||'-' || cd_pessoa_fisica
from tasy.ged_atendimento
where cd_pessoa_fisica is not null
and regexp_substr(ds_arquivo,'/([^/]+)\\?',1,1,null,1) = :file_name
"""


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


def lookup_new_name(conn: Any, file_name: str) -> str | None:
    """
    Return the first non-empty queried name for this file, or None to ignore it.
    """
    with conn.cursor() as cur:
        cur.execute(SQL_LOOKUP, file_name=file_name)
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
