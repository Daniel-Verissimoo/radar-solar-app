from nicegui import ui

from src.ui.pages.public import inject_public_styles


HERO_FEATURES = [
    ('Leitura simplificada', 'Conta de luz', 'Geração, injeção e créditos em uma visão objetiva.', 'receipt_long', 'text-secondary'),
    ('Conexão local', 'Rede de integradores', 'Especialistas próximos para análise, suporte e manutenção.', 'hub', 'text-primary'),
    ('Ativação rápida', 'O&M', 'Ação mais ágil quando a usina ou o faturamento saírem do esperado.', 'build_circle', 'text-secondary'),
]

PRODUCT_ITEMS = [
    'Monitoramento visual da geração, da injeção na rede e do saldo de créditos.',
    'Leitura simplificada da conta de luz para evidenciar erros e inconsistências.',
    'Encaminhamento ágil para integradores quando houver queda de eficiência ou problema de faturamento.',
]

PROFILE_CARDS = [
    {
        'icon': 'bolt',
        'icon_class': 'text-secondary',
        'title': 'Gerador de energia',
        'description': 'Acompanha a usina, entende a conta de luz e aciona suporte quando surge uma inconsistência.',
        'items': [
            'Visualização da geração, da compensação e do saldo de créditos.',
            'Leitura mais objetiva das cobranças e do faturamento da distribuidora.',
            'Solicitação rápida de apoio técnico quando a usina sair do esperado.',
        ],
        'button': 'Seguir como gerador',
        'url': '/login?profile=customer',
        'props': 'unelevated color=secondary',
        'delay': 'rs-animate-up-delay-2',
    },
    {
        'icon': 'travel_explore',
        'icon_class': 'text-primary',
        'title': 'Integrador solar',
        'description': 'Enxerga demanda real na região e transforma sinais do cliente em oportunidade comercial e técnica.',
        'items': [
            'Mapa de calor com concentração de instalações e potencial de atendimento.',
            'Leads vindos de inconsistências percebidas por quem já gera energia.',
            'Mais previsibilidade para serviços recorrentes de O&M e pós-venda.',
        ],
        'button': 'Seguir como integrador',
        'url': '/login?profile=company',
        'props': 'unelevated color=primary',
        'delay': 'rs-animate-up-delay-3',
    },
]


def _render_header() -> None:
    with ui.header().classes('bg-white/82 text-primary items-center justify-center px-4 py-2 shadow-sm backdrop-blur-md'):
        with ui.row().classes('w-full max-w-7xl items-center justify-between'):
            with ui.row().classes('items-center gap-3'):
                ui.image('/assets/images/logo_radarsolar.png').classes('w-16 max-w-full')
                with ui.column().classes('gap-0'):
                    ui.label('Radar Solar').classes('text-base font-bold text-slate-900')
                    ui.label('Monitoramento e conexão em energia solar').classes('text-xs text-slate-500')
            ui.button('Entrar', on_click=lambda: ui.navigate.to('/login')).props('unelevated color=secondary').classes('min-w-36 px-10 py-3 text-base font-semibold rs-button-soft')


def _render_hero() -> None:
    with ui.column().classes('justify-center gap-6 py-4 rs-animate-up'):
        ui.label('Radar Solar').classes('rs-badge text-sm font-semibold text-secondary')
        ui.label('A plataforma que conecta quem gera energia solar a quem mantém a operação funcionando.').classes(
            'rs-hero-title text-[clamp(2.4rem,4.8vw,4.5rem)] font-bold text-slate-900 max-w-3xl'
        )
        ui.label(
            'Para o gerador, o Radar Solar organiza geração, injeção na rede, saldo de créditos e leitura da '
            'conta de luz em uma visão clara. Quando surgem inconsistências, a plataforma aproxima o usuário '
            'do integrador certo para manutenção ou análise de faturamento.'
        ).classes('max-w-2xl text-lg text-slate-600 leading-8')

        with ui.row().classes('w-full pt-1'):
            ui.button('Entrar', on_click=lambda: ui.navigate.to('/login')).props(
                'unelevated color=secondary').classes('w-full px-10 py-4 text-base font-semibold rounded-2xl rs-button-soft')

        with ui.column().classes('w-full gap-4 pt-4 justify-between flex-1'):
            with ui.row().classes('w-full gap-4 no-wrap items-stretch'):
                for index, (eyebrow, value, label, icon, tone) in enumerate(HERO_FEATURES, start=1):
                    delay_class = f'rs-animate-up-delay-{min(index, 3)}'
                    with ui.column().classes(f'rs-panel rs-hover-soft rs-animate-up {delay_class} rounded-xl px-5 py-5 flex-1 min-w-0 gap-3 justify-between h-full min-h-[164px]'):
                        with ui.row().classes('items-center justify-between'):
                            ui.label(eyebrow).classes('text-xs font-semibold text-slate-500')
                            ui.icon(icon, size='22px').classes(tone)
                        ui.label(value).classes('text-xl font-bold text-slate-900')
                        ui.label(label).classes('text-sm text-slate-600 leading-6')


