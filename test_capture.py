"""Test script to diagnose capture-lead endpoint issues."""
import sys, os
sys.path.insert(0, r'C:\radar-solar-copia\radar-solar-dev')

os.environ['DATABASE_URL'] = 'postgresql://postgres:Ari3vilo99@localhost:5432/radarsolar'

from src.models import Usuario, Lead, LeadLog
from src.database import db

cnpj = '12345678000199'

# 1. Find any empresa user
empresa = Usuario.select().where(Usuario.tipo_perfil == 'EMPRESA').first()
if not empresa:
    empresa = Usuario.select().where(Usuario.tipo_perfil == 'B2B').first()
print(f"Empresa user: id={empresa.id}, nome={empresa.nome}, email={empresa.email}, tipo_perfil={empresa.tipo_perfil}")

# 2. Check existing lead
existing = Lead.select().where(
    Lead.empresa_responsavel == empresa.id,
    Lead.origem == 'Mapa RMR - Captura de lead',
    Lead.descricao_servico ** f'%{cnpj}%',
).first()
print(f"Existing lead: {existing}")

# 3. Try to create a lead
try:
    with db.atomic():
        cliente = Usuario.get_or_none(Usuario.cpf_cnpj == cnpj)
        if not cliente:
            cliente = Usuario.create(
                firebase_uid=None,
                nome='Teste CNPJ',
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
            nome_contato='Teste Nome',
            telefone_contato=None,
            origem='Mapa RMR - Captura de lead',
            descricao_servico=f'CNPJ {cnpj}. Teste endereco',
            status='Novo',
        )
        print(f"Lead created: id={lead.id}")
        LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=empresa)
        print("LeadLog created")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

# 4. Cleanup - delete the test lead and client
try:
    if 'lead' in dir():
        LeadLog.delete().where(LeadLog.lead == lead).execute()
        lead.delete_instance()
    if 'cliente' in dir() and not Usuario.select().where(Usuario.cpf_cnpj == cnpj).where(Usuario.tipo_perfil == 'B2C').count() > 1:
        pass  # Keep the client for now
except:
    pass
