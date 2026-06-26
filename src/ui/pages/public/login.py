from typing import Any

from nicegui import ui

from src.auth import PerfilConflitanteError, validar_email_para_profile
from src.ui.pages.public import inject_firebase_auth, inject_public_styles
from src.utils import log_info


PROFILE_CONFIG = {
    'customer': {
        'title': 'Gerador de energia',
        'subtitle': 'Acompanhe geração, créditos e detalhes da conta de luz.',
        'accent': 'secondary',
        'icon': 'bolt',
        'button': 'Enviar link de acesso',
        'helper': 'Veja geração, compensação, saldo de créditos e sinais de inconsistência.',
        'chip': 'Fluxo do gerador',
        'tab_class': 'customer',
        'panel_class': 'customer',
        'input_label': 'E-mail do gerador',
    },
    'company': {
        'title': 'Integrador solar',
        'subtitle': 'Acesse o radar comercial e os sinais de manutenção na região.',
        'accent': 'primary',
        'icon': 'travel_explore',
        'button': 'Enviar link de acesso',
        'helper': 'Acompanhe oportunidades de atendimento, O&M e conexão com clientes da região.',
        'chip': 'Fluxo do integrador',
        'tab_class': 'company',
        'panel_class': 'company',
        'input_label': 'E-mail do integrador',
    },
}


def _render_login_intro() -> None:
    with ui.column().classes('justify-center gap-5 py-4 rs-animate-up'):
        ui.image('/assets/images/logo_radarsolar.png').classes('w-52 max-w-full')
        ui.label('Acesso à plataforma').classes('text-5xl font-bold text-slate-900')
        ui.label(
            'Entre com o e-mail vinculado ao seu uso do Radar Solar. O link de acesso é enviado '
            'na hora e leva você direto para o fluxo correto.'
        ).classes('max-w-xl text-base text-slate-600 leading-7')
        ui.label(
            'Geradores acompanham usina, créditos e faturamento. Integradores acompanham oportunidades, '
            'atendimento e operação comercial na região.'
        ).classes('max-w-xl text-sm text-slate-500 leading-6')


def _send_magic_link(email_input: Any, profile_value: str) -> None:
    current_email = (email_input.value or '').strip()
    if not current_email:
        ui.notify('Informe o e-mail para receber o link.', type='warning')
        return

    try:
        current_email = validar_email_para_profile(current_email, profile_value)
    except PerfilConflitanteError as exc:
        ui.notify(str(exc), type='warning')
        return

    log_info(f'Login: enviando magic link (perfil={profile_value})')
    ui.notify('Link de acesso enviado! Verifique seu e-mail.', type='positive')
    ui.run_javascript(f'''
        (async () => {{
            const result = await window.radarSolarAuth.sendMagicLink({current_email!r}, {profile_value!r});
            if (!result.ok && result.error) {{
                alert('Erro: ' + result.error);
            }}
        }})();
    ''')


def render_login(selected_profile: str = 'customer') -> None:
    inject_public_styles()
    inject_firebase_auth()

    profiles = PROFILE_CONFIG
    if selected_profile not in profiles:
        selected_profile = 'customer'

    active_profile = {'value': selected_profile}
    profile_tabs = {}

    with ui.column().classes('w-full items-center justify-center min-h-screen px-4 py-10'):
        with ui.row().classes('rs-login-shell'):
            _render_login_intro()

            with ui.card().classes('rs-panel rs-login-panel rs-animate-up rs-animate-up-delay-1 rounded-3xl w-full max-w-2xl p-8 gap-5') as panel:
                badge = ui.label('').classes('text-sm font-semibold')
                with ui.column().classes('rs-login-copy gap-2'):
                    title = ui.label('').classes('text-3xl font-bold text-slate-900')
                    subtitle = ui.label('').classes('text-base text-slate-600 leading-7')
                    helper = ui.label('').classes('rs-login-helper text-sm text-slate-500 leading-6')

                with ui.column().classes('rounded-2xl bg-white/80 p-5 gap-4 border border-white/70'):
                    ui.label('Escolha o perfil').classes('text-sm font-semibold text-slate-500')
                    with ui.row().classes('rs-login-tabs'):
                        for key, data in profiles.items():
                            with ui.card().classes(
                                f'rs-login-tab {data["tab_class"]} rounded-2xl p-5 gap-2'
                            ) as tab:
                                profile_tabs[key] = tab
                                with ui.row().classes('items-center gap-3'):
                                    ui.icon(data['icon'], size='24px').classes(
                                        'text-secondary' if key == 'customer' else 'text-primary'
                                    )
                                    ui.label(data['title']).classes('text-lg font-bold text-slate-900')
                                ui.label(data['helper']).classes('text-sm text-slate-600 leading-6')
                                tab.on('click', lambda _=None, key=key: set_profile(key))
                    ui.label('Informe o e-mail para receber o link de acesso').classes('text-sm font-semibold text-slate-500 pt-1')
                    email = ui.input('').classes('w-full')
                    email.props('outlined')
                    ui.label('Você receberá um link seguro para entrar sem senha.').classes(
                        'text-sm text-slate-500 leading-6'
                    )

                def send_magic_link() -> None:
                    _send_magic_link(email, active_profile['value'])

                action = ui.button('', on_click=send_magic_link).classes('w-full py-3 text-base font-semibold rounded-xl rs-button-soft')
                ui.link('Voltar para a página inicial', '/').classes('text-sm text-slate-500')

    def set_profile(profile_key: str) -> None:
        active_profile['value'] = profile_key
        current = profiles[profile_key]
        badge.set_text(current['chip'])
        title.set_text(current['title'])
        subtitle.set_text(current['subtitle'])
        helper.set_text(current['helper'])
        email.label = current['input_label']
        action.set_text(current['button'])
        action.props(f"unelevated color={current['accent']}")
        badge.classes(remove='text-secondary text-primary')
        badge.classes(add='text-secondary' if profile_key == 'customer' else 'text-primary')
        panel.classes(remove='customer company')
        panel.classes(add=current['panel_class'])

        for key, tab in profile_tabs.items():
            if key == profile_key:
                tab.classes(add='is-active')
            else:
                tab.classes(remove='is-active')

    set_profile(selected_profile)
