import html
import re
import time
from collections.abc import Callable

from nicegui import ui

from src.auth import PerfilConflitanteError, validar_email_para_profile
from src.database import db
from src.models import CnpjCache, EmpresaPerfil, InstalacaoSolar, Lead, LeadLog, Usuario
from src.services.aneel_service import obter_instalacao_por_cnpj
from src.utils import _format_datetime_br, log_info, log_dados, log_ok, log_aviso


STATUS_KANBAN = ['Novo', 'Em Contato', 'Concluído']
STALE_DAYS = 7


def _obter_cnpj_lead(lead: Lead) -> str | None:
    if lead.cliente and lead.cliente.cpf_cnpj:
        cnpj = ''.join(ch for ch in lead.cliente.cpf_cnpj if ch.isdigit())
        if len(cnpj) == 14:
            return cnpj
    return None


def _obter_instalacao_cliente(lead: Lead) -> InstalacaoSolar | dict | None:
    if lead.cliente_id:
        inst = InstalacaoSolar.select().where(InstalacaoSolar.usuario == lead.cliente_id).first()
        if inst:
            return inst
    cpf_cnpj = lead.cliente.cpf_cnpj if lead.cliente else None
    if cpf_cnpj:
        inst = InstalacaoSolar.select().join(Usuario).where(Usuario.cpf_cnpj == cpf_cnpj).first()
        if inst:
            return inst
        cnpj_digits = ''.join(ch for ch in cpf_cnpj if ch.isdigit())
        aneel = obter_instalacao_por_cnpj(cnpj_digits)
        if aneel:
            return aneel[0]
    return None


def _obter_contato_lead(lead: Lead) -> dict | None:
    if not lead.cliente or not lead.cliente.cpf_cnpj:
        return None
    cnpj = ''.join(ch for ch in lead.cliente.cpf_cnpj if ch.isdigit())
    if len(cnpj) != 14:
        return None
    cache = CnpjCache.get_or_none(CnpjCache.cnpj == cnpj)
    if not cache:
        return None
    result = {}
    if cache.telefone1:
        result['telefone1'] = cache.telefone1
    if cache.telefone2:
        result['telefone2'] = cache.telefone2
    if cache.email:
        result['email'] = cache.email
    return result if result else None


def _obter_contato_instalacao(instalacao: InstalacaoSolar) -> dict | None:
    if not instalacao.usuario_id:
        return None
    cliente = Usuario.get_or_none(Usuario.id == instalacao.usuario_id)
    if not cliente or not cliente.cpf_cnpj:
        return None
    cnpj = ''.join(ch for ch in cliente.cpf_cnpj if ch.isdigit())
    if len(cnpj) != 14:
        return None
    cache = CnpjCache.get_or_none(CnpjCache.cnpj == cnpj)
    if not cache:
        return None
    result = {}
    if cache.telefone1:
        result['telefone1'] = cache.telefone1
    if cache.telefone2:
        result['telefone2'] = cache.telefone2
    if cache.email:
        result['email'] = cache.email
    return result if result else None


def _auto_atribuir_lead(lead: Lead) -> None:
    if lead.empresa_responsavel_id:
        return
    instalacao = _obter_instalacao_cliente(lead)
    if not instalacao:
        return
    empresas = (
        EmpresaPerfil.select()
        .where(EmpresaPerfil.estado == instalacao.estado)
        .order_by(EmpresaPerfil.id)
    )
    if not empresas:
        log_aviso(f'Auto-atribuicao: nenhuma empresa encontrada em {instalacao.estado} para lead #{lead.id}')
        return
    lead.empresa_responsavel = empresas[0].usuario
    lead.save()
    log_ok(f'Auto-atribuicao: lead #{lead.id} -> empresa #{empresas[0].usuario_id}')


def _registrar_log(lead: Lead, de_status: str | None, para_status: str, alterado_por_id: int | None = None) -> None:
    LeadLog.create(
        lead=lead,
        de_status=de_status,
        para_status=para_status,
        alterado_por_id=alterado_por_id,
    )


