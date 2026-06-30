import json
import math
import shapefile
import unicodedata
import pandas as pd  # Mantido e garantido o suporte ao pandas
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from nicegui import run  # Adicionado para o processamento assíncrono da Fase 4.1
from src.utils import log_info, log_erro, log_ok, log_aviso
from src.models import InstalacaoSolar
from src.services.aneel_service import carregar_instalacoes_aneel

# ── CONFIGURAÇÃO DE CAMINHOS ABSOLUTOS ──────────────────────────────────────
ROOT_DIR = Path(__file__).resolve().parents[2]
PROCESSED_DIR = ROOT_DIR / 'data' / 'data' / 'processed'
GEOJSON_PRONTO_PATH = PROCESSED_DIR / 'mapa_rmr.geojson'

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
# ------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _dne_delimitado_dir() -> Path:
    base = ROOT_DIR / 'data' / 'data' / 'raw' / 'correios'
    dirs = sorted(base.glob('eDNE_Basico_*'))
    return (dirs[-1] / 'Delimitado') if dirs else base

@lru_cache(maxsize=1)
def carregar_bairros_por_cep() -> tuple[dict[str, dict[str, set[str]]], dict[str, dict[str, set[str]]]]:
    DNE_DIR = _dne_delimitado_dir()
    CEP_XLSX = ROOT_DIR / 'data' / 'data' / 'raw' / 'correios' / 'ceps_pe.xlsx'

    if CEP_XLSX.exists():
        localidades = pd.read_excel(CEP_XLSX, sheet_name='LOG_LOCALIDADE')
        localidades = localidades.dropna(subset=['MUN_NU'])
        municipio_por_loc_nu = {
            int(row.LOC_NU): str(int(row.MUN_NU))
            for row in localidades.itertuples(index=False)
            if str(int(row.MUN_NU)) in RMR_MUNICIPIOS
        }
        cep_bairro = pd.read_excel(CEP_XLSX, sheet_name='CEP_BAIRRO')
        bairros_por_cep_exato: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        bairros_por_prefixo: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        for row in cep_bairro.itertuples(index=False):
            municipio_codigo = municipio_por_loc_nu.get(int(row.LOC_NU))
            if not municipio_codigo or pd.isna(row.BAIRRO):
                continue
            for cep in range(int(row.CEP_INICIO), int(row.CEP_FIM) + 1):
                bairros_por_cep_exato[municipio_codigo][f'{cep:08d}'].add(str(row.BAIRRO))
            mascara_inicio = int(row.MASCARA_INICIO) // 1000
            mascara_fim = int(row.MASCARA_FIM) // 1000
            for prefixo in range(mascara_inicio, mascara_fim + 1):
                bairros_por_prefixo[municipio_codigo][f'{prefixo:05d}'].add(str(row.BAIRRO))
        return (
            {m: dict(c) for m, c in bairros_por_cep_exato.items()},
            {m: dict(p) for m, p in bairros_por_prefixo.items()},
        )

    if not DNE_DIR.exists() or not (DNE_DIR / 'LOG_LOCALIDADE.TXT').exists():
        return {}, {}

    localidades_rmr = {}
    for row in _read_dne_rows(DNE_DIR / 'LOG_LOCALIDADE.TXT'):
        if len(row) < 9 or row[1] != 'PE' or row[8] not in RMR_MUNICIPIOS:
            continue
        localidades_rmr[row[0]] = row[8]

    bairros_por_id = {}
    for row in _read_dne_rows(DNE_DIR / 'LOG_BAIRRO.TXT'):
        if len(row) < 4 or row[2] not in localidades_rmr:
            continue
        bairros_por_id[row[0]] = {
            'municipio_codigo': localidades_rmr[row[2]],
            'nome': row[3],
        }

    bairros_por_prefixo: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    def add_prefixo(bairro_id: str, cep_inicio: str, cep_fim: str | None = None) -> None:
        bairro = bairros_por_id.get(bairro_id)
        if not bairro or not cep_inicio.isdigit():
            return
        cep_fim = cep_fim if cep_fim and cep_fim.isdigit() else cep_inicio
        inicio = int(cep_inicio) // 1000
        fim = int(cep_fim) // 1000
        for prefixo in range(inicio, fim + 1):
            bairros_por_prefixo[bairro['municipio_codigo']][f'{prefixo:05d}'].add(bairro['nome'])

    for row in _read_dne_rows(DNE_DIR / 'LOG_FAIXA_BAIRRO.TXT'):
        if len(row) >= 3:
            add_prefixo(row[0], row[1], row[2])

    for row in _read_dne_rows(DNE_DIR / 'LOG_LOGRADOURO_PE.TXT'):
        if len(row) >= 8:
            add_prefixo(row[3], row[7])

    return (
        {},
        {m: dict(p) for m, p in bairros_por_prefixo.items()},
    )

def _ler_geojson_estatico(caminho: Path) -> dict:
    """Função interna síncrona para ler o arquivo do disco."""
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo GeoJSON crucial ausente em: {caminho}")
    with open(caminho, 'r', encoding='utf-8') as f:
        return json.load(f)

