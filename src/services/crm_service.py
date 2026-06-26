# src/services/crm_service.py

from peewee import IntegrityError, DoesNotExist
from src.utils import log_info, log_aviso, log_ok
from src.models import Usuario, EmpresaPerfil, InstalacaoSolar, Fatura, Lead, LeadLog, CnpjCache


def auto_atribuir_lead(lead: Lead) -> None:
    if lead.empresa_responsavel_id:
        return
    instalacao = (
        InstalacaoSolar.select()
        .where(InstalacaoSolar.usuario == lead.cliente_id)
        .first()
    )
    if not instalacao:
        return
    empresa_perfil = (
        EmpresaPerfil.select()
        .where(EmpresaPerfil.estado == instalacao.estado)
        .order_by(EmpresaPerfil.id)
        .first()
    )
    if not empresa_perfil:
        log_aviso(f'Auto-atribuicao: nenhuma empresa em {instalacao.estado} para lead #{lead.id}')
        return
    lead.empresa_responsavel = empresa_perfil.usuario
    lead.save()
    log_ok(f'Auto-atribuicao: lead #{lead.id} -> empresa #{empresa_perfil.usuario_id}')


class CRMService:
    """
    Serviço central de acesso ao Banco de Dados SQLite (Peewee).
    Isola a lógica de negócio e as queries SQL da camada de Interface.
    """
    def __init__(self):
        pass

    # ==========================================
    # MÉTODOS DE USUÁRIO (AUTENTICAÇÃO / BASE)
    # ==========================================

    def obter_usuario_por_uid(self, firebase_uid: str):
        """Busca um usuário pelo ID do Firebase."""
        try:
            return Usuario.get(Usuario.firebase_uid == firebase_uid)
        except DoesNotExist:
            return None
        except Exception as e:
            log_error(f"Erro ao buscar usuário por UID: {e}")
            return None

    def criar_usuario(self, dados_usuario: dict):
        """
        Cria um novo usuário. 
        Espera um dicionário com: firebase_uid, nome, email, cpf_cnpj, telefone, tipo_perfil.
        """
        try:
            novo_usuario = Usuario.create(**dados_usuario)
            log_info(f"Usuário criado com sucesso: {novo_usuario.email}")
            return novo_usuario
        except IntegrityError as e:
            log_error(f"Erro de integridade ao criar usuário (Email ou CPF/CNPJ já existe): {e}")
            return None
        except Exception as e:
            log_error(f"Erro inesperado ao criar usuário: {e}")
            return None

    # ==========================================
    # MÉTODOS DE PERFIL EMPRESA (B2B)
    # ==========================================

    def obter_perfil_empresa(self, usuario_id: int):
        """Busca o perfil corporativo de um usuário B2B."""
        try:
            return EmpresaPerfil.get(EmpresaPerfil.usuario == usuario_id)
        except DoesNotExist:
            return None

    def salvar_perfil_empresa(self, usuario_id: int, dados_perfil: dict):
        """Cria ou atualiza o perfil de uma empresa (Upsert)."""
        try:
            perfil, criado = EmpresaPerfil.get_or_create(
                usuario=usuario_id,
                defaults=dados_perfil
            )
            if not criado:
                # Se já existe, atualiza os dados
                for campo, valor in dados_perfil.items():
                    setattr(perfil, campo, valor)
                perfil.save()
                log_info(f"Perfil da empresa atualizado para o usuário ID {usuario_id}")
            else:
                log_info(f"Novo perfil de empresa criado para o usuário ID {usuario_id}")
            return perfil
        except Exception as e:
            log_error(f"Erro ao salvar perfil da empresa: {e}")
            return None

    # ==========================================
    # MÉTODOS DE INSTALAÇÕES SOLARES
    # ==========================================

    def listar_instalacoes_por_usuario(self, usuario_id: int):
        """Retorna todas as instalações solares vinculadas a um usuário."""
        try:
            return list(InstalacaoSolar.select().where(InstalacaoSolar.usuario == usuario_id))
        except Exception as e:
            log_error(f"Erro ao listar instalações: {e}")
            return []

    def adicionar_instalacao(self, usuario_id: int, dados_instalacao: dict):
        """Vincula uma nova instalação solar a um usuário."""
        try:
            nova_instalacao = InstalacaoSolar.create(usuario=usuario_id, **dados_instalacao)
            log_info(f"Instalação {nova_instalacao.codigo_aneel} adicionada ao usuário ID {usuario_id}")
            return nova_instalacao
        except IntegrityError as e:
            log_error(f"Erro de integridade (Código ANEEL já existe?): {e}")
            return None
        except Exception as e:
            log_error(f"Erro ao adicionar instalação: {e}")
            return None
        
