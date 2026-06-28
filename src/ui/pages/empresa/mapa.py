from __future__ import annotations

import hashlib
import json
import random
import secrets
import time
from functools import lru_cache
from pathlib import Path

from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse, Response
from nicegui import app, ui

from src.models import CnpjCache, InstalacaoSolar, Lead
from src.services.geo_service import carregar_geojson_rmr, carregar_mapa_base_json, montar_mapa_json, carregar_bairros_por_cep, _norm, _bairro_key, _shape_centroid
from src.services.aneel_service import carregar_instalacoes_aneel, _text
from src.utils import log_aviso, log_info, log_dados, log_ok
import os

ROOT_DIR = Path(__file__).resolve().parents[4]
DATA_PATH = str(ROOT_DIR / 'data' / 'data' / 'processed' / 'aneel' / 'rmr_instalacoes.parquet')
CEP_CACHE_PATH = str(ROOT_DIR / 'data' / 'data' / 'processed' / 'cep_coords_cache.json')

LEAD_STATUS_LABELS = {
    'Novo': 'Novo',
    'Em Contato': 'Em andamento',
    'Concluído': 'Concluido',
}
MAPA_EMPRESA_TOKENS: dict[str, float] = {}
MAPA_TOKEN_TTL_SECONDS = 15 * 60

# Bounding box da RMR (limites aproximados para filtrar coordenadas inválidas)
RMR_LAT_MIN, RMR_LAT_MAX = -8.6, -7.0
RMR_LNG_MIN, RMR_LNG_MAX = -35.5, -34.4

@ui.page('/mapa')
async def mapa_page():
    # A página apenas entrega a casca (HTML/CSS/JS) instantaneamente.
    # O seu JS (mapa.js) vai bater na URL de dados em background e construir a UI.
    render_mapa(data_url='', show_header=True, include_leads=True)
    
def carregar_leads_mapa(data: dict) -> list[dict]:
    municipios_por_nome = {
        _norm(feature['properties']['nome']): feature
        for feature in data['municipios']['features']
    }
    bairros_por_municipio = data['bairrosPorMunicipio']
    bairros_por_cep_exato, bairros_por_prefixo = carregar_bairros_por_cep()

    leads = (
        Lead.select()
        .where(Lead.status.in_(list(LEAD_STATUS_LABELS)))
        .order_by(Lead.criado_em.desc())
    )
    pins: list[dict] = []

    for lead in leads:
        if not lead.cliente_id:
            continue

        instalacao = InstalacaoSolar.select().where(InstalacaoSolar.usuario == lead.cliente_id).first()
        if not instalacao:
            continue

        lat = instalacao.latitude
        lng = instalacao.longitude
        aproximado = False
        municipio_nome = _text(instalacao.cidade)
        municipio = municipios_por_nome.get(_norm(municipio_nome))
        municipio_codigo = municipio['properties']['codigo'] if municipio else ''

        if lat is None or lng is None:
            coordenada_exata = _geocodificar_endereco(instalacao)
            if coordenada_exata:
                lat, lng = coordenada_exata
                instalacao.latitude = lat
                instalacao.longitude = lng
                instalacao.save()

        if lat is None or lng is None:
            aproximado = True
            cep = ''.join(char for char in _text(instalacao.cep) if char.isdigit())
            candidatos = set()
            if municipio_codigo and len(cep) == 8:
                candidatos = bairros_por_cep_exato.get(municipio_codigo, {}).get(cep, set())
            if municipio_codigo and not candidatos and len(cep) >= 5:
                candidatos = bairros_por_prefixo.get(municipio_codigo, {}).get(cep[:5], set())

            bairro_centroid = None
            bairros = bairros_por_municipio.get(municipio_codigo, {}).get('features', []) if municipio_codigo else []
            bairros_por_key = {
                _bairro_key(feature['properties']['nome']): feature
                for feature in bairros
                if feature['properties']['tipo'] == 'bairro'
            }
            for candidato in candidatos:
                feature = bairros_por_key.get(_bairro_key(candidato))
                if not feature:
                    continue
                bairro_centroid = _shape_centroid(feature['geometry'])
                if bairro_centroid:
                    break

            if bairro_centroid:
                lat, lng = bairro_centroid
            elif municipio:
                municipio_centroid = _shape_centroid(municipio['geometry'])
                if municipio_centroid:
                    lat, lng = municipio_centroid

        if lat is None or lng is None:
            continue

        endereco = ', '.join(
            part
            for part in [
                _text(instalacao.logradouro),
                _text(instalacao.numero),
                municipio_nome,
                _text(instalacao.estado),
            ]
            if part
        )
        pins.append({
            'id': lead.id,
            'nome': _text(lead.nome_contato),
            'telefone': _text(lead.telefone_contato),
            'status': _text(lead.status),
            'status_label': LEAD_STATUS_LABELS.get(_text(lead.status), _text(lead.status)),
            'descricao': _text(lead.descricao_servico),
            'endereco': endereco,
            'cep': _text(instalacao.cep),
            'lat': float(lat),
            'lng': float(lng),
            'aproximado': aproximado,
        })

    return pins


