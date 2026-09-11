"""Importação e armazenamento independente dos resultados de origem."""
import hashlib
import json
import sqlite3
from datetime import datetime
from io import BytesIO
from pathlib import Path

import pandas as pd

FONTES = ("Resultados da OTS e OTD", "Resultados Estadia")
DB_PATH = Path(__file__).resolve().parent / "data" / "regras_estadia.sqlite3"


def conectar(path=DB_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("""CREATE TABLE IF NOT EXISTS importacoes (
        id INTEGER PRIMARY KEY, fonte TEXT NOT NULL, arquivo TEXT NOT NULL,
        aba TEXT NOT NULL, assinatura TEXT NOT NULL, criado_em TEXT NOT NULL,
        quantidade INTEGER NOT NULL, dados TEXT NOT NULL,
        UNIQUE(fonte, assinatura))""")
    conn.commit()
    return conn


def ler_planilha(content, aba, cabecalho=1):
    df = pd.read_excel(BytesIO(content), sheet_name=aba, header=cabecalho - 1, dtype=object)
    df = df.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if df.empty:
        raise ValueError("A aba selecionada não contém registros.")
    df.columns = [str(c).strip() for c in df.columns]
    if len(set(df.columns)) != len(df.columns):
        raise ValueError("Existem nomes de colunas repetidos. Ajuste o cabeçalho da planilha.")
    return df


def salvar(fonte, arquivo, aba, df, path=DB_PATH):
    if fonte not in FONTES or df.empty:
        raise ValueError("Selecione uma fonte válida e uma planilha com registros.")
    dados = df.to_json(orient="split", date_format="iso", force_ascii=False)
    assinatura = hashlib.sha256(dados.encode("utf-8")).hexdigest()
    with conectar(path) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO importacoes (fonte,arquivo,aba,assinatura,criado_em,quantidade,dados) VALUES (?,?,?,?,?,?,?)",
            (fonte, arquivo, aba, assinatura, datetime.now().astimezone().isoformat(timespec="seconds"), len(df), dados),
        )
        return cursor.rowcount == 1


def historico(path=DB_PATH):
    with conectar(path) as conn:
        return pd.read_sql_query("SELECT id,fonte,arquivo,aba,criado_em,quantidade FROM importacoes ORDER BY id DESC", conn)


def carregar(importacao_id, path=DB_PATH):
    with conectar(path) as conn:
        row = conn.execute("SELECT dados FROM importacoes WHERE id=?", (int(importacao_id),)).fetchone()
    if row is None:
        raise ValueError("Importação não encontrada.")
    data = json.loads(row[0])
    return pd.DataFrame(data["data"], columns=data["columns"])


def exportar(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter", engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}}) as writer:
        df.to_excel(writer, sheet_name="resultados", index=False)
    return output.getvalue()
