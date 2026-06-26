from __future__ import annotations

import argparse
from datetime import datetime
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.database import db
from src.models import CnpjCache
from src.utils import log_info, log_ok, log_aviso, log_erro, log_dados, log_separador

BASE_DIR = Path(__file__).resolve().parent.parent
EMPREENDIMENTOS_CSV = BASE_DIR / 'data' / 'processed' / 'aneel' / 'empreendimento-geracao-distribuida-rmr.csv'
PARQUET_PATH = BASE_DIR / 'data' / 'processed' / 'aneel' / 'rmr_instalacoes.parquet'

CNPJA_DELAY_SECONDS = 12.5
GEOCODING_DELAY = 1.1
CNPJA_URL = 'https://open.cnpja.com/office'
NOMINATIM_URL = 'https://nominatim.openstreetmap.org/search'


def only_digits(value: object) -> str:
    return ''.join(ch for ch in str(value) if ch.isdigit())


def carregar_cnpjs_do_csv() -> list[str]:
    if not EMPREENDIMENTOS_CSV.exists():
        log_erro(f'Arquivo nao encontrado: {EMPREENDIMENTOS_CSV}')
        return []

    linhas = EMPREENDIMENTOS_CSV.read_text(encoding='latin1').splitlines()
    if not linhas:
        return []

    header = linhas[0].split(';')
    try:
        idx = header.index('NumCPFCNPJ')
    except ValueError:
        log_erro('Coluna NumCPFCNPJ nao encontrada no CSV.')
        return []

    cnpjs_unicos: set[str] = set()
    for linha in linhas[1:]:
        partes = linha.split(';')
        if idx >= len(partes):
            continue
        cnpj_raw = only_digits(partes[idx])
        if len(cnpj_raw) == 14:
            cnpjs_unicos.add(cnpj_raw)

    return sorted(cnpjs_unicos)


def consultar_cnpja(cnpj: str) -> dict | None:
    url = f'{CNPJA_URL}/{cnpj}'
    request = Request(url, headers={'User-Agent': 'RadarSolar/1.0'})
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        if exc.code == 404:
            log_aviso(f'  CNPJ {cnpj} nao encontrado (404)')
            return {'taxId': cnpj, 'company': {}}
        if exc.code == 429:
            log_aviso(f'  Rate limited. Aguardando 60s...')
            time.sleep(60)
            return consultar_cnpja(cnpj)
        log_erro(f'  HTTP {exc.code} para {cnpj}')
        return None
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        log_erro(f'  Erro na requisicao {cnpj}: {exc}')
        return None


def extrair_dados_cnpj(dados: dict) -> dict:
    endereco = dados.get('address') or {}
    empresa = dados.get('company') or {}
    telefones = dados.get('phones') or []
    emails = dados.get('emails') or []

    def telefone_formatado(pos: int) -> str | None:
        if pos >= len(telefones):
            return None
        telefone = telefones[pos] or {}
        area = telefone.get('area') or ''
        numero = telefone.get('number') or ''
        valor = f'{area} {numero}'.strip()
        return valor or None

    return {
        'cnpj': only_digits(dados.get('taxId', '')),
        'razao_social': empresa.get('name'),
        'nome_fantasia': dados.get('alias'),
        'logradouro': endereco.get('street'),
        'numero': endereco.get('number'),
        'complemento': endereco.get('details'),
        'cep': only_digits(endereco.get('zip', '')),
        'bairro': endereco.get('district'),
        'cidade': endereco.get('city'),
        'estado': endereco.get('state'),
        'telefone1': telefone_formatado(0),
        'telefone2': telefone_formatado(1),
        'email': (emails[0] or {}).get('address') if emails else None,
    }


def montar_endereco_completo(dados: dict) -> str | None:
    end = dados.get('address') or {}
    partes = [end.get('street'), end.get('number'), end.get('district'),
              end.get('city'), end.get('state'), 'Brasil']
    partes = [p for p in partes if p]
    if not partes:
        return None
    return ', '.join(partes)


def geocodificar(endereco: str) -> tuple[float | None, float | None]:
    params = f'?q={quote(endereco)}&format=json&limit=1'
    request = Request(f'{NOMINATIM_URL}{params}',
                      headers={'User-Agent': 'RadarSolar/1.0 (geocoding)'})
    try:
        with urlopen(request, timeout=10) as resp:
            resultados = json.loads(resp.read().decode('utf-8'))
        if resultados:
            return (float(resultados[0]['lat']), float(resultados[0]['lon']))
    except (URLError, TimeoutError, json.JSONDecodeError, KeyError) as exc:
        log_erro(f'    Erro geocodificacao: {exc}')
    return (None, None)


def carregar_cnpj_por_empreendimento() -> dict[str, str]:
    colunas = ['CodEmpreendimento', 'NumCPFCNPJ', 'SigTipoConsumidor']
    df = pd.read_csv(EMPREENDIMENTOS_CSV, sep=';', encoding='latin1', usecols=colunas)
    df = df[df['SigTipoConsumidor'] == 'PJ']
    mapa: dict[str, str] = {}
    for _, row in df.iterrows():
        cnpj = only_digits(row['NumCPFCNPJ'])
        if len(cnpj) == 14:
            mapa[str(row['CodEmpreendimento']).strip()] = cnpj
    return mapa