async def obter_geojson_rmr_assincrono() -> dict:
    """Carrega o GeoJSON pré-processado sem travar o Event Loop do NiceGUI."""
    log_info(f"Carregando malha GeoJSON RMR em background via cpu_bound...")
    try:
        dados_geojson = await run.cpu_bound(_ler_geojson_estatico, GEOJSON_PRONTO_PATH)
        log_ok("Malha GeoJSON RMR carregada com sucesso.")
        return dados_geojson
    except Exception as exc:
        log_erro(f"Falha ao ler GeoJSON processado: {exc}")
        return {"type": "FeatureCollection", "features": []}

def carregar_geojson_rmr() -> dict:
    try:
        return _ler_geojson_estatico(GEOJSON_PRONTO_PATH)
    except FileNotFoundError:
        log_aviso(f'GeoJSON nao encontrado em {GEOJSON_PRONTO_PATH}')
        return {'type': 'FeatureCollection', 'features': [], 'municipios': {'type': 'FeatureCollection', 'features': []}, 'bairrosPorMunicipio': {}, 'instalacoesPorMunicipio': {}}



@lru_cache(maxsize=1)
def carregar_mapa_base_json() -> str:
    return json.dumps(carregar_geojson_rmr(), ensure_ascii=False)


def montar_mapa_json(leads: list[dict] | None = None, pjs: list[dict] | None = None) -> str:
    base_json = carregar_mapa_base_json()[:-1]
    extra = []
    extra.append(f'"leads":{json.dumps(leads or [], ensure_ascii=False)}')
    extra.append(f'"pjs":{json.dumps(pjs or [], ensure_ascii=False)}')
    return f'{base_json},{",".join(extra)}}}'


def _geocodificar_endereco(instalacao: InstalacaoSolar) -> tuple[float, float] | None:
    partes = [
        _text(instalacao.logradouro),
        _text(instalacao.numero),
        _text(instalacao.cep),
        _text(instalacao.cidade),
        _text(instalacao.estado),
        'Brasil',
    ]
    endereco = ', '.join(part for part in partes if part)
    if not endereco:
        return None

    query = urlencode({'format': 'json', 'limit': '1', 'q': endereco})
    request = Request(
        f'https://nominatim.openstreetmap.org/search?{query}',
        headers={'User-Agent': 'RadarSolar/1.0 (contato@radarsolar.local)'},
    )
    try:
        with urlopen(request, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    if not data:
        return None
    try:
        return float(data[0]['lat']), float(data[0]['lon'])
    except (KeyError, TypeError, ValueError):
        return None


def _shape_centroid(geometry: dict) -> tuple[float, float] | None:
    points: list[tuple[float, float]] = []

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
        return None
    return sum(lat for lat, _ in points) / len(points), sum(lng for _, lng in points) / len(points)

def _feature(geometry: dict, properties: dict) -> dict:
    return {
        'type': 'Feature',
        'geometry': geometry,
        'properties': properties,
    }


def _feature_collection(features: list[dict]) -> dict:
    return {
        'type': 'FeatureCollection',
        'features': features,
    }


def _norm(value: str) -> str:
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(char for char in value if not unicodedata.combining(char))
    return ' '.join(value.upper().split())


def _bairro_key(value: str) -> str:
    conectores = {'DA', 'DE', 'DI', 'DO', 'DAS', 'DOS'}
    return ' '.join(part for part in _norm(value).split() if part not in conectores)


def _read_dne_rows(path: Path):
    with path.open('r', encoding='latin1', errors='replace') as file:
        for line in file:
            yield line.rstrip('\n').split('@')


def _estimar_coordenada_por_cep(
    municipio_codigo: str, cep_digits: str, prefixo: str,
    bairros_por_cep_exato: dict, bairros_por_prefixo: dict, data: dict,
) -> tuple[float | None, float | None]:
    candidatos: set[str] = set()
    if municipio_codigo and len(cep_digits) == 8:
        candidatos = bairros_por_cep_exato.get(municipio_codigo, {}).get(cep_digits, set())
    if not candidatos and municipio_codigo and len(prefixo) >= 5:
        candidatos = bairros_por_prefixo.get(municipio_codigo, {}).get(prefixo[:5], set())

    bairros = data.get('bairrosPorMunicipio', {}).get(municipio_codigo, {}).get('features', [])
    if candidatos:
        bairros_por_key = {
            _bairro_key(f['properties']['nome']): f
            for f in bairros if f['properties']['tipo'] == 'bairro'
        }
        for candidato in candidatos:
            feature = bairros_por_key.get(_bairro_key(candidato))
            if not feature:
                continue
            c = _shape_centroid(feature['geometry'])
            if c:
                return c

    for feature in bairros:
        if feature['properties'].get('tipo') == 'bairro_fallback':
            c = _shape_centroid(feature['geometry'])
            if c:
                return c

    for feature in data['municipios']['features']:
        if feature['properties']['codigo'] == municipio_codigo:
            c = _shape_centroid(feature['geometry'])
            if c:
                return c

    return None, None