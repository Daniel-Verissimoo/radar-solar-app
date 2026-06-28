from __future__ import annotations

import argparse
import unicodedata
import zipfile
from pathlib import Path

import pandas as pd

from src.utils import log_info, log_dados, log_ok

BASE_DIR = Path(__file__).resolve().parent.parent
ANEEL_RAW_DIR = BASE_DIR / 'data' / 'data' / 'raw' / 'aneel'
OUTPUT_DIR = BASE_DIR / 'data' / 'data' / 'processed' / 'aneel'

EMPREENDIMENTOS_ZIP = ANEEL_RAW_DIR / 'empreendimento-geracao-distribuida.zip'
INFO_TECNICA_CSV = ANEEL_RAW_DIR / 'empreendimento-gd-informacoes-tecnicas-fotovoltaica.csv'

RMR_EMPREENDIMENTOS_CSV = OUTPUT_DIR / 'empreendimento-geracao-distribuida-rmr.csv'
RMR_INFO_TECNICA_CSV = OUTPUT_DIR / 'empreendimento-gd-informacoes-tecnicas-fotovoltaica-rmr.csv'

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


def normalize_text(value: object) -> str:
    text = '' if pd.isna(value) else str(value).strip().upper()
    text = unicodedata.normalize('NFKD', text)
    return ''.join(char for char in text if not unicodedata.combining(char))


def ensure_inputs_exist() -> None:
    missing = [path for path in [EMPREENDIMENTOS_ZIP, INFO_TECNICA_CSV] if not path.exists()]
    if missing:
        missing_list = '\n'.join(f'- {path.relative_to(BASE_DIR)}' for path in missing)
        raise FileNotFoundError(
            'Arquivos brutos ANEEL ausentes. Execute antes:\n'
            'uv run python scripts/update_aneel_data.py\n\n'
            f'Ausentes:\n{missing_list}'
        )


def extract_empreendimentos_rmr(chunksize: int, force: bool) -> set[str]:
    if RMR_EMPREENDIMENTOS_CSV.exists() and not force:
        log_info(f'Usando arquivo existente: {RMR_EMPREENDIMENTOS_CSV.relative_to(BASE_DIR)}')
        codigos = pd.read_csv(
            RMR_EMPREENDIMENTOS_CSV,
            sep=';',
            dtype=str,
            usecols=['CodEmpreendimento'],
            encoding='latin1',
        )['CodEmpreendimento'].dropna()
        return set(codigos.astype(str))

    RMR_EMPREENDIMENTOS_CSV.unlink(missing_ok=True)
    codigos: set[str] = set()
    total = 0
    written_header = False

    with zipfile.ZipFile(EMPREENDIMENTOS_ZIP) as archive:
        csv_name = archive.namelist()[0]
        with archive.open(csv_name) as file:
            reader = pd.read_csv(file, sep=';', dtype=str, chunksize=chunksize, encoding='latin1')
            for index, chunk in enumerate(reader, start=1):
                municipio_norm = chunk['NomMunicipio'].map(normalize_text)
                filtered = chunk[(chunk['SigUF'] == 'PE') & (municipio_norm.isin(RMR_MUNICIPIOS))].copy()
                if filtered.empty:
                    log_info(f'empreendimentos: chunk {index}; nenhum registro RMR')
                    continue

                filtered.to_csv(
                    RMR_EMPREENDIMENTOS_CSV,
                    sep=';',
                    index=False,
                    mode='a',
                    header=not written_header,
                    encoding='latin1',
                )
                written_header = True
                total += len(filtered)
                codigos.update(filtered['CodEmpreendimento'].dropna().astype(str))
                log_dados(f'empreendimentos: chunk {index}', total, 'acumulado RMR')

    log_ok(f'Empreendimentos RMR gerado: {RMR_EMPREENDIMENTOS_CSV.relative_to(BASE_DIR)} ({total} linhas)')
    return codigos


def extract_info_tecnica_rmr(codigos: set[str], chunksize: int, force: bool) -> None:
    if RMR_INFO_TECNICA_CSV.exists() and not force:
        log_info(f'Usando arquivo existente: {RMR_INFO_TECNICA_CSV.relative_to(BASE_DIR)}')
        return

    RMR_INFO_TECNICA_CSV.unlink(missing_ok=True)
    total = 0
    written_header = False

    reader = pd.read_csv(INFO_TECNICA_CSV, sep=';', dtype=str, chunksize=chunksize, encoding='latin1')
    for index, chunk in enumerate(reader, start=1):
        filtered = chunk[chunk['CodGeracaoDistribuida'].isin(codigos)].copy()
        if filtered.empty:
            log_info(f'info_tecnica: chunk {index}; nenhum registro RMR')
            continue

        filtered.to_csv(
            RMR_INFO_TECNICA_CSV,
            sep=';',
            index=False,
            mode='a',
            header=not written_header,
            encoding='latin1',
        )
        written_header = True
        total += len(filtered)
        log_dados(f'info_tecnica: chunk {index}', total, 'acumulado RMR')

    log_ok(f'Info tecnica RMR gerada: {RMR_INFO_TECNICA_CSV.relative_to(BASE_DIR)} ({total} linhas)')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Extrai CSVs ANEEL filtrados para a RMR.')
    parser.add_argument('--chunksize', type=int, default=200_000, help='Quantidade de linhas por chunk.')
    parser.add_argument('--force', action='store_true', help='Regenera os CSVs mesmo se ja existirem.')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ensure_inputs_exist()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    codigos = extract_empreendimentos_rmr(args.chunksize, args.force)
    extract_info_tecnica_rmr(codigos, args.chunksize, args.force)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