def atualizar_parquet() -> None:
    if not PARQUET_PATH.exists():
        log_aviso('  Parquet nao encontrado, pulando.')
        return

    cnpj_por_emp = carregar_cnpj_por_empreendimento()
    cache_por_cnpj: dict[str, CnpjCache] = {
        c.cnpj: c for c in CnpjCache.select()
    }
    if not cache_por_cnpj:
        log_info('  Cache vazio, nada a atualizar.')
        return

    df = pd.read_parquet(PARQUET_PATH)
    mask_pj = df['tipo_consumidor'] == 'PJ'
    atualizados_cep = 0
    atualizados_bairro = 0

    for idx in df[mask_pj].index:
        cod_emp = str(df.at[idx, 'cod_empreendimento']).strip()
        cnpj = cnpj_por_emp.get(cod_emp)
        if not cnpj:
            continue
        cache = cache_por_cnpj.get(cnpj)
        if not cache:
            continue

        cep_cache = only_digits(cache.cep or '')
        if len(cep_cache) == 8:
            cep_atual = str(df.at[idx, 'cep_original'] or '').strip()
            if cep_atual != cep_cache:
                df.at[idx, 'cep_original'] = cep_cache
                df.at[idx, 'cep_prefixo'] = cep_cache[:5]
                atualizados_cep += 1

        if cache.bairro:
            bairro_atual = str(df.at[idx, 'bairro_estimado'] or '').strip()
            if bairro_atual != cache.bairro:
                df.at[idx, 'bairro_estimado'] = cache.bairro
                atualizados_bairro += 1

    log_dados('CEPs atualizados', atualizados_cep)
    log_dados('Bairros atualizados', atualizados_bairro)

    if atualizados_cep or atualizados_bairro:
        df.to_parquet(PARQUET_PATH, index=False)
        log_ok(f'  Parquet salvo.')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Atualiza cache CNPJ e enriquece parquets ANEEL.')
    parser.add_argument('--limit', type=int, default=None, help='Processa no maximo N CNPJs pendentes.')
    parser.add_argument('--dry-run', action='store_true', help='Lista pendencias sem consultar APIs nem gravar dados.')
    parser.add_argument('--skip-geocode', action='store_true', help='Consulta CNPJa sem geocodificar no Nominatim.')
    parser.add_argument('--parquet-only', action='store_true', help='Apenas aplica cache existente no parquet.')
    parser.add_argument('--no-parquet', action='store_true', help='Nao atualiza o parquet ao final.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db.connect()
    db.create_tables([CnpjCache])

    if args.parquet_only:
        log_info('Atualizando parquet com dados do cache...')
        atualizar_parquet()
        db.close()
        return 0

    try:
        cnpjs_csv = carregar_cnpjs_do_csv()
        ja_cacheados = {c.cnpj for c in CnpjCache.select(CnpjCache.cnpj)}
        cnpjs_pendentes = [c for c in cnpjs_csv if c not in ja_cacheados]

        log_dados('CNPJs no CSV', len(cnpjs_csv))
        log_dados('Ja cacheados', len(ja_cacheados))
        log_dados('Pendentes', len(cnpjs_pendentes))

        if args.limit is not None:
            cnpjs_pendentes = cnpjs_pendentes[:max(args.limit, 0)]
            log_dados('Limite aplicado', len(cnpjs_pendentes))

        if args.dry_run:
            for cnpj in cnpjs_pendentes:
                log_info(f'Pendente: {cnpj}')
            log_info('Dry-run concluido sem consultas ou gravacoes.')
            return 0

        if not cnpjs_pendentes:
            log_info('Nada a fazer.')
            if not args.no_parquet:
                log_info('Atualizando parquet com dados do cache...')
                atualizar_parquet()
            return 0

        for i, cnpj in enumerate(cnpjs_pendentes, start=1):
            log_info(f'[{i}/{len(cnpjs_pendentes)}] Consultando {cnpj}...')
            dados = consultar_cnpja(cnpj)
            if dados is None:
                log_aviso(f'  Pulando {cnpj} apos erro.')
                time.sleep(CNPJA_DELAY_SECONDS)
                continue

            endereco = montar_endereco_completo(dados)
            lat = lng = None
            if endereco and not args.skip_geocode:
                log_info(f'  Geocodificando: {endereco}')
                lat, lng = geocodificar(endereco)
                if lat and lng:
                    log_ok(f'    -> {lat:.5f}, {lng:.5f}')
                else:
                    log_aviso('    -> sem coordenadas')
                time.sleep(GEOCODING_DELAY)
            elif endereco:
                log_info('  Geocodificacao pulada (--skip-geocode).')

            with db.atomic():
                CnpjCache.get_or_create(
                    cnpj=only_digits(dados.get('taxId', cnpj)),
                    defaults={
                        **extrair_dados_cnpj(dados),
                        'latitude': lat,
                        'longitude': lng,
                        'fetched_at': datetime.now(),
                    },
                )

            if i < len(cnpjs_pendentes):
                time.sleep(CNPJA_DELAY_SECONDS)

        if not args.no_parquet:
            log_info('Atualizando parquet com dados do cache...')
            atualizar_parquet()

        log_separador('Concluido')
        return 0
    finally:
        if not db.is_closed():
            db.close()


if __name__ == '__main__':
    raise SystemExit(main())
