import pandas as pd
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from src.normalize import normalizar_inversor, normalizar_modulo
from src.utils import log_aviso, log_dados, log_info, log_ok

INSTALACOES_PARQUET = Path(__file__).resolve().parents[2] / 'data' / 'data' / 'processed' / 'aneel' / 'rmr_instalacoes.parquet'
EMPREENDIMENTOS_CSV = Path(__file__).resolve().parents[2] / 'data' / 'data' / 'processed' / 'aneel' / 'empreendimento-geracao-distribuida-rmr.csv'


def _number(value: object) -> float:
    if pd.isna(value):
        return 0.0
    return float(value)


def _text(value: object) -> str:
    if pd.isna(value):
        return ''
    return str(value)


def _date_br(value: object) -> str:
    if pd.isna(value):
        return ''
    parsed = pd.to_datetime(value, errors='coerce')
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime('%d/%m/%Y')


@lru_cache(maxsize=1)
def carregar_dados_titular() -> dict[str, dict]:
    if not EMPREENDIMENTOS_CSV.exists():
        log_aviso('AneelService: arquivo de empreendimentos CSV nao encontrado')
        return {}

    colunas = ['CodEmpreendimento', 'NumCPFCNPJ', 'NomTitularEmpreendimento', 'DscModalidadeHabilitado']
    df = pd.read_csv(EMPREENDIMENTOS_CSV, sep=';', encoding='latin1', usecols=colunas)
    log_dados('AneelService: dados titular carregados do CSV', len(df), fonte=EMPREENDIMENTOS_CSV.name)
    
    return {
        _text(row.CodEmpreendimento): {
            'cpf_cnpj': _text(row.NumCPFCNPJ),
            'titular': _text(row.NomTitularEmpreendimento),
            'modalidade_habilitado': _text(row.DscModalidadeHabilitado),
        }
        for row in df.itertuples(index=False)
    }


@lru_cache(maxsize=1)
def carregar_instalacoes_aneel() -> tuple[dict[str, dict], dict[str, list[dict]], dict]:
    log_info('AneelService: carregando instalacoes ANEEL do Parquet...')
    dados_titular = carregar_dados_titular()
    
    colunas = [
        'municipio', 'cod_municipio_ibge', 'cod_empreendimento', 'tipo_consumidor',
        'classe_consumo', 'porte', 'data_conexao', 'potencia_kw', 'qtd_modulos',
        'bairro_estimado', 'cep_original', 'cep_prefixo', 'fabricante_modulo',
        'fabricante_inversor', 'modalidade', 'qtd_ucs_recebem_credito',
        'potencia_modulos_kw', 'potencia_inversores_kw', 'area_arranjo_m2',
        'latitude', 'longitude',
    ]
    
    df = pd.read_parquet(INSTALACOES_PARQUET, columns=colunas)
    log_dados('AneelService: instalacoes ANEEL carregadas do Parquet', len(df), fonte=INSTALACOES_PARQUET.name)
    
    df['potencia_kw'] = pd.to_numeric(df['potencia_kw'], errors='coerce').fillna(0)
    df['qtd_modulos'] = pd.to_numeric(df['qtd_modulos'], errors='coerce').fillna(0)

    agregados = {}
    instalacoes_por_municipio = {}
    
    for municipio, grupo in df.groupby('municipio', sort=True):
        agregados[municipio] = {
            'qtd_instalacoes': int(len(grupo)),
            'potencia_kw': round(float(grupo['potencia_kw'].sum()), 2),
            'qtd_modulos': int(grupo['qtd_modulos'].sum()),
        }
        grupo_ordenado = grupo.sort_values(['potencia_kw', 'data_conexao'], ascending=[False, False])
        instalacoes = []
        
        for row in grupo_ordenado.itertuples(index=False):
            codigo = _text(row.cod_empreendimento)
            dados_extra = dados_titular.get(codigo, {})
            data_conexao_parsed = pd.to_datetime(row.data_conexao, errors='coerce')
            data_conexao_ano = data_conexao_parsed.year if pd.notna(data_conexao_parsed) else None
            
            instalacoes.append({
                'codigo': codigo,
                'cpf_cnpj': dados_extra.get('cpf_cnpj', ''),
                'titular': dados_extra.get('titular', ''),
                'modalidade_habilitado': dados_extra.get('modalidade_habilitado') or _text(row.modalidade),
                'municipio': _text(row.municipio),
                'municipio_codigo': _text(row.cod_municipio_ibge),
                'bairro': _text(row.bairro_estimado) or 'Nao identificado',
                'classe': _text(row.classe_consumo),
                'tipo': _text(row.tipo_consumidor),
                'porte': _text(row.porte),
                'data_conexao': _date_br(row.data_conexao),
                'data_conexao_ano': data_conexao_ano,
                'potencia_kw': round(_number(row.potencia_kw), 2),
                'qtd_modulos': int(_number(row.qtd_modulos)),
                'fabricante_modulo': normalizar_modulo(_text(row.fabricante_modulo)),
                'fabricante_inversor': normalizar_inversor(_text(row.fabricante_inversor)),
                'qtd_uc_credito': int(_number(row.qtd_ucs_recebem_credito)),
                'potencia_modulos_kw': round(_number(row.potencia_modulos_kw), 2),
                'potencia_inversores_kw': round(_number(row.potencia_inversores_kw), 2),
                'area_arranjo_m2': round(_number(row.area_arranjo_m2), 2),
                'cep': _text(row.cep_original),
                'cep_prefixo': _text(row.cep_prefixo),
                'latitude': round(_number(row.latitude), 6),
                'longitude': round(_number(row.longitude), 6),
            })
        instalacoes_por_municipio[municipio] = instalacoes

    df['fabricante_modulo_norm'] = df['fabricante_modulo'].apply(
        lambda v: normalizar_modulo(_text(v)) if pd.notna(v) else ''
    )
    df['fabricante_inversor_norm'] = df['fabricante_inversor'].apply(
        lambda v: normalizar_inversor(_text(v)) if pd.notna(v) else ''
    )
    
    fabricantes_modulo = df.loc[df['fabricante_modulo_norm'] != '', 'fabricante_modulo_norm'].value_counts().head(15)
    fabricantes_inversor = df.loc[df['fabricante_inversor_norm'] != '', 'fabricante_inversor_norm'].value_counts().head(15)
    
    tipo_counts = df['tipo_consumidor'].value_counts()
    classe_counts = df['classe_consumo'].value_counts()
    porte_counts = df['porte'].value_counts()
    modalidade_counts = df['modalidade'].value_counts()

    serie_por_modalidade = df.groupby([df['data_conexao'].dt.year, 'modalidade']).size().unstack(fill_value=0)
    serie_por_modalidade.index = serie_por_modalidade.index.astype(int)
    
    charts = {
        'seriePorModalidade': {
            'labels': [str(y) for y in serie_por_modalidade.index.tolist()],
            'datasets': [{'label': col, 'data': [int(v) for v in serie_por_modalidade[col].values.tolist()]} for col in serie_por_modalidade.columns],
        },
        'porTipoPF_PJ': {
            'labels': tipo_counts.index.tolist(),
            'values': [int(v) for v in tipo_counts.values.tolist()],
        },
        'topFabricantesModulo': {
            'labels': fabricantes_modulo.index.tolist(),
            'values': [int(v) for v in fabricantes_modulo.values.tolist()],
        },
        'topFabricantesInversor': {
            'labels': fabricantes_inversor.index.tolist(),
            'values': [int(v) for v in fabricantes_inversor.values.tolist()],
        },
        'porClasse': {
            'labels': classe_counts.index.tolist(),
            'values': [int(v) for v in classe_counts.values.tolist()],
        },
        'porPorte': {
            'labels': porte_counts.index.tolist(),
            'values': [int(v) for v in porte_counts.values.tolist()],
        },
        'porModalidade': {
            'labels': modalidade_counts.index.tolist(),
            'values': [int(v) for v in modalidade_counts.values.tolist()],
        },
    }

    return agregados, instalacoes_por_municipio, charts


