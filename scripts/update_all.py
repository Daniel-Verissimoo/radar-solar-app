from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from src.utils import log_info, log_ok, log_erro, log_separador

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / 'scripts'


def _run(script_name: str, description: str, *args: str) -> int:
    script_path = SCRIPTS_DIR / script_name
    args = [a for a in args if a]
    cmd = [sys.executable, str(script_path), *args]
    log_separador(description)
    log_info(f'Script: {script_name} {" ".join(args)}')
    t0 = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - t0
    if result.returncode != 0:
        log_erro(f'{script_name} falhou (exit={result.returncode}) apos {elapsed:.0f}s')
    else:
        log_ok(f'{script_name} concluido em {elapsed:.0f}s')
    return result.returncode


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Pipeline completo Radar Solar: ANEEL → normalizacao → CNPJ → cache.',
    )
    parser.add_argument('--force', action='store_true',
                        help='Forca download ANEEL e regeneracao dos CSVs/parquets.')
    parser.add_argument('--skip-cnpj', action='store_true',
                        help='Pula a etapa de enriquecimento CNPJ (lenta, ~13s por CNPJ novo).')
    parser.add_argument('--validate-only', action='store_true',
                        help='Apenas valida estrutura dos dados auxiliares, sem baixar ou processar nada.')
    parser.add_argument('--aneel-only', action='store_true',
                        help='Executa apenas a etapa ANEEL (download + processamento).')
    parser.add_argument('--csv-only', action='store_true',
                        help='Executa apenas a extracao dos CSVs RMR (precisa dos ZIPs ANEEL).')
    parser.add_argument('--cnpj-only', action='store_true',
                        help='Executa apenas o enriquecimento CNPJ (precisa dos CSVs e parquets).')
    parser.add_argument('--chunksize', type=int, default=200_000,
                        help='Linhas por chunk na leitura dos CSVs ANEEL.')
    parser.add_argument('--cnpj-limit', type=int, default=None,
                        help='Processa no maximo N CNPJs pendentes na etapa CNPJ.')
    parser.add_argument('--cnpj-dry-run', action='store_true',
                        help='Lista CNPJs pendentes sem consultar APIs nem gravar dados.')
    parser.add_argument('--cnpj-skip-geocode', action='store_true',
                        help='Consulta CNPJa sem geocodificar no Nominatim.')
    parser.add_argument('--cnpj-no-parquet', action='store_true',
                        help='Nao atualiza o parquet ao final da etapa CNPJ.')
    return parser.parse_args()


def cnpj_args(args: argparse.Namespace) -> list[str]:
    return [
        f'--limit={args.cnpj_limit}' if args.cnpj_limit is not None else '',
        '--dry-run' if args.cnpj_dry_run else '',
        '--skip-geocode' if args.cnpj_skip_geocode else '',
        '--no-parquet' if args.cnpj_no_parquet else '',
    ]


def main() -> int:
    args = parse_args()

    if args.validate_only:
        return _run('update_aneel_data.py', 'Validacao dos dados auxiliares', '--validate-only')

    if args.aneel_only:
        return _run('update_aneel_data.py', 'Atualizacao ANEEL (download + parquets)',
                     '--force' if args.force else '')

    if args.csv_only:
        return _run('extract_aneel_rmr_csv.py', 'Extracao CSVs RMR',
                     '--force' if args.force else '',
                     f'--chunksize={args.chunksize}')

    if args.cnpj_only:
        return _run(
            'update_cnpj_enderecos.py',
            'Enriquecimento CNPJ (cache + geocodificacao)',
            *cnpj_args(args),
        )

    # --- Pipeline completo ---
    code = _run('update_aneel_data.py', '1/3: Atualizacao ANEEL',
                '--force' if args.force else '',
                '--force-process' if args.force else '')
    if code != 0:
        return code

    code = _run('extract_aneel_rmr_csv.py', '2/3: Extracao CSVs RMR',
                '--force' if args.force else '',
                f'--chunksize={args.chunksize}')
    if code != 0:
        return code

    if not args.skip_cnpj:
        code = _run('update_cnpj_enderecos.py', '3/3: Enriquecimento CNPJ', *cnpj_args(args))
        if code != 0:
            return code
    else:
        log_info('[skip] CNPJ enrichment pulado (--skip-cnpj).')

    log_separador('Pipeline completo concluido com sucesso!')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
