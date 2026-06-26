from __future__ import annotations

from dataclasses import dataclass

from src.models import Usuario
from src.utils import log_aviso, log_info, log_ok


PROFILE_TO_TIPO = {
    'customer': 'B2C',
    'company': 'B2B',
}

PROFILE_TO_HOME = {
    'customer': '/cliente/dashboard',
    'company': '/empresa/mapa',
}

TIPO_TO_LABEL = {
    'B2C': 'Gerador de energia',
    'B2B': 'Integrador solar',
}


class PerfilConflitanteError(ValueError):
    pass


@dataclass(frozen=True)
class AuthSession:
    usuario_id: int
    firebase_uid: str
    email: str
    nome: str
    profile: str
    tipo_perfil: str


def normalizar_profile(profile: str | None) -> str:
    if profile in PROFILE_TO_TIPO:
        return profile
    return 'customer'


def rota_inicial(profile: str | None) -> str:
    return PROFILE_TO_HOME[normalizar_profile(profile)]


def normalizar_email(email: str) -> str:
    return email.strip().lower()


def validar_email_para_profile(email: str, profile: str) -> str:
    email = normalizar_email(email)
    profile = normalizar_profile(profile)
    tipo_perfil = PROFILE_TO_TIPO[profile]
    usuario_existente = Usuario.get_or_none(Usuario.email == email)
    if usuario_existente and usuario_existente.tipo_perfil != tipo_perfil:
        perfil_existente = TIPO_TO_LABEL.get(usuario_existente.tipo_perfil, usuario_existente.tipo_perfil)
        perfil_solicitado = TIPO_TO_LABEL.get(tipo_perfil, tipo_perfil)
        log_aviso(
            f'Conflito de perfil: email {email} ja cadastrado como {perfil_existente}, '
            f'tentativa de acesso como {perfil_solicitado}'
        )
        raise PerfilConflitanteError(
            f'Este e-mail ja esta cadastrado como {perfil_existente}. '
            f'Para acessar como {perfil_solicitado}, use outro e-mail.'
        )
    return email


def criar_ou_atualizar_usuario(firebase_uid: str, email: str, profile: str, nome: str | None = None) -> tuple[Usuario, bool]:
    profile = normalizar_profile(profile)
    email = validar_email_para_profile(email, profile)
    tipo_perfil = PROFILE_TO_TIPO[profile]
    nome_base = (nome or '').strip() or email.split('@', 1)[0]

    log_info(f'Auth: criando/atualizando usuario (perfil={profile})')

    usuario, created = Usuario.get_or_create(
        email=email,
        defaults={
            'firebase_uid': firebase_uid,
            'nome': nome_base,
            'tipo_perfil': tipo_perfil,
        },
    )

    updated = False
    if usuario.firebase_uid != firebase_uid:
        usuario.firebase_uid = firebase_uid
        updated = True
    if usuario.tipo_perfil != tipo_perfil:
        usuario.tipo_perfil = tipo_perfil
        updated = True
    if not usuario.nome and nome_base:
        usuario.nome = nome_base
        updated = True

    if updated:
        usuario.save()

    if created:
        log_ok(f'Auth: novo usuario criado (id={usuario.id})')
    elif updated:
        log_ok(f'Auth: usuario atualizado (id={usuario.id})')
    else:
        log_info(f'Auth: usuario ja existente e atualizado (id={usuario.id})')

    return usuario, created


def serializar_sessao(usuario: Usuario, profile: str) -> dict:
    profile = normalizar_profile(profile)
    return {
        'usuario_id': usuario.id,
        'firebase_uid': usuario.firebase_uid or '',
        'email': usuario.email,
        'nome': usuario.nome,
        'profile': profile,
        'tipo_perfil': usuario.tipo_perfil,
    }
