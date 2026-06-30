import os
import time
from collections import defaultdict
from pathlib import Path

import httpx
from nicegui import app, ui
from dotenv import load_dotenv
from fastapi import Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# load_dotenv() antes dos imports locais para que src/database.py
# veja DATABASE_URL do .env
load_dotenv()

from src.auth import PerfilConflitanteError, criar_ou_atualizar_usuario, rota_inicial, serializar_sessao
from src.models import criar_tabelas, Usuario
from src.ui.layout import render_private_shell
from src.ui.pages.cliente.spa import render_cliente_spa
from src.ui.pages.empresa.kanban import render_kanban
from src.ui.pages.empresa.mapa import render_mapa
from src.ui.pages.empresa.perfil import render_perfil_empresa
from src.ui.pages.public.auth_confirm import render_auth_confirm
from src.ui.pages.public.homepage import render_homepage
from src.ui.pages.public.login import render_login
from src.utils import log_info, log_ok, log_erro, log_aviso, log_separador
from src.api.routes import router

_ENV_REQUIRED = ['FIREBASE_API_KEY', 'FIREBASE_PROJECT_ID', 'RADAR_SOLAR_STORAGE_SECRET']
for _key in _ENV_REQUIRED:
    if not os.getenv(_key):
        raise RuntimeError(f'{_key} nao definido no .env! Copie .env.example para .env e preencha os valores.')

# ── CONSTANTES DE SEGURANÇA ──────────────────────────────────────────────────
SESSION_TTL_SECONDS = 24 * 60 * 60
ALLOWED_ORIGINS = os.getenv('ALLOWED_ORIGINS', 'http://localhost:8080').split(',')
FORCE_HTTPS = os.getenv('FORCE_HTTPS', '').lower() in ('1', 'true', 'yes')
RATE_LIMIT_REQUESTS = int(os.getenv('RATE_LIMIT_REQUESTS', '60'))
RATE_LIMIT_WINDOW = int(os.getenv('RATE_LIMIT_WINDOW', '60'))

# ── INICIALIZAÇÃO ───────────────────────────────────────────────────────────
CURRENT_DIR = Path(__file__).parent
ASSETS_DIR = CURRENT_DIR / 'ui' / 'assets'

log_separador('Radar Solar - Inicializacao')

log_info('Criando/verificando tabelas do banco de dados...')
try:
    criar_tabelas()
    log_ok('Tabelas verificadas/criadas com sucesso')
except Exception as exc:
    log_erro(f'Falha ao criar tabelas: {exc}')

log_info('Registrando rotas de arquivos estaticos...')
app.add_static_files('/assets', str(ASSETS_DIR))
app.add_static_files('/empresa/static', str(CURRENT_DIR / 'ui' / 'pages' / 'empresa' / 'static'))
log_ok('Arquivos estaticos registrados: /assets, /demo/static')

log_info('Registrando rota de backup...')
_backup_secret = os.getenv('RADAR_SOLAR_STORAGE_SECRET', '')

@app.get('/api/backup')
async def api_backup(token: str = ''):
    if not _backup_secret or token != _backup_secret:
        return JSONResponse({'error': 'Nao autorizado'}, status_code=401)
    from pathlib import Path
    db_path = Path(__file__).resolve().parent.parent / 'data' / 'radarsolar.db'
    if not db_path.exists():
        return JSONResponse({'error': 'Banco nao encontrado'}, status_code=404)
    from fastapi.responses import Response as FastResponse
    data = db_path.read_bytes()
    return FastResponse(
        data,
        media_type='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename="radarsolar-{time.strftime("%Y%m%d")}.db"',
            'Content-Length': str(len(data)),
        },
    )

log_separador()

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=['GET'],
    allow_headers=['*'],
    expose_headers=['*'],
)

# ── RATE LIMITER (IN-MEMORY) ─────────────────────────────────────────────────
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

def check_rate_limit(ip: str) -> bool:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    timestamps = _rate_limit_store[ip]
    while timestamps and timestamps[0] < window_start:
        timestamps.pop(0)
    if len(timestamps) >= RATE_LIMIT_REQUESTS:
        return False
    timestamps.append(now)
    return True

# ── MIDDLEWARE: SEGURANÇA + RATE LIMIT ────────────────────────────────────────
@app.middleware('http')
async def security_middleware(request: Request, call_next):
    response = await call_next(request)

    if request.url.path.startswith('/api'):
        ip = request.client.host if request.client else 'unknown'
        if not check_rate_limit(ip):
            return JSONResponse(
                status_code=429,
                content={'error': 'Muitas requisicoes. Aguarde e tente novamente.'},
                headers={
                    'Retry-After': str(RATE_LIMIT_WINDOW),
                    'Access-Control-Allow-Origin': ','.join(ALLOWED_ORIGINS),
                },
            )

        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        if FORCE_HTTPS:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    return response

