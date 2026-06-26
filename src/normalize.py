from __future__ import annotations

import difflib
import re
import unicodedata
from functools import lru_cache

from src.utils import log_info


def _strip_accents(value: str) -> str:
    nfkd = unicodedata.normalize('NFKD', value)
    return ''.join(char for char in nfkd if not unicodedata.combining(char))


def _limpar(value: str) -> str:
    value = value.strip()
    value = value.replace('\xa0', ' ')
    return ' '.join(value.split())


def _normalizar_str(value: str) -> str:
    value = _limpar(value)
    value = value.upper()
    value = _strip_accents(value)
    return value


def _remover_conectores(value: str) -> str:
    conectores = {'DE', 'DO', 'DA', 'DAS', 'DOS', 'E'}
    return ' '.join(part for part in value.split() if part not in conectores)


_SINONIMOS_MODULO = {
    'JINKO': 'JINKO SOLAR',
    'CANADIAN': 'CANADIAN SOLAR',
    'CANDIAN': 'CANADIAN SOLAR',
    'CNAADIAN': 'CANADIAN SOLAR',
    'CANNADIAN': 'CANADIAN SOLAR',
    'CANANDIAN': 'CANADIAN SOLAR',
    'CANANDIAN': 'CANADIAN SOLAR',
    'CANAADIAN': 'CANADIAN SOLAR',
    'CANADIAM': 'CANADIAN SOLAR',
    'CANDIAN': 'CANADIAN SOLAR',
    'CANDIANSOLAR': 'CANADIAN SOLAR',
    'CANADIANSOLAR': 'CANADIAN SOLAR',
    'CANADIAN | CANADIAN': 'CANADIAN SOLAR',
    'CANADIAN MONO': 'CANADIAN SOLAR',
    'CANADIAN | JA-SOLAR': 'CANADIAN SOLAR',
    'CANADIAN / SUNOVA': 'CANADIAN SOLAR',
    'TRINA': 'TRINA SOLAR',
    'DAH': 'DAH SOLAR',
    'DAHSOLAR': 'DAH SOLAR',
    'DAH MONO': 'DAH SOLAR',
    'DAHMONO': 'DAH SOLAR',
    'DAH POLI': 'DAH SOLAR',
    'DAH POLY': 'DAH SOLAR',
    'DAH MONOPERC': 'DAH SOLAR',
    'DAH BIFACIAL': 'DAH SOLAR',
    'PAINEL DAH MONO': 'DAH SOLAR',
    'PAINEL SOLAR JINKO': 'JINKO SOLAR',
    'DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'DAH SOLAR | DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'DAH SOLAR | DAH SOLAR | DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'DAH SOLAR | DAH SOLAR | DAH SOLAR | DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'DHA': 'DAH SOLAR',
    'DAS': 'DAH SOLAR',
    'HONOR': 'HONOR SOLAR',
    'HORNOR': 'HONOR SOLAR',
    'JA': 'JA SOLAR',
    'JAH': 'JA SOLAR',
    'JA JAM': 'JA SOLAR',
    'JA SOLAR HOLDINGS CO.': 'JA SOLAR',
    'JASOLAR': 'JA SOLAR',
    'RISEN': 'RISEN SOLAR',
    'RISEN SOLAR TECHNOLOGY': 'RISEN SOLAR',
    'RISEN TECNOLOGY': 'RISEN SOLAR',
    'RESUN': 'RISEN SOLAR',
    'RESUNSOLAR': 'RISEN SOLAR',
    'RIZEN': 'RISEN SOLAR',
    'ULICA': 'ULICA SOLAR',
    'ULICASOLAR': 'ULICA SOLAR',
    'NEXEN': 'NEXEN SOLAR',
    'NEXEN MONOCRISTALINO': 'NEXEN SOLAR',
    'NEXENMONOCRISTALINO': 'NEXEN SOLAR',
    'MODULOS SOLAR NEXEN MONOCRISTALINO': 'NEXEN SOLAR',
    'SOLAR NEXEN': 'NEXEN SOLAR',
    'SOLARNEXEN': 'NEXEN SOLAR',
    'NEXEN; CANADIAN': 'NEXEN SOLAR',
    'LUXEN': 'LUXEN SOLAR',
    'RONMA': 'RONMA SOLAR',
    'GOKIN': 'GOKIN SOLAR',
    'SHINEFAR': 'SHINEFAR SOLAR',
    'ZNSHINESOLAR': 'ZNSHINE',
    'LEAPTONSOLAR': 'LEAPTON',
    'SUNOVASOLAR': 'SUNOVA',
    'PULLING': 'PULLING ENERGY',
    'PHONO': 'PHONO SOLAR',
    'LONGISOLAR': 'LONGI',
    'ERA': 'ERA SOLAR',
    'MODULO FOTOVOLTAICO FV ERASOLAR': 'ERA SOLAR',
    'DAH SOLAR | DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'SUNGOW': 'SUNGROW',
    'SOLARJINKO': 'JINKO SOLAR',
    'JNG': 'JINKO SOLAR',
    'SERAPHIM': 'SERAPHIM SOLAR',
    'SCHUTTEN': 'SCHUTTEN SOLAR',
    'SIRUS TOPCON BIFACIAL': 'SIRIUS',
    'SIRUS': 'SIRIUS',
    'DAH SOLAR | DAH SOLAR': 'DAH SOLAR',
    'CANADIAN / OSDA': 'CANADIAN SOLAR',
    'CANADIAN / SUNOVA': 'CANADIAN SOLAR',
    'JA SOLAR | TRINA SOLAR': 'JA SOLAR',
    'INTELBRAS - CANADIAN': 'INTELBRAS',
    'JINKO | TSUN': 'JINKO SOLAR',
    'LEAPTON | TSUN': 'LEAPTON',
    'LEAPTON | TRINA': 'LEAPTON',
    'LEAPTON | CANADIAN SOLAR': 'LEAPTON',
    'SUNOVA N-TYPE BIFACIAL': 'SUNOVA',
    'GROWATT': 'GROWATT',
    'TSUN BISTAR': 'TSUN',
    'TSUN BISPAR': 'TSUN',
    'TSUN POWER': 'TSUN POWER',
    'SUNOVA BLUESUN': 'SUNOVA',
    'SUNOVABLUESUN': 'SUNOVA',
    'SUNOVA SOLAR': 'SUNOVA',
    'SUNNOVA SOLAR': 'SUNOVA',
    'HONOR MONOPERC HALF-CELL': 'HONOR SOLAR',
    'AE SOLAR': 'AE SOLAR',
    'AESOLAR': 'AE SOLAR',
    'DA SOLAR': 'DAH SOLAR',
    'DAH SOLAR': 'DAH SOLAR',
    'DH SOLAR': 'DAH SOLAR',
    'GEL SOLAR': 'AE SOLAR',
    'AMERI SOLAR': 'AMERISOLAR',
    'AMERISOLAR / CANADIAN': 'AMERISOLAR',
    'AMERISOLAR_450W': 'AMERISOLAR',
    'RUNDASOLAR': 'RUNDA SOLAR',
    'RENE SOLA': 'RENESOLA',
    'RENOSOLA': 'RENESOLA',
    'RENASOLA': 'RENESOLA',
    'RENOSOLAR': 'RENESOLA',
    'RENERSOLA': 'RENESOLA',
    'YINGLI': 'YINGLI SOLAR',
    'LOGI SOLAR': 'LONGI',
    'LONGO SOLAR': 'LONGI',
    'SOLAR SPACE': 'SOLARSPACE',
    'SOLARSPACE': 'SOLARSPACE',
    'HALF CELL': '',
    'HALFCELL': '',
    'N-TYPE': '',
    'NTYPE': '',
    'NPLUS': '',
    'N PLUS': '',
    'N TYPE': '',
    'N-TOPCON': '',
    'HALF-CELL': '',
    'MONO': '',
    'POLI': '',
    'POLY': '',
    'MONOPERC HALF-CELL': '',
    'MONOPERCHALFCELL': '',
    'HALFCELL': '',
    'BIFACIAL': '',
    'TOPCOM': '',
    'TOPCON': '',
    'VERTEX': '',
    'JA BIFACIAL': 'JA SOLAR',
    'DAH BIFACIAL': 'DAH SOLAR',
    'LONGI SOLAR': 'LONGI',
    'LONGI GREEN ENERGY': 'LONGI',
    'LONGI LR5-72HTH 575W': 'LONGI',
    'LONGI LR5-72HPH 570M': 'LONGI',
    'BLUESUN SOLAR': 'BLUESUN',
    'BLUESUNSUNOVA': 'SUNOVA',
    'SOFAR SOLAR': 'SOFAR SOLAR',
    'HELIUS SOLAR': 'HELIUS',
    'INTELBRAS SOLAR': 'INTELBRAS',
    'PAINEL LEAPTON': 'LEAPTON',
    'PAINEL LEAPTON 590W N-TYPE MONOCRISTALINO': 'LEAPTON',
    'PAINEL LEAPTON PANTHER': 'LEAPTON',
    'LEAPTON PANTHER': 'LEAPTON',
    'LEAPTON PANTHER 560W N-TYPE': 'LEAPTON',
    'LEAPTON PANTHER 585W N-TYPE': 'LEAPTON',
    'LEAPTON PHANTER': 'LEAPTON',
    'LEAPTON PARTHER': 'LEAPTON',
    'LEAPTON- MONO': 'LEAPTON',
    'LEAPTON MONO': 'LEAPTON',
    'LEAPTON MONO HALF-CELL': 'LEAPTON',
    'LEAPTON MONOFACIAL': 'LEAPTON',
    'LEAPTONMONO': 'LEAPTON',
    'LEAPTON ENERGY': 'LEAPTON',
    'LEAPTON 570W': 'LEAPTON',
    'LEAPTON SOLAR E SOLARGIGA': 'LEAPTON',
    'LEAPTON | CANADIAN SOLAR': 'LEAPTON',
    'LEAPTON | LEAPTON': 'LEAPTON',
    'LEAPTON | TRINA': 'LEAPTON',
    'LEAPTON | TSUN': 'LEAPTON',
    'LEAPTON;CANADIAN': 'LEAPTON',
    'LEAPTON (EXPANSAO) | LEAPTON (EXISTENTES)': 'LEAPTON',
    'LEAPTON SOLAR | LONGI SOLAR': 'LEAPTON',
    'SUNOVA N-TYPE BIFACIAL': 'SUNOVA',
    'SUNOVA BLUESUN': 'SUNOVA',
    'JA SOLAR | TRINA SOLAR | SOLAR N PLUS | SOLAR N PLUS': 'JA SOLAR',
}

