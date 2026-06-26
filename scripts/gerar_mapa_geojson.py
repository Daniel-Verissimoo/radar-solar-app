"""
ETL Inicial — Gera o arquivo mapa_rmr.geojson a partir de shapefiles IBGE + parquets ANEEL.

Executar UMA ÚNICA VEZ para semear o cache assíncrono do servidor:
    uv run python scripts/gerar_mapa_geojson.py
    
Arquivo gerado em: data/data/processed/mapa_rmr.geojson
"""
from __future__ import annotations

import json
import sys
import unicodedata
from pathlib import Path
from collections import defaultdict

import shapefile
import pandas as pd

# ── CAMINHOS ABSOLUTOS (BLINDAGEM) ──────────────────────────────────────────
ROOT_DIR = Path(r"C:\radar-solar-copia\radar-solar-dev")
RAW_DIR = ROOT_DIR / 'data' / 'data' / 'raw'
PROCESSED_DIR = ROOT_DIR / 'data' / 'data' / 'processed'
PARQUET_DIR = PROCESSED_DIR / 'aneel'
GEOJSON_PATH = PROCESSED_DIR / 'mapa_rmr.geojson'

# Shapefiles IBGE
MUNICIPIOS_SHP = RAW_DIR / 'ibge' / 'PE_Municipios_2024' / 'PE_Municipios_2024.shp'
BAIRROS_SHP = RAW_DIR / 'ibge' / 'PE_bairros_CD2022' / 'PE_bairros_CD2022.shp'

# Parquets ANEEL (já processados)
INSTALACOES_PARQUET = PARQUET_DIR / 'rmr_instalacoes.parquet'
MUNICIPIOS_PARQUET = PARQUET_DIR / 'rmr_municipios.parquet'
BAIRROS_PARQUET = PARQUET_DIR / 'rmr_bairros.parquet'

# Códigos IBGE da RMR
RMR_MUNICIPIOS = {
    '2600054',  # Abreu e Lima
    '2601052',  # Aracoiaba
    '2602902',  # Cabo de Santo Agostinho
    '2603454',  # Camaragibe
    '2606804',  # Igarassu
    '2607208',  # Ipojuca
    '2607604',  # Ilha de Itamaraca
    '2607752',  # Itapissuma
    '2607901',  # Jaboatao dos Guararapes
    '2609402',  # Moreno
    '2609600',  # Olinda
    '2610707',  # Paulista
    '2611606',  # Recife
    '2613701',  # Sao Lourenco da Mata
}

# Mapeamento codigo IBGE -> nome normalizado (para cruzar com parquet)
CODIGO_PARA_NOME = {
    '2600054': 'ABREU E LIMA',
    '2601052': 'ARACOIABA',
    '2602902': 'CABO DE SANTO AGOSTINHO',
    '2603454': 'CAMARAGIBE',
    '2606804': 'IGARASSU',
    '2607208': 'IPOJUCA',
    '2607604': 'ILHA DE ITAMARACA',
    '2607752': 'ITAPISSUMA',
    '2607901': 'JABOATAO DOS GUARARAPES',
    '2609402': 'MORENO',
    '2609600': 'OLINDA',
    '2610707': 'PAULISTA',
    '2611606': 'RECIFE',
    '2613701': 'SAO LOURENCO DA MATA',
}


def norm(value: str) -> str:
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return ' '.join(value.upper().split())


def bairro_key(value: str) -> str:
    conectores = {'DA', 'DE', 'DI', 'DO', 'DAS', 'DOS'}
    return ' '.join(part for part in norm(value).split() if part not in conectores)


def feature(geometry: dict, properties: dict) -> dict:
    return {'type': 'Feature', 'geometry': geometry, 'properties': properties}


def feature_collection(features: list[dict]) -> dict:
    return {'type': 'FeatureCollection', 'features': features}


def carregar_instalacoes_aneel() -> tuple[dict, dict, dict]:
    """Carrega instalacoes, agregados e charts dos parquets ANEEL."""
    from src.services.aneel_service import carregar_instalacoes_aneel as _original
    return _original()