def _obter_leads_por_status(empresa_id: int) -> dict[str, list[Lead]]:
    leads_por_status = {status: [] for status in STATUS_KANBAN}
    leads = (
        Lead.select()
        .where(
            (Lead.status.in_(STATUS_KANBAN))
            & ((Lead.empresa_responsavel.is_null(True)) | (Lead.empresa_responsavel == empresa_id))
        )
        .order_by(Lead.criado_em.desc())
    )
    for lead in leads:
        leads_por_status.setdefault(lead.status, []).append(lead)
    total = sum(len(v) for v in leads_por_status.values())
    log_dados(f'Kanban B2B: leads carregados para empresa {empresa_id}', total)
    return leads_por_status


def _mudar_status(lead: Lead, novo_status: str, alterado_por_id: int | None = None) -> None:
    if novo_status not in STATUS_KANBAN:
        raise ValueError('Status invalido para o Kanban.')
    de_status = lead.status
    lead.status = novo_status
    lead.save()
    _registrar_log(lead, de_status, novo_status, alterado_por_id)
    log_ok(f'Kanban: lead #{lead.id} movido de {de_status} para {novo_status}')


def _dias_no_status(lead: Lead) -> int:
    ultimo_log = (
        LeadLog.select()
        .where((LeadLog.lead == lead) & (LeadLog.para_status == lead.status))
        .order_by(LeadLog.criado_em.desc())
        .first()
    )
    if ultimo_log:
        ref = ultimo_log.criado_em
    else:
        ref = lead.criado_em
    delta = time.time() - ref.timestamp()
    return int(delta // 86400)


def _obter_ou_criar_cliente_b2c(email: str, nome: str, telefone: str | None) -> tuple[Usuario, bool]:
    email = validar_email_para_profile(email, 'customer')
    usuario = Usuario.get_or_none(Usuario.email == email)
    if usuario:
        atualizado = False
        if nome and usuario.nome != nome:
            usuario.nome = nome
            atualizado = True
        if telefone and not usuario.telefone:
            usuario.telefone = telefone
            atualizado = True
        if atualizado:
            usuario.save()
        return usuario, False

    usuario = Usuario.create(
        firebase_uid=None,
        nome=nome or email.split('@', 1)[0],
        email=email,
        telefone=telefone,
        tipo_perfil='B2C',
    )
    return usuario, True


def _criar_lead_manual(
    empresa_id: int,
    email: str,
    nome: str,
    telefone: str | None,
    descricao: str | None,
) -> tuple[Lead, bool]:
    empresa = Usuario.get_by_id(empresa_id)
    with db.atomic():
        cliente, criado = _obter_ou_criar_cliente_b2c(email, nome, telefone)
        lead = Lead.create(
            cliente=cliente,
            empresa_responsavel=empresa,
            nome_contato=nome or cliente.nome,
            telefone_contato=telefone or cliente.telefone,
            origem='Kanban B2B - Lead manual',
            descricao_servico=descricao or 'Lead cadastrado manualmente pelo integrador.',
            status='Novo',
        )
    _registrar_log(lead, None, 'Novo', empresa_id)
    log_ok(f'Kanban: lead manual #{lead.id} criado (cliente: {email}, empresa: {empresa_id})')
    return lead, criado


def _render_formulario_lead(empresa_id: int, on_created: Callable[[], None]) -> None:
    with ui.card().classes('w-full rounded-2xl border border-slate-200 bg-white p-5 gap-4'):
        ui.label('Adicionar lead').classes('text-lg font-bold text-slate-900')
        ui.label(
            'Informe o e-mail do cliente. Se ele ainda nao existir, criaremos uma conta B2C para manter o vinculo.'
        ).classes('text-sm text-slate-600')

        with ui.row().classes('w-full gap-3 items-start max-[900px]:flex-col'):
            lead_email = ui.input('E-mail do cliente *').props('outlined maxlength="100"').classes('flex-1 min-w-64')
            lead_nome = ui.input('Nome do contato').props('outlined maxlength="100"').classes('flex-1 min-w-64')
            lead_telefone = ui.input('Telefone').props('outlined maxlength="20"').classes('w-56 max-[900px]:w-full')

        lead_descricao = ui.textarea('Descricao / necessidade').props('outlined autogrow maxlength="1000"').classes('w-full')

        def adicionar_lead() -> None:
            raw_email = str(lead_email.value or '').strip()
            raw_nome = str(lead_nome.value or '').strip()
            raw_telefone = str(lead_telefone.value or '').strip()
            raw_descricao = str(lead_descricao.value or '').strip()

            if not raw_email:
                ui.notify('Informe o e-mail do cliente.', color='warning')
                return

            if not re.match(r"[^@]+@[^@]+\.[^@]+", raw_email):
                ui.notify('O formato do e-mail é inválido.', color='negative')
                return

            email_seguro = html.escape(raw_email)
            nome_seguro = html.escape(raw_nome) if raw_nome else ''
            telefone_seguro = html.escape(raw_telefone) if raw_telefone else None
            descricao_segura = html.escape(raw_descricao) if raw_descricao else None

            if len(email_seguro) > 100 or len(nome_seguro) > 100 or (telefone_seguro and len(telefone_seguro) > 20):
                ui.notify('Limite de caracteres excedido.', color='negative')
                return

            try:
                lead, cliente_criado = _criar_lead_manual(
                    empresa_id, email_seguro, nome_seguro, telefone_seguro, descricao_segura
                )
            except PerfilConflitanteError as exc:
                ui.notify(str(exc), color='negative')
                return
            except Exception as exc:
                ui.notify(f'Nao foi possivel criar o lead: {exc}', color='negative')
                return

            ui.notify(f'Lead de {lead.nome_contato} adicionado ao Kanban.', color='positive')

            lead_email.value = ''
            lead_nome.value = ''
            lead_telefone.value = ''
            lead_descricao.value = ''

            on_created()

        ui.button('Adicionar lead', on_click=adicionar_lead).props('color=primary').classes('rounded-xl self-start')


def _render_resumo_kanban(leads_por_status: dict[str, list[Lead]]) -> int:
    total_leads = sum(len(leads) for leads in leads_por_status.values())
    with ui.row().classes('w-full gap-4 max-[900px]:flex-col'):
        with ui.card().classes('flex-1 p-5 rounded-2xl'):
            ui.label('Leads ativos').classes('text-sm text-slate-500')
            ui.label(str(total_leads)).classes('text-3xl font-bold text-slate-900')
        for status in STATUS_KANBAN:
            with ui.card().classes('flex-1 p-5 rounded-2xl'):
                ui.label(status).classes('text-sm text-slate-500')
                ui.label(str(len(leads_por_status[status]))).classes('text-3xl font-bold text-slate-900')
    return total_leads


def _render_empty_state() -> None:
    with ui.card().classes('w-full p-6 rounded-2xl border border-slate-200 bg-slate-50'):
        ui.label('Nenhum lead ativo no momento.').classes('text-lg font-semibold text-slate-900')
        ui.label(
            'Quando um cliente solicitar contato pelo Dashboard B2C, a oportunidade aparecera aqui.'
        ).classes('text-sm text-slate-600')


def _lead_localizacao(lead: Lead) -> str:
    instalacao = _obter_instalacao_cliente(lead)
    if not instalacao:
        return '-'
    cidade_uf = ' / '.join(part for part in [instalacao.cidade, instalacao.estado] if part)
    return cidade_uf or instalacao.cep or '-'


def _deletar_lead(lead: Lead, empresa_id: int) -> None:
    LeadLog.delete().where(LeadLog.lead == lead).execute()
    lead.delete_instance()
    log_ok(f'Kanban: lead #{lead.id} excluido pela empresa #{empresa_id}')


_ORIGEM_CONFIG = {
    'Mapa RMR - Captura de lead': ('purple', 'Mapa'),
    'Kanban B2B - Lead manual': ('blue', 'Manual'),
    'Dashboard B2C': ('green', 'Site'),
}


def _origem_badge(origem: str) -> None:
    cor, rotulo = _ORIGEM_CONFIG.get(origem, ('gray', origem[:12]))
    cor_map = {
        'purple': ('bg-purple-100', 'text-purple-800'),
        'blue': ('bg-blue-100', 'text-blue-800'),
        'green': ('bg-green-100', 'text-green-800'),
        'gray': ('bg-gray-100', 'text-gray-800'),
    }
    bg, tx = cor_map.get(cor, ('bg-gray-100', 'text-gray-800'))
    ui.label(rotulo).classes(f'text-xs font-semibold {bg} {tx} px-2 py-0.5 rounded-md')


def _get(inst, field, default=''):
    if inst is None:
        return default
    if isinstance(inst, dict):
        return inst.get(field, default)
    return getattr(inst, field, default) or default


def _render_instalacao_dialog(lead: Lead) -> ui.dialog | None:
    instalacao = _obter_instalacao_cliente(lead)
    if not instalacao:
        return None
    cnpj = _obter_cnpj_lead(lead)
    is_dict = isinstance(instalacao, dict)
    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4 min-w-[400px] max-w-[600px]'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Instalacao').classes('text-xl font-bold')
            ui.button(icon='close', on_click=dialog.close).props('flat dense')
        ui.separator()
        with ui.column().classes('w-full gap-2 text-sm'):
            classe = _get(instalacao, 'classe_consumo' if not is_dict else 'classe')
            if classe:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Classe:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(classe)
            if is_dict:
                subgrupo = instalacao.get('tipo', '')
            else:
                subgrupo = _get(instalacao, 'subgrupo_tarifario')
            if subgrupo:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Subgrupo:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(subgrupo)
            if is_dict:
                potencia = instalacao.get('potencia_kw', 0)
            else:
                potencia = _get(instalacao, 'potencia_instalada_kwp', 0)
            if potencia:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Potencia:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(f'{potencia} kWp')
            qtd = _get(instalacao, 'qtd_modulos', 0) if not is_dict else instalacao.get('qtd_modulos', 0)
            if qtd:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Modulos:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(str(qtd))
            fab_mod = _get(instalacao, 'fabricante_modulo') if not is_dict else instalacao.get('fabricante_modulo', '')
            if fab_mod:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Fab. Modulo:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(fab_mod)
            fab_inv = _get(instalacao, 'fabricante_inversor') if not is_dict else instalacao.get('fabricante_inversor', '')
            if fab_inv:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Fab. Inversor:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(fab_inv)
            if is_dict:
                conexao = instalacao.get('data_conexao', '')
            else:
                conexao = instalacao.data_conexao.strftime('%d/%m/%Y') if instalacao.data_conexao else ''
            if conexao:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Conexao:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(conexao)
            cod_aneel = _get(instalacao, 'codigo_aneel') if not is_dict else instalacao.get('codigo', '')
            if cod_aneel:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Cod. ANEEL:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(cod_aneel)
            if is_dict:
                if instalacao.get('municipio'):
                    with ui.row().classes('w-full gap-2'):
                        ui.label('Municipio:').classes('font-semibold text-slate-500 min-w-20')
                        ui.label(instalacao['municipio'])
                if instalacao.get('bairro'):
                    with ui.row().classes('w-full gap-2'):
                        ui.label('Bairro:').classes('font-semibold text-slate-500 min-w-20')
                        ui.label(instalacao['bairro'])
            else:
                modalidade = _get(instalacao, 'modalidade_geracao')
                if modalidade:
                    with ui.row().classes('w-full gap-2'):
                        ui.label('Modalidade:').classes('font-semibold text-slate-500 min-w-20')
                        ui.label(modalidade)

        ui.separator()
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Contato').classes('text-base font-bold')
            if cnpj and len(cnpj) == 14:
                ui.button('Editar contato', icon='edit', on_click=lambda c=cnpj, d=dialog: _abrir_edicao_contato(c, d)).props('flat dense text-primary')
        with ui.column().classes('w-full gap-2 text-sm'):
            cache_contato = None
            if cnpj:
                cache = CnpjCache.get_or_none(CnpjCache.cnpj == cnpj)
                if cache:
                    cache_contato = {
                        'telefone1': cache.telefone1 or '',
                        'telefone2': cache.telefone2 or '',
                        'email': cache.email or '',
                    }
            tel1 = (cache_contato or {}).get('telefone1', '')
            tel2 = (cache_contato or {}).get('telefone2', '')
            email = (cache_contato or {}).get('email', '')
            with ui.row().classes('w-full gap-2'):
                ui.label('Telefone:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(tel1 if tel1 else '-').classes('rs-contato-tel1')
            with ui.row().classes('w-full gap-2'):
                ui.label('Tel. 2:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(tel2 if tel2 else '-').classes('rs-contato-tel2')
            with ui.row().classes('w-full gap-2'):
                ui.label('E-mail:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(email if email else '-').classes('rs-contato-email')
    return dialog


def _abrir_edicao_contato(cnpj: str, parent_dialog: ui.dialog | None = None) -> None:
    cache = CnpjCache.get_or_none(CnpjCache.cnpj == cnpj)
    if not cache:
        ui.notify('CNPJ nao encontrado', type='warning')
        return
    with ui.dialog() as edit_dialog, ui.card().classes('p-6 gap-4 min-w-[350px]'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label('Editar contato').classes('text-lg font-bold')
            ui.button(icon='close', on_click=edit_dialog.close).props('flat dense')
        ui.separator()
        tel1_input = ui.input('Telefone 1', value=cache.telefone1 or '').classes('w-full')
        tel2_input = ui.input('Telefone 2', value=cache.telefone2 or '').classes('w-full')
        email_input = ui.input('E-mail', value=cache.email or '').classes('w-full')
        with ui.row().classes('w-full justify-end gap-2'):
            ui.button('Cancelar', on_click=edit_dialog.close).props('flat')
            def _salvar():
                v1 = tel1_input.value.strip() or None
                v2 = tel2_input.value.strip() or None
                ve = email_input.value.strip() or None
                cache.telefone1 = v1
                cache.telefone2 = v2
                cache.email = ve
                cache.save()
                ui.notify('Contato atualizado!', type='positive')
                edit_dialog.close()
                if parent_dialog:
                    parent_dialog.close()
            ui.button('Salvar', on_click=_salvar).props('color=primary')
        edit_dialog.open()


def _render_detalhes_dialog(lead: Lead):
    with ui.dialog() as dialog, ui.card().classes('p-6 gap-4 min-w-[400px] max-w-[600px]'):
        with ui.row().classes('w-full items-center justify-between'):
            ui.label(lead.nome_contato).classes('text-xl font-bold')
            ui.button(icon='close', on_click=dialog.close).props('flat dense')

        ui.separator()

        with ui.column().classes('w-full gap-2 text-sm'):
            with ui.row().classes('w-full gap-2'):
                ui.label('Nome:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(lead.nome_contato)
            with ui.row().classes('w-full gap-2'):
                ui.label('Origem:').classes('font-semibold text-slate-500 min-w-20')
                _origem_badge(lead.origem)
            with ui.row().classes('w-full gap-2'):
                ui.label('Tel.:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(lead.telefone_contato or '-')
            if lead.cliente and lead.cliente.cpf_cnpj:
                cpf_cnpj = lead.cliente.cpf_cnpj
                tipo = 'PJ' if len(cpf_cnpj) == 14 else 'PF' if len(cpf_cnpj) == 11 else ''
                with ui.row().classes('w-full gap-2'):
                    ui.label('CPF/CNPJ:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(f'{cpf_cnpj} ({tipo})' if tipo else cpf_cnpj)
            with ui.row().classes('w-full gap-2'):
                ui.label('Local:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(_lead_localizacao(lead))
            with ui.row().classes('w-full gap-2'):
                ui.label('Criado:').classes('font-semibold text-slate-500 min-w-20')
                ui.label(_format_datetime_br(lead.criado_em))
            if lead.descricao_servico:
                with ui.row().classes('w-full gap-2'):
                    ui.label('Descricao:').classes('font-semibold text-slate-500 min-w-20')
                    ui.label(lead.descricao_servico)

        ui.separator()
        ui.label('Historico').classes('text-base font-bold')

        logs = LeadLog.select().where(LeadLog.lead == lead).order_by(LeadLog.criado_em.desc()).limit(20)
        if logs:
            with ui.column().classes('w-full gap-1 max-h-[200px] overflow-y-auto'):
                for log_entry in logs:
                    de = log_entry.de_status or '(criacao)'
                    para = log_entry.para_status
                    data = _format_datetime_br(log_entry.criado_em)
                    quem = f'#{log_entry.alterado_por_id}' if log_entry.alterado_por_id else 'sistema'
                    ui.label(f'{data} - {de} -> {para} (por {quem})').classes('text-xs text-slate-600')
        else:
            ui.label('Nenhum registro de movimentacao.').classes('text-sm text-slate-400')

    return dialog


def _render_lead_card(lead: Lead, status: str, mover_lead: Callable[[Lead, str], None], on_delete: Callable[[Lead], None] | None = None) -> None:
    dias_no_status = _dias_no_status(lead)
    is_stale = dias_no_status >= STALE_DAYS

    card_class = 'w-full rounded-xl bg-white border overflow-hidden'
    if is_stale:
        card_class += ' border-amber-300'
    else:
        card_class += ' border-slate-200'

    contato_cache = _obter_contato_lead(lead)

    with ui.card().classes(card_class).tight():
        with ui.row().classes('w-full items-center justify-between gap-1 px-4 pt-3 pb-1'):
            with ui.row().classes('items-center gap-2 min-w-0'):
                ui.label(lead.nome_contato).classes('text-base font-semibold text-slate-900')

        with ui.column().classes('w-full gap-0.5 px-4 pb-1.5 text-sm'):
            with ui.row().classes('items-center gap-1'):
                ui.label('Origem:').classes('text-slate-400')
                _origem_badge(lead.origem)
            if contato_cache:
                if contato_cache.get('telefone1'):
                    ui.label(f'Tel: {contato_cache["telefone1"]}').classes('text-slate-600')
                if contato_cache.get('email'):
                    ui.label(contato_cache['email']).classes('text-slate-600')

        with ui.row().classes('w-full gap-2 px-4 pb-2'):
            if lead.cliente and lead.cliente.cpf_cnpj:
                cpf_cnpj = lead.cliente.cpf_cnpj
                tipo = 'PJ' if len(cpf_cnpj) == 14 else 'PF' if len(cpf_cnpj) == 11 else ''
                label = f'{cpf_cnpj} ({tipo})' if tipo else cpf_cnpj
                ui.label(label).classes('text-sm font-mono text-slate-500')
            days_label = f'{dias_no_status}d neste status'
            if is_stale:
                days_label += ' ⚠'
            ui.label(days_label).classes(
                'text-sm' + (' text-amber-600 font-medium' if is_stale else ' text-slate-400')
            )

        with ui.grid(columns=2).classes('w-full gap-x-4 gap-y-1 px-4 pb-2'):
            ui.label(_lead_localizacao(lead)).classes('text-slate-700')
            if lead.telefone_contato:
                ui.label(f'📞 {lead.telefone_contato}').classes('text-slate-700')

        if lead.descricao_servico:
            ui.label(lead.descricao_servico).classes('text-sm text-slate-600 px-4 pb-2 leading-5')

        with ui.row().classes('w-full gap-1 px-3 pb-3 flex-wrap'):
            for destino in STATUS_KANBAN:
                if destino == status: continue
                mov_icon = {'Novo': 'fiber_new', 'Em Contato': 'arrow_forward', 'Concluído': 'task_alt'}[destino]
                mov_cor = 'primary' if destino != 'Concluído' else 'positive'
                ui.button(icon=mov_icon, on_click=lambda l=lead, d=destino: mover_lead(l, d)
                ).props(f'flat round color={mov_cor} size=sm').tooltip(f'Mover para {destino}')
            detalhes_dialog = _render_detalhes_dialog(lead)
            ui.button(icon='search', on_click=detalhes_dialog.open
            ).props('flat round color=accent size=sm').tooltip('Detalhes')
            instalacao_dialog = _render_instalacao_dialog(lead)
            if instalacao_dialog:
                ui.button(icon='solar_power', on_click=instalacao_dialog.open
                ).props('flat round color=info size=sm').tooltip('Instalacao')
            cnpj_card = _obter_cnpj_lead(lead)
            if cnpj_card and len(cnpj_card) == 14:
                ui.button(icon='contact_phone', on_click=lambda c=cnpj_card: _abrir_edicao_contato(c, None)
                ).props('flat round color=warning size=sm').tooltip('Editar contato')
            if on_delete:
                with ui.dialog() as del_dialog, ui.card().classes('p-5 gap-4'):
                    ui.label(f'Excluir lead de {lead.nome_contato}?').classes('text-lg font-bold')
                    ui.label('Esta acao nao pode ser desfeita.').classes('text-sm text-slate-600')
                    with ui.row().classes('gap-2 justify-end'):
                        ui.button('Cancelar', on_click=del_dialog.close).props('flat')
                        ui.button('Excluir', color='negative', on_click=lambda l=lead, d=del_dialog: (d.close(), on_delete(l)))
                ui.button(icon='delete', on_click=del_dialog.open
                ).props('flat round color=negative size=sm').tooltip('Excluir')


def _render_colunas_kanban(
    leads_por_status: dict[str, list[Lead]],
    mover_lead: Callable[[Lead, str], None],
    on_delete: Callable[[Lead], None] | None = None,
) -> None:
    with ui.row().classes('w-full gap-4 items-start max-[1100px]:flex-col'):
        for status in STATUS_KANBAN:
            with ui.column().classes('flex-1 min-w-0 gap-3 rounded-2xl bg-slate-100 p-4'):
                ui.label(status).classes('text-lg font-bold text-slate-900')
                ui.label(f'{len(leads_por_status[status])} oportunidade(s)').classes('text-xs text-slate-500')
                for lead in leads_por_status[status]:
                    _render_lead_card(lead, status, mover_lead, on_delete)


def render_kanban(auth: dict) -> None:
    container = ui.column().classes('w-full gap-6 p-6')
    empresa_id = int(auth['usuario_id'])

    def renderizar() -> None:
        container.clear()
        leads_por_status = _obter_leads_por_status(empresa_id)

        with container:
            ui.label('Kanban de leads').classes('text-2xl font-bold text-slate-900')
            _render_formulario_lead(empresa_id, renderizar)
            total_leads = _render_resumo_kanban(leads_por_status)

            if total_leads == 0:
                _render_empty_state()
                return

            _render_colunas_kanban(leads_por_status, mover_lead, on_delete=deletar_lead)

    def deletar_lead(lead: Lead) -> None:
        _deletar_lead(lead, empresa_id)
        ui.notify(f'Lead de {lead.nome_contato} excluido.', color='positive')
        renderizar()

    def mover_lead(lead: Lead, destino: str) -> None:
        try:
            _mudar_status(lead, destino, alterado_por_id=empresa_id)
        except ValueError as exc:
            ui.notify(str(exc), color='negative')
            return
        ui.notify(f'Lead de {lead.nome_contato} movido para {destino}.', color='positive')
        renderizar()

    renderizar()