_SINONIMOS_INVERSOR = {
    'HOYMILES': 'HOYMILES',
    'HOYMILLES': 'HOYMILES',
    'HOYLIMES': 'HOYMILES',
    'HOMYLES': 'HOYMILES',
    'SOFAR': 'SOFAR SOLAR',
    'SOFARSOLAR': 'SOFAR SOLAR',
    'SOFARSOLAR CO., LTD.': 'SOFAR SOLAR',
    'SHENZHEN SOFAR': 'SOFAR SOLAR',
    'SHENZHEN': 'SOFAR SOLAR',
    'SHENZEN SOFAR': 'SOFAR SOLAR',
    'SHENZHEN SOFARSOLAR': 'SOFAR SOLAR',
    'SOFA': 'SOFAR SOLAR',
    'SOFAR 5KTLM-G2': 'SOFAR SOLAR',
    'SOFAR 20000TL-SX': 'SOFAR SOLAR',
    'SOFAR 3,3': 'SOFAR SOLAR',
    'SFAR': 'SOFAR SOLAR',
    'SOFARSOLAR CO., LTD.': 'SOFAR SOLAR',
    'SHEZEN SOFAR': 'SOFAR SOLAR',
    'BELENERGY': 'BEL ENERGY',
    'BEL ENERGY': 'BEL ENERGY',
    'BELENERGY PLUS': 'BEL ENERGY',
    'BELENERGY POWER': 'BEL ENERGY',
    'BELENERGY POWER - (SOLIS)': 'BEL ENERGY',
    'CANADIAN': 'CANADIAN SOLAR',
    'CANADIAN SOLAR': 'CANADIAN SOLAR',
    'HUAWEY': 'HUAWEI',
    'HAUWAY': 'HUAWEI',
    'HUA': 'HUAWEI',
    'DAYE': 'DEYE',
    'DEYS': 'DEYE',
    'DETE': 'DEYE',
    'DYER': 'DEYE',
    'GUANGZHOU SANJING ELECTRIC CO., LTD (SAJ)': 'SAJ',
    'GUANGZHOU SANJING (SAJ)': 'SAJ',
    'GUANGZHOUSANJING': 'SAJ',
    'GUANGZHOU SANJING(SAJ)': 'SAJ',
    'GUANGZHOUSANJING(SAJ)': 'SAJ',
    'GUANGZHOU SANJING_X000D_ (SAJ)': 'SAJ',
    'GUANGZHOU SANJING ELECTRIC CO., LTD (SAJ)R5-6': 'SAJ',
    'GUANGZHOUSANJINGSAJ': 'SAJ',
    'SOLAR ENERGY DO BRASIL (SAJ)': 'SAJ',
    'HOYMILES | HOYMILES': 'HOYMILES',
    'HOYMILES | HOYMILES | HOYMILES': 'HOYMILES',
    'HOYMILES | HOYMILES | HOYMILES | HOYMILES': 'HOYMILES',
    'HOYMILES | HOYMILES | HOYMILES | HOYMILES | HOYMILES': 'HOYMILES',
    'HOYMILES | ELGIN': 'HOYMILES',
    'EGT 3600 PRO': '',
    'EGT 4600 PRO': '',
    'EGT 8000 PRO': '',
    'EGT 6000 MAX': '',
    'EGT 15000 MAX': '',
    'EGT 20000 MAX': '',
    'EGT 33000 MAX': '',
    'EGT 75000 MAX': '',
    'EGT 60000 MAX': '',
    'EGT 22000 MAX': '',
    'EGT 15000 MAX 220V': '',
    'EGT 20000 MAX 220V': '',
    'EGT 8000 PRO G2': '',
    'EGT 3215X': '',
    'EGT4600PRO': '',
    'EGT3600PRO': '',
    'EGT8000PRO': '',
    'SG5K-D': '',
    'SG2K-S': '',
    'SG3K-S': '',
    'SG4K-D': '',
    'SG6K-D': '',
    'SG8K3-D': '',
    'SG3K-D': '',
    'HYPONTECH': 'HYPONTECH',
    'HI HYPONTECH': 'HYPONTECH',
    'HIHYPONTECH': 'HYPONTECH',
    'HYPON TECH': 'HYPONTECH',
    'HYPOTECH': 'HYPONTECH',
    'SMA': 'SMA',
    'SMA SOLAR TECHNOLOGY AG': 'SMA',
    'SMA TECHNOLOGIE AG': 'SMA',
    'SMA-TECHNOLOGIE': 'SMA',
    'SMASOLAR': 'SMA',
    'SMS TECHNOLOGIE': 'SMA',
    'CHINT POWER': 'CHINT',
    'CHINTPOWER': 'CHINT',
    'CHINT': 'CHINT',
    'ECOSOLYS': 'ECOSOLYS',
    'ECOSLYS': 'ECOSOLYS',
    'NEP': 'NEP',
    'NEP BDM': 'NEP',
    'NEP NORTHERN ELECTRIC': 'NEP',
    'COHEART': 'COHEART',
    'COHEART GREEN ENERGY DEVICES MANUFACTURER': 'COHEART',
    'COHEART POWER': 'COHEART',
    'COHEART POWER  COHEART INDUSTRIES LTD': 'COHEART',
    'KEHUATECH': 'KEHUA',
    'KEHUA TECH': 'KEHUA',
    'KEUA TECH': 'KEHUA',
    'SOLAX': 'SOLAX',
    'SOLAX POWER': 'SOLAX',
    'SOLXA POWER': 'SOLAX',
    'AUXSOL': 'AUXSOL',
    'AUXOL': 'AUXSOL',
    'UAXSOL': 'AUXSOL',
    'AUSTA': 'AUSTA',
    'AUSTA SOLAR': 'AUSTA',
    'AUSTRA': 'AUSTA',
    'NINGBO AUSTA SOALR TECH CO.,LTD': 'AUSTA',
    'NINGBO AUSTA SOLAR TECH CO., LTD': 'AUSTA',
    'NINGBO AUSTA SOLAR TECH CO. LTDA': 'AUSTA',
    'B&B POWER': 'B&B',
    'B&B': 'B&B',
    'B&B TOWER': 'B&B',
    'B&BPOWER': 'B&B',
    'BEBPOWER': 'B&B',
    'BEB': 'B&B',
    'MOSO B&B POWER': 'B&B',
    'EACH ENERGY': 'EACH ENERGY',
    'TECH POWER': 'TECH POWER',
    'TECHPOWER': 'TECH POWER',
    'TECK POWER': 'TECH POWER',
    'SOLAR MAXX TECH': 'SOLAR MAXX',
    'SOLARMAXX TECH': 'SOLAR MAXX',
    'SOLAR MAXX': 'SOLAR MAXX',
    'SOLAR MAXX TEXH': 'SOLAR MAXX',
    'INGETEAM': 'INGETEAM',
    'INGETEAM POWER TECHNOLOGY S.A.': 'INGETEAM',
    'INGETEAM POWER TECHNOLOGY S.A': 'INGETEAM',
    'INGETEAM LTDA': 'INGETEAM',
    'RENO': 'RENO',
    'RENO-5K PLUS': 'RENO',
    'RENO-3K PLUS': 'RENO',
    'RENO-10K': 'RENO',
    'RENO-8K': 'RENO',
    'RENO-20K-LV (SOLIS)': 'RENO',
    'RENO-4K PLUS': 'RENO',
    'RENO 15K': 'RENO',
    'RENO 20K': 'RENO',
    'RENO3000': 'RENO',
    'RENO - 500': 'RENO',
    'RENO-3K': 'RENO',
    'RENO-C 555 PA555WMCY': 'RENO',
    'SUN2000L - 4KTL': 'HUAWEI',
    'SUN2000L - 5KTL': 'HUAWEI',
    'SUN2000 - 33KTL-A': 'HUAWEI',
    'SUN2000-5KTL-L1': 'HUAWEI',
    'SUN 2000 - 15KTL-M2': 'HUAWEI',
    'NANSEN': 'NANSEN',
    'NANSEN SOLAR': 'NANSEN',
    'GENERAL ELETRIC': 'GE',
    'GENERAL ELECTRIC': 'GE',
    'GENERALELETRIC': 'GE',
    'GE': 'GE',
    'GE GEP7.0-1-10': 'GE',
    'LEVEROS': 'LEVEROS',
    'LEVEROS - HYPONTECH': 'LEVEROS',
    'WEG(HUAWEI)': 'WEG',
    'DAH SOLAR': 'CANADIAN SOLAR',
    'DAHSOLAR': 'CANADIAN SOLAR',
    'ALTENERGY POWER SYSTEM INC. (APSYSTEMS)': 'APSYSTEMS',
    'ALTENERGY POWER SYSTEM INC': 'APSYSTEMS',
    'SOLPALENT': 'SOLPLANET',
    'RISEN': 'RISEN',
    'RISEN SOLAR': 'RISEN',
    'RUNDA SOLAR': 'RUNDA SOLAR',
    'GS6000': '',
    'GS3000': '',
}

