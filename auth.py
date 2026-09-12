import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import streamlit as st

from core import conectar

APP_NAME = "Performance RW"


def brasilia_now():
    return datetime.now(timezone(timedelta(hours=-3)))


def load_security_config():
    return {"session_timeout_minutes": 60, "max_login_attempts": 5, "lockout_minutes": 5}


def current_user():
    return st.session_state.get("auth_user", {})


def log_security(action, screen, status, message="", username=None, role=None):
    user = current_user()
    with conectar() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS security_logs (id INTEGER PRIMARY KEY, usuario TEXT, perfil TEXT, acao TEXT, tela TEXT, data_hora TEXT, status TEXT, mensagem TEXT)")
        conn.execute("INSERT INTO security_logs (usuario,perfil,acao,tela,data_hora,status,mensagem) VALUES (?,?,?,?,?,?,?)", (username if username is not None else user.get("username", ""), role if role is not None else user.get("role", ""), action, screen, brasilia_now().isoformat(), status, message))


def hash_password(password: str, iterations: int=260000) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
    return f"pbkdf2_sha256${iterations}${base64.b64encode(salt).decode('ascii')}${base64.b64encode(digest).decode('ascii')}"

def verify_password(password: str, password_hash: str) -> bool:
    if not password_hash:
        return False
    if password_hash.startswith('pbkdf2_sha256$'):
        try:
            _, iterations, salt, expected = password_hash.split('$', 3)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), base64.b64decode(salt.encode('ascii')), int(iterations))
            return hmac.compare_digest(base64.b64encode(digest).decode('ascii'), expected)
        except Exception:
            return False
    try:
        from passlib.context import CryptContext
        context = CryptContext(schemes=['bcrypt', 'pbkdf2_sha256'], deprecated='auto')
        return bool(context.verify(password, password_hash))
    except Exception:
        return False

def _mapping_to_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return {key: _mapping_to_dict(item) for key, item in value.items()}
    return value

def load_users(streamlit_secrets: Mapping[str, Any] | None=None) -> dict[str, dict[str, str]]:
    users: dict[str, dict[str, str]] = {}
    if streamlit_secrets is not None:
        try:
            secrets_dict = _mapping_to_dict(streamlit_secrets)
            auth_config = secrets_dict.get('auth', {}) or {}
            admin = auth_config.get('admin') or {}
            if admin:
                users['admin'] = {'name': admin.get('name') or 'Administrador', 'username': admin.get('username') or 'admin', 'email': admin.get('email') or '', 'password': admin.get('password') or '', 'password_hash': admin.get('password_hash') or '', 'role': admin.get('role') or 'admin'}
            users.update(auth_config.get('users', {}) or {})
        except Exception:
            pass
    env_admin_password = os.getenv('AUTH_ADMIN_PASSWORD', '').strip()
    if env_admin_password:
        users['admin'] = {'name': os.getenv('AUTH_ADMIN_NAME', 'Administrador'), 'username': os.getenv('AUTH_ADMIN_USERNAME', 'admin'), 'email': os.getenv('AUTH_ADMIN_EMAIL', ''), 'password': env_admin_password, 'password_hash': os.getenv('AUTH_ADMIN_PASSWORD_HASH', ''), 'role': os.getenv('AUTH_ADMIN_ROLE', 'admin')}
    env_users = os.getenv('AUTH_USERS_JSON', '').strip()
    if env_users:
        try:
            users.update(json.loads(env_users))
        except json.JSONDecodeError:
            pass
    normalized: dict[str, dict[str, str]] = {}
    for key, user in users.items():
        username = str(user.get('username') or key).strip()
        if not username:
            continue
        normalized[username.lower()] = {'username': username, 'name': str(user.get('name') or username), 'email': str(user.get('email') or ''), 'password': str(user.get('password') or ''), 'password_hash': str(user.get('password_hash') or ''), 'role': str(user.get('role') or 'CONSULTA').upper()}
        email = str(user.get('email') or '').strip().lower()
        if email:
            normalized[email] = normalized[username.lower()]
    return normalized

