"""Validação humana de OTD, separada dos resultados importados."""
import hashlib
import json
from datetime import datetime, timezone

import pandas as pd

from core import DB_PATH, conectar, exportar
from rules import schedule_indicators, attendance, text
MONITORING_LINK_SUPPORTED = True
VIGENCIA_PREVISAO = True


def reviews(path=DB_PATH):
    with conectar(path) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS otd_validacoes (
            id INTEGER PRIMARY KEY, assinatura TEXT NOT NULL, monitoramento TEXT NOT NULL,
            dentro INTEGER NOT NULL, justificativa TEXT NOT NULL, usuario TEXT NOT NULL, data_hora TEXT NOT NULL)""")
        rows = conn.execute("SELECT assinatura,dentro,justificativa,usuario,data_hora FROM otd_validacoes ORDER BY id").fetchall()
    return {r[0]: r[1:] for r in rows}


def review_queue(ots, analysis, path=DB_PATH, stays=None):
    if ots.empty or "Codigo de Monitoramento" not in ots:
        return pd.DataFrame()
    original = schedule_indicators(ots)
    current = schedule_indicators(ots, analysis).set_index("Monitoramento")
    saved = reviews(path)
    rows = []
    for source in original.loc[original.OTD.eq("Atrasado")].to_dict("records"):
        code = source["Monitoramento"]
        linked = analysis.loc[analysis.Monitoramento.eq(code)] if analysis is not None and "Monitoramento" in analysis else pd.DataFrame()
        fields = ["Nota Fiscal", "Placa", "Origem", "Destino", "Chegada no Destino", "Correspondência Estadias", "OTD 2"]
        evidence = linked.reindex(columns=fields).fillna("").astype(str).sort_values(["Nota Fiscal", "Placa"]).to_dict("records")
        if stays is not None and "monitoramento" in stays:
            matches = stays.loc[stays.monitoramento.map(lambda v: text(v).removesuffix(".0")).eq(text(code).removesuffix(".0"))]
            if not matches.empty and text(code):
                mapping = {"nf": "Nota Fiscal", "placa_norm": "Placa", "origem": "Origem", "destino": "Destino", "chegada_destino": "Chegada no Destino", "chegada_origem": "Chegada na Origem", "id": "Registro Estadias", "chave_viagem": "Chave da viagem"}
                direct = matches.reindex(columns=list(mapping)).rename(columns=mapping).fillna("").astype(str).drop_duplicates()
                direct["Correspondência Estadias"] = "Código de monitoramento exato — conferir viagem"
                evidence = direct.sort_values(["Nota Fiscal", "Placa", "Registro Estadias"]).to_dict("records")
        signature = hashlib.sha256(json.dumps([source, evidence], sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        decision = saved.get(signature, (0, "", "", ""))
        rows.append({**source, "OTD automático": current.loc[code, "OTD"],
                     **{field: "\n".join(r.get(field, "") or "Sem informação" for r in evidence) for field in ["Nota Fiscal", "Placa", "Origem", "Destino", "Chegada na Origem", "Chegada no Destino", "Registro Estadias"]},
                     "NF / Placa / Chegada no destino": "\n".join(f'{r["Nota Fiscal"]} / {r["Placa"]} / {r["Chegada no Destino"] or "Sem chegada"} / {r["Correspondência Estadias"]}' for r in evidence) or "Sem vínculo NF + placa",
                     "Dentro da regra": bool(decision[0]), "Justificativa": decision[1],
                     "Validado por": decision[2], "Validado em": decision[3], "_assinatura": signature})
    return pd.DataFrame(rows)


def save_reviews(edited, original, user, path=DB_PATH):
    if user.get("role") not in {"ADMIN", "OPERACIONAL"} or not user.get("username"):
        raise ValueError("Somente Admin e Operacional podem validar OTD.")
    updates = []
    for row in edited.to_dict("records"):
        match = original.loc[original.Monitoramento.eq(row["Monitoramento"])]
        if len(match) != 1 or not isinstance(row["Dentro da regra"], bool):
            raise ValueError("Registro de validação inválido.")
        old = match.iloc[0]
        reason = text(row["Justificativa"])
        if bool(old["Dentro da regra"]) == row["Dentro da regra"] and text(old["Justificativa"]) == reason:
            continue
        if not reason:
            raise ValueError(f'Informe a justificativa do monitoramento {row["Monitoramento"]}.')
        updates.append((old._assinatura, row["Monitoramento"], int(row["Dentro da regra"]), reason, user["username"], datetime.now(timezone.utc).isoformat(timespec="seconds")))
    reviews(path)
    with conectar(path) as conn:
        conn.executemany("INSERT INTO otd_validacoes (assinatura,monitoramento,dentro,justificativa,usuario,data_hora) VALUES (?,?,?,?,?,?)", updates)
    return len(updates)


def apply_reviews(analysis, queue):
    if analysis is None or queue.empty:
        return analysis
    result = analysis.copy()
    result["OTD 2 automático"] = result["OTD 2"]
    result["OTD validado manualmente"] = False
    for row in queue.loc[queue["Dentro da regra"]].to_dict("records"):
        mask = result.Monitoramento.eq(row["Monitoramento"]) & result["OTD 2"].eq("Fora do prazo")
        result.loc[mask, "OTD 2"] = "Dentro do prazo"
        result.loc[mask, "OTD validado manualmente"] = True
        result.loc[mask, "Motivo da classificação"] += f'; OTD 2 validado manualmente por {row["Validado por"]} em {row["Validado em"]}: {row["Justificativa"]}'
    result["Atendeu todas as regras"] = result.apply(attendance, axis=1)
    return result


def render_reviews(queue, month, user):
    import streamlit as st
    st.subheader("OTD atrasado — análise manual")
    st.caption("Atrasos pelo agendamento original, incluindo os já validados. NFs, placas e chegadas são buscadas diretamente no Estadias pelo código de monitoramento exato. Múltiplos registros aparecem em linhas correspondentes dentro das células para conferência. A aprovação vale para o monitoramento e suas NFs vinculadas; altera OTD/OTD 2, sem aprovar as outras regras. Alterações na base exigem nova validação.")
    if queue.empty:
        st.info("Nenhum agendamento OTD atrasado na base.")
        return
    selected = queue if month == "Todos" else queue.loc[queue["Mês OTS"].eq(month)]
    view = selected.drop(columns=["_assinatura", "OTS", "OTD", "Mês OTD"], errors="ignore").rename(columns={"Mês OTS": "Mês de vigência"})
    st.metric("OTD validados manualmente no período", int(selected["Dentro da regra"].sum()))
    with st.form("otd_review_form"):
        allowed = user.get("role") in {"ADMIN", "OPERACIONAL"}
        editor_key = hashlib.sha256(selected.to_json(orient="split", default_handler=str).encode()).hexdigest()
        edited = st.data_editor(view, hide_index=True, use_container_width=True, disabled=[c for c in view if c not in {"Dentro da regra", "Justificativa"}] if allowed else True,
                                column_config={"Dentro da regra": st.column_config.CheckboxColumn("Dentro da regra — validado manualmente")}, key="otd_review_" + editor_key)
        submitted = st.form_submit_button("Salvar análise manual", disabled=not allowed)
    if submitted:
        count = save_reviews(edited, queue, user)
        st.session_state["otd_review_saved"] = f"{count} validações salvas. Indicadores atualizados."
        st.rerun()
    st.download_button("Exportar lista OTD", exportar(view), "otd_analise_manual.xlsx")
