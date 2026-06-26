from __future__ import annotations

from collections.abc import Callable

from nicegui import ui

from src.ui.pages.cliente.dashboard import render_dashboard
from src.ui.pages.cliente.faturas import render_faturas
from src.ui.pages.cliente.perfil import render_perfil


CLIENT_SECTIONS: dict[str, dict] = {
    'perfil': {
        'title': 'Perfil do cliente',
        'subtitle': 'Dados de contato e instalacao.',
        'icon': 'person',
        'label': 'Perfil',
        'render': render_perfil,
    },
    'dashboard': {
        'title': 'Dashboard do gerador',
        'subtitle': 'Acompanhamento da usina e dos creditos.',
        'icon': 'dashboard',
        'label': 'Dashboard',
        'render': render_dashboard,
    },
    'faturas': {
        'title': 'Faturas',
        'subtitle': 'Insercao e historico de contas de energia.',
        'icon': 'receipt_long',
        'label': 'Faturas',
        'render': render_faturas,
    },
}


def render_cliente_spa(auth: dict, initial_section: str) -> None:
    section_key = initial_section if initial_section in CLIENT_SECTIONS else 'perfil'
    nav_buttons = {}

    ui.add_head_html('''
    <style>
        .rs-private-body {
            background: linear-gradient(180deg, #f8fafc 0%, #eef4ff 100%);
        }
    </style>
    ''')
    ui.query('body').classes(add='rs-private-body')

    drawer = ui.left_drawer(value=True, top_corner=True, bottom_corner=True).classes('bg-orange-600 text-white w-72 px-4 py-5')
    with drawer:
        with ui.column().classes('w-full gap-6'):
            with ui.row().classes('items-center gap-3'):
                ui.image('/assets/images/logo_radarsolar.png').classes('w-12')
                with ui.column().classes('gap-0'):
                    ui.label('Radar Solar').classes('text-base font-bold')
                    ui.label('Area autenticada').classes('text-xs text-white/70')

            with ui.column().classes('gap-2'):
                ui.label(auth['nome']).classes('text-lg font-semibold rs-current-user-name')
                ui.label(auth['email']).classes('text-sm text-white/70')

            with ui.column().classes('w-full gap-2'):
                for key, section in CLIENT_SECTIONS.items():
                    with ui.button(on_click=lambda key=key: switch_section(key)).props('flat color=white').classes(
                        'w-full justify-start rounded-xl px-4 py-3 normal-case text-slate-300'
                    ) as button:
                        nav_buttons[key] = button
                        with ui.row().classes('items-center gap-3'):
                            ui.icon(section['icon'], size='20px')
                            ui.label(section['label']).classes('text-sm font-medium')

            ui.space()
            ui.button('Sair', on_click=lambda: ui.navigate.to('/logout')).props('outline color=white').classes(
                'w-full rounded-xl'
            )

    with ui.header().classes('bg-white/85 shadow-sm backdrop-blur-md px-6 py-3 items-center justify-between'):
        with ui.row().classes('items-center gap-3'):
            ui.button(icon='menu', on_click=drawer.toggle).props('flat round color=primary').classes('shrink-0')
            with ui.column().classes('gap-0'):
                header_title = ui.label('').classes('text-xl font-bold text-slate-900')
                header_subtitle = ui.label('').classes('text-sm text-slate-500')

    content = ui.column().classes('w-full')

    def update_active_nav(active_key: str) -> None:
        for key, button in nav_buttons.items():
            if key == active_key:
                button.classes(remove='text-slate-300')
                button.classes(add='bg-white/12 text-white')
            else:
                button.classes(remove='bg-white/12 text-white')
                button.classes(add='text-slate-300')

    def switch_section(key: str) -> None:
        section = CLIENT_SECTIONS[key]
        header_title.set_text(section['title'])
        header_subtitle.set_text(section['subtitle'])
        update_active_nav(key)
        content.clear()
        with content:
            render: Callable = section['render']
            if key == 'dashboard':
                render(auth, refresh_callback=lambda: switch_section('dashboard'))
            else:
                render(auth)

    switch_section(section_key)