# ── FUNÇÕES AUXILIARES E GUARDA DE ROTAS ─────────────────────────────────────
def apply_theme() -> None:
    ui.colors(primary='#1D293B', secondary='#F97316', accent='#FFD700', dark='#0F172A')

def render_redirect(path: str, message: str = 'Redirecionando...') -> None:
    with ui.column().classes('w-full min-h-screen items-center justify-center gap-4'):
        ui.spinner(size='lg').classes('text-secondary')
        ui.label(message).classes('text-base text-slate-600')
    ui.timer(0.1, lambda: ui.navigate.to(path), once=True)

def verificar_autenticacao(perfil_exigido: str) -> dict | None:
    """Guarda de Rotas Centralizado: Verifica perfil, sessão e expiração do usuário."""
    auth = app.storage.user.get('auth')
    log_info(f'Verificando Acesso ({perfil_exigido})...')

    if not auth or auth.get('profile') != perfil_exigido:
        log_aviso(f'Acesso negado para o perfil {perfil_exigido}.')
        apply_theme()
        render_redirect(f'/login?profile={perfil_exigido}')
        return None

    auth_created = app.storage.user.get('auth_created_at', 0)
    if auth_created and (time.time() - auth_created) > SESSION_TTL_SECONDS:
        log_aviso(f'Sessao expirada.')
        app.storage.user.pop('auth', None)
        app.storage.user.pop('auth_created_at', None)
        apply_theme()
        render_redirect(f'/login?profile={perfil_exigido}')
        return None

    usuario_id = auth.get('usuario_id')
    if usuario_id is not None:
        existe = Usuario.select().where(Usuario.id == usuario_id).exists()
        if not existe:
            log_aviso(f'Sessao invalida: usuario {usuario_id} nao existe no banco.')
            app.storage.user.pop('auth', None)
            app.storage.user.pop('auth_created_at', None)
            apply_theme()
            render_redirect(f'/login?profile={perfil_exigido}')
            return None

    return auth

