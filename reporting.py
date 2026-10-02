"""Painel e publicação da análise; nenhuma alteração nos bancos de origem."""
import base64
import json
import re
from decimal import Decimal, ROUND_HALF_UP
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd

from rules import RULES, UNKNOWN, date, text

RESULT_PATH = "backups/performance_latest.json"
RESULT_URL = f"https://api.github.com/repos/mathotto95-byte/Performance/contents/{RESULT_PATH}"
PANEL_COLUMNS = ["Tarefa", "Envio", "Prazo", "Nota", "Código", "Placa", "Origem", "Destino", "Horário de Início da Estadia", "Horário de Fim da Estadia", "Horas de Estadia", "Valor", "Dentro da Regra"]


def money(hours):
    return float((Decimal(str(hours)) * Decimal("68.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def currency(value):
    return (f"R$ {value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")) if pd.notna(value) else ""


def control_panel(result, stays):
    lookup = {(text(r["Nota Fiscal"]), text(r["Placa"])): r for r in result.to_dict("records")}
    rows = []
    for stay in stays.to_dict("records"):
        plate = re.sub(r"[^A-Z0-9]", "", text(stay.get("placa_norm")).upper())
        nfs = {n.removesuffix(".0").lstrip("0") or "0" for n in re.split(r"[;,/|\s]+", text(stay.get("nf"))) if n}
        code = text(stay.get("id")) or text(stay.get("lcte_id")) or text(stay.get("chave_viagem"))
        sent = date(stay.get("analise_enviada_em"))
        for side, minutes, allowance in [("origem", "estadia_carga_min", "franquia_carga_min"), ("destino", "estadia_descarga_min", "franquia_descarga_min")]:
            count = pd.to_numeric(stay.get(minutes), errors="coerce")
            if pd.isna(count) or count <= 0:
                continue
            arrival, end = date(stay.get(f"chegada_{side}")), date(stay.get(f"saida_{side}"))
            free = pd.to_numeric(stay.get(allowance), errors="coerce")
            start = arrival + pd.Timedelta(minutes=float(free)) if pd.notna(arrival) and pd.notna(free) and free >= 0 else pd.NaT
            hours = (end - start).total_seconds() / 3600 if pd.notna(start) and pd.notna(end) and end >= start else None
            period = f"{code}|{side}"
            for nf in sorted(nfs):
                analysis = lookup.get((nf, plate), {})
                exact = analysis.get("Correspondência Estadias") == "Exata"
                rows.append({"Tarefa": text(stay.get("tarefa")), "Envio": sent,
                             "Prazo": sent + pd.Timedelta(days=15) if pd.notna(sent) else pd.NaT,
                             "Nota": nf, "Código": code, "Placa": plate,
                             "Origem": text(stay.get("origem")), "Destino": text(stay.get("destino")),
                             "Horário de Início da Estadia": start, "Horário de Fim da Estadia": end,
                             "Horas de Estadia": hours, "Valor": money(hours) if hours is not None else None,
                             "Dentro da Regra": analysis.get("Atendeu todas as regras", UNKNOWN) if exact else UNKNOWN,
                             "Período": side.upper(), "_period": period if code else None,
                             **{rule: analysis.get(rule, UNKNOWN) if exact else UNKNOWN for rule in RULES}})
    return pd.DataFrame(rows, columns=[*PANEL_COLUMNS, "Período", "_period", *RULES]).drop_duplicates()


def panel_totals(panel):
    totals = {"Valor total": 0.0, "Valor dentro": 0.0, "Valor fora": 0.0}
    for _, group in panel.dropna(subset=["_period"]).groupby("_period"):
        amounts = group.Valor.dropna().unique()
        if len(amounts) != 1:
            continue
        value = float(amounts[0])
        totals["Valor total"] += value
        states = set(group["Dentro da Regra"])
        if "Não" in states:
            totals["Valor fora"] += value
        elif states == {"Sim"}:
            totals["Valor dentro"] += value
    return totals


def render_panel(panel):
    import streamlit as st
    from core import exportar
    st.caption("Períodos após a franquia, a R$ 68,00/hora. Totais financeiros contam cada período uma vez, mesmo com várias NFs. Tarefa ausente permanece vazia.")
    if panel.empty:
        st.info("Nenhum período de estadia disponível na base selecionada.")
        return
    with st.expander("Filtros"):
        for col in ["Tarefa", "Nota", "Placa", "Origem", "Destino", "Dentro da Regra", *RULES]:
            options = sorted(panel[col].dropna().astype(str).unique())
            selected = st.multiselect(col, options, key="control_" + col)
            if selected:
                panel = panel[panel[col].astype(str).isin(selected)]
        for col in ["Envio", "Prazo"]:
            if st.checkbox(f"Filtrar por {col}", key="control_date_" + col):
                start = st.date_input(f"{col}: de", key=col + "_start")
                end = st.date_input(f"{col}: até", key=col + "_end")
                panel = panel[panel[col].map(lambda value: pd.notna(value) and start <= value.date() <= end)]
        overdue = st.checkbox("Somente prazo vencido")
    today = pd.Timestamp.now(tz="America/Sao_Paulo").date()
    expired = panel.Prazo.map(lambda value: pd.notna(value) and value.date() < today)
    if overdue:
        panel = panel[expired]
    expired = panel.Prazo.map(lambda value: pd.notna(value) and value.date() < today)
    counts = {"Registros": len(panel), "Dentro das regras": int(panel["Dentro da Regra"].eq("Sim").sum()),
              "Fora das regras": int(panel["Dentro da Regra"].eq("Não").sum()),
              "Sem informação": int(panel["Dentro da Regra"].eq(UNKNOWN).sum()),
              **{k: currency(v) for k, v in panel_totals(panel).items()},
              "Registros com prazo vencido": int(panel.loc[expired, "Código"].replace("", pd.NA).nunique())}
    cells = st.columns(4)
    for i, (name, value) in enumerate(counts.items()):
        cells[i % 4].metric(name, value)
    view = panel[[*PANEL_COLUMNS, "Período", *RULES]].copy()
    for column in ["Envio", "Prazo", "Horário de Início da Estadia", "Horário de Fim da Estadia"]:
        view[column] = view[column].map(lambda v: (v.tz_convert("America/Sao_Paulo") if v.tzinfo else v).strftime("%d/%m/%Y %H:%M") if pd.notna(v) else "")
    st.dataframe(view.style.format({"Valor": currency, "Horas de Estadia": lambda v: f"{v:.2f}" if pd.notna(v) else ""}), hide_index=True, use_container_width=True)
    st.download_button("Exportar painel", exportar(view), "painel_controle.xlsx")


def publish(result, sources, analyzed_at, token):
    if not token:
        raise ValueError("Configure performance_publish.token com escrita no repositório Performance.")
    if result.empty or result.duplicated(["Nota Fiscal", "Placa"]).any():
        raise ValueError("Análise vazia ou duplicada; publicação anterior preservada.")
    required = {*RULES, "Atendeu todas as regras", "Correspondência Estadias", "Motivo da classificação", "Chegada na Origem", "Chegada no Destino"}
    if not required.issubset(result.columns):
        raise ValueError("Análise incompleta; publicação anterior preservada.")
    valid = result["Nota Fiscal"].fillna("").ne("") & result.Placa.fillna("").ne("")
    if not valid.all():
        raise ValueError("Existem resultados sem NF ou placa. Corrija a base antes de publicar.")
    payload = {"schema": "performance_results_v1", "analyzed_at": analyzed_at, "sources": sources,
               "rows": json.loads(result.to_json(orient="records", force_ascii=False))}
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "Content-Type": "application/json", "User-Agent": "Performance-RW"}
    body = {"message": "Atualiza analise PerformanceRW", "branch": "main",
            "content": base64.b64encode(json.dumps(payload, ensure_ascii=False).encode()).decode()}
    try:
        try:
            with urlopen(Request(RESULT_URL + "?ref=main", headers=headers), timeout=30) as response:
                body["sha"] = json.load(response)["sha"]
        except HTTPError as exc:
            if exc.code != 404:
                raise
        with urlopen(Request(RESULT_URL, data=json.dumps(body).encode(), headers=headers, method="PUT"), timeout=30) as response:
            json.load(response)
    except HTTPError as exc:
        raise ValueError(f"Publicação não concluída (GitHub {exc.code}). Confira a permissão de escrita; se houve outra publicação, tente novamente.") from None
    except (URLError, TimeoutError, ValueError):
        raise ValueError("Não foi possível confirmar a publicação. Confira a conexão e consulte o resultado no Estadias antes de repetir.") from None
