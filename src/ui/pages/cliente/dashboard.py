from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from nicegui import ui
from src.models import Fatura, InstalacaoSolar, Lead, LeadLog, Usuario
from src.services.crm_service import auto_atribuir_lead
from src.utils import _format_datetime_br, _normalizar_estado, log_info, log_dados, log_ok


LIMIAR_QUEDA_GERACAO_PERCENT = 20.0
LIMIAR_DIFERENCA_GERACAO_INJECAO_PERCENT = 35.0


def _format_kwh(value: float | None) -> str:
    if value is None:
        return '-'
    return f'{value:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.') + ' kWh'


def _format_percent(value: float) -> str:
    return f'{value:.1f}%'.replace('.', ',')


def _obter_faturas_usuario(usuario_id: int) -> list[Fatura]:
    instalacoes_ids = (
        InstalacaoSolar.select(InstalacaoSolar.id)
        .where(InstalacaoSolar.usuario == usuario_id)
    )
    faturas = list(
        Fatura.select()
        .where(Fatura.instalacao.in_(instalacoes_ids))
        .order_by(Fatura.criado_em.desc())
    )
    log_dados(f'Dashboard B2C: faturas carregadas para usuario {usuario_id}', len(faturas))
    return faturas


def _obter_lead_aberto(usuario_id: int) -> Lead | None:
    return (
        Lead.select()
        .where(
            (Lead.cliente == usuario_id)
            & (Lead.status.in_(['Novo', 'Em Contato']))
        )
        .order_by(Lead.criado_em.desc())
        .first()
    )


def _salvar_solicitacao_manutencao(
    usuario: Usuario,
    instalacao: InstalacaoSolar,
    payload: dict[str, Any],
) -> Lead:
    lead_aberto = _obter_lead_aberto(usuario.id)
    if lead_aberto:
        log_info(f'Dashboard B2C: lead #{lead_aberto.id} ja aberto, retornando existente')
        return lead_aberto

    nome = str(payload['nome']).strip()
    telefone = str(payload['telefone']).strip()
    cpf_cnpj = str(payload.get('cpf_cnpj') or '').strip() or None

    if cpf_cnpj:
        dono_cpf = Usuario.get_or_none((Usuario.cpf_cnpj == cpf_cnpj) & (Usuario.id != usuario.id))
        if dono_cpf:
            raise ValueError('CPF/CNPJ ja esta vinculado a outro usuario.')

    usuario.nome = nome
    usuario.telefone = telefone
    if cpf_cnpj:
        usuario.cpf_cnpj = cpf_cnpj
    usuario.save()

    instalacao.cep = str(payload['cep']).strip()
    instalacao.logradouro = str(payload.get('logradouro') or '').strip()
    instalacao.numero = str(payload.get('numero') or '').strip()
    instalacao.complemento = str(payload.get('complemento') or '').strip() or None
    instalacao.cidade = str(payload['cidade']).strip()
    instalacao.estado = _normalizar_estado(payload['estado'])
    instalacao.save()

    descricao = str(payload.get('descricao') or '').strip()
    lead = Lead.create(
        cliente=usuario,
        empresa_responsavel=None,
        nome_contato=nome,
        telefone_contato=telefone,
        origem='Dashboard B2C - Solicitar manutencao',
        descricao_servico=descricao or 'Cliente solicitou contato para avaliacao/manutencao da instalacao solar.',
        status='Novo',
    )
    LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=usuario)
    auto_atribuir_lead(lead)
    log_ok(f'Dashboard B2C: lead de manutencao #{lead.id} criado para usuario {usuario.email}')
    return lead


def _cancelar_solicitacao(lead: Lead) -> None:
    lead.status = 'Cancelado'
    lead.save()