# ==========================================
    # MÉTODOS DE FATURAS (B2C)
    # ==========================================

    def listar_faturas_da_instalacao(self, instalacao_id: int):
        """Lista todas as faturas vinculadas a uma instalação específica."""
        try:
            from src.models import Fatura # Importação local se necessário, ou coloque no topo do arquivo
            return list(Fatura.select().where(Fatura.instalacao == instalacao_id).order_by(Fatura.mes_referencia.desc()))
        except Exception as e:
            log_error(f"Erro ao listar faturas da instalação {instalacao_id}: {e}")
            return []

    def adicionar_fatura(self, dados_fatura: dict):
        """Registra uma nova fatura de energia."""
        try:
            from src.models import Fatura
            nova_fatura = Fatura.create(**dados_fatura)
            log_info(f"Fatura de {nova_fatura.mes_referencia} adicionada com sucesso.")
            return nova_fatura
        except Exception as e:
            log_error(f"Erro ao adicionar fatura: {e}")
            return None

    # ==========================================
    # MÉTODOS DE LEADS / KANBAN (B2B)
    # ==========================================

    def listar_leads_por_empresa(self, empresa_id: int):
        """Busca todos os leads capturados por uma empresa específica (para popular o Kanban)."""
        try:
            from src.models import Lead
            return list(Lead.select().where(Lead.empresa_responsavel == empresa_id))
        except Exception as e:
            log_error(f"Erro ao listar leads da empresa {empresa_id}: {e}")
            return []

    def criar_lead(self, dados_lead: dict):
        """Cria um novo lead de oportunidade de negócio."""
        try:
            from src.models import Lead
            novo_lead = Lead.create(**dados_lead)
            log_info(f"Lead {novo_lead.nome_contato} criado (Status: {novo_lead.status}).")
            return novo_lead
        except Exception as e:
            log_error(f"Erro ao criar lead: {e}")
            return None

    def atualizar_status_lead(self, lead_id: int, novo_status: str):
        """Atualiza a coluna do lead no Kanban (ex: 'Novo' -> 'Em Negociação')."""
        try:
            from src.models import Lead
            lead = Lead.get_by_id(lead_id)
            lead.status = novo_status
            lead.save()
            log_info(f"Status do Lead ID {lead_id} atualizado para {novo_status}.")
            return lead
        except DoesNotExist:
            log_error(f"Lead ID {lead_id} não encontrado para atualização.")
            return None
        except Exception as e:
            log_error(f"Erro ao atualizar status do lead: {e}")
            return None

    # ==========================================
    # MÉTODOS DE CACHE DE CNPJ
    # ==========================================

    def obter_cnpj_em_cache(self, cnpj: str):
        """Verifica se os dados de um CNPJ já foram buscados e salvos localmente."""
        try:
            from src.models import CnpjCache
            return CnpjCache.get(CnpjCache.cnpj == cnpj)
        except DoesNotExist:
            return None

    def salvar_cnpj_cache(self, dados_cnpj: dict):
        """Salva o resultado de uma busca de CNPJ na API para evitar novas requisições."""
        try:
            from src.models import CnpjCache
            cache, criado = CnpjCache.get_or_create(
                cnpj=dados_cnpj.get('cnpj'),
                defaults=dados_cnpj
            )
            if criado:
                log_info(f"CNPJ {cache.cnpj} salvo em cache com sucesso.")
            return cache
        except IntegrityError:
             # Se der erro de integridade, pode ser concorrência, retornamos o existente
             from src.models import CnpjCache
             return CnpjCache.get(CnpjCache.cnpj == dados_cnpj.get('cnpj'))
        except Exception as e:
            log_error(f"Erro ao salvar CNPJ em cache: {e}")
            return None