from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.utils import log_info, log_ok, log_aviso, log_erro, log_dados, log_separador

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / 'data' / 'data' / 'raw'
ANEEL_RAW_DIR = RAW_DIR / 'aneel'
PROCESSED_DIR = BASE_DIR / 'data' / 'data' / 'processed' / 'aneel'
MANIFEST_PATH = ANEEL_RAW_DIR / 'manifest.json'

RMR_MUNICIPIOS = {
    'ABREU E LIMA',
    'ARACOIABA',
    'CABO DE SANTO AGOSTINHO',
    'CAMARAGIBE',
    'IGARASSU',
    'ILHA DE ITAMARACA',
    'IPOJUCA',
    'ITAPISSUMA',
    'JABOATAO DOS GUARARAPES',
    'MORENO',
    'OLINDA',
    'PAULISTA',
    'RECIFE',
    'SAO LOURENCO DA MATA',
}

EMPREENDIMENTOS_COLS = [
    'DatGeracaoConjuntoDados',
    'AnmPeriodoReferencia',
    'NomAgente',
    'DscClasseConsumo',
    'DscSubGrupoTarifario',
    'SigUF',
    'CodMunicipioIbge',
    'NomMunicipio',
    'CodCEP',
    'SigTipoConsumidor',
    'CodEmpreendimento',
    'DthAtualizaCadastralEmpreend',
    'DscModalidadeHabilitado',
    'QtdUCRecebeCredito',
    'DscFonteGeracao',
    'DscPorte',
    'NumCoordNEmpreendimento',
    'NumCoordEEmpreendimento',
    'MdaPotenciaInstaladaKW',
]

INFO_TECNICA_COLS = [
    'CodGeracaoDistribuida',
    'MdaAreaArranjo',
    'MdaPotenciaInstalada',
    'NomFabricanteModulo',
    'NomFabricanteInversor',
    'DatConexao',
    'MdaPotenciaModulos',
    'MdaPotenciaInversores',
    'QtdModulos',
    'NomModeloModulo',
    'NomModeloInversor',
]

ANEEL_RESOURCES = {
    'empreendimentos': {
        'url': 'https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/b1bd71e7-d0ad-4214-9053-cbd58e9564a7/download/empreendimento-geracao-distribuida.zip',
        'filename': 'empreendimento-geracao-distribuida.zip',
    },
    'info_tecnica_fotovoltaica': {
        'url': 'https://dadosabertos.aneel.gov.br/dataset/5e0fafd2-21b9-4d5b-b622-40438d40aba2/resource/49fa9ca0-f609-4ae3-a6f7-b97bd0945a3a/download/empreendimento-gd-informacoes-tecnicas-fotovoltaica.csv',
        'filename': 'empreendimento-gd-informacoes-tecnicas-fotovoltaica.csv',
    },
}


@dataclass(frozen=True)
class RemoteMetadata:
    etag: str | None
    last_modified: str | None
    content_length: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {'resources': {}}
    with MANIFEST_PATH.open('r', encoding='utf-8') as file:
        return json.load(file)


def save_manifest(manifest: dict) -> None:
    ANEEL_RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest['updated_at'] = utc_now_iso()
    with MANIFEST_PATH.open('w', encoding='utf-8') as file:
        json.dump(manifest, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write('\n')


def fetch_remote_metadata(url: str) -> RemoteMetadata | None:
    request = Request(url, method='HEAD', headers={'User-Agent': 'RadarSolarDataPipeline/1.0'})
    try:
        with urlopen(request, timeout=30) as response:
            return RemoteMetadata(
                etag=response.headers.get('ETag'),
                last_modified=response.headers.get('Last-Modified'),
                content_length=response.headers.get('Content-Length'),
            )
    except (HTTPError, URLError, TimeoutError) as exc:
        log_aviso(f'Nao foi possivel consultar metadados remotos: {exc}')
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_text(value: object) -> str:
    text = '' if pd.isna(value) else str(value).strip().upper()
    replacements = str.maketrans(
        'ÁÀÂÃÄÉÈÊËÍÌÎÏÓÒÔÕÖÚÙÛÜÇ',
        'AAAAAEEEEIIIIOOOOOUUUUC',
    )
    return text.translate(replacements)


def parse_float_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str).str.strip().str.replace('.', '', regex=False).str.replace(',', '.', regex=False),
        errors='coerce',
    )


def parse_int_series(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.strip(), errors='coerce').astype('Int64')


def extract_cep_prefix(value: object) -> str:
    digits = ''.join(filter(str.isdigit, '' if pd.isna(value) else str(value)))
    return digits[:5] if len(digits) >= 5 else ''