_GENERICOS_MODULO = {
    'HALF CELL', 'HALFCELL', 'HALF-CELL', 'N TYPE', 'NTYPE', 'N-TYPE',
    'NPLUS', 'N PLUS', 'MONO', 'POLI', 'POLY', 'BIFACIAL', 'TOPCOM',
    'TOPCON', 'N-TOPCON', 'VERTEX', 'MONOPERC HALF-CELL',
    'MONOPERC', 'HALFCELL', 'N-TYPE BIFACIAL',
}

_GENERICOS_INVERSOR = {
    'EGT 3600 PRO', 'EGT 4600 PRO', 'EGT 8000 PRO', 'EGT 6000 MAX',
    'EGT 15000 MAX', 'EGT 20000 MAX', 'EGT 33000 MAX', 'EGT 75000 MAX',
    'EGT 60000 MAX', 'EGT 22000 MAX', 'EGT 15000 MAX 220V',
    'EGT 20000 MAX 220V', 'EGT 8000 PRO G2', 'EGT 3215X',
    'EGT4600PRO', 'EGT3600PRO', 'EGT8000PRO',
    'SG5K-D', 'SG2K-S', 'SG3K-S', 'SG4K-D', 'SG6K-D', 'SG8K3-D', 'SG3K-D',
    'GS6000', 'GS3000',
}

