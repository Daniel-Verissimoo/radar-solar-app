"""Teste rapido do servidor e API de mapa."""
import sys, json, time, asyncio, traceback
sys.path.insert(0, '.')

# Importar e testar os componentes sem iniciar o servidor HTTP
# 1. Testar carregamento do GeoJSON
from src.services.geo_service import carregar_geojson_rmr, carregar_mapa_base_json, montar_mapa_json
from src.ui.pages.empresa.mapa import carregar_pjs_mapa

print("1. carregar_geojson_rmr()...")
t0 = time.time()
data = carregar_geojson_rmr()
print(f"   OK ({time.time()-t0:.1f}s) - {len(data['municipios']['features'])} municipios")

print("2. carregar_mapa_base_json()...")
t0 = time.time()
base = carregar_mapa_base_json()
print(f"   OK ({time.time()-t0:.1f}s) - {len(base)} chars")

print("3. carregar_pjs_mapa(data)...")
t0 = time.time()
pjs = carregar_pjs_mapa(data)
print(f"   OK ({time.time()-t0:.1f}s) - {len(pjs)} PJs encontrados")

print("4. montar_mapa_json(pjs=[])...")
t0 = time.time()
result = montar_mapa_json(pjs=pjs)
print(f"   OK ({time.time()-t0:.1f}s) - {len(result)} chars")

print("5. Validar JSON resultante...")
parsed = json.loads(result)
keys = list(parsed.keys())
print(f"   OK - Chaves: {keys}")
print(f"   leads: {len(parsed.get('leads', []))}")
print(f"   pjs: {len(parsed.get('pjs', []))}")
print(f"   municipios: {len(parsed['municipios']['features'])}")

print("\n=== TODOS OS TESTES PASSARAM ===")
