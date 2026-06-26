"""
Migra dados do SQLite local para PostgreSQL.
Uso: python scripts/migrar_sqlite_para_postgres.py

Requisitos:
  1. DATABASE_URL configurado no .env apontando para o PostgreSQL
  2. Tabelas ja criadas no PostgreSQL (rode o app uma vez com DATABASE_URL)
  3. SQLite local com dados em data/radarsolar.db
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', '')
if not DATABASE_URL:
    print('ERRO: Defina DATABASE_URL no .env antes de rodar a migracao.')
    sys.exit(1)

os.environ['DATABASE_URL'] = DATABASE_URL

TABELAS = ['cnpjcache', 'fatura', 'instalacaosolar', 'lead', 'empresaperfil', 'usuario']


def sqlite_conn():
    import sqlite3
    base_dir = Path(__file__).resolve().parents[1]
    db_path = base_dir / 'data' / 'radarsolar.db'
    if not db_path.exists():
        print(f'ERRO: SQLite nao encontrado em {db_path}')
        sys.exit(1)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def pg_conn():
    import psycopg2
    from urllib.parse import urlparse
    url = urlparse(os.environ['DATABASE_URL'])
    conn = psycopg2.connect(
        dbname=url.path.lstrip('/'),
        user=url.username,
        password=url.password,
        host=url.hostname or 'localhost',
        port=url.port or 5432,
    )
    return conn


def contar_sqlite(conn, tabela):
    return conn.execute(f'SELECT COUNT(*) FROM {tabela}').fetchone()[0]

def contar_pg(conn, tabela):
    cur = conn.cursor()
    cur.execute(f'SELECT COUNT(*) FROM {tabela}')
    return cur.fetchone()[0]


def migrar():
    sqlite = sqlite_conn()
    pg = pg_conn()
    pg.autocommit = True
    total_inseridos = 0

    for tabela in TABELAS:
        qtd_sqlite = contar_sqlite(sqlite, tabela)
        qtd_pg = contar_pg(pg, tabela)

        if qtd_sqlite == 0:
            print(f'[OK] {tabela}: vazio, nada a migrar')
            continue

        print(f'[   ] {tabela}: {qtd_sqlite} registros no SQLite, {qtd_pg} no PG', end='')

        if qtd_pg > 0:
            print(' — ja populado, pulando')
            continue

        rows = sqlite.execute(f'SELECT * FROM {tabela}').fetchall()
        if not rows:
            continue

        colunas = list(rows[0].keys())
        placeholders = ', '.join(['%s'] * len(colunas))
        colunas_str = ', '.join(colunas)

        valores = [[row[c] for c in colunas] for row in rows]

        cur = pg.cursor()
        cur.executemany(
            f'INSERT INTO {tabela} ({colunas_str}) VALUES ({placeholders})',
            valores,
        )
        pg.commit()
        inseridos = cur.rowcount
        total_inseridos += inseridos
        print(f' — migrados {inseridos} registros')

    sqlite.close()
    pg.close()
    print(f'\nMigracao concluida. Total: {total_inseridos} registros migrados.')


if __name__ == '__main__':
    migrar()
