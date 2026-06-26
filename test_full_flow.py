"""Full integration test that simulates exactly what the browser does."""
import sys, os, json, urllib.request
sys.path.insert(0, r'C:\radar-solar-copia\radar-solar-dev')

# Test 1: Direct DB operations (already works)
print("=== Test 1: Direct DB operations ===")
os.environ['DATABASE_URL'] = 'postgresql://postgres:Ari3vilo99@localhost:5432/radarsolar'
from src.models import Usuario, Lead, LeadLog
from src.database import db

cnpj_test = '88888888000199'
empresa = Usuario.select().where(Usuario.tipo_perfil == 'B2B').first()
print(f"Empresa: id={empresa.id}, nome={empresa.nome}")

try:
    with db.atomic():
        cliente = Usuario.get_or_none(Usuario.cpf_cnpj == cnpj_test)
        if not cliente:
            cliente = Usuario.create(firebase_uid=None, nome='Test', email=cnpj_test + '@test.com', cpf_cnpj=cnpj_test, tipo_perfil='B2C')
        lead = Lead.create(cliente=cliente, empresa_responsavel=empresa, nome_contato='Test', telefone_contato=None, origem='Mapa RMR - Captura de lead', descricao_servico='CNPJ ' + cnpj_test, status='Novo')
        LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=empresa)
        print(f"Lead {lead.id} created successfully")
except Exception as e:
    print(f"Direct DB ERROR: {e}")

# Test 2: HTTP call to the running server (without auth - expect 401)
print("\n=== Test 2: HTTP POST without auth ===")
try:
    req = urllib.request.Request(
        'http://localhost:8080/api/empresa/capturar-lead',
        data=json.dumps({'cnpj': '77777777000199', 'nome': 'Test', 'endereco': 'Rua', 'telefone': ''}).encode(),
        headers={'Content-Type': 'application/json'}
    )
    resp = urllib.request.urlopen(req)
    print(f"Response: {resp.status} - {resp.read().decode()}")
except urllib.error.HTTPError as e:
    print(f"Expected error: {e.code} - {e.read().decode()}")
except urllib.error.URLError as e:
    print(f"Connection error: {e}")

print("\n=== Test 3: Server is running ===")
try:
    resp = urllib.request.urlopen('http://localhost:8080/')
    print(f"Home page: {resp.status}")
except Exception as e:
    print(f"Home page error: {e}")
