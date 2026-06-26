from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from nicegui import app, ui

from src.models import EmpresaPerfil, Usuario
from src.utils import _buscar_endereco_por_cep, _normalizar_cep, _normalizar_estado, _only_digits, log_info, log_ok, log_erro


def _normalizar_cnpj(value: Any) -> str:
    cnpj = _only_digits(value)
    if cnpj and len(cnpj) != 14:
        raise ValueError('Informe um CNPJ valido com 14 digitos.')
    return cnpj


def _buscar_cnpj(cnpj: str) -> dict[str, str] | None:
    try:
        with urlopen(f'https://brasilapi.com.br/api/cnpj/v1/{cnpj}', timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return None

    return {
        'razao_social': data.get('razao_social') or '',
        'nome_fantasia': data.get('nome_fantasia') or '',
        'email': data.get('email') or '',
        'telefone': data.get('ddd_telefone_1') or data.get('ddd_telefone_2') or '',
        'cep': _only_digits(data.get('cep')),
        'logradouro': data.get('logradouro') or '',
        'numero': data.get('numero') or '',
        'complemento': data.get('complemento') or '',
        'cidade': data.get('municipio') or '',
        'estado': data.get('uf') or '',
    }


def _obter_ou_criar_perfil_empresa(usuario_id: int) -> EmpresaPerfil:
    perfil = EmpresaPerfil.select().where(EmpresaPerfil.usuario == usuario_id).first()
    if perfil:
        return perfil
    return EmpresaPerfil.create(usuario=usuario_id)


def _render_commercial_fields(usuario: Usuario, perfil: EmpresaPerfil):
    with ui.card().classes('w-full p-6 rounded-2xl gap-5'):
        ui.label('Dados comerciais').classes('text-lg font-semibold text-slate-900')
        ui.label(
            'O e-mail de login fica bloqueado. Use o e-mail comercial para contato com clientes.'
        ).classes('text-sm text-slate-600')

        with ui.row().classes('w-full gap-4 items-start'):
            cnpj = ui.input('CNPJ', value=usuario.cpf_cnpj or '').classes('w-56')
            buscar_cnpj = ui.button('Buscar CNPJ').props('outline color=primary').classes('rounded-xl')
            razao_social = ui.input('Razao social / nome da empresa *', value=usuario.nome).classes(
                'flex-1 min-w-72'
            )

        with ui.row().classes('w-full gap-4 items-start'):
            nome_fantasia = ui.input('Nome fantasia', value=perfil.nome_fantasia or '').classes('flex-1 min-w-64')
            email_login = ui.input('E-mail de login', value=usuario.email).classes('flex-1 min-w-64')
            email_login.disable()

        with ui.row().classes('w-full gap-4 items-start'):
            email_comercial = ui.input('E-mail comercial', value=perfil.email_comercial or '').classes(
                'flex-1 min-w-64'
            )
            telefone = ui.input('Telefone/WhatsApp', value=usuario.telefone or '').classes('w-56')
    return cnpj, buscar_cnpj, razao_social, nome_fantasia, email_comercial, telefone


def _render_address_fields(perfil: EmpresaPerfil):
    with ui.card().classes('w-full p-6 rounded-2xl gap-5'):
        ui.label('Endereco comercial').classes('text-lg font-semibold text-slate-900')
        ui.label(
            'Esses dados ajudam a posicionar a empresa na regiao de atendimento do MVP.'
        ).classes('text-sm text-slate-600')

        with ui.row().classes('w-full gap-4 items-start'):
            cep = ui.input('CEP', value=perfil.cep or '').classes('w-44')
            cidade = ui.input('Cidade', value=perfil.cidade or '').classes('flex-1 min-w-56')
            estado = ui.input('UF', value=perfil.estado or '').classes('w-24')
            buscar_cep = ui.button('Buscar CEP').props('outline color=primary').classes('rounded-xl')

        with ui.row().classes('w-full gap-4 items-start'):
            logradouro = ui.input('Logradouro', value=perfil.logradouro or '').classes('flex-1 min-w-64')
            numero = ui.input('Numero', value=perfil.numero or '').classes('w-32')
            complemento = ui.input('Complemento', value=perfil.complemento or '').classes('w-52')
    return cep, cidade, estado, buscar_cep, logradouro, numero, complemento


def _preencher_endereco_empresa(
    data: dict[str, str],
    cep: ui.input,
    logradouro: ui.input,
    numero: ui.input,
    complemento: ui.input,
    cidade: ui.input,
    estado: ui.input,
) -> None:
    cep.value = data.get('cep') or cep.value
    logradouro.value = data.get('logradouro') or ''
    numero.value = data.get('numero') or numero.value
    complemento.value = data.get('complemento') or complemento.value
    cidade.value = data.get('cidade') or ''
    estado.value = data.get('estado') or ''
    cep.update()
    logradouro.update()
    numero.update()
    complemento.update()
    cidade.update()
    estado.update()


def _bind_empresa_lookup_handlers(
    cnpj: ui.input,
    buscar_cnpj: ui.button,
    razao_social: ui.input,
    nome_fantasia: ui.input,
    email_comercial: ui.input,
    telefone: ui.input,
    cep: ui.input,
    cidade: ui.input,
    estado: ui.input,
    buscar_cep: ui.button,
    logradouro: ui.input,
    numero: ui.input,
    complemento: ui.input,
) -> None:
    def preencher_endereco(data: dict[str, str]) -> None:
        _preencher_endereco_empresa(data, cep, logradouro, numero, complemento, cidade, estado)

    def preencher_por_cnpj() -> None:
        try:
            cnpj_normalizado = _normalizar_cnpj(cnpj.value)
        except ValueError as exc:
            ui.notify(str(exc), color='warning')
            return
        if not cnpj_normalizado:
            ui.notify('Informe um CNPJ para buscar os dados da empresa.', color='warning')
            return

        dados = _buscar_cnpj(cnpj_normalizado)
        if not dados:
            ui.notify('CNPJ nao encontrado ou servico indisponivel.', color='warning')
            return

        cnpj.value = cnpj_normalizado
        razao_social.value = dados['razao_social'] or razao_social.value
        nome_fantasia.value = dados['nome_fantasia'] or nome_fantasia.value
        email_comercial.value = dados['email'] or email_comercial.value
        telefone.value = dados['telefone'] or telefone.value
        cnpj.update()
        razao_social.update()
        nome_fantasia.update()
        email_comercial.update()
        telefone.update()
        preencher_endereco(dados)
        ui.notify('Dados da empresa preenchidos pelo CNPJ.', color='positive')

    def preencher_por_cep() -> None:
        try:
            cep_normalizado = _normalizar_cep(cep.value)
        except ValueError as exc:
            ui.notify(str(exc), color='warning')
            return
        if not cep_normalizado:
            ui.notify('Informe um CEP para buscar o endereco.', color='warning')
            return

        endereco = _buscar_endereco_por_cep(cep_normalizado)
        if not endereco:
            ui.notify('CEP nao encontrado.', color='warning')
            return

        cep.value = cep_normalizado
        preencher_endereco({'cep': cep_normalizado, **endereco})
        ui.notify('Endereco preenchido pelo CEP.', color='positive')

    buscar_cnpj.on('click', preencher_por_cnpj)
    buscar_cep.on('click', preencher_por_cep)
    cep.on('blur', lambda _: preencher_por_cep() if str(cep.value or '').strip() else None)


def _render_empresa_save_button(
    usuario: Usuario,
    perfil: EmpresaPerfil,
    cnpj: ui.input,
    razao_social: ui.input,
    nome_fantasia: ui.input,
    email_comercial: ui.input,
    telefone: ui.input,
    cep: ui.input,
    cidade: ui.input,
    estado: ui.input,
    logradouro: ui.input,
    numero: ui.input,
    complemento: ui.input,
) -> None:
    def salvar_perfil() -> None:
        try:
            if not str(razao_social.value or '').strip():
                raise ValueError('O campo "Razao social / nome da empresa" e obrigatorio.')

            cnpj_limpo = _normalizar_cnpj(cnpj.value)
            if cnpj_limpo:
                dono_cnpj = Usuario.get_or_none((Usuario.cpf_cnpj == cnpj_limpo) & (Usuario.id != usuario.id))
                if dono_cnpj:
                    raise ValueError('CNPJ ja esta vinculado a outro usuario.')

            usuario.nome = str(razao_social.value).strip()
            usuario.cpf_cnpj = cnpj_limpo or None
            usuario.telefone = str(telefone.value or '').strip() or None
            usuario.save()

            perfil.nome_fantasia = str(nome_fantasia.value or '').strip() or None
            perfil.email_comercial = str(email_comercial.value or '').strip() or None
            perfil.cep = _normalizar_cep(cep.value) or None
            perfil.logradouro = str(logradouro.value or '').strip() or None
            perfil.numero = str(numero.value or '').strip() or None
            perfil.complemento = str(complemento.value or '').strip() or None
            perfil.cidade = str(cidade.value or '').strip() or None
            perfil.estado = _normalizar_estado(estado.value) or None
            perfil.save()
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
        log_ok(f'Perfil B2B: empresa {usuario.email} atualizado')
        ui.notify('Perfil da empresa atualizado com sucesso.', color='positive')

    with ui.row().classes('w-full justify-end'):
        ui.button('Salvar perfil', on_click=salvar_perfil).props('color=primary').classes('rounded-xl px-5')


def render_perfil_empresa(auth: dict) -> None:
    try:
        usuario = Usuario.get_or_none(Usuario.id == auth.get('usuario_id'))
    except Exception as exc:
        log_erro(f'Perfil: erro ao buscar usuario: {exc}')
        with ui.column().classes('w-full gap-6 p-6'):
            ui.label('Perfil da empresa').classes('text-2xl font-bold text-slate-900')
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Erro ao carregar dados do usuario.').classes('text-base text-red-600')
        return

    with ui.column().classes('w-full gap-6 p-6'):
        ui.label('Perfil da empresa').classes('text-2xl font-bold text-slate-900')

        if not usuario:
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Nao foi possivel carregar o usuario autenticado.').classes('text-base text-red-600')
            return

        try:
            perfil = _obter_ou_criar_perfil_empresa(usuario.id)
        except Exception as exc:
            log_erro(f'Perfil: erro ao criar/obter perfil: {exc}')
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label('Erro ao carregar perfil da empresa.').classes('text-base text-red-600')
            return

        try:
            cnpj, buscar_cnpj, razao_social, nome_fantasia, email_comercial, telefone = _render_commercial_fields(
                usuario, perfil
            )
            cep, cidade, estado, buscar_cep, logradouro, numero, complemento = _render_address_fields(perfil)

            _bind_empresa_lookup_handlers(
                cnpj,
                buscar_cnpj,
                razao_social,
                nome_fantasia,
                email_comercial,
                telefone,
                cep,
                cidade,
                estado,
                buscar_cep,
                logradouro,
                numero,
                complemento,
            )
            _render_empresa_save_button(
                usuario,
                perfil,
                cnpj,
                razao_social,
                nome_fantasia,
                email_comercial,
                telefone,
                cep,
                cidade,
                estado,
                logradouro,
                numero,
                complemento,
            )
        except Exception as exc:
            log_erro(f'Perfil: erro ao renderizar campos: {exc}')
            with ui.card().classes('w-full p-6 rounded-2xl'):
                ui.label(f'Erro ao renderizar formulario: {exc}').classes('text-base text-red-600')