_CANONICAIS_MODULO_BASE = [
    'INTELBRAS',
    'TSUN',
    'CANADIAN SOLAR',
    'LEAPTON',
    'JA SOLAR',
    'HANERSUN',
    'JINKO SOLAR',
    'SUNOVA',
    'DAH SOLAR',
    'TRINA SOLAR',
    'ASTRONERGY',
    'PULLING ENERGY',
    'BEL ENERGY',
    'BYD',
    'OSDA',
    'RENESOLA',
    'RISEN SOLAR',
    'LONGI',
    'HONOR SOLAR',
    'ZNSHINE',
    'RENOVIGI',
    'HELIUS',
    'ELGIN',
    'ERA SOLAR',
    'WEG',
    'TALESUN',
    'GCL',
    'DMEGC',
    'RONMA SOLAR',
    'LUXEN SOLAR',
    'QN SOLAR',
    'ULICA SOLAR',
    'NEXEN SOLAR',
    'SIRIUS',
    'SHINEFAR SOLAR',
    'VSUN',
    'SINE ENERGY',
    'TSUN POWER',
    'SOLAREDGE',
    'HT SAAE',
    'YINGLI SOLAR',
    'RUNERGY',
    'SOLARGICA',
    'SERAPHIM SOLAR',
    'AE SOLAR',
    'RUNDA SOLAR',
    'AMERISOLAR',
    'BLUESUN',
    'CENTRO ENERGY',
    'SCHUTTEN SOLAR',
    'JAM SOLAR',
    'HARNERSUN',
    'TOPCOM SOLAR',
    'SOLAR N PLUS',
    'TW SOLAR',
    'SUNPRO',
    'FORTLEV',
    'TAOSTIC',
    'OUROLUX',
    'LUXEM SOLAR',
    'CONSORT',
    'GOKIN SOLAR',
    'VERTYS SOLAR GROUP',
    'XPOWER SOLAR',
    'BALFAR SOLAR',
    'ODEX SOLAR',
    'RENERGY',
    'YH SUNPRO',
    'PHONO SOLAR',
    'SUNERGY',
    'PRLIGHT',
    'SUNTECH',
    'EMPALUX',
    'SOLARMAXX',
    'AKCOME',
    'TONGWEI',
    'SOLUXTEC',
    'JINERGY',
    'AXITEC',
    'SOLARSPACE',
    'SOLARJINKO',
    'SUNKET',
    'HUAWEI',
    'RENEPV',
    'GROWATT',
    'DEYE',
    'SUNGROW',
    'SAJ',
    'APSYSTEMS',
    'GOODWE',
    'NEXEN',
    'HOYMILES',
    'REC',
    'Q CELLS',
    'EMSH',
    'JASOLAR',
    'HARNERSUN',
    'SOFAR SOLAR',
    'LONGI SOLAR',
    'HELIUS SOLAR',
    'BEDIN SOLAR',
    'ASTROSEMI SOLAR',
    'RESUN',
    'RESUN SOLAR ENERGY',
    'SOLAR FOTOVOLTAICA 585W',
    'SOLAR LEADING LIMITED',
]