def _bairro_polygon_cache(data: dict) -> dict:
    cache = {}
    for mun_codigo, mun_data in data['bairrosPorMunicipio'].items():
        for feature in mun_data.get('features', []):
            if feature['properties'].get('tipo') == 'bairro':
                nome = feature['properties'].get('nome', '')
                keys = {_bairro_key(nome)}
                bairros_possiveis = feature['properties'].get('bairros_possiveis')
                if bairros_possiveis:
                    keys.update(_bairro_key(b) for b in bairros_possiveis)
                geom = feature['geometry']
                centroid = _shape_centroid(geom)
                if centroid:
                    for key in keys:
                        cache[(mun_codigo, key)] = {'centroid': centroid, 'geometry': geom}
    return cache


def _ponto_em_poligono(lng: float, lat: float, polygon: list) -> bool:
    inside = False
    j = len(polygon) - 1
    for i in range(len(polygon)):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > lat) != (yj > lat)) and (lng < (xj - xi) * (lat - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _dentro_municipio(lat: float, lng: float, mun_codigo: str,
                      municipio_polygons: dict, municipio_centroids: dict) -> tuple[float | None, float | None]:
    if mun_codigo not in municipio_polygons:
        return lat, lng
    geom = municipio_polygons[mun_codigo]
    coords = _extrair_coords(geom)
    if not coords:
        return lat, lng
    if any(_ponto_em_poligono(lng, lat, poly) for poly in coords):
        return lat, lng
    centroide = municipio_centroids.get(mun_codigo)
    if centroide:
        return centroide
    return None, None


def _extrair_coords(geometry: dict) -> list[list[tuple[float, float]]]:
    gtype = geometry.get('type', '')
    coords = geometry.get('coordinates', [])
    if gtype == 'Polygon':
        return [coords[0]] if coords else []
    if gtype == 'MultiPolygon':
        return [p[0] for p in coords if p]
    return []


def _random_point_in_bbox(geometry: dict, seed: int) -> tuple[float, float]:
    points = []
    def collect(coords):
        if not coords:
            return
        first = coords[0]
        if isinstance(first, (int, float)) and len(coords) >= 2:
            points.append((float(coords[1]), float(coords[0])))
            return
        for item in coords:
            collect(item)
    collect(geometry.get('coordinates', []))
    if not points:
        return 0.0, 0.0
    lats = [p[0] for p in points]
    lngs = [p[1] for p in points]
    lat_min, lat_max = min(lats), max(lats)
    lng_min, lng_max = min(lngs), max(lngs)
    rng = random.Random(seed)
    lat = lat_min + rng.random() * (lat_max - lat_min)
    lng = lng_min + rng.random() * (lng_max - lng_min)
    return lat, lng


def carregar_pjs_mapa(data: dict) -> list[dict]:
    instalacoes = []
    for lista in data['instalacoesPorMunicipio'].values():
        instalacoes.extend(lista)

    pjs = [inst for inst in instalacoes if inst.get('tipo') == 'PJ' and inst.get('cpf_cnpj')]
    pins: list[dict] = []
    cnpj_cache: dict[str, CnpjCache] = {
        c.cnpj: c for c in CnpjCache.select()
    }
    bairro_polygons = _bairro_polygon_cache(data)
    municipio_polygons = {
        f['properties']['codigo']: f['geometry']
        for f in data['municipios']['features']
        if f['geometry']
    }
    municipio_centroids = {
        codigo: _shape_centroid(geom)
        for codigo, geom in municipio_polygons.items()
    }

    cep_cache = {}
    cep_cache_path = Path(CEP_CACHE_PATH)
    if cep_cache_path.exists():
        try:
            with open(cep_cache_path, 'r', encoding='utf-8') as f:
                cep_cache = json.load(f)
        except Exception:
            cep_cache = {}

    for inst in pjs:
        cnpj = ''.join(ch for ch in inst['cpf_cnpj'] if ch.isdigit())
        if len(cnpj) != 14:
            continue
        cache = cnpj_cache.get(cnpj)

        lat = None
        lng = None
        # 1. Tenta coordenada do CEP (precisao de logradouro)
        cep_raw = inst.get('cep', '')
        cep_digits = ''.join(ch for ch in cep_raw if ch.isdigit())
        if cep_digits and len(cep_digits) == 8:
            entry = cep_cache.get(cep_digits)
            if entry:
                lat = float(entry['latitude'])
                lng = float(entry['longitude'])
        # 2. Tenta cache da empresa
        if lat is None and cache and cache.latitude is not None and cache.longitude is not None:
            lat = cache.latitude
            lng = cache.longitude
        # 3. Tenta centroide do bairro
        if lat is None:
            mun_codigo = inst.get('municipio_codigo', '')
            bairro_nome = inst.get('bairro', '')
            keys_to_try = []
            if bairro_nome and bairro_nome != 'Nao identificado':
                keys_to_try.append(_bairro_key(bairro_nome))
            bairros_possiveis = inst.get('bairros_possiveis')
            if bairros_possiveis:
                keys_to_try.extend(_bairro_key(b) for b in bairros_possiveis)
            for key in keys_to_try:
                entry = bairro_polygons.get((mun_codigo, key))
                if entry:
                    centroid = entry['centroid']
                    seed = int(hashlib.md5(inst['codigo'].encode()).hexdigest()[:8], 16)
                    rng = random.Random(seed)
                    lat = centroid[0] + rng.uniform(-0.0015, 0.0015)
                    lng = centroid[1] + rng.uniform(-0.0015, 0.0015)
                    break
        # 4. Fallback: coordenada ANEEL original
        if lat is None:
            inst_lat = inst.get('latitude')
            inst_lng = inst.get('longitude')
            if inst_lat is not None and inst_lng is not None:
                lat_valida, lng_valida = _dentro_municipio(
                    inst_lat, inst_lng, inst.get('municipio_codigo', ''),
                    municipio_polygons, municipio_centroids,
                )
                if lat_valida is not None:
                    lat, lng = lat_valida, lng_valida
                else:
                    lat, lng = inst_lat, inst_lng
        if lat is None or lng is None:
            continue
        if not (RMR_LAT_MIN <= lat <= RMR_LAT_MAX and RMR_LNG_MIN <= lng <= RMR_LNG_MAX):
            continue
        seed = int(hashlib.md5(inst['codigo'].encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        lat += rng.uniform(-0.0008, 0.0008)
        lng += rng.uniform(-0.0008, 0.0008)

        logradouro_rel = ''
        numero_rel = ''
        bairro_rel = ''
        endereco_rel = inst.get('municipio', '')
        cep = inst.get('cep', '')
        if cache and cache.logradouro:
            logradouro_rel = cache.logradouro or ''
            numero_rel = cache.numero or ''
            bairro_rel = cache.bairro or ''
            endereco_rel = ', '.join(p for p in [logradouro_rel, numero_rel, bairro_rel, cache.cidade or '', cache.estado or ''] if p)
            cep = cache.cep or cep
        else:
            bairro_rel = inst.get('bairro', '')
            if bairro_rel and bairro_rel != 'Nao identificado':
                endereco_rel = f'{inst["municipio"]}, {bairro_rel}'

        pins.append({
            'codigo': inst['codigo'],
            'titular': inst['titular'],
            'cnpj': cnpj,
            'endereco': endereco_rel,
            'logradouro': logradouro_rel,
            'numero': numero_rel,
            'bairro': bairro_rel,
            'cep': cep,
            'municipio': inst['municipio'],
            'uf': (cache.estado if cache else None) or '',
            'data_instalacao': inst.get('data_conexao', ''),
            'qtd_modulos': inst.get('qtd_modulos', 0),
            'potencia_kw': inst['potencia_kw'],
            'telefone1': cache.telefone1 if cache else None,
            'telefone2': cache.telefone2 if cache else None,
            'email': cache.email if cache else None,
            'lat': float(lat),
            'lng': float(lng),
        })

    return pins


def carregar_mapa_data(include_leads: bool = False) -> dict:
    base = carregar_geojson_rmr()
    data = {**base}
    data['leads'] = carregar_leads_mapa(data) if include_leads else []
    return data


# Mude de: def render_demo_mapa(data_url: str, show_header: bool = True) -> None:
# Para:
def render_mapa(data_url: str, show_header: bool = False, include_leads: bool = True) -> None:
    if include_leads:
        token = secrets.token_urlsafe(24)
        MAPA_EMPRESA_TOKENS[token] = time.time() + MAPA_TOKEN_TTL_SECONDS
        data_url = f'/api/empresa/mapa-rmr?token={token}'
    else:
        data_url = '/api/demo/mapa-rmr'
    _render_demo_mapa_content(data_url, show_header=show_header, enable_capture=include_leads)


def _render_mapa_header() -> None:
    with ui.row().classes('w-full items-end justify-between gap-4'):
        with ui.column().classes('gap-1'):
            ui.label('Demo mapa RMR').classes('text-3xl font-bold text-slate-900')
            ui.label('Mapa de calor municipal com dados de geracao distribuida da ANEEL.').classes('text-base text-slate-600')


def _render_mapa_summary() -> None:
    ui.html('''
        <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="rs-map-controls">
                <div class="grid grid-cols-1 gap-3 md:grid-cols-4">
                    <div class="rounded-2xl bg-orange-50 p-4">
                        <div class="text-xs font-bold uppercase text-orange-700">Selecao</div>
                        <div class="rs-selected-name text-xl font-bold text-slate-900">RMR</div>
                    </div>
                    <div class="rounded-2xl bg-blue-50 p-4">
                        <div class="text-xs font-bold uppercase text-blue-700">Instalacoes</div>
                        <div class="rs-total-installations text-xl font-bold text-slate-900">-</div>
                    </div>
                    <div class="rounded-2xl bg-emerald-50 p-4">
                        <div class="text-xs font-bold uppercase text-emerald-700">Potencia instalada</div>
                        <div class="rs-total-power text-xl font-bold text-slate-900">-</div>
                    </div>
                    <div class="rounded-2xl bg-amber-50 p-4">
                        <div class="text-xs font-bold uppercase text-amber-700">Qtd modulos</div>
                        <div class="rs-total-modules text-xl font-bold text-slate-900">-</div>
                    </div>
                </div>
            </div>
        </section>
    ''').classes('w-full')


def _render_mapa_charts() -> None:
    ui.html('''
        <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="rs-chart-title mb-4 text-xl font-bold text-slate-900">Graficos - RMR</div>
            <div class="mb-2 text-xs font-bold uppercase text-slate-500">Barras</div>
            <div class="rs-charts-grid">
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Conexoes por ano por modalidade</div>
                    <canvas id="chart-series-modalidade"></canvas>
                </div>
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Top fabricantes de modulos</div>
                    <canvas id="chart-modulos"></canvas>
                </div>
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Top fabricantes de inversores</div>
                    <canvas id="chart-inversores"></canvas>
                </div>
            </div>
            <div class="mb-2 mt-4 text-xs font-bold uppercase text-slate-500">Pizzas</div>
            <div class="rs-charts-grid rs-pies-grid">
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">PF vs PJ</div>
                    <canvas id="chart-tipo"></canvas>
                </div>
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Por classe</div>
                    <canvas id="chart-classe"></canvas>
                </div>
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Por porte</div>
                    <canvas id="chart-porte"></canvas>
                </div>
                <div class="rs-chart-box">
                    <div class="mb-2 text-xs font-bold uppercase text-slate-500">Modalidade</div>
                    <canvas id="chart-modalidade"></canvas>
                </div>
            </div>
        </section>
    ''').classes('w-full')


def _render_mapa_table() -> None:
    ui.html('''
        <section class="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm">
            <div class="mb-4 flex flex-wrap items-end justify-between gap-3">
                <div>
                    <div class="text-xl font-bold text-slate-900">Instalacoes do municipio</div>
                    <div class="rs-list-helper text-sm text-slate-500">Clique em um municipio no mapa para listar as instalacoes.</div>
                </div>
                <div class="rs-map-pagination">
                    <button class="rs-page-button rs-prev-page" type="button">Anterior</button>
                    <span class="rs-page-status text-sm font-semibold text-slate-500"></span>
                    <button class="rs-page-button rs-next-page" type="button">Proxima</button>
                </div>
            </div>
            <div class="mb-4 grid grid-cols-1 gap-3 md:grid-cols-4">
                <label class="text-sm font-bold text-slate-600">Classe
                    <select class="rs-filter rs-filter-classe mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Tipo
                    <select class="rs-filter rs-filter-tipo mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Porte
                    <select class="rs-filter rs-filter-porte mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Modalidade
                    <select class="rs-filter rs-filter-modalidade mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Bairro
                    <select class="rs-filter rs-filter-bairro mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Fabricante Modulo
                    <select class="rs-filter rs-filter-fab-mod mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
                <label class="text-sm font-bold text-slate-600">Fabricante Inversor
                    <select class="rs-filter rs-filter-fab-inv mt-1 w-full rounded-xl border border-slate-200 bg-white px-3 py-2 text-slate-900"></select>
                </label>
            </div>
            <div class="rs-map-installations">
                <table class="rs-map-table">
                    <thead>
                        <tr>
                            <th style="width:32px"></th>
                            <th>Codigo</th>
                            <th>CPF/CNPJ</th>
                            <th>Titular</th>
                            <th>Municipio</th>
                            <th>Bairros possiveis</th>
                            <th>Classe</th>
                            <th>Tipo</th>
                            <th>Porte</th>
                            <th>Modalidade</th>
                            <th>Data de Conexao</th>
                            <th>Potencia kW</th>
                            <th>Modulos</th>
                            <th>Fab. Modulo</th>
                            <th>Fab. Inversor</th>
                            <th>Qtd UC Credito</th>
                            <th>CEP</th>
                        </tr>
                    </thead>
                    <tbody class="rs-installations-body">
                        <tr><td colspan="17">Nenhum municipio selecionado.</td></tr>
                    </tbody>
                </table>
            </div>
        </section>
    ''').classes('w-full')


def _inject_mapa_script(data_url: str, enable_capture: bool = False) -> None:
    capture_js = ''
    if enable_capture:
        capture_js = 'window.CAPTURE_LEAD_URL = "/api/empresa/capturar-lead";'
    ui.add_body_html(f'''
    <script>
    window.DATA_URL = {json.dumps(data_url)};
    {capture_js}
    </script>
    <script src="/empresa/static/mapa.js?v={int(time.time())}"></script>
    ''')


def _render_demo_mapa_content(data_url: str, show_header: bool = True, enable_capture: bool = False) -> None:
    ui.add_head_html('<link rel="stylesheet" href="/empresa/static/mapa.css">')

    container_classes = 'w-full gap-5 p-6'
    if show_header:
        container_classes += ' min-h-screen'

    with ui.column().classes(container_classes):
        if show_header:
            _render_mapa_header()

        _render_mapa_summary()
        ui.html('<div id="demo-mapa-rmr">Carregando dados do mapa...</div>').classes('w-full')
        _render_mapa_charts()
        _render_mapa_table()

    _inject_mapa_script(data_url, enable_capture=enable_capture)
