from __future__ import annotations

from fastapi import Request
from nicegui import ui

from src.auth import rota_inicial


NAV_ITEMS = {
    'customer': [
        ('/cliente/perfil', 'person', 'Perfil'),
        ('/cliente/dashboard', 'dashboard', 'Dashboard'),
        ('/cliente/faturas', 'receipt_long', 'Faturas'),
    ],
    'company': [
        ('/empresa/perfil', 'person', 'Perfil'),
        ('/empresa/mapa', 'map', 'Mapa'),
        ('/empresa/kanban', 'view_kanban', 'Kanban'),
    ],
}


def require_auth(request: Request, expected_profile: str | None = None) -> dict | None:
    auth = request.session.get('auth')
    if not auth:
        return None
    if expected_profile and auth.get('profile') != expected_profile:
        return None
    return auth


def render_private_shell(auth: dict, current_path: str, title: str, subtitle: str) -> None:
    profile = auth['profile']
    items = NAV_ITEMS[profile]
    drawer_classes = {
        'customer': 'bg-orange-600 text-white',
        'company': 'bg-slate-900 text-white',
    }[profile]
    drawer_caption = 'Area autenticada' if profile == 'customer' else 'Integrador solar'

    ui.add_head_html('''
    <style>
        .rs-private-body {
            background: linear-gradient(180deg, #f8fafc 0%, #eef4ff 100%);
        }
    </style>
    ''')
    ui.query('body').classes(add='rs-private-body')

    drawer = ui.left_drawer(value=True, top_corner=True, bottom_corner=True).classes(f'{drawer_classes} w-72 px-4 py-5')
    with drawer:
        with ui.column().classes('w-full gap-6'):
            with ui.row().classes('items-center gap-3'):
                ui.image('/assets/images/logo_radarsolar.png').classes('w-12')
                with ui.column().classes('gap-0'):
                    ui.label('Radar Solar').classes('text-base font-bold')
                    ui.label(drawer_caption).classes('text-xs text-white/70')

            with ui.column().classes('gap-2'):
                ui.label(auth['nome']).classes('text-lg font-semibold rs-current-user-name')
                ui.label(auth['email']).classes('text-sm text-white/70')

            with ui.column().classes('w-full gap-2'):
                for path, icon, label in items:
                    active_class = 'bg-white/12 text-white' if path == current_path else 'text-slate-300'
                    with ui.button(on_click=lambda path=path: ui.navigate.to(path)).props('flat color=white').classes(
                        f'w-full justify-start rounded-xl px-4 py-3 normal-case {active_class}'
                    ):
                        with ui.row().classes('items-center gap-3'):
                            ui.icon(icon, size='20px')
                            ui.label(label).classes('text-sm font-medium')

            ui.space()
            ui.button('Sair', on_click=lambda: ui.navigate.to('/logout')).props('outline color=white').classes(
                'w-full rounded-xl'
            )

    with ui.header().classes('bg-white/85 shadow-sm backdrop-blur-md px-6 py-3 items-center justify-between'):
        with ui.row().classes('items-center gap-3'):
            ui.button(icon='menu', on_click=drawer.toggle).props('flat round color=primary').classes('shrink-0')
            with ui.column().classes('gap-0'):
                ui.label(title).classes('text-xl font-bold text-slate-900')
                ui.label(subtitle).classes('text-sm text-slate-500')


def redirect_path_for(auth: dict) -> str:
    return rota_inicial(auth.get('profile'))