_CANONICAIS_INVERSOR_BASE = [
    'GROWATT',
    'DEYE',
    'SUNGROW',
    'SAJ',
    'SOLPLANET',
    'INTELBRAS',
    'SOLIS',
    'HOYMILES',
    'HUAWEI',
    'GOODWE',
    'LIVOLTEK',
    'APSYSTEMS',
    'RENOVIGI',
    'SOFAR SOLAR',
    'BEL ENERGY',
    'WEG',
    'PHB',
    'FRONIUS',
    'RENAC',
    'KEHUA',
    'KSTAR',
    'FOXESS',
    'NEXEN',
    'SOLAREDGE',
    'TSUNESS',
    'GINLONG',
    'ELSYS',
    'ENPHASE',
    'REFUSOL',
    'CANADIAN SOLAR',
    'ABB',
    'HOPEWIND',
    'SMA',
    'HYPONTECH',
    'CHINT',
    'ECOSOLYS',
    'NEP',
    'COHEART',
    'SOLAX',
    'AUXSOL',
    'AUSTA',
    'B&B',
    'EACH ENERGY',
    'TECH POWER',
    'SOLAR MAXX',
    'INGETEAM',
    'RENO',
    'NANSEN',
    'GE',
    'LEVEROS',
    'RISEN',
    'RUNDA SOLAR',
]