def main() -> int:
    # ── 1. VALIDAÇÃO ────────────────────────────────────────────────────────
    for path, label in [
        (MUNICIPIOS_SHP, 'Shapefile municipios'),
        (BAIRROS_SHP, 'Shapefile bairros'),
        (INSTALACOES_PARQUET, 'Parquet instalacoes'),
        (MUNICIPIOS_PARQUET, 'Parquet municipios'),
        (BAIRROS_PARQUET, 'Parquet bairros'),
    ]:
        if not path.exists():
            print(f'[ERRO] {label} ausente: {path}')
            return 1
        print(f'[OK] {label}: {path}')

    # ── 2. CARREGAR MÉTRICAS DOS PARQUETS ───────────────────────────────────
    print('\nCarregando metricas dos parquets...')
    df_municipios = pd.read_parquet(MUNICIPIOS_PARQUET)
    df_bairros = pd.read_parquet(BAIRROS_PARQUET)
    df_instalacoes = pd.read_parquet(INSTALACOES_PARQUET)

    # Agregar qtd_modulos por municipio a partir das instalacoes
    modulos_por_municipio = (
        df_instalacoes.groupby('municipio_norm')['qtd_modulos']
        .sum()
        .to_dict()
    )

    # Índice: codigo IBGE -> metricas
    metricas_municipio: dict[str, dict] = {}
    for _, row in df_municipios.iterrows():
        codigo = row.get('cod_municipio_ibge') or ''
        nome_norm = norm(row['municipio'])
        qtd_mod = int(modulos_por_municipio.get(nome_norm, 0) or 0)
        if codigo in RMR_MUNICIPIOS:
            metricas_municipio[codigo] = {
                'qtd_instalacoes': int(row['qtd_instalacoes']),
                'potencia_kw': round(float(row['potencia_kw']), 2),
                'qtd_modulos': qtd_mod,
            }
        # Fallback: buscar pelo nome
        if codigo not in RMR_MUNICIPIOS or not codigo:
            for ibge_cod, ibge_nome in CODIGO_PARA_NOME.items():
                if norm(ibge_nome) == nome_norm:
                    metricas_municipio[ibge_cod] = {
                        'qtd_instalacoes': int(row['qtd_instalacoes']),
                        'potencia_kw': round(float(row['potencia_kw']), 2),
                        'qtd_modulos': qtd_mod,
                    }
                    break

    # Bairros: nome normalizado -> metricas (por codigo municipio)
    # Agregar qtd_modulos dos bairros a partir do df_instalacoes
    bairro_modulos = (
        df_instalacoes.groupby(['municipio_norm', 'bairro_estimado'])['qtd_modulos']
        .sum()
        .to_dict()
    )

    metricas_bairro: dict[str, dict[str, dict]] = defaultdict(dict)
    for _, row in df_bairros.iterrows():
        codigo = None
        for ibge_cod, ibge_nome in CODIGO_PARA_NOME.items():
            if norm(ibge_nome) == norm(row['municipio']):
                codigo = ibge_cod
                break
        if codigo:
            nome_bairro = str(row['bairro_estimado'])
            # Buscar qtd_modulos do bairro
            mun_norm = norm(row['municipio'])
            qtd_mod = int(bairro_modulos.get((mun_norm, nome_bairro), 0) or 0)
            metricas_bairro[codigo][nome_bairro] = {
                'qtd_instalacoes': float(row['qtd_instalacoes']),
                'potencia_kw': round(float(row['potencia_kw']), 2),
                'qtd_modulos': qtd_mod,
            }

    # ── 3. CARREGAR INSTALAÇÕES + CHARTS (via serviço existente) ────────────
    print('Carregando instalacoes e charts (aneel_service)...')
    sys.path.insert(0, str(ROOT_DIR))
    agregados, instalacoes_por_municipio, charts = carregar_instalacoes_aneel()

    # ── 4. LER SHAPEFILES E MONTAR FEATURES ─────────────────────────────────
    print('Processando shapefile de municipios...')
    municipios_features: list[dict] = []
    municipios_por_codigo: dict[str, dict] = {}

    reader = shapefile.Reader(str(MUNICIPIOS_SHP), encoding='cp1252')
    for sr in reader.iterShapeRecords():
        rec = sr.record.as_dict()
        codigo = rec['CD_MUN']
        if codigo not in RMR_MUNICIPIOS:
            continue
        nome = rec['NM_MUN']
        m = metricas_municipio.get(codigo, {'qtd_instalacoes': 0, 'potencia_kw': 0.0, 'qtd_modulos': 0})
        f = feature(sr.shape.__geo_interface__, {
            'codigo': codigo,
            'nome': nome,
            'tipo': 'municipio',
            'metricas': m,
        })
        municipios_features.append(f)
        municipios_por_codigo[codigo] = f

    print('Processando shapefile de bairros...')
    bairros_por_municipio: dict[str, list[dict]] = {c: [] for c in RMR_MUNICIPIOS}

    reader2 = shapefile.Reader(str(BAIRROS_SHP), encoding='utf-8')
    for sr in reader2.iterShapeRecords():
        rec = sr.record.as_dict()
        codigo = rec['CD_MUN']
        if codigo not in RMR_MUNICIPIOS:
            continue
        nome_bairro = rec['NM_BAIRRO']
        bairros_por_municipio[codigo].append(feature(sr.shape.__geo_interface__, {
            'codigo': rec['CD_BAIRRO'],
            'nome': nome_bairro,
            'municipio_codigo': codigo,
            'municipio_nome': rec['NM_MUN'],
            'tipo': 'bairro',
        }))

    # ── 5. FALLBACK: municipios sem bairros no shapefile ────────────────────
    for codigo, bairros in bairros_por_municipio.items():
        if bairros or codigo not in municipios_por_codigo:
            continue
        mun = municipios_por_codigo[codigo]
        bairros.append(feature(mun['geometry'], {
            'codigo': f'{codigo}-sem-bairros',
            'nome': mun['properties']['nome'],
            'municipio_codigo': codigo,
            'municipio_nome': mun['properties']['nome'],
            'tipo': 'bairro_fallback',
        }))

    # ── 6. DISTRIBUIR MÉTRICAS NOS BAIRROS ──────────────────────────────────
    print('Distribuindo metricas nos bairros...')
    bairro_metricas: dict[str, dict[str, dict]] = {c: {} for c in RMR_MUNICIPIOS}

    for municipio_nome, instalacoes in instalacoes_por_municipio.items():
        mun_feature = next(
            (f for f in municipios_features if norm(f['properties']['nome']) == norm(municipio_nome)),
            None,
        )
        if not mun_feature:
            continue
        codigo_mun = mun_feature['properties']['codigo']

        # Nomes válidos de bairros para este municipio
        nomes_validos: dict[str, str] = {}
        for f in bairros_por_municipio.get(codigo_mun, []):
            if f['properties']['tipo'] == 'bairro':
                key = bairro_key(f['properties']['nome'])
                nomes_validos[key] = f['properties']['nome']

        for inst in instalacoes:
            bairro_inst = inst.get('bairro', '') or 'Nao identificado'
            bairros_possiveis = []

            key_inst = bairro_key(bairro_inst)
            if key_inst in nomes_validos:
                bairros_possiveis = [nomes_validos[key_inst]]
            else:
                # Tenta match parcial
                for valid_key, valid_nome in nomes_validos.items():
                    if valid_key in key_inst or key_inst in valid_key:
                        bairros_possiveis = [valid_nome]
                        break

            if not bairros_possiveis:
                bairros_possiveis = [bairro_inst]

            inst['bairros_possiveis'] = bairros_possiveis
            peso = 1.0 / len(bairros_possiveis)
            for bairro_nome in bairros_possiveis:
                bm = bairro_metricas[codigo_mun].setdefault(
                    bairro_nome,
                    {'qtd_instalacoes': 0.0, 'potencia_kw': 0.0, 'qtd_modulos': 0.0},
                )
                bm['qtd_instalacoes'] += peso
                bm['potencia_kw'] += inst['potencia_kw'] * peso
                bm['qtd_modulos'] += inst['qtd_modulos'] * peso

    # Aplicar metricas nos features de bairro
    nao_identificado_por_municipio = {}
    for codigo, features_list in bairros_por_municipio.items():
        # Extrair nao identificado se existir
        nao_id = bairro_metricas.get(codigo, {}).get('Nao identificado')
        if nao_id:
            nao_identificado_por_municipio[codigo] = {
                'qtd_instalacoes': round(nao_id['qtd_instalacoes'], 2),
                'potencia_kw': round(nao_id['potencia_kw'], 2),
                'qtd_modulos': round(nao_id['qtd_modulos'], 2),
            }

        # Contar quantas features tem o mesmo nome (geometrias duplicadas)
        qtd_por_nome: dict[str, int] = defaultdict(int)
        for f in features_list:
            qtd_por_nome[f['properties']['nome']] += 1

        for f in features_list:
            nome = f['properties']['nome']
            bm = bairro_metricas.get(codigo, {}).get(
                nome,
                {'qtd_instalacoes': 0.0, 'potencia_kw': 0.0, 'qtd_modulos': 0.0},
            )
            divisor = qtd_por_nome[nome]
            f['properties']['metricas'] = {
                'qtd_instalacoes': round(bm['qtd_instalacoes'] / divisor, 2),
                'potencia_kw': round(bm['potencia_kw'] / divisor, 2),
                'qtd_modulos': round(bm['qtd_modulos'] / divisor, 2),
            }

    # ── 7. MONTAR AGREGADOS (maximos, totais) ──────────────────────────────
    print('Montando agregados...')
    maximos = {
        'qtd_instalacoes': max((f['properties']['metricas']['qtd_instalacoes'] for f in municipios_features), default=0),
        'potencia_kw': max((f['properties']['metricas']['potencia_kw'] for f in municipios_features), default=0),
        'qtd_modulos': max((f['properties']['metricas']['qtd_modulos'] for f in municipios_features), default=0),
    }
    totais = {
        'qtd_instalacoes': sum(f['properties']['metricas']['qtd_instalacoes'] for f in municipios_features),
        'potencia_kw': round(sum(f['properties']['metricas']['potencia_kw'] for f in municipios_features), 2),
        'qtd_modulos': sum(f['properties']['metricas']['qtd_modulos'] for f in municipios_features),
    }
    maximos_bairros = {
        codigo: max(
            (f['properties']['metricas']['qtd_instalacoes'] for f in features),
            default=0,
        )
        for codigo, features in bairros_por_municipio.items()
    }

    # Ordenar
    municipios_features.sort(key=lambda f: f['properties']['nome'])
    for features in bairros_por_municipio.values():
        features.sort(key=lambda f: f['properties']['nome'])

    # ── 8. MONTAR ESTRUTURA FINAL ───────────────────────────────────────────
    print('Montando estrutura final do GeoJSON...')
    result = {
        'municipios': feature_collection(municipios_features),
        'maximos': maximos,
        'totais': totais,
        'maximosBairros': maximos_bairros,
        'naoIdentificadoPorMunicipio': nao_identificado_por_municipio,
        'instalacoesPorMunicipio': instalacoes_por_municipio,
        'bairrosPorMunicipio': {
            codigo: feature_collection(features)
            for codigo, features in bairros_por_municipio.items()
        },
        'charts': charts,
    }

    # ── 9. SALVAR ────────────────────────────────────────────────────────────
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    with open(GEOJSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    tamanho_mb = GEOJSON_PATH.stat().st_size / 1024 / 1024
    print(f'\nGeoJSON gerado com sucesso: {GEOJSON_PATH}')
    print(f'Tamanho: {tamanho_mb:.2f} MB')
    print(f'Municipios: {len(municipios_features)}')
    for cod, feats in bairros_por_municipio.items():
        nome_mun = municipios_por_codigo.get(cod, {}).get('properties', {}).get('nome', cod)
        print(f'  {nome_mun}: {len(feats)} bairros')
    print(f'Instalacoes carregadas: {sum(len(v) for v in instalacoes_por_municipio.values())}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
