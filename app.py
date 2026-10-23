from io import BytesIO
from pathlib import Path
import hashlib

import pandas as pd
import streamlit as st

from core import FONTES, carregar, exportar, historico, ler_planilha, salvar
from theme import apply_theme
from auth import enforce_authentication, current_user, logout
import ots_sync
import rules
from importlib import reload

# Streamlit pode manter o módulo anterior em memória durante a atualização.
if not hasattr(rules, "indicators") or not hasattr(rules, "MANUAL_OTD_SUPPORTED"):
    reload(rules)
if not hasattr(ots_sync, "_save_snapshot"):
    reload(ots_sync)

from ots_sync import settings as ots_settings, sync as sync_ots, status as ots_status
from rules import prepare_lcte, indicators, schedule_indicators
import reporting
if "Previsão de Carga" not in reporting.PANEL_COLUMNS:
    reload(reporting)
from reporting import control_panel, render_panel, publish
import backup
import manual_otd
if not hasattr(manual_otd, "VIGENCIA_PREVISAO"):
    reload(manual_otd)
from manual_otd import review_queue, apply_reviews, render_reviews


def analyze(lcte, ots, estadias):
    result = rules.analyze(lcte, ots, estadias)
    return apply_reviews(result, review_queue(ots, result, stays=estadias))


LOGO_PATH = Path(__file__).resolve().parent / "assets" / "rodo_wall_logo.png"

st.set_page_config(page_title="Performance RW", page_icon=str(LOGO_PATH), layout="wide")
apply_theme()
if not enforce_authentication():
    st.stop()
backup_config = backup.settings()
backup.start_scheduler(backup_config)
logo, titulo, atualizar = st.columns([1.2, 4, 1])
with logo:
    with st.container(key="rw-logo"):
        st.image(str(LOGO_PATH), width=180)
with titulo:
    st.title("Performance RW")
with atualizar:
    st.write("")
    if st.button("Atualizar página", use_container_width=True):
        st.rerun()
st.caption("Importação e consulta dos resultados de OTS/OTD e Estadia.")
if st.button("Ver resultados das análises", type="primary"):
    st.session_state["performance_menu"] = "Análise Performance"

st.sidebar.title("Performance RW")
st.sidebar.caption("Gestão operacional • RW")
usuario = current_user()
st.sidebar.write(f"**Usuário:** {usuario['name']}")
st.sidebar.write(f"**Perfil:** {usuario['role'].title()}")
menu = ["Performance IPP", "Visão geral", "Análise Performance", "Painel de Controle", "Consultar resultados", "Histórico"]
if usuario['role'] in {"ADMIN", "OPERACIONAL"}:
    menu.append("Backup")
    menu.insert(1, "Importações")
    menu.insert(1, "Sincronização OTS e OTD")
    menu.insert(2, "Sincronização Estadias")
pagina = st.sidebar.radio("Menu", menu, key="performance_menu")
if st.sidebar.button("Sair", use_container_width=True):
    logout()
st.sidebar.divider()
st.sidebar.caption("Bases: OTS e OTD / Estadia")
st.divider()
hist = historico()