CANONICAIS_MODULO = set(_CANONICAIS_MODULO_BASE) | {
    v for k, v in _SINONIMOS_MODULO.items() if v
}
CANONICAIS_INVERSOR = set(_CANONICAIS_INVERSOR_BASE) | {
    v for k, v in _SINONIMOS_INVERSOR.items() if v
}

log_info(
    f'Normalizacao carregada: '
    f'{len(_SINONIMOS_MODULO)} sinonimos de modulos -> {len(CANONICAIS_MODULO)} canonicos, '
    f'{len(_SINONIMOS_INVERSOR)} sinonimos de inversores -> {len(CANONICAIS_INVERSOR)} canonicos'
)


@lru_cache(maxsize=4096)
def _fuzzy(value: str, canonicos: tuple[str, ...]) -> str | None:
    if len(value) < 3:
        return value if value in canonicos else None
    matches = difflib.get_close_matches(value, canonicos, n=1, cutoff=0.78)
    if matches:
        return matches[0]
    return None


def _match_solar_suffix(value: str, canonicos: set[str]) -> str | None:
    if value.endswith('SOLAR') and not value.endswith(' SOLAR'):
        with_suffix = f'{value.removesuffix("SOLAR")} SOLAR'.strip()
        if with_suffix in canonicos:
            return with_suffix
    if not value.endswith('SOLAR'):
        with_solar = f'{value} SOLAR'
        if with_solar in canonicos:
            return with_solar
    if value.endswith(' SOLAR'):
        without = value.removesuffix(' SOLAR')
        if without in canonicos:
            return without
    return None


