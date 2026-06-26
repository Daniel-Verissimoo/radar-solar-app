import sys
from pathlib import Path

from src.database import CAMINHO_DB
from src.models import criar_tabelas
from src.utils import log_info, log_ok, log_erro


def inicializar_banco() -> None:
    log_info(f"Inicializando banco SQLite em: {CAMINHO_DB}")
    try:
        criar_tabelas()
        log_ok("Tabelas criadas fisicamente no radarsolar.db")
    except Exception as e:
        log_erro(f"Falha ao criar a base de dados: {e}")


if __name__ == "__main__":
    inicializar_banco()