if pagina == "Performance IPP":
    st.subheader("Performance IPP")
    st.caption("Indicador exclusivo das regras OTS e OTD. Antecipados são contabilizados junto com OK.")
    estado = ots_status(fonte=FONTES[0])
    if not estado:
        st.info("Sincronize ou importe a base de Resultados da OTS e OTD para gerar o relatório.")
    else:
        try:
            ipp = schedule_indicators(carregar(estado[0]))
            if ipp.empty:
                st.info("Nenhum monitoramento analisável foi encontrado.")
            else:
                meses_ipp = sorted(ipp["Mês OTS"].dropna().unique(), reverse=True)
                mes_ipp = st.selectbox("Mês de vigência — Previsão de Carga", ["Todos", *meses_ipp], key="ipp_month")
                if mes_ipp != "Todos":
                    ipp = ipp.loc[ipp["Mês OTS"].eq(mes_ipp)].copy()
                st.caption("O filtro usa a Previsão de Carga para OTS e OTD.")
                if ipp.empty:
                    st.info("Nenhum registro encontrado para o mês selecionado.")
                    st.stop()
                atendida = ipp.OTS.isin(["OK", "Antecipado"]) & ipp.OTD.isin(["OK", "Antecipado"])
                fora = ipp.OTS.eq("Atrasado") | ipp.OTD.eq("Atrasado")
                resumo_cards = st.columns(4)
                resumo_cards[0].metric("Total de itens", len(ipp))
                resumo_cards[1].metric("Dentro da regra", int(atendida.sum()))
                resumo_cards[2].metric("Fora da regra", int(fora.sum()))
                resumo_cards[3].metric("Sem informação", int((~atendida & ~fora).sum()))
                cards = st.columns(5)
                ots_total = int(ipp.OTS.isin(["OK", "Antecipado", "Atrasado"]).sum())
                otd_total = int(ipp.OTD.isin(["OK", "Antecipado", "Atrasado"]).sum())
                for card, label, quantidade, base in [
                    (cards[0], "OTS 1 atendida", len(ipp), len(ipp)),
                    (cards[1], "OTS atendida", int(ipp.OTS.isin(["OK", "Antecipado"]).sum()), ots_total),
                    (cards[2], "OTS não atendida", int(ipp.OTS.eq("Atrasado").sum()), ots_total),
                    (cards[3], "OTD atendida", int(ipp.OTD.isin(["OK", "Antecipado"]).sum()), otd_total),
                    (cards[4], "OTD não atendida", int(ipp.OTD.eq("Atrasado").sum()), otd_total),
                ]:
                    card.metric(label, quantidade, f"{quantidade / base * 100:.2f}%" if base else None)
                resumo = pd.DataFrame({"Indicador": ["OTS", "OTD"], "OK (inclui antecipado)": [int(ipp.OTS.isin(["OK", "Antecipado"]).sum()), int(ipp.OTD.isin(["OK", "Antecipado"]).sum())], "Atrasado": [int(ipp.OTS.eq("Atrasado").sum()), int(ipp.OTD.eq("Atrasado").sum())], "Sem informação": [int(ipp.OTS.eq("Sem informação").sum()), int(ipp.OTD.eq("Sem informação").sum())]})
                st.dataframe(resumo, hide_index=True, use_container_width=True)
                st.download_button("Exportar Performance IPP", exportar(ipp), "performance_ipp.xlsx")
        except ValueError as exc:
            st.error(str(exc))