_MODELO_PREFIXOS = {
    'CS': 'CANADIAN SOLAR',
    'CS3U': 'CANADIAN SOLAR',
    'CS6U': 'CANADIAN SOLAR',
    'CS3W': 'CANADIAN SOLAR',
    'TSM': 'TRINA SOLAR',
    'JKM': 'JINKO SOLAR',
    'JAP': 'JA SOLAR',
    'RSM': 'RISEN SOLAR',
    'LR': 'LONGI',
    'GCL': 'GCL',
}


def _extrair_marca(value: str, canonicos: set[str], sinominos: dict[str, str]) -> str | None:
    for prefix, marca in sorted(_MODELO_PREFIXOS.items(), key=lambda x: -len(x[0])):
        if value.startswith(prefix):
            resto = value[len(prefix):].lstrip('-').lstrip('_')
            if resto and (
                resto[:1].isdigit()
                or len(prefix) >= 2
            ):
                return marca

    tokens = re.split(r'[|/;,\-+]+', value)
    for token in tokens:
        token = token.strip()
        if token in canonicos:
            return token
        if token in sinominos:
            return sinominos[token]
        if token and token.endswith('S') and token[:-1] in canonicos:
            return token[:-1]
        cand = _match_solar_suffix(token, canonicos)
        if cand:
            return cand
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        for can in sorted(canonicos, key=len, reverse=True):
            if can in token:
                return can
            if token in can:
                return can
    return None


def _filtrar_genericos(value: str, genericos: set[str]) -> str:
    if value in genericos:
        return ''
    tokens = value.split()
    if len(tokens) <= 4 and all(t in genericos or t in {'CELL', 'FACIAL', 'HALF', 'TOP', 'CON', 'N', 'P'} for t in tokens):
        return ''
    return value


def normalizar_fabricante(
    value: str | None,
    canonicos: set[str],
    sinominos: dict[str, str],
    genericos: set[str],
) -> str:
    if not value:
        return ''

    value = _normalizar_str(value)
    if not value:
        return ''

    if value in sinominos:
        return sinominos[value]

    if value in canonicos:
        return value

    gen = _filtrar_genericos(value, genericos)
    if gen == '':
        return ''

    resultado = _match_solar_suffix(value, canonicos)
    if resultado:
        if resultado in sinominos:
            return sinominos[resultado]
        return resultado

    canonicos_t = tuple(sorted(canonicos))

    resultado = _fuzzy(value, canonicos_t)
    if resultado:
        return resultado

    extraido = _extrair_marca(value, canonicos, sinominos)
    if extraido:
        return extraido

    return gen


def normalizar_modulo(value: str | None) -> str:
    return normalizar_fabricante(value, CANONICAIS_MODULO, _SINONIMOS_MODULO, _GENERICOS_MODULO)


def normalizar_inversor(value: str | None) -> str:
    return normalizar_fabricante(value, CANONICAIS_INVERSOR, _SINONIMOS_INVERSOR, _GENERICOS_INVERSOR)
