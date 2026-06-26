from nicegui import ui

from src.ui.pages.public import inject_firebase_auth, inject_public_styles


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

    def complete_magic_link():
        ui.run_javascript('''
            (async () => {
                const result = await window.radarSolarAuth.completeSignIn();
                if (result.status === 'success') {
                    const p = result.payload;
                    window.location.href = '/auth/exchange?id_token=' + encodeURIComponent(p.idToken)
                        + '&profile=' + encodeURIComponent(p.profile)
                        + '&email=' + encodeURIComponent(p.email)
                        + '&firebase_uid=' + encodeURIComponent(p.firebase_uid)
                        + '&display_name=' + encodeURIComponent(p.display_name || '');
                } else if (result.status === 'error') {
                    window.location.href = '/login?error=' + encodeURIComponent(result.error);
                }
            })();
        ''')

    ui.timer(0.4, complete_magic_link, once=True)
