"""
Test script that simulates the exact environment of the API call.
This bypasses the web layer and directly tests the database operations.
"""
import sys, os
sys.path.insert(0, r'C:\radar-solar-copia\radar-solar-dev')
os.environ['DATABASE_URL'] = 'postgresql://postgres:Ari3vilo99@localhost:5432/radarsolar'

from src.models import Usuario, Lead, LeadLog
from src.database import db

# Simulate the EXACT data flow from the API route
# This matches what the browser would send
simulated_auth = {
    'usuario_id': 1,  # First B2B user
    'firebase_uid': '',
    'email': 'hicavat393@dyleris.com',
    'nome': 'hicavat393',
    'profile': 'company',
    'tipo_perfil': 'B2B',
}

# Simulate the request body
body = {
    'cnpj': '00000000000191',  # A valid-looking CNPJ
    'nome': 'EMPRESA TESTE LTDA',
    'endereco': 'RUA DAS FLORES, 100, RECIFE/PE',
    'telefone': '',
}

cnpj = (body.get('cnpj') or '').strip()
nome = (body.get('nome') or 'Cliente do mapa').strip()
endereco = (body.get('endereco') or '').strip()
telefone = (body.get('telefone') or '').strip()

print(f"=== Simulating capture API call ===")
print(f"Auth: usuario_id={simulated_auth['usuario_id']}")
print(f"Body: cnpj={cnpj}, nome={nome}")

try:
    empresa_id = int(simulated_auth['usuario_id'])
    empresa = Usuario.get_by_id(empresa_id)
    print(f"1. Empresa found: id={empresa.id}")

    with db.atomic():
        cliente = Usuario.get_or_none(Usuario.cpf_cnpj == cnpj)
        if not cliente:
            print(f"2. Cliente not found, creating...")
            cliente = Usuario.create(
                firebase_uid=None,
                nome=nome or f'CNPJ {cnpj}',
                email=f'{cnpj}@mapa.radarsolar',
                cpf_cnpj=cnpj,
                tipo_perfil='B2C',
            )
            print(f"3. Cliente created: id={cliente.id}")
        else:
            print(f"2. Cliente exists: id={cliente.id}")

        lead = Lead.create(
            cliente=cliente,
            empresa_responsavel=empresa,
            nome_contato=nome,
            telefone_contato=telefone or None,
            origem='Mapa RMR - Captura de lead',
            descricao_servico=f'CNPJ {cnpj}. {endereco}'.strip(),
            status='Novo',
        )
        print(f"4. Lead created: id={lead.id}")

        LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=empresa)
        print(f"5. LeadLog created")

    print("=== SUCCESS ===")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
