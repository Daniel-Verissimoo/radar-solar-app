import os
from pathlib import Path

from peewee import SqliteDatabase, PostgresqlDatabase, OperationalError
from src.utils import log_info, log_ok, log_aviso

DATABASE_URL = os.getenv('DATABASE_URL', '')

BASE_DIR = Path(__file__).resolve().parent.parent

def _conectar_sqlite() -> SqliteDatabase:
    CAMINHO_DB = BASE_DIR / 'data' / 'radarsolar.db'
    log_info(f'Banco SQLite: {CAMINHO_DB}')
    db = SqliteDatabase(CAMINHO_DB, pragmas={'foreign_keys': 1})
    log_ok('Conexao SQLite estabelecida com foreign_keys=ON')
    return db

if DATABASE_URL:
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    try:
        db = PostgresqlDatabase(
            parsed.path.lstrip('/'),
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname or 'localhost',
            port=parsed.port or 5432,
        )
        db.connect(reuse_if_open=True)
        db.close()
        log_ok(f'Conexao PostgreSQL estabelecida: {parsed.hostname}/{parsed.path.lstrip("/")}')
    except OperationalError:
        log_aviso(f'PostgreSQL indisponivel em {parsed.hostname}:{parsed.port}, usando SQLite como fallback')
        db = _conectar_sqlite()
else:
    db = _conectar_sqlite()
