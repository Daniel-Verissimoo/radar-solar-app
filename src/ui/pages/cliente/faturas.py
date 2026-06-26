from __future__ import annotations

from typing import Any

from nicegui import ui

from src.models import Fatura, InstalacaoSolar, Usuario
from src.utils import log_info, log_dados, log_ok


FATURA_TABLE_COLUMNS = [
    {'name': 'mes_referencia', 'label': 'Mes', 'field': 'mes_referencia'},
    {'name': 'consumo_kwh', 'label': 'Consumo (kWh)', 'field': 'consumo_kwh'},
    {'name': 'geracao_app_kwh', 'label': 'Producao (kWh)', 'field': 'geracao_app_kwh'},
    {'name': 'injecao_kwh', 'label': 'Injecao (kWh)', 'field': 'injecao_kwh'},
    {'name': 'saldo_creditos', 'label': 'Creditos (kWh)', 'field': 'saldo_creditos'},
    {'name': 'valor_fatura_rs', 'label': 'Valor (R$)', 'field': 'valor_fatura_rs'},
]


def _parse_float(value: Any, field_name: str, optional: bool = False) -> float | None:
    text = '' if value is None else str(value).strip()
    if not text:
        if optional:
            return None
        raise ValueError(f'O campo "{field_name}" e obrigatorio.')
    try:
        if ',' in text:
            text = text.replace('.', '').replace(',', '.')
        elif text.count('.') > 1:
            text = text.replace('.', '')
        return float(text)
    except ValueError as exc:
        raise ValueError(f'O campo "{field_name}" deve ser numerico.') from exc


def _format_num_br(value: float | None, decimals: int = 2) -> str:
    if value is None:
        return '-'
    formatted = f'{value:,.{decimals}f}'
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


def _format_moeda_br(value: float | None) -> str:
    if value is None:
        return '-'
    return f'R$ {_format_num_br(value, 2)}'


def _formatar_valor_input_br(campo: ui.input, optional: bool = False) -> None:
    texto = (campo.value or '').strip()
    if not texto:
        return
    try:
        if ',' in texto:
            texto = texto.replace('.', '').replace(',', '.')
        elif texto.count('.') > 1:
            texto = texto.replace('.', '')
        numero = float(texto)
        campo.value = _format_num_br(numero)
        campo.update()
    except ValueError:
        if optional and not texto:
            return


def _obter_ou_criar_instalacao_manual(usuario_id: int) -> InstalacaoSolar:
    instalacao = InstalacaoSolar.select().where(InstalacaoSolar.usuario == usuario_id).first()
    if instalacao:
        return instalacao

    instalacao = InstalacaoSolar.create(
        usuario=usuario_id,
        concessionaria='Neoenergia',
        classe_consumo='B2C',
        cep='',
        logradouro='',
        numero='',
        cidade='',
        estado='',
    )
    log_info(f'Faturas: instalacao criada automaticamente para usuario {usuario_id}')
    return instalacao


def _obter_fatura_do_usuario(usuario_id: int, fatura_id: int) -> Fatura | None:
    return (
        Fatura.select()
        .join(InstalacaoSolar)
        .where(
            (Fatura.id == fatura_id)
            & (InstalacaoSolar.usuario == usuario_id)
        )
        .first()
    )


def _usuario_ja_tem_fatura_na_competencia(
    usuario_id: int,
    mes_referencia: str,
    fatura_id_ignorar: int | None = None,
) -> bool:
    query = (
        Fatura.select()
        .join(InstalacaoSolar)
        .where(
            (InstalacaoSolar.usuario == usuario_id)
            & (Fatura.mes_referencia == mes_referencia)
        )
    )

    if fatura_id_ignorar:
        query = query.where(Fatura.id != fatura_id_ignorar)

    return query.exists()


def _listar_faturas_usuario(usuario_id: int) -> list[Fatura]:
    instalacoes_ids = InstalacaoSolar.select(InstalacaoSolar.id).where(InstalacaoSolar.usuario == usuario_id)
    faturas = list(
        Fatura.select()
        .where(Fatura.instalacao.in_(instalacoes_ids))
        .order_by(Fatura.criado_em.desc())
    )
    log_dados(f'Faturas: listagem carregada para usuario {usuario_id}', len(faturas))
    return faturas


def _fatura_table_row(fatura: Fatura) -> dict:
    return {
        'id': fatura.id,
        'mes_referencia': fatura.mes_referencia,
        'consumo_kwh': _format_num_br(fatura.consumo_kwh),
        'geracao_app_kwh': _format_num_br(fatura.geracao_app_kwh),
        'injecao_kwh': _format_num_br(fatura.injecao_kwh),
        'saldo_creditos': _format_num_br(fatura.saldo_creditos),
        'valor_fatura_rs': _format_moeda_br(fatura.valor_fatura_rs),
    }


def _fatura_select_options(faturas: list[Fatura]) -> dict[int, str]:
    return {
        fatura.id: f'#{fatura.id} - {fatura.mes_referencia} - {_format_moeda_br(fatura.valor_fatura_rs)}'
        for fatura in faturas
    }