def download_to_temp(url: str) -> Path:
    request = Request(url, headers={'User-Agent': 'RadarSolarDataPipeline/1.0'})
    temp = tempfile.NamedTemporaryFile(delete=False, prefix='aneel_', suffix='.download')
    temp_path = Path(temp.name)
    temp.close()

    try:
        with urlopen(request, timeout=120) as response, temp_path.open('wb') as file:
            shutil.copyfileobj(response, file)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise

    return temp_path


def metadata_matches(previous: dict, remote: RemoteMetadata | None) -> bool:
    if remote is None:
        return False
    comparable = ['etag', 'last_modified', 'content_length']
    available = [field for field in comparable if getattr(remote, field) and previous.get(field)]
    if not available:
        return False
    return all(previous.get(field) == getattr(remote, field) for field in available)


def update_resource(name: str, config: dict, manifest: dict, force: bool = False) -> bool:
    ANEEL_RAW_DIR.mkdir(parents=True, exist_ok=True)
    resources = manifest.setdefault('resources', {})
    previous = resources.get(name, {})
    destination = ANEEL_RAW_DIR / config['filename']

    log_info(f'{name}: verificando versao remota')
    metadata = fetch_remote_metadata(name)
    if metadata and sha256_local == metadata.get('sha256'):
        log_info(f'{name}: sem alteracao pelos metadados remotos; download ignorado')
        return 0

    if force:
        log_info(f'{name}: download forcado')
    elif not destination.exists():
        log_info(f'{name}: arquivo local ausente; baixando')
    else:
        log_info(f'{name}: metadados mudaram ou indisponiveis; baixando para confirmar sha256')

    temp_path = download_to_temp(config['url'])
    try:
        new_sha256 = sha256_file(temp_path)
        old_sha256 = previous.get('sha256')

        if not force and destination.exists() and old_sha256 == new_sha256:
            log_info(f'{name}: conteudo identico pelo sha256; arquivo local mantido')
            changed = False
        else:
            shutil.move(str(tmp_path), str(destination))
            log_ok(f'{name}: arquivo atualizado em {destination.relative_to(BASE_DIR)}')
            changed = True

        resources[name] = {
            'url': config['url'],
            'filename': config['filename'],
            'etag': remote.etag if remote else None,
            'last_modified': remote.last_modified if remote else None,
            'content_length': remote.content_length if remote else None,
            'sha256': new_sha256,
            'downloaded_at': utc_now_iso(),
            'changed': changed,
        }
        return changed
    finally:
        temp_path.unlink(missing_ok=True)


def read_empreendimentos_rmr(chunksize: int = 200_000) -> pd.DataFrame:
    zip_path = ANEEL_RAW_DIR / ANEEL_RESOURCES['empreendimentos']['filename']
    if not zip_path.exists():
        raise FileNotFoundError(f'Arquivo ANEEL ausente: {zip_path}')

    frames: list[pd.DataFrame] = []
    with zipfile.ZipFile(zip_path) as archive:
        csv_name = archive.namelist()[0]
        with archive.open(csv_name) as file:
            reader = pd.read_csv(
                file,
                sep=';',
                dtype=str,
                usecols=EMPREENDIMENTOS_COLS,
                chunksize=chunksize,
                encoding='latin1',
            )
            for index, chunk in enumerate(reader, start=1):
                chunk['municipio_norm'] = chunk['NomMunicipio'].map(normalize_text)
                filtered = chunk[(chunk['SigUF'] == 'PE') & (chunk['municipio_norm'].isin(RMR_MUNICIPIOS))].copy()
                if not filtered.empty:
                    frames.append(filtered)
                log_dados(f'empreendimentos: chunk {index}', sum(len(frame) for frame in frames), 'acumulado RMR')

    if not frames:
        return pd.DataFrame(columns=EMPREENDIMENTOS_COLS + ['municipio_norm'])
    return pd.concat(frames, ignore_index=True)


def read_info_tecnica_for(codigos: set[str], chunksize: int = 250_000) -> pd.DataFrame:
    csv_path = ANEEL_RAW_DIR / ANEEL_RESOURCES['info_tecnica_fotovoltaica']['filename']
    if not csv_path.exists():
        raise FileNotFoundError(f'Arquivo ANEEL ausente: {csv_path}')

    frames: list[pd.DataFrame] = []
    reader = pd.read_csv(
        csv_path,
        sep=';',
        dtype=str,
        usecols=INFO_TECNICA_COLS,
        chunksize=chunksize,
        encoding='latin1',
    )
    for index, chunk in enumerate(reader, start=1):
        filtered = chunk[chunk['CodGeracaoDistribuida'].isin(codigos)].copy()
        if not filtered.empty:
            frames.append(filtered)
        log_dados(f'info_tecnica: chunk {index}', sum(len(frame) for frame in frames), 'acumulado RMR')

    if not frames:
        return pd.DataFrame(columns=INFO_TECNICA_COLS)
    return pd.concat(frames, ignore_index=True)


