"""
Baixa automaticamente o e-DNE Basico do site dos Correios e extrai para data/raw/correios/.
Uso: uv run python scripts/baixar_dne.py
     uv run python scripts/baixar_dne.py --force
"""
from __future__ import annotations

import re
import sys
import zipfile
import tempfile
import shutil
from pathlib import Path
from urllib.request import urlopen
from urllib.error import URLError

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils import log_info, log_ok, log_aviso, log_erro

BASE_DIR = Path(__file__).resolve().parent.parent
CORREIOS_DIR = BASE_DIR / 'data' / 'data' / 'raw' / 'correios'
DNE_URL = 'https://www2.correios.com.br/sistemas/edne/download/eDNE_Basico.zip'


def _extrair_versao(leiame_path: Path) -> str | None:
    try:
        texto = leiame_path.read_text(encoding='latin1', errors='replace')
        m = re.search(r'DNE vers[ãa]o\s*(\d{5})', texto)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


def main() -> int:
    CORREIOS_DIR.mkdir(parents=True, exist_ok=True)
    import argparse
    parser = argparse.ArgumentParser(description='Baixa e extrai o e-DNE Basico dos Correios.')
    parser.add_argument('--force', action='store_true', help='Baixa novamente mesmo se ja existir.')
    args = parser.parse_args()

    dne_dirs = sorted(CORREIOS_DIR.glob('eDNE_Basico_*'))
    if dne_dirs and not args.force:
        ultimo = dne_dirs[-1]
        leiame = ultimo / 'Delimitado' / 'LEIAME.TXT'
        if leiame.exists():
            versao = _extrair_versao(leiame)
            log_ok(f'DNE ja baixado: {ultimo.name} (versao {versao})')
            log_info(f'Use --force para baixar novamente.')
            return 0

    log_info(f'Baixando e-DNE Basico de {DNE_URL}...')
    try:
        with urlopen(DNE_URL, timeout=120) as resp:
            total = int(resp.headers.get('Content-Length', 0))
            baixado = 0
            dados = bytearray()
            while bloco := resp.read(65536):
                dados.extend(bloco)
                baixado += len(bloco)
                if total:
                    pct = baixado * 100 // total
                    print(f'\r  Baixando... {pct}% ({baixado//1024//1024}MB / {total//1024//1024}MB)', end='', file=sys.stderr)
            print(file=sys.stderr)
    except URLError as e:
        log_erro(f'Falha ao baixar DNE: {e}')
        return 1

    log_ok(f'Download concluido ({len(dados)//1024//1024}MB)')

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / 'download.zip'
        zip_path.write_bytes(dados)

        with zipfile.ZipFile(zip_path) as zf:
            nomes = zf.namelist()

            inner_zip = None
            for nome in nomes:
                if nome.lower().startswith('edne_basico_') and nome.lower().endswith('.zip'):
                    inner_zip = nome
                    break

            if not inner_zip:
                log_erro('eDNE_Basico_*.zip nao encontrado dentro do pacote baixado.')
                return 1

            log_info(f'Extraindo {inner_zip}...')
            inner_path = tmp_path / inner_zip
            with zf.open(inner_zip) as src, open(inner_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)

        versao = None
        with zipfile.ZipFile(inner_path) as zf:
            leiame_info = None
            for nome in zf.namelist():
                if nome.upper() == 'LEIAME.TXT':
                    leiame_info = nome
                    break
                if nome.upper().endswith('/LEIAME.TXT'):
                    leiame_info = nome
                    break

            if leiame_info:
                with zf.open(leiame_info) as f:
                    texto = f.read().decode('latin1', errors='replace')
                    m = re.search(r'DNE vers[ãa]o\s*(\d{5})', texto)
                    if m:
                        versao = m.group(1)

            extract_dir = tmp_path / 'extracted'
            extract_dir.mkdir()
            zf.extractall(extract_dir)

        if not versao:
            versao = inner_zip.replace('.zip', '').replace('eDNE_Basico_', '')
            log_aviso(f'Versao detectada pelo nome do arquivo: {versao}')

        dest_dir = CORREIOS_DIR / f'eDNE_Basico_{versao}'

        delimitado_src = extract_dir / 'Delimitado'
        if delimitado_src.exists() and delimitado_src.is_dir():
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            delimitado_dest = dest_dir / 'Delimitado'
            shutil.copytree(delimitado_src, delimitado_dest)

            leiame_src = extract_dir / 'LEIAME.TXT'
            if leiame_src.exists():
                shutil.copy2(leiame_src, dest_dir / 'LEIAME.TXT')
        else:
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            shutil.copytree(extract_dir, dest_dir)

        log_ok(f'DNE extraido para: {dest_dir} (versao {versao})')

    for old_dir in sorted(CORREIOS_DIR.glob('eDNE_Basico_*')):
        if old_dir.name != f'eDNE_Basico_{versao}':
            log_aviso(f'Versao anterior encontrada: {old_dir.name}')
            try:
                shutil.rmtree(old_dir)
                log_info(f'Removido: {old_dir.name}')
            except Exception as e:
                log_aviso(f'Nao foi possivel remover {old_dir.name}: {e}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
