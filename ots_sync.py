"""Leitura dos resultados publicados pelo OTSeOTD; nunca altera a origem."""
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pandas as pd

from core import DB_PATH, FONTES, conectar, salvar

REPOSITORY = "mathotto95-byte/OTSeOTD"
BACKUP_PATH = "backups/ots_otd_latest.json"
COLUMNS = {
    "id": "ID", "tipo_registro": "Status", "previsao_carga": "Previsao Carga",
    "data_limite": "Data Limite", "agendamento_carga": "Agendamento Carga",
    "agenda_gfl": "Agenda GFL", "codigo_monitoramento": "Codigo de Monitoramento",
    "data_hora_registro": "Data/Hora do Registro", "usuario_registro": "Usuario",
    "registro_origem_id": "ID do Registro Anterior", "dados_alterados": "Dados Alterados",
}


def settings():
    import streamlit as st
    try:
        cfg = dict(st.secrets.get("ots_sync", {}))
        fallback = st.secrets.get("GITHUB_TOKEN", "") or st.secrets.get("github", {}).get("token", "")
    except FileNotFoundError:
        cfg, fallback = {}, ""
    return {
        "token": str(cfg.get("token") or fallback or os.getenv("GITHUB_TOKEN", "")).strip(),
        "branch": str(cfg.get("branch", "main")),
    }


def parse_payload(payload):
    if not isinstance(payload, dict) or payload.get("schema") != "ots_otd_backup_v1":
        raise ValueError("O arquivo não é um backup válido do Banco OTS e OTD.")
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Backup vazio ou inválido. A base atual foi preservada.")
    if payload.get("records") != len(rows):
        raise ValueError("A quantidade de registros não confere com o backup.")
    if any(not set(COLUMNS).issubset(row) for row in rows):
        raise ValueError("O backup não contém todas as colunas do Banco OTS e OTD.")
    df = pd.DataFrame(rows)
    if df.id.isna().any() or df.id.duplicated().any():
        raise ValueError("O backup contém IDs ausentes ou duplicados.")
    df = df.sort_values(["data_hora_registro", "id"], ascending=False, kind="stable").reset_index(drop=True)
    view = df[list(COLUMNS)].rename(columns=COLUMNS)
    for col, fmt in [("Previsao Carga", "%d/%m/%Y"), ("Data Limite", "%d/%m/%Y"), ("Data/Hora do Registro", "%d/%m/%Y %H:%M")]:
        def format_value(value):
            if value is None or value == "":
                return ""
            parsed = pd.to_datetime(value, errors="coerce")
            return str(value) if pd.isna(parsed) else parsed.strftime(fmt)
        view[col] = view[col].map(format_value)
    return view


def download_payload(token, branch="main"):
    url = f"https://api.github.com/repos/{REPOSITORY}/contents/{BACKUP_PATH}?ref={quote(branch, safe='')}"
    headers = {"Accept": "application/vnd.github.raw+json", "User-Agent": "Performance-RW"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urlopen(Request(url, headers=headers), timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise ValueError(f"GitHub retornou {exc.code}. Confira o token, a permissão de leitura do OTSeOTD, a branch e a publicação do backup.") from None
        raise ValueError(f"GitHub indisponível (HTTP {exc.code}). Tente novamente.") from None
    except (URLError, TimeoutError, json.JSONDecodeError):
        raise ValueError("Não foi possível ler o backup no GitHub. A base atual foi preservada.") from None


def sync(token, branch="main", path=DB_PATH):
    payload = download_payload(token, branch)
    view = parse_payload(payload)
    changed = salvar(FONTES[0], f"{REPOSITORY}/{BACKUP_PATH}", "Banco OTS e OTD", view, path)
    # Uma base A → B → A precisa apontar novamente para A, mesmo sem duplicar o conteúdo.
    serialized = view.to_json(orient="split", date_format="iso", force_ascii=False)
    with conectar(path) as conn:
        row = conn.execute("SELECT id FROM importacoes WHERE fonte=? AND dados=?", (FONTES[0], serialized)).fetchone()
        conn.execute("CREATE TABLE IF NOT EXISTS sincronizacoes (fonte TEXT PRIMARY KEY, importacao_id INTEGER, gerado_em TEXT, sincronizado_em TEXT)")
        conn.execute("INSERT OR REPLACE INTO sincronizacoes VALUES (?,?,?,?)", (FONTES[0], row[0], payload.get("generated_at", ""), datetime.now(timezone.utc).isoformat(timespec="seconds")))
    return len(view), changed


def status(path=DB_PATH):
    with conectar(path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS sincronizacoes (fonte TEXT PRIMARY KEY, importacao_id INTEGER, gerado_em TEXT, sincronizado_em TEXT)")
        row = conn.execute("SELECT importacao_id,gerado_em,sincronizado_em FROM sincronizacoes WHERE fonte=?", (FONTES[0],)).fetchone()
    return row