def build_cep_bairro_lookup() -> list[tuple[int, int, str, str]]:
    dne_dir = RAW_DIR / 'correios' / 'eDNE_Basico_26031' / 'Delimitado'
    faixa_bairro = pd.read_csv(
        dne_dir / 'LOG_FAIXA_BAIRRO.TXT',
        sep='@',
        names=['BAI_NU', 'FCB_CEP_INI', 'FCB_CEP_FIM'],
        dtype=str,
        encoding='latin1',
    )
    bairros = pd.read_csv(
        dne_dir / 'LOG_BAIRRO.TXT',
        sep='@',
        names=['BAI_NU', 'UFE_SG', 'LOC_NU', 'BAI_NO', 'BAI_NO_ABREV'],
        dtype=str,
        encoding='latin1',
    )
    localidades = pd.read_csv(
        dne_dir / 'LOG_LOCALIDADE.TXT',
        sep='@',
        names=['LOC_NU', 'UFE_SG', 'LOC_NO', 'CEP', 'LOC_IN_SIT', 'LOC_IN_TIPO_LOC', 'LOC_NU_SUB', 'LOC_NO_ABREV', 'MUN_NU'],
        dtype=str,
        encoding='latin1',
    )

    bairros_pe = bairros[bairros['UFE_SG'] == 'PE'][['BAI_NU', 'LOC_NU', 'BAI_NO']]
    localidades_pe = localidades[localidades['UFE_SG'] == 'PE'][['LOC_NU', 'LOC_NO']]
    merged = faixa_bairro.merge(bairros_pe, on='BAI_NU', how='inner').merge(localidades_pe, on='LOC_NU', how='left')

    lookup = []
    for row in merged.itertuples(index=False):
        try:
            lookup.append((int(row.FCB_CEP_INI), int(row.FCB_CEP_FIM), str(row.BAI_NO), str(row.LOC_NO)))
        except (TypeError, ValueError):
            continue
    return lookup


def resolve_bairro_for_prefix(cep_prefix: str, lookup: list[tuple[int, int, str, str]]) -> tuple[str | None, str | None]:
    if not cep_prefix:
        return None, None
    cep_ini = int(f'{cep_prefix}000')
    cep_fim = int(f'{cep_prefix}999')
    for faixa_ini, faixa_fim, bairro, municipio in lookup:
        if faixa_ini <= cep_fim and faixa_fim >= cep_ini:
            return bairro, municipio
    return None, None


def normalize_joined_data(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        'CodEmpreendimento': 'cod_empreendimento',
        'DatGeracaoConjuntoDados': 'data_geracao_dados',
        'AnmPeriodoReferencia': 'periodo_referencia',
        'NomAgente': 'concessionaria',
        'DscClasseConsumo': 'classe_consumo',
        'DscSubGrupoTarifario': 'subgrupo_tarifario',
        'SigUF': 'uf',
        'CodMunicipioIbge': 'cod_municipio_ibge',
        'NomMunicipio': 'municipio',
        'CodCEP': 'cep_original',
        'SigTipoConsumidor': 'tipo_consumidor',
        'DthAtualizaCadastralEmpreend': 'data_atualizacao_cadastral',
        'DscModalidadeHabilitado': 'modalidade',
        'QtdUCRecebeCredito': 'qtd_ucs_recebem_credito',
        'DscFonteGeracao': 'fonte_geracao',
        'DscPorte': 'porte',
        'NumCoordNEmpreendimento': 'latitude',
        'NumCoordEEmpreendimento': 'longitude',
        'MdaPotenciaInstaladaKW': 'potencia_kw',
        'MdaAreaArranjo': 'area_arranjo_m2',
        'MdaPotenciaInstalada': 'potencia_tecnica_kw',
        'NomFabricanteModulo': 'fabricante_modulo',
        'NomFabricanteInversor': 'fabricante_inversor',
        'DatConexao': 'data_conexao',
        'MdaPotenciaModulos': 'potencia_modulos_kw',
        'MdaPotenciaInversores': 'potencia_inversores_kw',
        'QtdModulos': 'qtd_modulos',
        'NomModeloModulo': 'modelo_modulo',
        'NomModeloInversor': 'modelo_inversor',
    }
    df = df.rename(columns=rename_map)
    for column in ['potencia_kw', 'latitude', 'longitude', 'area_arranjo_m2', 'potencia_tecnica_kw', 'potencia_modulos_kw', 'potencia_inversores_kw']:
        if column in df:
            df[column] = parse_float_series(df[column])
    for column in ['qtd_ucs_recebem_credito', 'qtd_modulos']:
        if column in df:
            df[column] = parse_int_series(df[column])
    for column in ['data_conexao', 'data_atualizacao_cadastral', 'data_geracao_dados']:
        if column in df:
            df[column] = pd.to_datetime(df[column], errors='coerce')
    df['cep_prefixo'] = df['cep_original'].map(extract_cep_prefix)
    return df