def _avaliar_alertas(faturas: list[Fatura]) -> tuple[list[str], list[str]]:
    alertas: list[str] = []
    status: list[str] = []

    if len(faturas) < 2:
        status.append('Sem historico suficiente para validar tendencia de geracao (minimo de 2 faturas).')
    else:
        atual = faturas[0].geracao_app_kwh
        anterior = faturas[1].geracao_app_kwh
        if atual is None or anterior is None or anterior <= 0:
            status.append('Sem dados de geracao completos para comparar com o mes anterior.')
        else:
            queda_percentual = ((anterior - atual) / anterior) * 100
            if queda_percentual >= LIMIAR_QUEDA_GERACAO_PERCENT:
                alertas.append(
                    f'Queda de geracao acima do limite: {_format_percent(queda_percentual)} em relacao ao mes anterior.'
                )
            else:
                status.append(
                    f'Geracao dentro da faixa esperada: variacao de {_format_percent(queda_percentual)} frente ao mes anterior.'
                )

    fatura_atual = faturas[0] if faturas else None
    if fatura_atual and fatura_atual.geracao_app_kwh and fatura_atual.geracao_app_kwh > 0 and fatura_atual.injecao_kwh is not None:
        diferenca = abs(fatura_atual.geracao_app_kwh - fatura_atual.injecao_kwh)
        percentual_diferenca = (diferenca / fatura_atual.geracao_app_kwh) * 100
        if percentual_diferenca >= LIMIAR_DIFERENCA_GERACAO_INJECAO_PERCENT:
            alertas.append(
                f'Diferenca elevada entre geracao e injecao: {_format_percent(percentual_diferenca)} no mes atual.'
            )
        else:
            status.append(
                f'Proporcao geracao x injecao sem desvio critico ({_format_percent(percentual_diferenca)} de diferenca).'
            )
    else:
        status.append('Sem dados suficientes para avaliar a diferenca entre geracao e injecao.')

    return alertas, status


def _gerar_dados_grafico(faturas: list[Fatura], limite: int = 6) -> tuple[list[str], list[float], list[float], list[float]]:
    def chave_mes_referencia(fatura: Fatura) -> datetime:
        try:
            return datetime.strptime(fatura.mes_referencia, '%m/%Y')
        except (TypeError, ValueError):
            return fatura.criado_em

    ordenadas = sorted(faturas, key=chave_mes_referencia)
    recorte = ordenadas[-limite:]
    labels = [f.mes_referencia for f in recorte]
    consumo = [round(f.consumo_kwh or 0, 2) for f in recorte]
    injecao = [round(f.injecao_kwh or 0, 2) for f in recorte]
    geracao = [round(f.geracao_app_kwh or 0, 2) for f in recorte]
    return labels, consumo, injecao, geracao