def render_faturas(auth: dict) -> None:
    usuario = Usuario.get_or_none(Usuario.id == auth.get('usuario_id'))

    with ui.column().classes('w-full gap-6 p-6'):
        ui.label('Insercao manual da fatura Neoenergia').classes('text-2xl font-bold text-slate-900')

        if not usuario:
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Nao foi possivel carregar o usuario autenticado.').classes('text-base text-red-600')
            return

        state = {
            'edit_id': None,
        }

        with ui.card().classes('w-full p-6 rounded-2xl gap-4'):
            ui.label('Dados da conta de energia').classes('text-lg font-semibold text-slate-900')
            ui.label('Preencha os campos abaixo para salvar a fatura no seu historico.').classes(
                'text-sm text-slate-600'
            )

            with ui.row().classes('w-full gap-4 items-start'):
                mes_referencia = ui.input('Mes de referencia (MM/AAAA)').classes('w-56')
                consumo_kwh = ui.input('Consumo (kWh)').classes('w-44').props('inputmode=decimal')
                valor_fatura_rs = ui.input('Valor da fatura (R$)').classes('w-44').props('inputmode=decimal')

            with ui.row().classes('w-full gap-4 items-start'):
                injecao_kwh = ui.input('Injecao na rede (kWh)').classes('w-44').props('inputmode=decimal')
                creditos_utilizados = ui.input('Creditos utilizados (kWh)').classes('w-52').props('inputmode=decimal')
                saldo_creditos = ui.input('Saldo de creditos (kWh)').classes('w-52').props('inputmode=decimal')
                geracao_app_kwh = ui.input('Geracao no app (kWh)').classes('w-48').props('inputmode=decimal')

            consumo_kwh.on('blur', lambda _: _formatar_valor_input_br(consumo_kwh))
            valor_fatura_rs.on('blur', lambda _: _formatar_valor_input_br(valor_fatura_rs))
            injecao_kwh.on('blur', lambda _: _formatar_valor_input_br(injecao_kwh, optional=True))
            creditos_utilizados.on('blur', lambda _: _formatar_valor_input_br(creditos_utilizados, optional=True))
            saldo_creditos.on('blur', lambda _: _formatar_valor_input_br(saldo_creditos, optional=True))
            geracao_app_kwh.on('blur', lambda _: _formatar_valor_input_br(geracao_app_kwh, optional=True))

            fatura_para_editar = ui.select(options={}, label='Fatura para editar').classes('w-80')

            table = ui.table(
                columns=FATURA_TABLE_COLUMNS,
                rows=[],
                row_key='id',
            ).classes('w-full')

            def carregar_faturas() -> None:
                faturas = _listar_faturas_usuario(usuario.id)
                table.rows = [_fatura_table_row(fatura) for fatura in faturas]
                fatura_para_editar.options = _fatura_select_options(faturas)
                table.update()
                fatura_para_editar.update()

            def limpar_formulario() -> None:
                state['edit_id'] = None
                mes_referencia.value = ''
                consumo_kwh.value = ''
                valor_fatura_rs.value = ''
                injecao_kwh.value = ''
                creditos_utilizados.value = ''
                saldo_creditos.value = ''
                geracao_app_kwh.value = ''
                fatura_para_editar.value = None
                fatura_para_editar.update()

            def carregar_fatura_por_id(fatura_id: int | str | None) -> None:
                if not fatura_id:
                    ui.notify('Selecione uma fatura para editar.', color='warning')
                    return

                try:
                    fatura_id = int(fatura_id)
                except (TypeError, ValueError):
                    ui.notify('Fatura invalida para edicao.', color='negative')
                    return

                fatura = _obter_fatura_do_usuario(usuario.id, fatura_id)
                if not fatura:
                    ui.notify('Fatura nao encontrada.', color='negative')
                    return

                state['edit_id'] = fatura.id
                mes_referencia.value = fatura.mes_referencia
                consumo_kwh.value = _format_num_br(fatura.consumo_kwh)
                valor_fatura_rs.value = _format_num_br(fatura.valor_fatura_rs)
                injecao_kwh.value = '' if fatura.injecao_kwh is None else _format_num_br(fatura.injecao_kwh)
                creditos_utilizados.value = '' if fatura.creditos_utilizados is None else _format_num_br(fatura.creditos_utilizados)
                saldo_creditos.value = '' if fatura.saldo_creditos is None else _format_num_br(fatura.saldo_creditos)
                geracao_app_kwh.value = '' if fatura.geracao_app_kwh is None else _format_num_br(fatura.geracao_app_kwh)
                ui.notify('Fatura carregada para correcao.', color='primary')

            def salvar_fatura() -> None:
                try:
                    mes = (mes_referencia.value or '').strip()
                    if not mes:
                        raise ValueError('O campo "Mes de referencia" e obrigatorio.')

                    payload = {
                        'mes_referencia': mes,
                        'consumo_kwh': _parse_float(consumo_kwh.value, 'Consumo (kWh)'),
                        'valor_fatura_rs': _parse_float(valor_fatura_rs.value, 'Valor da fatura (R$)'),
                        'injecao_kwh': _parse_float(injecao_kwh.value, 'Injecao na rede (kWh)', optional=True),
                        'creditos_utilizados': _parse_float(
                            creditos_utilizados.value,
                            'Creditos utilizados (kWh)',
                            optional=True,
                        ),
                        'saldo_creditos': _parse_float(saldo_creditos.value, 'Saldo de creditos (kWh)', optional=True),
                        'geracao_app_kwh': _parse_float(geracao_app_kwh.value, 'Geracao no app (kWh)', optional=True),
                    }
                except ValueError as exc:
                    ui.notify(str(exc), color='negative')
                    return

                if _usuario_ja_tem_fatura_na_competencia(usuario.id, mes, state['edit_id']):
                    ui.notify('Ja existe uma fatura cadastrada para essa competencia.', color='warning')
                    return

                if state['edit_id']:
                    fatura = _obter_fatura_do_usuario(usuario.id, state['edit_id'])
                    if not fatura:
                        ui.notify('Fatura nao encontrada para edicao.', color='negative')
                        return
                    for field, value in payload.items():
                        setattr(fatura, field, value)
                    fatura.save()
                    log_ok(f'Faturas: fatura #{fatura.id} atualizada (mes {mes})')
                    ui.notify('Fatura atualizada com sucesso.', color='positive')
                else:
                    instalacao = _obter_ou_criar_instalacao_manual(usuario.id)
                    fatura = Fatura.create(instalacao=instalacao, **payload)
                    log_ok(f'Faturas: nova fatura #{fatura.id} criada (mes {mes})')
                    ui.notify('Fatura salva com sucesso.', color='positive')

                limpar_formulario()
                carregar_faturas()

            def editar_fatura_selecionada() -> None:
                carregar_fatura_por_id(fatura_para_editar.value)

            def excluir_fatura_selecionada() -> None:
                fatura_id = fatura_para_editar.value
                if not fatura_id:
                    ui.notify('Selecione uma fatura para excluir.', color='warning')
                    return

                try:
                    fatura_id = int(fatura_id)
                except (TypeError, ValueError):
                    ui.notify('Fatura invalida para exclusao.', color='negative')
                    return

                fatura = _obter_fatura_do_usuario(usuario.id, fatura_id)
                if not fatura:
                    ui.notify('Fatura nao encontrada para exclusao.', color='negative')
                    return

                mes_excluido = fatura.mes_referencia
                fatura.delete_instance()
                limpar_formulario()
                carregar_faturas()
                log_ok(f'Faturas: fatura #{fatura_id} ({mes_excluido}) excluida')
                ui.notify('Fatura excluida com sucesso.', color='positive')

            def confirmar_exclusao() -> None:
                fatura_id = fatura_para_editar.value
                if not fatura_id:
                    ui.notify('Selecione uma fatura para excluir.', color='warning')
                    return

                try:
                    fatura_id_int = int(fatura_id)
                except (TypeError, ValueError):
                    ui.notify('Fatura invalida para exclusao.', color='negative')
                    return

                fatura = _obter_fatura_do_usuario(usuario.id, fatura_id_int)
                if not fatura:
                    ui.notify('Fatura nao encontrada para exclusao.', color='negative')
                    return

                with ui.dialog() as dialog, ui.card().classes('w-[28rem] p-6 gap-4'):
                    ui.label('Confirmar exclusao').classes('text-lg font-semibold text-slate-900')
                    ui.label(
                        f'Voce esta prestes a excluir a fatura {fatura.mes_referencia} no valor de {_format_moeda_br(fatura.valor_fatura_rs)}.'
                    ).classes('text-sm text-slate-700')
                    ui.label(
                        'Esta acao nao pode ser desfeita.'
                    ).classes('text-sm text-slate-600')
                    with ui.row().classes('w-full justify-end gap-2 pt-2'):
                        ui.button('Cancelar', on_click=dialog.close).props('flat color=primary')
                        ui.button(
                            'Excluir',
                            on_click=lambda: (dialog.close(), excluir_fatura_selecionada()),
                        ).props('color=negative')

                dialog.open()

            fatura_para_editar.on_value_change(lambda _: editar_fatura_selecionada())

            with ui.row().classes('w-full gap-3 pt-2'):
                ui.button('Salvar fatura', on_click=salvar_fatura).props('color=primary').classes('rounded-xl px-5')
                ui.button('Excluir selecionada', on_click=confirmar_exclusao).props(
                    'outline color=negative'
                ).classes('rounded-xl px-5')
                ui.button('Limpar', on_click=limpar_formulario).props('outline color=primary').classes('rounded-xl px-5')

            ui.label('Dica: ao escolher uma fatura no campo, os dados sao carregados automaticamente.').classes(
                'text-xs text-slate-500'
            )

            carregar_faturas()