def enrich_with_bairro(df: pd.DataFrame) -> pd.DataFrame:
    lookup = build_cep_bairro_lookup()
    unique_prefixes = sorted(prefix for prefix in df['cep_prefixo'].dropna().unique() if prefix)
    resolved = {prefix: resolve_bairro_for_prefix(prefix, lookup) for prefix in unique_prefixes}
    df['bairro_estimado'] = df['cep_prefixo'].map(lambda prefix: resolved.get(prefix, (None, None))[0])
    df['municipio_dne'] = df['cep_prefixo'].map(lambda prefix: resolved.get(prefix, (None, None))[1])
    return df


def write_parquets(instalacoes: pd.DataFrame) -> None:
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    instalacoes_path = PROCESSED_DIR / 'rmr_instalacoes.parquet'
    municipios_path = PROCESSED_DIR / 'rmr_municipios.parquet'
    bairros_path = PROCESSED_DIR / 'rmr_bairros.parquet'
    equipamentos_path = PROCESSED_DIR / 'rmr_equipamentos.parquet'
    serie_path = PROCESSED_DIR / 'rmr_serie_mensal.parquet'

    instalacoes.to_parquet(instalacoes_path, index=False)

    municipios = (
        instalacoes.groupby(['uf', 'municipio'], dropna=False)
        .agg(
            qtd_instalacoes=('cod_empreendimento', 'count'),
            potencia_kw=('potencia_kw', 'sum'),
            potencia_media_kw=('potencia_kw', 'mean'),
            data_primeira_conexao=('data_conexao', 'min'),
            data_ultima_conexao=('data_conexao', 'max'),
        )
        .reset_index()
    )
    municipios.to_parquet(municipios_path, index=False)

    bairros_base = instalacoes.copy()
    bairros_base['bairro_estimado'] = bairros_base['bairro_estimado'].fillna('Nao identificado')
    bairros = (
        bairros_base.groupby(['uf', 'municipio', 'bairro_estimado'], dropna=False)
        .agg(
            qtd_instalacoes=('cod_empreendimento', 'count'),
            potencia_kw=('potencia_kw', 'sum'),
            potencia_media_kw=('potencia_kw', 'mean'),
            latitude_centroide=('latitude', 'mean'),
            longitude_centroide=('longitude', 'mean'),
            data_primeira_conexao=('data_conexao', 'min'),
            data_ultima_conexao=('data_conexao', 'max'),
        )
        .reset_index()
    )
    bairros['score_oportunidade'] = bairros['qtd_instalacoes'] * 0.6 + bairros['potencia_kw'].fillna(0) * 0.4
    bairros.to_parquet(bairros_path, index=False)

    equipamentos_base = bairros_base.copy()
    equipamentos_base['fabricante_modulo'] = equipamentos_base['fabricante_modulo'].fillna('Nao informado').str.strip()
    equipamentos_base['fabricante_inversor'] = equipamentos_base['fabricante_inversor'].fillna('Nao informado').str.strip()
    equipamentos = (
        equipamentos_base.groupby(['uf', 'municipio', 'bairro_estimado', 'fabricante_modulo', 'fabricante_inversor'], dropna=False)
        .agg(qtd_instalacoes=('cod_empreendimento', 'count'), potencia_kw=('potencia_kw', 'sum'))
        .reset_index()
    )
    equipamentos.to_parquet(equipamentos_path, index=False)

    serie_base = instalacoes.dropna(subset=['data_conexao']).copy()
    serie_base['ano_mes'] = serie_base['data_conexao'].dt.to_period('M').astype(str)
    serie = (
        serie_base.groupby(['ano_mes', 'uf', 'municipio'], dropna=False)
        .agg(novas_instalacoes=('cod_empreendimento', 'count'), potencia_adicionada_kw=('potencia_kw', 'sum'))
        .reset_index()
        .sort_values(['municipio', 'ano_mes'])
    )
    serie['potencia_acumulada_kw'] = serie.groupby('municipio')['potencia_adicionada_kw'].cumsum()
    serie.to_parquet(serie_path, index=False)

    log_info('Parquets gerados:')
    for path in parquet_paths:
        tamanho_mb = path.stat().st_size / 1024 / 1024
        log_info(f'  {path.relative_to(BASE_DIR)} ({tamanho_mb:.2f} MB)')