def render_dashboard(auth: dict, refresh_callback: Callable[[], None] | None = None) -> None:
    usuario = Usuario.get_or_none(Usuario.id == auth.get('usuario_id'))

    with ui.column().classes('w-full gap-6 p-6'):
        ui.label('Dashboard B2C').classes('text-2xl font-bold text-slate-900')

        if not usuario:
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Nao foi possivel carregar o usuario autenticado.').classes('text-base text-red-600')
            return

        faturas = _obter_faturas_usuario(usuario.id)
        fatura_atual = faturas[0] if faturas else None

        if not fatura_atual:
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Voce ainda nao possui faturas cadastradas.').classes('text-lg font-semibold text-slate-900')
                ui.label('Acesse o modulo de faturas para inserir seus dados e habilitar este dashboard.').classes(
                    'text-sm text-slate-600'
                )
            return

        with ui.row().classes('w-full gap-4 max-[1100px]:flex-col'):
            with ui.card().classes('flex-1 p-6 rounded-2xl'):
                ui.label('Consumo').classes('text-sm text-slate-500')
                ui.label(_format_kwh(fatura_atual.consumo_kwh)).classes('text-3xl font-bold text-slate-900')
                ui.label(f'Mes {fatura_atual.mes_referencia}').classes('text-xs text-slate-500')

            with ui.card().classes('flex-1 p-6 rounded-2xl'):
                ui.label('Injecao na rede').classes('text-sm text-slate-500')
                ui.label(_format_kwh(fatura_atual.injecao_kwh)).classes('text-3xl font-bold text-slate-900')
                ui.label('Energia devolvida para compensacao').classes('text-xs text-slate-500')

            with ui.card().classes('flex-1 p-6 rounded-2xl'):
                ui.label('Saldo de creditos').classes('text-sm text-slate-500')
                ui.label(_format_kwh(fatura_atual.saldo_creditos)).classes('text-3xl font-bold text-slate-900')
                ui.label('Saldo acumulado na fatura').classes('text-xs text-slate-500')

        labels, consumo_hist, injecao_hist, geracao_hist = _gerar_dados_grafico(faturas)
        with ui.card().classes('w-full p-6 rounded-2xl'):
            ui.label('Historico recente da fatura').classes('text-lg font-semibold text-slate-900')
            ui.label('Comparativo dos ultimos meses entre consumo, injecao e geracao.').classes(
                'text-sm text-slate-600'
            )
            ui.echart({
                'tooltip': {'trigger': 'axis'},
                'legend': {'data': ['Consumo', 'Injecao', 'Geracao']},
                'xAxis': {'type': 'category', 'data': labels},
                'yAxis': {'type': 'value', 'name': 'kWh'},
                'series': [
                    {'name': 'Consumo', 'type': 'bar', 'data': consumo_hist, 'itemStyle': {'color': '#1D4ED8'}},
                    {'name': 'Injecao', 'type': 'bar', 'data': injecao_hist, 'itemStyle': {'color': '#0D9488'}},
                    {'name': 'Geracao', 'type': 'line', 'data': geracao_hist, 'smooth': True, 'itemStyle': {'color': '#EA580C'}},
                ],
            }).classes('w-full h-96')

        alertas, status_operacao = _avaliar_alertas(faturas)
        houve_alerta = len(alertas) > 0
        classes_alerta = 'w-full p-6 rounded-2xl border-2 '
        if houve_alerta:
            classes_alerta += 'bg-red-50 border-red-300'
            cor_texto = 'text-red-700'
            titulo_alerta = 'Avisos'
        else:
            classes_alerta += 'bg-emerald-50 border-emerald-300'
            cor_texto = 'text-emerald-700'
            titulo_alerta = 'Status da geracao'

        with ui.card().classes(classes_alerta):
            ui.label(titulo_alerta).classes(f'text-lg font-semibold {cor_texto}')
            for alerta in alertas:
                ui.label(f'- {alerta}').classes(f'text-sm {cor_texto}')
            for status in status_operacao:
                ui.label(f'- {status}').classes(f'text-sm {cor_texto}')

        instalacao_atual = fatura_atual.instalacao
        lead_aberto = _obter_lead_aberto(usuario.id)

        with ui.dialog() as solicitacao_dialog, ui.card().classes('w-full max-w-3xl p-6 gap-5'):
            ui.label('Solicitar manutencao ou contato').classes('text-xl font-bold text-slate-900')
            ui.label(
                'Complete os dados essenciais para que o integrador consiga entrar em contato e localizar a instalacao.'
            ).classes('text-sm text-slate-600 leading-6')

            with ui.row().classes('w-full gap-4 items-start'):
                nome_contato = ui.input('Nome completo *', value=usuario.nome).classes('flex-1 min-w-64')
                telefone_contato = ui.input('Telefone/WhatsApp *', value=usuario.telefone or '').classes('w-56')
                cpf_cnpj = ui.input('CPF/CNPJ', value=usuario.cpf_cnpj or '').classes('w-56')

            with ui.row().classes('w-full gap-4 items-start'):
                cep = ui.input('CEP *', value=instalacao_atual.cep).classes('w-44')
                cidade = ui.input('Cidade *', value=instalacao_atual.cidade).classes('flex-1 min-w-56')
                estado = ui.input('UF *', value=instalacao_atual.estado).classes('w-24')

            with ui.row().classes('w-full gap-4 items-start'):
                logradouro = ui.input('Logradouro', value=instalacao_atual.logradouro).classes('flex-1 min-w-64')
                numero = ui.input('Numero', value=instalacao_atual.numero).classes('w-32')
                complemento = ui.input('Complemento', value=instalacao_atual.complemento or '').classes('w-52')

            descricao = ui.textarea(
                'Descreva o problema ou motivo do contato',
                value='Quero uma avaliacao da minha instalacao solar com base nos alertas do Radar Solar.',
            ).classes('w-full')

            def confirmar_solicitacao() -> None:
                try:
                    obrigatorios = {
                        'Nome completo': nome_contato.value,
                        'Telefone/WhatsApp': telefone_contato.value,
                        'CEP': cep.value,
                        'Cidade': cidade.value,
                        'UF': estado.value,
                    }
                    for label, value in obrigatorios.items():
                        if not str(value or '').strip():
                            raise ValueError(f'O campo "{label}" e obrigatorio.')

                    lead = _salvar_solicitacao_manutencao(
                        usuario,
                        instalacao_atual,
                        {
                            'nome': nome_contato.value,
                            'telefone': telefone_contato.value,
                            'cpf_cnpj': cpf_cnpj.value,
                            'cep': cep.value,
                            'cidade': cidade.value,
                            'estado': estado.value,
                            'logradouro': logradouro.value,
                            'numero': numero.value,
                            'complemento': complemento.value,
                            'descricao': descricao.value,
                        },
                    )
                except ValueError as exc:
                    ui.notify(str(exc), color='negative')
                    return

                solicitacao_dialog.close()
                ui.notify(f'Solicitacao registrada como lead #{lead.id}.', color='positive')
                ui.timer(
                    0.3,
                    refresh_callback or (lambda: ui.navigate.to('/cliente/dashboard')),
                    once=True,
                )

            with ui.row().classes('w-full justify-end gap-3'):
                ui.button('Cancelar', on_click=solicitacao_dialog.close).props('flat color=primary')
                ui.button('Enviar solicitacao', on_click=confirmar_solicitacao).props('color=secondary')

        with ui.dialog() as status_dialog, ui.card().classes('w-full max-w-xl p-6 gap-4'):
            ui.label('Solicitacao de contato aberta').classes('text-xl font-bold text-slate-900')
            if lead_aberto:
                ui.label(f'Lead #{lead_aberto.id}').classes('text-sm font-semibold text-orange-700')
                ui.label(f'Status atual: {lead_aberto.status}').classes('text-base text-slate-800')
                ui.label(f'Solicitado em: {_format_datetime_br(lead_aberto.criado_em)}').classes('text-sm text-slate-600')
                if lead_aberto.descricao_servico:
                    ui.label('Descricao enviada').classes('text-sm font-semibold text-slate-700 pt-2')
                    ui.label(lead_aberto.descricao_servico).classes('text-sm text-slate-600 leading-6')
                ui.label(
                    'Ao cancelar, a solicitacao deixa de aparecer como oportunidade aberta para o integrador no Kanban.'
                ).classes('text-sm text-slate-500 leading-6')

            def cancelar_solicitacao_aberta() -> None:
                if not lead_aberto:
                    ui.notify('Nao existe solicitacao aberta para cancelar.', color='warning')
                    return
                _cancelar_solicitacao(lead_aberto)
                status_dialog.close()
                ui.notify('Solicitacao cancelada.', color='positive')
                ui.timer(
                    0.3,
                    refresh_callback or (lambda: ui.navigate.to('/cliente/dashboard')),
                    once=True,
                )

            with ui.row().classes('w-full justify-end gap-3'):
                ui.button('Fechar', on_click=status_dialog.close).props('flat color=primary')
                if lead_aberto:
                    ui.button('Cancelar solicitacao', on_click=cancelar_solicitacao_aberta).props('outline color=negative')

        with ui.card().classes('w-full p-6 rounded-2xl border border-orange-200 bg-orange-50'):
            with ui.row().classes('w-full items-center justify-between gap-4'):
                with ui.column().classes('gap-1'):
                    ui.label('Precisa de apoio tecnico?').classes('text-lg font-semibold text-slate-900')
                    if lead_aberto:
                        ui.label(
                            f'Solicitacao aberta em {_format_datetime_br(lead_aberto.criado_em)}.'
                        ).classes('text-sm text-orange-800')
                    else:
                        ui.label(
                            'Envie seus dados de contato e instalacao para virar uma oportunidade de atendimento para o integrador.'
                        ).classes('text-sm text-slate-700')
                ui.button(
                    'Ver solicitacao' if lead_aberto else 'Solicitar manutencao',
                    on_click=status_dialog.open if lead_aberto else solicitacao_dialog.open,
                ).props('color=secondary').classes('rounded-xl px-5')

        with ui.card().classes('w-full p-6 rounded-2xl border border-slate-200 bg-slate-50'):
            ui.label('Regras de alerta em uso (temporario)').classes('text-base font-semibold text-slate-900')
            ui.label(
                f'- Regra 1: queda de geracao >= {_format_percent(LIMIAR_QUEDA_GERACAO_PERCENT)} versus mes anterior gera alerta.'
            ).classes('text-sm text-slate-700')
            ui.label(
                f'- Regra 2: diferenca entre geracao e injecao >= {_format_percent(LIMIAR_DIFERENCA_GERACAO_INJECAO_PERCENT)} no mes atual gera alerta.'
            ).classes('text-sm text-slate-700')
            ui.label('- Sem historico/dados suficientes: sistema informa status sem disparar falso positivo.').classes('text-sm text-slate-700')
