import os
import time

import httpx
from nicegui import app, ui

from src.auth import PerfilConflitanteError, criar_ou_atualizar_usuario, rota_inicial, serializar_sessao
from src.ui.pages.public import inject_firebase_auth, inject_public_styles
from src.utils import log_aviso, log_info, log_ok


FIREBASE_API_KEY = os.getenv('FIREBASE_API_KEY', '')


async def _verificar_token_firebase(id_token: str) -> dict | None:
    if not id_token or not FIREBASE_API_KEY:
        return None
    url = f'https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={FIREBASE_API_KEY}'
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, json={'idToken': id_token}, timeout=10)
            if r.status_code == 200:
                users = r.json().get('users', [])
                if users:
                    return users[0]
    except Exception:
        pass
    return None


def render_auth_confirm() -> None:
    inject_public_styles()
    inject_firebase_auth()

    with ui.column().classes('w-full min-h-screen items-center justify-center px-4'):
        with ui.card().classes('rs-panel rounded-3xl w-full max-w-lg p-8 items-center text-center gap-5'):
            ui.spinner(size='lg').classes('text-secondary')
            ui.label('Confirmando acesso').classes('text-3xl font-bold text-slate-900')
            ui.label(
                'Estamos validando o link enviado para o seu e-mail e preparando a area correta do Radar Solar.'
            ).classes('text-base text-slate-600 leading-7')

    async def complete_magic_link() -> None:
        result = await ui.run_javascript(
            '(async () => { return await window.radarSolarAuth.completeSignIn(); })()',
            timeout=60,
        )
        if not result:
            return
        if result.get('status') == 'error':
            ui.notify(result.get('error', 'Nao foi possivel concluir o acesso.'), type='negative')
            ui.navigate.to('/login')
            return
        if result.get('status') == 'success':
            payload = result.get('payload') or {}
            id_token = payload.get('idToken', '')
            verified = await _verificar_token_firebase(id_token)
            if not verified:
                log_aviso('Auth: token Firebase invalido ou nao verificado')
                ui.notify('Nao foi possivel validar sua identidade. Tente novamente.', type='negative')
                ui.navigate.to('/login')
                return
            verified_uid = verified.get('localId', '')
            verified_email = verified.get('email', '') or payload.get('email', '')
            if verified_uid != payload.get('firebase_uid', ''):
                log_aviso(f'Auth: UID divergente (payload={payload.get("firebase_uid")}, verified={verified_uid})')
                ui.notify('Falha de seguranca na autenticacao.', type='negative')
                ui.navigate.to('/login')
                return
            try:
                usuario, _created = criar_ou_atualizar_usuario(
                    firebase_uid=verified_uid,
                    email=verified_email,
                    profile=payload.get('profile', 'customer'),
                    nome=payload.get('display_name', ''),
                )
            except PerfilConflitanteError as exc:
                ui.notify(str(exc), type='negative')
                ui.navigate.to('/login')
                return
            log_ok(f'Auth confirm: {verified_email} autenticado com sucesso (perfil={payload.get("profile")})')
            app.storage.user['auth'] = serializar_sessao(usuario, payload.get('profile', 'customer'))
            app.storage.user['auth_created_at'] = time.time()
            ui.navigate.to(rota_inicial(payload.get('profile', 'customer')))

    ui.timer(0.4, complete_magic_link, once=True)