def process_aneel_data() -> None:
    log_info('Processando empreendimentos ANEEL para PE/RMR...')
    empreendimentos = read_empreendimentos_rmr(args.chunksize, args.force_process)
    log_dados('empreendimentos RMR processados', len(empreendimentos))

    log_info('Processando informacoes tecnicas fotovoltaicas...')
    info_tecnica = read_info_tecnica_rmr(args.chunksize, args.force_process)
    log_dados('info tecnica RMR processados', len(info_tecnica))

    joined = empreendimentos.merge(
        info_tecnica,
        left_on='CodEmpreendimento',
        right_on='CodGeracaoDistribuida',
        how='left',
    )
    instalacoes = normalize_joined_data(joined)
    instalacoes = enrich_with_bairro(instalacoes)
    write_parquets(instalacoes)


def validate_supporting_raw_data() -> bool:
    ibge_dir = RAW_DIR / 'ibge'

    checks = [
        ('IBGE municipios PE', ibge_dir / 'PE_Municipios_2024' / 'PE_Municipios_2024.shp'),
        ('IBGE bairros PE', ibge_dir / 'PE_bairros_CD2022' / 'PE_bairros_CD2022.shp'),
        ('Correios DNE delimitado', RAW_DIR / 'correios' / 'eDNE_Basico_26031' / 'Delimitado' / 'LOG_BAIRRO.TXT'),
        ('Correios DNE faixas bairro', RAW_DIR / 'correios' / 'eDNE_Basico_26031' / 'Delimitado' / 'LOG_FAIXA_BAIRRO.TXT'),
        ('Correios DNE localidades', RAW_DIR / 'correios' / 'eDNE_Basico_26031' / 'Delimitado' / 'LOG_LOCALIDADE.TXT'),
    ]

    log_info('Validando bases auxiliares...')
    all_ok = True
    for label, path in checks:
        exists = path.exists()
        all_ok = all_ok and exists
        if exists:
            log_ok(f'{label}: {path.relative_to(BASE_DIR)}')
        else:
            log_aviso(f'{label}: AUSENTE ({path.relative_to(BASE_DIR)})')
    return all_ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Baixa bases ANEEL quando houver nova versao disponivel.')
    parser.add_argument('--force', action='store_true', help='Baixa novamente mesmo se metadados/sha256 indicarem igualdade.')
    parser.add_argument('--validate-only', action='store_true', help='Valida estrutura local sem baixar ANEEL.')
    parser.add_argument('--process-only', action='store_true', help='Nao baixa dados; apenas gera os Parquets com os arquivos locais.')
    parser.add_argument('--force-process', action='store_true', help='Gera Parquets mesmo se os arquivos remotos nao mudaram.')
    return parser.parse_args()


def processed_outputs_exist() -> bool:
    expected = [
        'rmr_instalacoes.parquet',
        'rmr_municipios.parquet',
        'rmr_bairros.parquet',
        'rmr_equipamentos.parquet',
        'rmr_serie_mensal.parquet',
    ]
    return all((PROCESSED_DIR / filename).exists() for filename in expected)


def main() -> int:
    args = parse_args()
    if not validate_supporting_raw_data():
        log_erro('Bases auxiliares obrigatorias ausentes em data/raw.')
        return 1

    if args.validate_only:
        return 0

    if args.process_only:
        process_aneel_data()
        return 0

    manifest = load_manifest()
    any_changed = False
    for name, config in ANEEL_RESOURCES.items():
        try:
            changed = update_resource(name, config, manifest, force=args.force)
        except (HTTPError, URLError, TimeoutError) as exc:
            log_erro(f'Falha ao baixar {name}: {exc}')
            return 1
        any_changed = any_changed or changed

    manifest['last_run'] = {
        'checked_at': utc_now_iso(),
        'any_changed': any_changed,
    }
    save_manifest(manifest)
    if any_changed or args.force_process or not processed_outputs_exist():
        process_aneel_data()
    else:
        log_info('Parquets ja existem e dados remotos nao mudaram; processamento ignorado')
    log_separador(f'Concluido. Houve atualizacao: {any_changed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