elif pagina in {"Análise Performance", "Painel de Controle"}:
    st.subheader("Performance por NF + Placa")
    st.caption("Observação do LCTE → monitoramento OTS/OTD. NF + placa → chegadas do Estadias. Utiliza a última versão de cada monitoramento na base selecionada.")
    st.info("OTS 2 e OTD 2 consideram dentro do prazo o mesmo dia ou depois do limite. OTD 3 usa a Agenda GFL quando está no mesmo dia da Data Limite e, quando a agenda é posterior, exige chegada na Data Limite. OTD 1 compara o registro com a emissão da NF.")
    bases = {}
    sources = {}
    for fonte in FONTES:
        versoes = hist[hist.fonte == fonte]
        if versoes.empty:
            bases[fonte] = pd.DataFrame()
            st.warning(f"Base não recebida: {fonte}")
            continue
        ids = versoes.id.astype(int).tolist()
        estado = ots_status(fonte=fonte)
        if estado and estado[0] in ids:
            ids.remove(estado[0])
            ids.insert(0, estado[0])
        labels = {int(r.id): f"#{r.id} • {r.criado_em} • {r.arquivo}" for r in versoes.itertuples()}
        selected = st.selectbox(fonte, ids, format_func=labels.get)
        bases[fonte] = carregar(selected)
        metadata = versoes[versoes.id == selected].iloc[0]
        sources[fonte] = {"id": selected, "arquivo": metadata.arquivo, "importado_em": metadata.criado_em,
                          "assinatura": hashlib.sha256(bases[fonte].to_json(orient="split", date_format="iso").encode()).hexdigest()}
    if bases[FONTES[2]].empty:
        st.info("Acesse Sincronização Estadias e clique em Sincronizar Estadias: o LCTE e a Observação serão recebidos junto com os resultados. Se o backup ainda não incluir a planilha, envie um novo backup completo no Estadias. A importação manual permanece disponível como alternativa.")
    else:
        try:
            resultado = analyze(bases[FONTES[2]], bases[FONTES[0]], bases[FONTES[1]])
            analyzed_at = pd.Timestamp.now(tz="America/Sao_Paulo").isoformat()
            resultado["Data/Hora da última análise"] = analyzed_at
            resultado_completo = resultado
            meses = resultado["Emissão da NF"].map(rules.date).map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else "Sem data")
            mes = st.selectbox("Mês de emissão da NF", ["Todos", *sorted(meses.unique(), reverse=True)], key="analysis_month")
            if mes != "Todos":
                resultado = resultado.loc[meses.eq(mes)].copy()
            st.caption("O mês selecionado filtra os indicadores, as listas e as exportações da tela.")
            if pagina == "Painel de Controle":
                render_panel(control_panel(resultado, bases[FONTES[1]]))
            else:
                table, general = indicators(resultado)
                unique = resultado.drop_duplicates(["Nota Fiscal", "Placa"])
                unique = unique[unique["Nota Fiscal"].fillna("").ne("") & unique.Placa.fillna("").ne("")]
                st.subheader("Resultado geral por NF + Placa")
                cards = st.columns(4)
                cards[0].metric("NFs/viagens analisadas", len(unique))
                for card, label, status in zip(cards[1:], ["Dentro das regras", "Fora das regras", "Sem informação"], ["Sim", "Não", "Sem informação"]):
                    card.metric(label, int(unique["Atendeu todas as regras"].eq(status).sum()))
                st.subheader("Estadias dentro das regras")
                panel = control_panel(resultado, bases[FONTES[1]])
                approved = panel[panel["Dentro da Regra"].eq("Sim") & panel["Horas de Estadia"].gt(0) & panel["Valor"].notna()]
                if approved.empty:
                    st.info("Nenhuma estadia com período válido e todas as regras atendidas. Resultados Sem informação não são considerados aprovados.")
                else:
                    render_panel(approved)
                st.subheader("Válidas para validação manual — OTS 2 e OTD 2")
                st.caption("Lista de NFs com OTS 2 e OTD 2 dentro do prazo. Confira as demais regras, a correspondência e a existência de estadia antes de aprovar.")
                manual = resultado.loc[resultado["OTS 2"].eq("Dentro do prazo") & resultado["OTD 2"].eq("Dentro do prazo")].copy()
                manual.insert(0, "Tratativa", "Válida para validação manual")
                st.metric("NFs para validação manual", len(manual))
                st.dataframe(manual, hide_index=True, use_container_width=True)
                st.download_button("Exportar validação manual", exportar(manual), "validacao_manual.xlsx")
                with st.expander("Indicadores por regra"):
                    cols = st.columns(3)
                    for i, (name, value) in enumerate(general.items()):
                        cols[i % 3].metric(name, "—" if value is None else f"{value:.2f}%" if name.endswith("%") else value)
                    st.caption("Percentuais excluem Sem informação. Contagem por NF + placa única; nenhum dado ausente é presumido como regra dispensada.")
                    st.dataframe(table, hide_index=True, use_container_width=True)
                with st.expander("Todos os resultados da análise"):
                    st.dataframe(resultado, hide_index=True, use_container_width=True)
                    st.download_button("Exportar análise", exportar(resultado), "performance_nf_placa.xlsx")
                if usuario['role'] in {"ADMIN", "OPERACIONAL"}:
                    st.caption("Publica a análise completa das versões selecionadas para consulta no Estadias.")
                    if st.button("Publicar resultado para Estadias", type="primary"):
                        token = st.secrets.get("performance_publish", {}).get("token") or ots_settings()["token"]
                        publish(resultado_completo, sources, analyzed_at, token)
                        st.success("Resultado publicado. No Estadias, abra PerformanceRW e clique em Atualizar resultado.")
        except ValueError as exc:
            st.error(str(exc))

