import os
from datetime import datetime

from peewee import Model, CharField, FloatField, ForeignKeyField, DateTimeField, IntegerField, DateField

from src.database import db
from src.utils import log_info, log_ok, log_aviso


class BaseModel(Model):
    criado_em = DateTimeField(default=datetime.now)
    atualizado_em = DateTimeField(default=datetime.now)

    def save(self, *args, **kwargs):
        self.atualizado_em = datetime.now()
        return super().save(*args, **kwargs)

    class Meta:
        database = db


class Usuario(BaseModel):
    firebase_uid = CharField(unique=True, null=True)
    nome = CharField()
    email = CharField(unique=True)
    cpf_cnpj = CharField(unique=True, null=True)
    telefone = CharField(null=True)
    tipo_perfil = CharField()


class EmpresaPerfil(BaseModel):
    usuario = ForeignKeyField(Usuario, backref='perfil_empresa', unique=True, on_delete='CASCADE')
    nome_fantasia = CharField(null=True)
    email_comercial = CharField(null=True)
    cep = CharField(null=True)
    logradouro = CharField(null=True)
    numero = CharField(null=True)
    complemento = CharField(null=True)
    cidade = CharField(null=True)
    estado = CharField(max_length=2, null=True)
    regiao_atendimento = CharField(null=True)


class InstalacaoSolar(BaseModel):
    usuario = ForeignKeyField(Usuario, backref='instalacoes', on_delete='CASCADE')
    codigo_aneel = CharField(unique=True, null=True)
    conta_contrato_celpe = CharField(null=True)
    concessionaria = CharField(null=True)
    classe_consumo = CharField(null=True)
    subgrupo_tarifario = CharField(null=True)
    modalidade_geracao = CharField(null=True)
    qtd_ucs_recebem_credito = IntegerField(null=True)
    potencia_instalada_kwp = FloatField(null=True)
    potencia_modulos_kw = FloatField(null=True)
    potencia_inversores_kw = FloatField(null=True)
    qtd_modulos = IntegerField(null=True)
    area_arranjo_m2 = FloatField(null=True)
    fabricante_modulo = CharField(null=True)
    modelo_modulo = CharField(null=True)
    fabricante_inversor = CharField(null=True)
    modelo_inversor = CharField(null=True)
    data_conexao = DateField(null=True)
    cep = CharField()
    logradouro = CharField()
    numero = CharField()
    complemento = CharField(null=True)
    cidade = CharField()
    estado = CharField(max_length=2)
    latitude = FloatField(null=True)
    longitude = FloatField(null=True)


class Fatura(BaseModel):
    instalacao = ForeignKeyField(InstalacaoSolar, backref='faturas', on_delete='CASCADE')
    mes_referencia = CharField()
    consumo_kwh = FloatField()
    injecao_kwh = FloatField(null=True)
    creditos_utilizados = FloatField(null=True)
    saldo_creditos = FloatField(null=True)
    valor_fatura_rs = FloatField()
    geracao_app_kwh = FloatField(null=True)


class Lead(BaseModel):
    cliente = ForeignKeyField(Usuario, backref='leads_gerados', null=True, on_delete='SET NULL')
    empresa_responsavel = ForeignKeyField(Usuario, backref='leads_capturados', null=True, on_delete='SET NULL')
    nome_contato = CharField()
    telefone_contato = CharField(null=True)
    origem = CharField()
    descricao_servico = CharField(null=True)
    valor_estimado_rs = FloatField(null=True)
    status = CharField(default='Novo')


class LeadLog(BaseModel):
    lead = ForeignKeyField(Lead, backref='logs', on_delete='CASCADE')
    de_status = CharField(null=True)
    para_status = CharField()
    alterado_por = ForeignKeyField(Usuario, null=True, on_delete='SET NULL')


class CnpjCache(BaseModel):
    cnpj = CharField(unique=True)
    razao_social = CharField(null=True)
    nome_fantasia = CharField(null=True)
    logradouro = CharField(null=True)
    numero = CharField(null=True)
    complemento = CharField(null=True)
    cep = CharField(null=True)
    bairro = CharField(null=True)
    cidade = CharField(null=True)
    estado = CharField(max_length=2, null=True)
    telefone1 = CharField(null=True)
    telefone2 = CharField(null=True)
    email = CharField(null=True)
    latitude = FloatField(null=True)
    longitude = FloatField(null=True)
    fetched_at = DateTimeField(default=datetime.now)


def _is_postgres() -> bool:
    return bool(os.getenv('DATABASE_URL', ''))


def _table_exists(table_name: str) -> bool:
    if _is_postgres():
        sql = "SELECT tablename FROM pg_catalog.pg_tables WHERE tablename = %s"
    else:
        sql = "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?"
    row = db.execute_sql(sql, (table_name,)).fetchone()
    return row is not None


def _coluna_nullable(coluna: str, tabela: str) -> bool:
    if _is_postgres():
        row = db.execute_sql(
            "SELECT is_nullable FROM information_schema.columns WHERE table_name = %s AND column_name = %s",
            (tabela, coluna),
        ).fetchone()
        return row is not None and row[0] == 'YES'
    else:
        colunas = list(db.execute_sql(f"PRAGMA table_info('{tabela}')"))
        match = next((c for c in colunas if c[1] == coluna), None)
        return match is not None and match[3] == 0


def criar_tabelas() -> None:
    with db:
        db.create_tables([Usuario, EmpresaPerfil, InstalacaoSolar, Fatura, Lead, LeadLog, CnpjCache])
        log_ok('Tabelas criadas/verificadas: Usuario, EmpresaPerfil, InstalacaoSolar, Fatura, Lead, LeadLog, CnpjCache')
        migrar_lead_empresa_responsavel_nullable()


def migrar_lead_empresa_responsavel_nullable() -> None:
    if not _table_exists('lead'):
        return
    if _coluna_nullable('empresa_responsavel_id', 'lead'):
        return

    tabela_antiga = 'lead_old_empresa_not_null'
    if _table_exists(tabela_antiga):
        raise RuntimeError(f'Migracao interrompida: tabela temporaria {tabela_antiga!r} ja existe.')

    log_info('Migracao: tornando empresa_responsavel_id nullable na tabela Lead...')
    with db.atomic():
        db.execute_sql(f'ALTER TABLE lead RENAME TO {tabela_antiga}')
        db.create_tables([Lead])
        db.execute_sql('''
            INSERT INTO lead (
                id, criado_em, atualizado_em, cliente_id, empresa_responsavel_id,
                nome_contato, telefone_contato, origem, descricao_servico,
                valor_estimado_rs, status
            ) SELECT
                id, criado_em, atualizado_em, cliente_id, empresa_responsavel_id,
                nome_contato, telefone_contato, origem, descricao_servico,
                valor_estimado_rs, status
            FROM lead_old_empresa_not_null
        ''')
        db.execute_sql(f'DROP TABLE {tabela_antiga}')
        log_ok('Migracao de Lead concluida: empresa_responsavel_id agora aceita NULL')
