from __future__ import annotations

import json

from nicegui import app, ui

from src.models import InstalacaoSolar, Usuario
from src.utils import _buscar_endereco_por_cep, _normalizar_cep, _normalizar_estado, log_info, log_ok


def _obter_ou_criar_instalacao(usuario_id: int) -> InstalacaoSolar:
    instalacao = InstalacaoSolar.select().where(InstalacaoSolar.usuario == usuario_id).first()
    if instalacao:
        return instalacao

    return InstalacaoSolar.create(
        usuario=usuario_id,
        concessionaria='Neoenergia',
        classe_consumo='B2C',
        cep='',
        logradouro='',
        numero='',
        cidade='',
        estado='',
    )


def _limpar_endereco_inputs(cidade: ui.input, estado: ui.input, logradouro: ui.input) -> None:
    cidade.value = ''
    estado.value = ''
    logradouro.value = ''
    cidade.update()
    estado.update()
    logradouro.update()


def _render_contact_fields(usuario: Usuario):
    with ui.card().classes('w-full p-6 rounded-2xl gap-5'):
        ui.label('Dados de contato').classes('text-lg font-semibold text-slate-900')
        ui.label(
            'Essas informacoes ajudam o integrador a entender quem solicitou contato e onde fica a instalacao.'
        ).classes('text-sm text-slate-600')

        with ui.row().classes('w-full gap-4 items-start'):
            nome = ui.input('Nome completo *', value=usuario.nome).classes('flex-1 min-w-64')
            email = ui.input('E-mail', value=usuario.email).classes('flex-1 min-w-64')
            email.disable()

        with ui.row().classes('w-full gap-4 items-start'):
            telefone = ui.input('Telefone/WhatsApp', value=usuario.telefone or '').classes('w-56')
            cpf_cnpj = ui.input('CPF/CNPJ', value=usuario.cpf_cnpj or '').classes('w-56')
    return nome, telefone, cpf_cnpj


def _render_address_fields(instalacao: InstalacaoSolar):
    with ui.card().classes('w-full p-6 rounded-2xl gap-5'):
        ui.label('Endereco da instalacao').classes('text-lg font-semibold text-slate-900')
        ui.label(
            'Nao pedimos latitude/longitude ao cliente. A localizacao inicial usa CEP, cidade e endereco aproximado.'
        ).classes('text-sm text-slate-600')

        with ui.row().classes('w-full gap-4 items-start'):
            cep = ui.input('CEP', value=instalacao.cep).classes('w-44')
            cidade = ui.input('Cidade', value=instalacao.cidade).classes('flex-1 min-w-56')
            estado = ui.input('UF', value=instalacao.estado).classes('w-24')
            buscar_cep = ui.button('Buscar CEP').props('outline color=primary').classes('rounded-xl')

        with ui.row().classes('w-full gap-4 items-start'):
            logradouro = ui.input('Logradouro', value=instalacao.logradouro).classes('flex-1 min-w-64')
            numero = ui.input('Numero', value=instalacao.numero).classes('w-32')
            complemento = ui.input('Complemento', value=instalacao.complemento or '').classes('w-52')
    return cep, cidade, estado, buscar_cep, logradouro, numero, complemento


def _preencher_endereco_por_cep(cep: ui.input, cidade: ui.input, estado: ui.input, logradouro: ui.input) -> None:
    try:
        cep_normalizado = _normalizar_cep(cep.value)
    except ValueError as exc:
        _limpar_endereco_inputs(cidade, estado, logradouro)
        ui.notify(str(exc), color='warning')
        return

    if not cep_normalizado:
        _limpar_endereco_inputs(cidade, estado, logradouro)
        ui.notify('Informe um CEP para buscar o endereco.', color='warning')
        return

    endereco = _buscar_endereco_por_cep(cep_normalizado)
    if not endereco:
        _limpar_endereco_inputs(cidade, estado, logradouro)
        ui.notify('CEP nao encontrado.', color='warning')
        return

    cep.value = cep_normalizado
    cidade.value = endereco['cidade']
    estado.value = endereco['estado']
    logradouro.value = endereco['logradouro']
    cep.update()
    cidade.update()
    estado.update()
    logradouro.update()
    ui.notify('Endereco preenchido pelo CEP.', color='positive')


def render_perfil(auth: dict) -> None:
    usuario = Usuario.get_or_none(Usuario.id == auth.get('usuario_id'))

    with ui.column().classes('w-full gap-6 p-6'):
        ui.label('Perfil do cliente').classes('text-2xl font-bold text-slate-900')

        if not usuario:
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Nao foi possivel carregar o usuario autenticado.').classes('text-base text-red-600')
            return

        instalacao = _obter_ou_criar_instalacao(usuario.id)

        nome, telefone, cpf_cnpj = _render_contact_fields(usuario)
        cep, cidade, estado, buscar_cep, logradouro, numero, complemento = _render_address_fields(instalacao)

        buscar_cep.on('click', lambda: _preencher_endereco_por_cep(cep, cidade, estado, logradouro))
        cep.on(
            'blur',
            lambda _: _preencher_endereco_por_cep(cep, cidade, estado, logradouro)
            if str(cep.value or '').strip()
            else None,
        )

        def salvar_perfil() -> None:
            try:
                if not str(nome.value or '').strip():
                    raise ValueError('O campo "Nome completo" e obrigatorio.')

                cpf_cnpj_limpo = str(cpf_cnpj.value or '').strip() or None
                if cpf_cnpj_limpo:
                    dono_cpf = Usuario.get_or_none((Usuario.cpf_cnpj == cpf_cnpj_limpo) & (Usuario.id != usuario.id))
                    if dono_cpf:
                        raise ValueError('CPF/CNPJ ja esta vinculado a outro usuario.')

                usuario.nome = str(nome.value).strip()
                usuario.telefone = str(telefone.value or '').strip() or None
                usuario.cpf_cnpj = cpf_cnpj_limpo
                usuario.save()

                instalacao.cep = _normalizar_cep(cep.value)
                instalacao.cidade = str(cidade.value).strip()
                instalacao.estado = _normalizar_estado(estado.value) if str(estado.value or '').strip() else ''
                instalacao.logradouro = str(logradouro.value or '').strip()
                instalacao.numero = str(numero.value or '').strip()
                instalacao.complemento = str(complemento.value or '').strip() or None
                instalacao.save()
            except ValueError as exc:
                ui.notify(str(exc), color='negative')
                return

            auth_atual = app.storage.user.get('auth') or {}
            auth_atual['nome'] = usuario.nome
            app.storage.user['auth'] = auth_atual
            ui.run_javascript(
                "document.querySelectorAll('.rs-current-user-name').forEach(el => el.textContent = "
                f"{json.dumps(usuario.nome)})"
            )
            log_ok(f'Perfil B2C: usuario {usuario.email} atualizado')
            ui.notify('Perfil atualizado com sucesso.', color='positive')

        with ui.row().classes('w-full justify-end'):
            ui.button('Salvar perfil', on_click=salvar_perfil).props('color=primary').classes('rounded-xl px-5')
