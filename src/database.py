import os
from pathlib import Path

from peewee import SqliteDatabase, PostgresqlDatabase
from src.utils import log_info, log_ok

DATABASE_URL = os.getenv('DATABASE_URL', '')

if DATABASE_URL:
    from urllib.parse import urlparse
    parsed = urlparse(DATABASE_URL)
    db = PostgresqlDatabase(
        parsed.path.lstrip('/'),
        user=parsed.username,
        password=parsed.password,
        host=parsed.hostname or 'localhost',
        port=parsed.port or 5432,
    )
    log_ok(f'Conexao PostgreSQL estabelecida: {parsed.hostname}/{parsed.path.lstrip("/")}')
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    CAMINHO_DB = BASE_DIR / 'data' / 'radarsolar.db'
    log_info(f'Banco SQLite: {CAMINHO_DB}')
    db = SqliteDatabase(CAMINHO_DB, pragmas={'foreign_keys': 1})
    log_ok('Conexao SQLite estabelecida com foreign_keys=ON')