elif pagina == "Sincronização Estadias":
    st.subheader("Resultados do Estadias")
    st.caption("Recebe os resultados e o LCTE com Observação já importado no Estadias. Não é necessário importar a mesma planilha novamente.")
    config = ots_settings()
    try:
        config["token"] = st.secrets.get("estadias_sync", {}).get("token") or config["token"]
        config["branch"] = str(st.secrets.get("estadias_sync", {}).get("branch", "backup-data"))
    except FileNotFoundError:
        config["branch"] = "backup-data"
    st.caption("O token precisa de leitura no repositório Estadias. Pode usar o mesmo token do OTS ou estadias_sync.token nos Secrets.")
    if st.button("Sincronizar Estadias", type="primary"):
        try:
            with st.spinner("Recebendo resultados…"):
                total, changed = sync_ots(**config, fonte=FONTES[1])
            st.success(f"Base conferida: {total:,} registros.")
            lcte_state = ots_status(fonte=FONTES[2])
            if lcte_state:
                st.success(f"LCTE / Observação disponível: {len(carregar(lcte_state[0])):,} registros. Abra Análise Performance.")
            else:
                st.warning("Este backup não contém LCTE. No Estadias, envie um backup completo com as importações e sincronize novamente.")
        except ValueError as exc:
            st.error(str(exc))
    estado = ots_status(fonte=FONTES[1])
    if estado:
        st.caption(f"Backup: {estado[1]} • Sincronização UTC: {estado[2]}")
        st.dataframe(carregar(estado[0]), hide_index=True, use_container_width=True)

elif pagina == "Sincronização OTS e OTD":
    st.subheader("Banco OTS e OTD")
    st.caption("Origem: ontimeshipdev.streamlit.app • mathotto95-byte/OTSeOTD")
    st.info("Recebe o último backup publicado no GitHub, com todos os registros e alterações. Para incluir mudanças recentes, use Enviar backup para GitHub no OTS/OTD antes de sincronizar.")
    config = ots_settings()
    if not config["token"]:
        st.warning("Para repositório privado, configure ots_sync.token nos Secrets do Performance com acesso de leitura ao OTSeOTD.")
    if st.button("Sincronizar resultados", type="primary"):
        try:
            with st.spinner("Recebendo Banco OTS e OTD…"):
                total, changed = sync_ots(**config)
            st.success(f"{total:,} registros recebidos." if changed else f"Base conferida: {total:,} registros, sem alterações.")
        except ValueError as exc:
            st.error(str(exc))
    estado = ots_status()
    if estado:
        st.write(f"Backup da origem: {estado[1]}")
        st.caption(f"Última sincronização (UTC): {estado[2]}")
        resultado = carregar(estado[0])
        st.dataframe(resultado, hide_index=True, use_container_width=True)
        st.download_button("Exportar Banco OTS e OTD", exportar(resultado), "banco_ots_otd.xlsx")

elif pagina == "Visão geral":
    bases = {}
    for fonte in FONTES:
        base = hist[hist.fonte == fonte]
        estado = ots_status(fonte=fonte)
        if estado:
            base = hist[hist.id == estado[0]]
        bases[fonte] = carregar(int(base.iloc[0].id)) if not base.empty else pd.DataFrame()
    st.subheader("Atendimento das regras OTS e OTD")
    if bases[FONTES[2]].empty:
        st.info("Sincronize Estadias para receber o LCTE e exibir os indicadores das cinco regras.")
    else:
        try:
            resultado = analyze(bases[FONTES[2]], bases[FONTES[0]], bases[FONTES[1]])
            meses = resultado["Emissão da NF"].map(rules.date).map(lambda d: d.strftime("%Y-%m") if pd.notna(d) else "Sem data")
            mes = st.selectbox("Mês da análise", ["Todos", *sorted(meses.unique(), reverse=True)], key="overview_month")
            resultado_completo = resultado.copy()
            meses_comparativo = []
            for periodo in sorted(meses.unique(), reverse=True):
                periodo_resultado = resultado_completo.loc[meses.eq(periodo)]
                periodo_table, _ = indicators(periodo_resultado)
                meses_comparativo.append({
                    "Mês": periodo,
                    **{row["Regra"]: "—" if pd.isna(row["% Dentro"]) else f'{row["% Dentro"]:.2f}%'
                       for row in periodo_table.to_dict("records")},
                })
            if mes != "Todos":
                resultado = resultado.loc[meses.eq(mes)]
            table, general = indicators(resultado)
            for col, row in zip(st.columns(len(rules.RULES)), table.to_dict("records")):
                with col:
                    col.metric(row["Regra"], "—" if pd.isna(row["% Dentro"]) else f'{row["% Dentro"]:.2f}%')
            st.subheader("Resumo comparativo por mês")
            st.dataframe(pd.DataFrame(meses_comparativo, columns=["Mês", *rules.RULES]), hide_index=True, use_container_width=True)
        except ValueError as exc:
            st.error(str(exc))

