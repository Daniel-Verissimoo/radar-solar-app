from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


# ── Helpers de log no terminal ──────────────────────────────────────────────


def _ts() -> str:
    return time.strftime('%H:%M:%S')


def log_info(msg: str) -> None:
    print(f'[{_ts()}]  INFO  {msg}')


def log_ok(msg: str) -> None:
    print(f'[{_ts()}]  OK    {msg}')


def log_aviso(msg: str) -> None:
    print(f'[{_ts()}]  AVISO {msg}')


def log_erro(msg: str) -> None:
    print(f'[{_ts()}]  ERRO  {msg}', file=sys.stderr)


def log_dados(msg: str, linhas: int, fonte: str = '') -> None:
    fonte_str = f' [{fonte}]' if fonte else ''
    print(f'[{_ts()}]  DADOS {msg}: {linhas} linha(s){fonte_str}')


def log_separador(titulo: str = '') -> None:
    linha = '=' * 50
    if titulo:
        print(f'\n{linha}\n  {titulo}\n{linha}')
    else:
        print(f'\n{linha}')


def _only_digits(value: Any) -> str:
    return re.sub(r'\D', '', '' if value is None else str(value))


def _normalizar_estado(value: Any) -> str:
    estado = '' if value is None else str(value).strip().upper()
    if estado and len(estado) != 2:
        raise ValueError('Informe a UF com 2 letras, exemplo: PE.')
    return estado


def _normalizar_cep(value: Any) -> str:
    cep = _only_digits(value)
    if cep and len(cep) != 8:
        raise ValueError('Informe um CEP valido com 8 digitos.')
    return cep


def _buscar_endereco_por_cep(cep: str) -> dict[str, str] | None:
    try:
        with urlopen(f'https://viacep.com.br/ws/{cep}/json/', timeout=8) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    if data.get('erro'):
        return None

    return {
        'logradouro': data.get('logradouro') or '',
        'cidade': data.get('localidade') or '',
        'estado': data.get('uf') or '',
    }


def _format_datetime_br(value: datetime | None) -> str:
    if value is None:
        return '-'
    return value.strftime('%d/%m/%Y as %H:%M')
