import sys, os
sys.path.insert(0, r'C:\radar-solar-copia\radar-solar-dev')
os.environ['DATABASE_URL'] = 'postgresql://postgres:Ari3vilo99@localhost:5432/radarsolar'
from src.database import db
from src.models import Usuario

with db:
    max_id = Usuario.select().order_by(Usuario.id.desc()).first().id
    db.execute_sql("SELECT setval('usuario_id_seq', %s)" % max_id)
    print('Sequence updated to', max_id)

    u = Usuario.create(firebase_uid='test_seq', nome='test', email='test_seq_fix@test.com', tipo_perfil='B2C')
    print('Created temp user id=', u.id)
    u.delete_instance()
    print('Deleted temp user')