elif pagina == "Backup":
    backup.render(backup_config)

elif pagina == "Importações":
    fonte = st.selectbox("Base de destino", FONTES)
    st.caption("Importe o Excel exportado pelo sistema de origem. Cada envio é salvo como uma versão completa da base selecionada.")
    upload = st.file_uploader("Arquivo de resultados", type=["xlsx", "xls"], key=fonte)
    if upload is not None:
        try:
            content = upload.getvalue()
            with pd.ExcelFile(BytesIO(content)) as workbook:
                abas = workbook.sheet_names
            preferidas = ["ots_otd"] if fonte == FONTES[0] else ["resultado_completo", "resultado", "completo"]
            preferida = next((aba for aba in preferidas if aba in abas), abas[0])
            aba = st.selectbox("Aba com os resultados", abas, index=abas.index(preferida))
            linha = st.number_input("Linha do cabeçalho", min_value=1, max_value=100, value=1)
            df = ler_planilha(content, aba, int(linha))
            st.write(f"{len(df):,} registros • {len(df.columns)} colunas")
            st.dataframe(df.head(100), hide_index=True, use_container_width=True)
            st.caption("Prévia dos primeiros 100 registros. Confira a fonte, a aba e as colunas antes de importar.")
            if st.button("Importar resultados", type="primary"):
                if fonte == FONTES[2]:
                    prepare_lcte(df)
                if salvar(fonte, upload.name, aba, df):
                    st.success(f"Importação concluída: {len(df):,} registros salvos.")
                else:
                    st.info("Esta base já foi importada. Nenhuma duplicação foi criada.")
        except Exception as exc:
            st.error(f"Não foi possível importar o arquivo: {exc}")

elif pagina == "Consultar resultados":
    fonte = st.selectbox("Base", FONTES)
    base = hist[hist.fonte == fonte]
    if base.empty:
        st.info("Nenhuma importação disponível para esta base.")
    else:
        opcoes = {int(row.id): f"#{row.id} • {row.criado_em} • {row.arquivo} • {row.aba}" for row in base.itertuples()}
        estado = ots_status(fonte=fonte)
        if estado and estado[0] in opcoes:
            opcoes = {estado[0]: opcoes[estado[0]] + " • Última sincronização", **{k: v for k, v in opcoes.items() if k != estado[0]}}
        selecionada = st.selectbox("Versão importada", list(opcoes), format_func=opcoes.get)
        df = carregar(selecionada)
        busca = st.text_input("Buscar nos resultados")
        if busca.strip():
            mask = df.astype(str).apply(lambda col: col.str.contains(busca.strip(), case=False, regex=False)).any(axis=1)
            df = df.loc[mask]
        st.write(f"{len(df):,} registros")
        st.dataframe(df, hide_index=True, use_container_width=True)
        st.download_button("Exportar consulta em Excel", exportar(df), "regras_estadia_resultados.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

else:
    st.subheader("Histórico de importações")
    if hist.empty:
        st.info("Nenhuma importação realizada.")
    else:
        st.dataframe(hist.rename(columns={"fonte": "Base", "arquivo": "Arquivo", "aba": "Aba", "criado_em": "Importado em", "quantidade": "Registros"}), hide_index=True, use_container_width=True)