def _render_product_panel() -> None:
    with ui.column().classes('rs-panel rs-animate-up rs-animate-up-delay-2 rounded-2xl p-6 md:p-8 gap-5 justify-between self-center'):
        ui.label('Visão do produto').classes('text-xl font-bold text-primary')
        with ui.column().classes('gap-4'):
            with ui.row().classes('w-full items-stretch gap-4 rs-grid'):
                with ui.column().classes('rounded-xl bg-slate-900 px-5 py-5 gap-2 items-center text-center'):
                    ui.label('Usina monitorada').classes('text-sm font-medium text-slate-300')
                    ui.label('94%').classes('text-4xl font-bold text-white')
                    ui.label('eficiência na geração do mês').classes('text-sm text-slate-400')
                with ui.column().classes('rounded-xl bg-orange-500 px-5 py-5 gap-2 items-center text-center'):
                    ui.label('Créditos em energia').classes('text-sm font-medium text-orange-100')
                    ui.label('182 kWh').classes('text-4xl font-bold text-white')
                    ui.label('saldo projetado para o próximo ciclo').classes('text-sm text-orange-50')
            with ui.column().classes('rounded-xl border border-slate-200 bg-white px-5 py-5 gap-4'):
                ui.label('O que o Radar Solar organiza').classes('text-lg font-bold text-slate-900')
                for item in PRODUCT_ITEMS:
                    ui.label(f'• {item}').classes('text-sm text-slate-600 leading-6')
            with ui.column().classes('rounded-xl border border-slate-200 bg-slate-50 px-5 py-5 gap-3'):
                ui.label('Cobertura inicial').classes('text-sm font-semibold text-slate-500')
                ui.label('Região Metropolitana do Recife').classes('text-2xl font-bold text-slate-900')
                ui.label(
                    'Começamos pela RMR para concentrar a rede de integradores e acelerar conexões qualificadas '
                    'entre geração distribuída e operação local.'
                ).classes('text-sm text-slate-600 leading-6')


def _render_profile_card(card: dict) -> None:
    with ui.card().classes(f'rs-panel rs-card rs-animate-up {card["delay"]} rounded-2xl p-8 gap-5 h-full items-center text-center'):
        with ui.row().classes('items-center justify-center gap-4 w-full'):
            ui.icon(card['icon'], size='34px').classes(card['icon_class'])
            ui.label(card['title']).classes('text-2xl font-bold text-slate-900')
        ui.label(card['description']).classes('text-base text-slate-600 leading-7 text-center')
        with ui.column().classes('w-full items-center gap-3'):
            for item in card['items']:
                ui.label(item).classes('max-w-md text-sm text-slate-700 text-center')
        ui.button(card['button'], on_click=lambda url=card['url']: ui.navigate.to(url)).props(
            card['props']).classes('mt-auto w-full py-3 font-semibold rounded-xl rs-button-soft')


def _render_profiles() -> None:
    with ui.column().classes('w-full items-center gap-4 pt-0 text-center rs-animate-up rs-animate-up-delay-2'):
        ui.label('Dois fluxos, uma mesma plataforma').classes('text-3xl font-bold text-primary text-center')
        ui.label('Cada perfil entra no produto com contexto próprio, sem perder a conexão entre acompanhamento e serviço.').classes(
            'max-w-3xl text-base text-slate-600 text-center'
        )

        with ui.row().classes('w-full items-stretch justify-center gap-6 rs-grid'):
            for card in PROFILE_CARDS:
                _render_profile_card(card)


def _render_footer() -> None:
    with ui.column().classes('w-full items-center mt-14 border-t border-slate-200/80 px-4 py-8'):
        ui.label('Radar Solar © 2026').classes('text-sm font-medium text-slate-500')
        ui.label('Transparência energética para quem gera e prospecção qualificada para quem integra.').classes(
            'text-sm text-slate-400 text-center'
        )


def render_homepage() -> None:
    inject_public_styles()
    _render_header()

    with ui.column().classes('rs-shell w-full items-center pb-16'):
        with ui.column().classes('w-full max-w-7xl px-4 pt-8 gap-10'):
            with ui.row().classes('w-full items-stretch gap-6 rs-grid min-h-[calc(100vh-8rem)]'):
                _render_hero()
                _render_product_panel()

            _render_profiles()

        _render_footer()
