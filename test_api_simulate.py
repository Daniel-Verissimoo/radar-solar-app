"""Simulate exactly what the browser sends to the capture-lead API."""
import sys, os, json
sys.path.insert(0, r'C:\radar-solar-copia\radar-solar-dev')
os.environ['DATABASE_URL'] = 'postgresql://postgres:Ari3vilo99@localhost:5432/radarsolar'

from src.models import Usuario, Lead, LeadLog
from src.database import db

# Simulate auth dict that would come from app.storage.user
auth = {
    'usuario_id': 1,
    'firebase_uid': '',
    'email': 'hicavat393@dyleris.com',
    'nome': 'hicavat393',
    'profile': 'company',
    'tipo_perfil': 'B2B',
}

cnpj = '99999999000199'
nome = 'Teste Simulado'
endereco = 'RECIFE/PE'
telefone = ''

print(f"Auth: usuario_id={auth['usuario_id']}, profile={auth['profile']}")
print(f"Body: cnpj={cnpj}, nome={nome}, endereco={endereco}")

try:
    empresa_id = int(auth['usuario_id'])
    empresa = Usuario.get_by_id(empresa_id)
    print(f"Empresa found: id={empresa.id}, nome={empresa.nome}")

    existing = Lead.select().where(
        Lead.empresa_responsavel == empresa_id,
        Lead.origem == 'Mapa RMR - Captura de lead',
        Lead.descricao_servico ** f'%{cnpj}%',
    ).first()
    print(f"Existing lead: {existing}")

    with db.atomic():
        cliente = Usuario.get_or_none(Usuario.cpf_cnpj == cnpj)
        if not cliente:
            cliente = Usuario.create(
                firebase_uid=None,
                nome=nome or f'CNPJ {cnpj}',
                email=f'{cnpj}@mapa.radarsolar',
                cpf_cnpj=cnpj,
                tipo_perfil='B2C',
            )
            print(f"Cliente created: id={cliente.id}")
        else:
            print(f"Cliente exists: id={cliente.id}")
        lead = Lead.create(
            cliente=cliente,
            empresa_responsavel=empresa,
            nome_contato=nome,
            telefone_contato=telefone or None,
            origem='Mapa RMR - Captura de lead',
            descricao_servico=f'CNPJ {cnpj}. {endereco}'.strip(),
            status='Novo',
        )
        print(f"Lead created: id={lead.id}")
        LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=empresa)
        print("LeadLog created")

    print("SUCCESS: Full flow works!")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
