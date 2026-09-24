from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from core import FONTES, carregar, exportar, historico, ler_planilha, salvar
from theme import apply_theme
from rw_theme import apply_theme as apply_rw_theme, render_brand_header, render_sidebar_logo
from auth import enforce_authentication, current_user, logout
from ots_sync import settings as ots_settings, sync as sync_ots, status as ots_status


LOGO_PATH = Path(__file__).resolve().parent / "assets" / "rodo_wall_logo.png"

st.set_page_config(page_title="Performance RW", page_icon=str(LOGO_PATH), layout="wide")
apply_theme()
apply_rw_theme(LOGO_PATH)
if not enforce_authentication():
    st.stop()
titulo, atualizar = st.columns([4, 1])
with titulo:
    render_brand_header("Performance RW", "Importação e consulta dos resultados de OTS/OTD e Estadia.")
with atualizar:
    st.write("")
    if st.button("Atualizar página", use_container_width=True):
        st.rerun()

render_sidebar_logo()
st.sidebar.title("Performance RW")
st.sidebar.caption("Gestão operacional • RW")
usuario = current_user()
st.sidebar.write(f"**Usuário:** {usuario['name']}")
st.sidebar.write(f"**Perfil:** {usuario['role'].title()}")
menu = ["Visão geral", "Consultar resultados", "Histórico"]
if usuario['role'] in {"ADMIN", "OPERACIONAL"}:
    menu.insert(1, "Importações")
    menu.insert(1, "Sincronização OTS e OTD")
pagina = st.sidebar.radio("Menu", menu)
if st.sidebar.button("Sair", use_container_width=True):
    logout()
st.sidebar.divider()
st.sidebar.caption("Bases: OTS e OTD / Estadia")
st.divider()
hist = historico()

if pagina == "Sincronização OTS e OTD":
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
    for col, fonte in zip(st.columns(2), FONTES):
        base = hist[hist.fonte == fonte]
        estado = ots_status() if fonte == FONTES[0] else None
        if estado:
            base = hist[hist.id == estado[0]]
        with col:
            st.subheader(fonte)
            st.metric("Registros na última importação", int(base.iloc[0].quantidade) if not base.empty else 0)
            if base.empty:
                st.info("Aguardando importação.")
            else:
                st.caption(f"Arquivo: {base.iloc[0].arquivo} • {base.iloc[0].criado_em}")
    st.info("Regras de cruzamento e cálculo aguardando definição. Os dados importados ficam disponíveis para consulta.")

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
        estado = ots_status() if fonte == FONTES[0] else None
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