# ── ESCUDO DE SEGURANÇA: TRATAMENTO GLOBAL DE ERROS ─────────────────────────
@app.exception_handler(Exception)
async def escudo_global_de_erros(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        raise exc

    log_erro(f'Excecao em {request.url.path}: {type(exc).__name__}')

    if request.url.path.startswith('/api'):
        return JSONResponse(
            status_code=500,
            content={'error': 'Erro interno do servidor.'},
        )

    raise exc

# ── ROTAS PÚBLICAS ───────────────────────────────────────────────────────────
@ui.page('/')
def home() -> None:
    log_info('ROTA /')
    apply_theme()
    render_homepage()

@ui.page('/demo/mapa')
def demo_mapa() -> None:
    log_info('ROTA /demo/mapa')
    apply_theme()
    render_mapa('/api/demo/mapa-rmr', show_header=True, include_leads=False)

@ui.page('/login')
def login(profile: str = 'company') -> None:
    log_info(f'ROTA /login (profile={profile})')
    auth = app.storage.user.get('auth')
    if auth:
        apply_theme()
        render_redirect('/cliente/dashboard' if auth.get('profile') == 'customer' else '/empresa/mapa')
        return
    apply_theme()
    render_login(profile)

@ui.page('/auth/confirm')
def auth_confirm() -> None:
    log_info('ROTA /auth/confirm')
    auth = app.storage.user.get('auth')
    if auth:
        apply_theme()
        render_redirect('/cliente/dashboard' if auth.get('profile') == 'customer' else '/empresa/mapa')
        return
    apply_theme()
    render_auth_confirm()

def _verificar_token_firebase_sync(id_token: str) -> dict | None:
    if not id_token:
        return None
    api_key = os.getenv('FIREBASE_API_KEY', '')
    url = f'https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={api_key}'
    try:
        with httpx.Client() as client:
            r = client.post(url, json={'idToken': id_token}, timeout=10)
            if r.status_code == 200:
                users = r.json().get('users', [])
                if users:
                    return users[0]
    except Exception:
        pass
    return None

@ui.page('/auth/exchange')
def auth_exchange(request: Request) -> None:
    log_info('ROTA /auth/exchange')
    auth = app.storage.user.get('auth')
    if auth:
        apply_theme()
        render_redirect('/cliente/dashboard' if auth.get('profile') == 'customer' else '/empresa/mapa')
        return

    id_token = request.query_params.get('id_token', '')
    profile = request.query_params.get('profile', 'customer')
    email = request.query_params.get('email', '')
    firebase_uid = request.query_params.get('firebase_uid', '')
    display_name = request.query_params.get('display_name', '')

    if not id_token or not email or not firebase_uid:
        log_aviso('Auth: exchange com parametros insuficientes')
        apply_theme()
        render_redirect('/login', 'Link de acesso invalido.')
        return

    verified = _verificar_token_firebase_sync(id_token)
    if not verified:
        log_aviso('Auth: token Firebase invalido no exchange')
        apply_theme()
        render_redirect('/login', 'Nao foi possivel validar sua identidade.')
        return

    verified_uid = verified.get('localId', '')
    verified_email = verified.get('email', '') or email

    if verified_uid != firebase_uid:
        log_aviso(f'Auth: UID divergente (payload={firebase_uid}, verified={verified_uid})')
        apply_theme()
        render_redirect('/login', 'Falha de seguranca na autenticacao.')
        return

    try:
        usuario, _created = criar_ou_atualizar_usuario(
            firebase_uid=verified_uid,
            email=verified_email,
            profile=profile,
            nome=display_name,
        )
    except PerfilConflitanteError as exc:
        log_aviso(f'Auth: conflito de perfil no exchange: {exc}')
        apply_theme()
        render_redirect('/login', str(exc))
        return

    log_ok(f'Auth exchange: {verified_email} autenticado com sucesso (perfil={profile})')
    app.storage.user['auth'] = serializar_sessao(usuario, profile)
    app.storage.user['auth_created_at'] = time.time()
    apply_theme()
    render_redirect(rota_inicial(profile))

@ui.page('/logout')
def logout() -> None:
    log_info('ROTA /logout')
    app.storage.user.pop('auth', None)
    apply_theme()
    render_redirect('/login', 'Saindo da conta...')

# ── ROTAS PRIVADAS: CLIENTE ──────────────────────────────────────────────────
@ui.page('/cliente/dashboard')
def cliente_dashboard() -> None:
    auth = verificar_autenticacao('customer')
    if not auth: return
    apply_theme()
    render_cliente_spa(auth, 'dashboard')

@ui.page('/cliente/faturas')
def cliente_faturas() -> None:
    auth = verificar_autenticacao('customer')
    if not auth: return
    apply_theme()
    render_cliente_spa(auth, 'faturas')

@ui.page('/cliente/perfil')
def cliente_perfil() -> None:
    auth = verificar_autenticacao('customer')
    if not auth: return
    apply_theme()
    render_cliente_spa(auth, 'perfil')

# ── ROTAS PRIVADAS: EMPRESA ──────────────────────────────────────────────────
@ui.page('/empresa/mapa')
def empresa_mapa() -> None:
    auth = verificar_autenticacao('company')
    if not auth: return
    apply_theme()
    render_private_shell(auth, '/empresa/mapa', 'Mapa do integrador', 'Concentracao de instalacoes e oportunidades.')
    render_mapa(data_url='/api/empresa/mapa-rmr')

@ui.page('/empresa/perfil')
def empresa_perfil() -> None:
    auth = verificar_autenticacao('company')
    if not auth: return
    apply_theme()
    render_private_shell(auth, '/empresa/perfil', 'Perfil da empresa', 'Dados comerciais e regiao de atendimento.')
    render_perfil_empresa(auth)

@ui.page('/empresa/kanban')
def empresa_kanban() -> None:
    auth = verificar_autenticacao('company')
    if not auth: return
    apply_theme()
    render_private_shell(auth, '/empresa/kanban', 'Kanban comercial', 'Acompanhamento do pipeline de atendimento.')
    render_kanban(auth)

# ── INCLUSÃO DE ROTAS DE API ─────────────────────────────────────────────────
app.include_router(router)

# ── INICIALIZAÇÃO BLINDADA DO SERVIDOR ────────────────────────────────────────
STORAGE_SECRET = os.getenv('RADAR_SOLAR_STORAGE_SECRET')

if not STORAGE_SECRET:
    raise RuntimeError('RADAR_SOLAR_STORAGE_SECRET nao definido no .env!')

SERVER_HOST = os.getenv('SERVER_HOST', 'localhost')
SERVER_PORT = int(os.getenv('SERVER_PORT', '8080'))

session_kwargs = {
    'https_only': FORCE_HTTPS,
    'same_site': 'strict',
}

log_info(f'Iniciando servidor NiceGUI em {SERVER_HOST}:{SERVER_PORT}...')
ui.run(
    title='Radar Solar - Inteligência Energética',
    host=SERVER_HOST,
    port=SERVER_PORT,
    storage_secret=STORAGE_SECRET,
    session_middleware_kwargs=session_kwargs,
)
