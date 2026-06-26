"""
Consulta coordenadas de CEPs na base banco-ceps (GitHub) e salva cache local.
Uso: uv run python scripts/geocodificar_ceps.py
"""
import asyncio
import json
from pathlib import Path

import httpx
import pandas as pd

ROOT_DIR = Path(r"C:\radar-solar-copia\radar-solar-dev")
PARQUET_PATH = ROOT_DIR / "data" / "data" / "processed" / "aneel" / "rmr_instalacoes.parquet"
CACHE_PATH = ROOT_DIR / "data" / "data" / "processed" / "cep_coords_cache.json"
BASE_URL = "https://raw.githubusercontent.com/gpfconfea/banco-ceps/main/cep"
CONCURRENCY = 20


async def baixar_cep(client: httpx.AsyncClient, cep: str, sem: asyncio.Semaphore) -> dict | None:
    url = f"{BASE_URL}/{cep}.json"
    async with sem:
        try:
            r = await client.get(url, timeout=10)
            if r.status_code != 200:
                return None
            data = r.json()
            lat = data.get("latitude")
            lng = data.get("longitude")
            if lat and lng:
                return {"cep": cep, "latitude": float(lat), "longitude": float(lng), "logradouro": data.get("logradouro", "")}
        except Exception:
            return None
    return None


async def main():
    print("Carregando CEPs do parquet ANEEL...")
    df = pd.read_parquet(PARQUET_PATH, columns=["cep_original", "tipo_consumidor"])
    pj = df[df["tipo_consumidor"] == "PJ"]
    ceps = sorted(pj["cep_original"].dropna().str.replace(r"\D", "", regex=True).unique().tolist())
    print(f"CEPs unicos para consulta: {len(ceps)}")

    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            existente = json.load(f)
    else:
        existente = {}
    ja_tem = set(existente.keys())
    pendentes = [c for c in ceps if c not in ja_tem]
    print(f"Ja em cache: {len(ja_tem)}, Pendentes: {len(pendentes)}")

    if not pendentes:
        print("Nenhum CEP pendente. Cache atualizado.")
        return

    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": "RadarSolar/1.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        tasks = [baixar_cep(client, cep, sem) for cep in pendentes]
        resultados = await asyncio.gather(*tasks)

    novos = 0
    for res in resultados:
        if res:
            existente[res["cep"]] = res
            novos += 1

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(existente, f, ensure_ascii=False, indent=2)
    print(f"Cache salvo: {len(existente)} CEPs ({novos} novos)")
    print(f"Taxa de cobertura: {len(existente)}/{len(ceps)} ({100*len(existente)//len(ceps)}%)")


if __name__ == "__main__":
    asyncio.run(main())