@lru_cache(maxsize=1)
def carregar_index_cnpj() -> dict[str, list[str]]:
    dados = carregar_dados_titular()
    index: dict[str, list[str]] = defaultdict(list)
    for cod, info in dados.items():
        cnpj = ''.join(ch for ch in info['cpf_cnpj'] if ch.isdigit())
        if len(cnpj) >= 11:
            index[cnpj].append(cod)
    log_ok(f'Index CNPJ construido: {len(index)} CNPJs mapeados')
    return dict(index)


def obter_instalacao_por_cnpj(cnpj: str) -> list[dict]:
    cnpj_digits = ''.join(ch for ch in cnpj if ch.isdigit()) if cnpj else ''
    if len(cnpj_digits) < 11:
        return []
    index = carregar_index_cnpj()
    codes = index.get(cnpj_digits, [])
    if not codes:
        return []
    df = pd.read_parquet(INSTALACOES_PARQUET, filters=[('cod_empreendimento', 'in', codes)])
    dados_tit = carregar_dados_titular()
    results = []
    for row in df.itertuples(index=False):
        cod = _text(row.cod_empreendimento)
        extra = dados_tit.get(cod, {})
        results.append({
            'codigo': cod,
            'cpf_cnpj': cnpj_digits,
            'titular': extra.get('titular', ''),
            'municipio': _text(row.municipio),
            'municipio_codigo': _text(row.cod_municipio_ibge),
            'bairro': _text(row.bairro_estimado) or 'Nao identificado',
            'classe': _text(row.classe_consumo),
            'tipo': _text(row.tipo_consumidor),
            'data_conexao': _date_br(row.data_conexao),
            'potencia_kw': round(_number(row.potencia_kw), 2),
            'qtd_modulos': int(_number(row.qtd_modulos)),
            'fabricante_modulo': normalizar_modulo(_text(row.fabricante_modulo)),
            'fabricante_inversor': normalizar_inversor(_text(row.fabricante_inversor)),
            'cep': _text(row.cep_original),
            'latitude': round(_number(row.latitude), 6),
            'longitude': round(_number(row.longitude), 6),
        })
    return results