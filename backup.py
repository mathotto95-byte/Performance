"""Duas cópias do SQLite no GitHub privado, diariamente às 20h de Brasília."""
import base64
import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import ZipFile, ZIP_DEFLATED

from core import DB_PATH

BRASILIA = timezone(timedelta(hours=-3))
SLOTS = ("backups/performance_1.zip", "backups/performance_2.zip")
_lock = threading.Lock()
_worker = None
_config = {}
_status = {"mensagem": "Aguardando configuração do backup."}


def settings():
    import streamlit as st
    from ots_sync import settings as ots_settings
    try:
        cfg = dict(st.secrets.get("performance_backup", {}))
        token = cfg.get("token") or st.secrets.get("performance_publish", {}).get("token") or ots_settings()["token"]
    except FileNotFoundError:
        cfg, token = {}, ""
    return {"token": token, "repository": cfg.get("repository", "mathotto95-byte/Performance-backups"), "branch": cfg.get("branch", "main")}


def snapshot(path=DB_PATH, now=None):
    now = now or datetime.now(BRASILIA)
    path = Path(path).resolve()
    if not path.exists():
        raise ValueError("Banco ainda não existe; backups anteriores preservados.")
    source = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    memory = sqlite3.connect(":memory:")
    try:
        source.backup(memory)
        tables = {r[0] for r in memory.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not any(t in tables and memory.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in ("importacoes", "otd_validacoes")):
            raise ValueError("Banco sem dados operacionais; backups anteriores preservados.")
        if memory.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Falha na integridade do banco; backup cancelado.")
        data = memory.serialize()
    finally:
        source.close()
        memory.close()
    manifest = {"schema": "performance_sqlite_v1", "created_at": now.isoformat(), "sha256": hashlib.sha256(data).hexdigest()}
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("regras_estadia.sqlite3", data)
    return output.getvalue()


def backup_date(data):
    with ZipFile(BytesIO(data)) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        database = archive.read("regras_estadia.sqlite3")
    if manifest.get("schema") != "performance_sqlite_v1" or hashlib.sha256(database).hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup remoto inválido; nenhuma cópia foi substituída.")
    stamp = datetime.fromisoformat(manifest["created_at"])
    if stamp.tzinfo is None:
        raise ValueError("Backup sem fuso horário.")
    return stamp


def github(config, endpoint, body=None, raw=False):
    url = f'https://api.github.com/repos/{config["repository"]}/{endpoint}'.rstrip("/")
    headers = {"Authorization": f'Bearer {config["token"]}', "Accept": "application/vnd.github.raw+json" if raw else "application/vnd.github+json", "User-Agent": "PerformanceRW-backup", "Content-Type": "application/json"}
    request = Request(url, headers=headers, data=json.dumps(body).encode() if body is not None else None, method="PUT" if body is not None else "GET")
    with urlopen(request, timeout=60) as response:
        return response.read() if raw else json.load(response)


def due_time(now):
    today = now.astimezone(BRASILIA).replace(hour=20, minute=0, second=0, microsecond=0)
    return today if now >= today else today - timedelta(days=1)


def run_backup(config, path=DB_PATH, now=None, force=False):
    now = now or datetime.now(BRASILIA)
    if not config.get("token"):
        raise ValueError("Configure um token com leitura e escrita no repositório privado de backup.")
    # A autorização do backup não autoriza exposição pública do banco completo.
    if not github(config, "").get("private"):
        raise ValueError("O repositório de backup precisa ser privado.")
    slots = []
    ref = quote(config["branch"], safe="")
    for name in SLOTS:
        try:
            metadata = github(config, f"contents/{name}?ref={ref}")
        except HTTPError as exc:
            if exc.code != 404:
                raise
            slots.append({"name": name, "date": None, "sha": None})
            continue
        data = github(config, f"contents/{name}?ref={ref}", raw=True)
        # Confirma que o SHA corresponde aos bytes lidos, evitando sobrescrita concorrente.
        blob_sha = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if blob_sha != metadata["sha"]:
            raise ValueError("O backup remoto mudou durante a leitura. Tentaremos novamente.")
        slots.append({"name": name, "date": backup_date(data), "sha": metadata["sha"]})
    newest = max((s["date"] for s in slots if s["date"]), default=None)
    if not force and newest and newest >= due_time(now):
        return f"Backup em dia. Última cópia: {newest.astimezone(BRASILIA):%d/%m/%Y %H:%M}."
    target = min(slots, key=lambda s: s["date"] or datetime.min.replace(tzinfo=BRASILIA))
    data = snapshot(path, now)
    body = {"message": "Backup diário PerformanceRW (retenção: duas cópias)", "branch": config["branch"], "content": base64.b64encode(data).decode()}
    if target["sha"]:
        body["sha"] = target["sha"]
    github(config, f'contents/{target["name"]}', body)
    return f'Backup salvo em {target["name"]} às {now.astimezone(BRASILIA):%d/%m/%Y %H:%M}.'


def execute(config, force=False):
    with _lock:
        try:
            message = run_backup(config, force=force)
        except HTTPError as exc:
            message = f"Backup pendente: GitHub {exc.code}. Confira o repositório privado, a branch e a permissão do token."
        except (URLError, TimeoutError):
            message = "Backup pendente: falha de conexão. Haverá nova tentativa."
        except Exception as exc:
            message = f"Backup pendente: {type(exc).__name__}. Verifique os dados e a configuração." if not isinstance(exc, ValueError) else str(exc)
        _status.update(mensagem=message)
        return message


def start_scheduler(config):
    global _worker, _config
    _config = dict(config)
    if not config.get("token"):
        return
    if _worker and _worker.is_alive():
        return
    with _lock:
        if _worker and _worker.is_alive():
            return

        def work():
            while True:
                execute(dict(_config))
                now = datetime.now(BRASILIA)
                upcoming = now.replace(hour=20, minute=0, second=0, microsecond=0)
                if upcoming <= now:
                    upcoming += timedelta(days=1)
                threading.Event().wait(min(900, max(1, (upcoming - now).total_seconds())))

        _worker = threading.Thread(target=work, daemon=True, name="performance-backup-20h")
        _worker.start()


def status():
    return _status["mensagem"]


def render(config):
    import streamlit as st
    st.subheader("Backup do Performance")
    st.write("Diariamente às **20h — horário de Brasília**, com **duas cópias rotativas**. O arquivo mais antigo é substituído após criar e validar a nova cópia.")
    st.caption("Inclui importações, sincronizações, validações manuais e histórico do banco. Secrets e arquivos de configuração não estão no banco e não são incluídos.")
    st.info("O agendamento funciona enquanto o processo do Streamlit está ativo. Ao voltar de uma suspensão, verifica e executa o backup pendente dos dados disponíveis.")
    st.write(status())
    st.link_button("Abrir repositório privado de backups", f'https://github.com/{config["repository"]}')
    if not config.get("token"):
        st.warning("Configure performance_backup.token com Contents: Read and write no repositório privado. Também pode reutilizar o token de publicação ou de sincronização, se tiver essa permissão.")
    if st.button("Fazer backup agora", disabled=not config.get("token")):
        with st.spinner("Validando o banco e enviando o backup…"):
            st.write(execute(config, force=True))
