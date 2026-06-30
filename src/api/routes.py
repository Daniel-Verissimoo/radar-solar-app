import time, traceback, json
from fastapi import APIRouter, Request as FastAPIRequest, Query
from fastapi.responses import Response, JSONResponse
from nicegui import app
from src.database import db
from src.models import CnpjCache, Lead, LeadLog, Usuario
from src.services.geo_service import carregar_geojson_rmr
from src.ui.pages.empresa.mapa import (
    montar_mapa_json,
    carregar_pjs_mapa,
    carregar_leads_mapa,
    MAPA_EMPRESA_TOKENS,
)
from src.utils import log_erro, log_ok, log_aviso

_last_capture_error: str | None = None

router = APIRouter(tags=["Mapas API"])

@router.get('/api/empresa/mapa-rmr')
async def api_empresa_mapa_rmr(
    request: FastAPIRequest,
    token: str = Query(default="", max_length=100, pattern="^[a-zA-Z0-9_-]*$")
) -> Response:

    now = time.time()

    for stored_token, expires_at in list(MAPA_EMPRESA_TOKENS.items()):
        if expires_at < now:
            MAPA_EMPRESA_TOKENS.pop(stored_token, None)

    if not token or MAPA_EMPRESA_TOKENS.get(token, 0) < now:
        return JSONResponse({'error': 'Nao autorizado'}, status_code=401)

    try:
        data = carregar_geojson_rmr()
        return Response(
            montar_mapa_json(
                leads=carregar_leads_mapa(data),
                pjs=carregar_pjs_mapa(data),
            ),
            media_type='application/json',
            headers={'Cache-Control': 'no-store'},
        )
    except Exception:
        tb = traceback.format_exc()
        log_erro(f'Falha interna ao montar mapa-rmr da empresa:\n{tb}')
        return JSONResponse({'error': 'Erro interno do servidor.'}, status_code=500)

@router.post('/api/empresa/capturar-lead')
async def api_empresa_capturar_lead(request: FastAPIRequest) -> JSONResponse:
    auth = app.storage.user.get('auth')
    if not auth or auth.get('profile') != 'company':
        return JSONResponse({'error': 'Nao autorizado'}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({'error': 'JSON invalido'}, status_code=400)

    cnpj = (body.get('cnpj') or '').strip()
    if not cnpj:
        return JSONResponse({'error': 'CNPJ obrigatorio'}, status_code=400)

    nome = (body.get('nome') or 'Cliente do mapa').strip()
    endereco = (body.get('endereco') or '').strip()
    telefone = (body.get('telefone') or '').strip()

    try:
        empresa_id = int(auth['usuario_id'])
        empresa = Usuario.get_by_id(empresa_id)

        existing_lead = Lead.select().where(
            Lead.empresa_responsavel == empresa_id,
            Lead.origem == 'Mapa RMR - Captura de lead',
            Lead.descricao_servico ** f'%{cnpj}%',
        ).first()
        if existing_lead:
            return JSONResponse({'error': 'Lead ja capturado', 'lead_id': existing_lead.id}, status_code=409)

        with db.atomic():
            cliente = Usuario.get_or_none(Usuario.cpf_cnpj == cnpj)
            if not cliente:
                cliente = Usuario.create(
                    firebase_uid=None,
                    nome=nome or f'CNPJ {cnpj}',
                    email=f'{cnpj}@mapa.radarsolar',
                    cpf_cnpj=cnpj,
                    tipo_perfil='B2C',
                )
            lead = Lead.create(
                cliente=cliente,
                empresa_responsavel=empresa,
                nome_contato=nome,
                telefone_contato=telefone or None,
                origem='Mapa RMR - Captura de lead',
                descricao_servico=f'CNPJ {cnpj}. {endereco}'.strip(),
                status='Novo',
            )
            LeadLog.create(lead=lead, de_status=None, para_status='Novo', alterado_por=empresa)

        log_ok(f'Lead #{lead.id} capturado do mapa pela empresa #{empresa_id} (CNPJ {cnpj})')
        return JSONResponse({'ok': True, 'lead_id': lead.id})
    except Usuario.DoesNotExist:
        log_erro('capturar-lead: usuario (empresa) nao existe no banco')
        app.storage.user.pop('auth', None)
        app.storage.user.pop('auth_created_at', None)
        return JSONResponse({'error': 'Sessao invalida. Faca login novamente.'}, status_code=401)
    except Exception as e:
        global _last_capture_error
        _last_capture_error = traceback.format_exc()
        log_erro(f'capturar-lead: {e}')
        log_erro(f'capturar-lead traceback: {_last_capture_error}')
        return JSONResponse({'error': 'Erro interno do servidor.'}, status_code=500)


@router.put('/api/empresa/contato/{cnpj}')
async def api_empresa_atualizar_contato(cnpj: str, request: FastAPIRequest) -> JSONResponse:
    auth = app.storage.user.get('auth')
    if not auth or auth.get('profile') != 'company':
        return JSONResponse({'error': 'Nao autorizado'}, status_code=401)

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({'error': 'JSON invalido'}, status_code=400)

    cnpj_digits = ''.join(ch for ch in cnpj if ch.isdigit())
    if len(cnpj_digits) != 14:
        return JSONResponse({'error': 'CNPJ invalido'}, status_code=400)

    cache = CnpjCache.get_or_none(CnpjCache.cnpj == cnpj_digits)
    if not cache:
        return JSONResponse({'error': 'CNPJ nao encontrado no cache'}, status_code=404)

    if 'telefone1' in body:
        cache.telefone1 = (body['telefone1'] or '').strip() or None
    if 'telefone2' in body:
        cache.telefone2 = (body['telefone2'] or '').strip() or None
    if 'email' in body:
        cache.email = (body['email'] or '').strip() or None
    cache.save()

    log_ok(f'Contato atualizado para CNPJ {cnpj_digits}')
    return JSONResponse({'ok': True})


@router.get('/api/debug/last-capture-error')
async def debug_last_capture_error() -> JSONResponse:
    return JSONResponse({'error': _last_capture_error})


@router.get('/api/demo/mapa-rmr')
async def api_demo_mapa_rmr() -> Response:
    try:
        data = carregar_geojson_rmr()
        return Response(
            montar_mapa_json(pjs=carregar_pjs_mapa(data)),
            media_type='application/json',
            headers={'Cache-Control': 'no-store'},
        )
    except Exception:
        tb = traceback.format_exc()
        log_erro(f'Falha interna ao montar mapa-rmr demo:\n{tb}')
        return JSONResponse({'error': 'Erro interno do servidor.'}, status_code=500)