def admin_is_configured(streamlit_secrets: Mapping[str, Any] | None=None) -> bool:
    return any((user.get('role') == 'ADMIN' and (user.get('password') or user.get('password_hash')) for user in load_users(streamlit_secrets).values()))

def authenticate(identifier: str, password: str, streamlit_secrets: Mapping[str, Any] | None=None) -> dict[str, str] | None:
    users = load_users(streamlit_secrets)
    user = users.get(identifier.strip().lower())
    if not user:
        return None
    password_hash = user.get('password_hash', '')
    secret_password = user.get('password', '')
    valid_hash = bool(password_hash and verify_password(password, password_hash))
    valid_secret = bool(secret_password and hmac.compare_digest(password.encode('utf-8'), secret_password.encode('utf-8')))
    if not (valid_hash or valid_secret):
        return None
    authenticated_user = {'username': user['username'], 'name': user['name'], 'role': user['role']}
    return authenticated_user

def session_is_expired(last_activity: datetime, timeout_minutes: int) -> bool:
    return brasilia_now() - last_activity > timedelta(minutes=timeout_minutes)

def is_authenticated() -> bool:
    return bool(st.session_state.get('authenticated') and current_user())

def clear_authentication() -> None:
    for key in ['authenticated', 'auth_user', 'login_at', 'last_activity']:
        st.session_state.pop(key, None)

def logout(reason: str='logout') -> None:
    log_security('logout', 'Sistema', 'SUCESSO', reason)
    clear_authentication()
    st.rerun()

def render_login_page() -> None:
    st.title(APP_NAME)
    st.subheader('Login')
    st.caption('Informe seu usuario e senha para acessar o sistema.')
    if not admin_is_configured(st.secrets):
        st.warning('Usuário administrador não configurado. Configure as credenciais no Streamlit Secrets.')
    config = load_security_config()
    now = brasilia_now()
    lockout_until = st.session_state.get('lockout_until')
    if lockout_until and now < lockout_until:
        remaining = int((lockout_until - now).total_seconds() // 60) + 1
        st.error(f'Muitas tentativas invalidas. Tente novamente em {remaining} minuto(s).')
        return
    with st.form('login_form'):
        identifier = st.text_input('Usuario ou e-mail')
        password = st.text_input('Senha', type='password')
        submitted = st.form_submit_button('Entrar', type='primary', use_container_width=True)
    if not submitted:
        return
    if not identifier or not password:
        st.error('Usuario ou senha invalidos.')
        return
    user = authenticate(identifier, password, st.secrets)
    if not user:
        attempts = int(st.session_state.get('failed_login_attempts', 0)) + 1
        st.session_state.failed_login_attempts = attempts
        log_security('login_invalido', 'Login', 'FALHA', 'Usuario ou senha invalidos.', identifier, '')
        if attempts >= int(config.get('max_login_attempts', 5)):
            st.session_state.lockout_until = now + timedelta(minutes=int(config.get('lockout_minutes', 5)))
            log_security('login_bloqueado', 'Login', 'BLOQUEADO', 'Limite de tentativas invalidas.', identifier, '')
        st.error('Usuario ou senha invalidos.')
        return
    st.session_state.authenticated = True
    st.session_state.auth_user = user
    st.session_state.login_at = now
    st.session_state.last_activity = now
    st.session_state.failed_login_attempts = 0
    st.session_state.pop('lockout_until', None)
    log_security('login', 'Login', 'SUCESSO', 'Login bem-sucedido.', user['username'], user['role'])
    st.rerun()

def enforce_authentication() -> bool:
    if not is_authenticated():
        render_login_page()
        return False
    config = load_security_config()
    last_activity = st.session_state.get('last_activity', brasilia_now())
    if session_is_expired(last_activity, int(config.get('session_timeout_minutes', 60))):
        log_security('sessao_expirada', 'Sistema', 'EXPIRADA', 'Sessao encerrada por inatividade.')
        clear_authentication()
        st.warning('Sua sessao expirou. Faca login novamente.')
        render_login_page()
        return False
    st.session_state.last_activity = brasilia_now()
    return True

