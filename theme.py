import streamlit as st


def apply_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
            --rw-bg: #030914;
            --rw-panel: #071526;
            --rw-panel-soft: #0f2438;
            --rw-navy: #020d3f;
            --rw-gold: #d4af37;
            --rw-gold-strong: #d6a933;
            --rw-border: rgba(212, 175, 55, 0.32);
            --rw-text: #f8fafc;
            --rw-muted: rgba(248, 250, 252, 0.72);
        }

        .stApp {
            background: var(--rw-bg) !important;
            color: var(--rw-text) !important;
        }
        .block-container {
            padding-top: 4.5rem;
            max-width: 1550px;
        }
        h1, h2, h3, label, p, span, div {
            color: var(--rw-text);
        }
        [data-testid="stCaptionContainer"] p {
            color: var(--rw-muted) !important;
        }

        [data-testid="stSidebar"] {
            background: var(--rw-navy) !important;
            border-right: 1px solid var(--rw-border);
        }
        [data-testid="stSidebar"] * {
            color: var(--rw-text) !important;
        }

        div[data-testid="stMetric"] {
            background: var(--rw-navy);
            border: 1px solid var(--rw-border);
            border-radius: 8px;
            padding: 12px 14px;
        }
        div[data-testid="stMetric"] * {
            color: var(--rw-text) !important;
        }

        div[data-testid="stExpander"] {
            background: rgba(7, 21, 38, 0.72);
            border: 1px solid var(--rw-border);
            border-radius: 8px;
        }
        div[data-testid="stExpander"] summary {
            color: var(--rw-text) !important;
            font-weight: 800;
        }

        div[data-testid="stVerticalBlockBorderWrapper"] {
            background: rgba(7, 21, 38, 0.72);
            border-color: var(--rw-border) !important;
            border-radius: 8px;
        }

        div[data-testid="stDataFrame"] {
            border: 1px solid var(--rw-border);
            border-radius: 8px;
            overflow: hidden;
        }

        .stButton > button, .stDownloadButton > button {
            background: var(--rw-panel);
            border: 1px solid var(--rw-gold);
            border-radius: 8px;
            color: var(--rw-text) !important;
            font-weight: 800;
        }
        .stButton > button:hover, .stDownloadButton > button:hover {
            background: var(--rw-gold);
            border-color: var(--rw-gold);
            color: var(--rw-bg) !important;
        }
        .stButton > button[kind="primary"] {
            background: var(--rw-gold);
            color: var(--rw-bg) !important;
            border-color: var(--rw-gold);
        }
        .stButton > button[kind="primary"]:hover {
            background: var(--rw-gold-strong);
            color: var(--rw-bg) !important;
        }

        [data-baseweb="input"] input, [data-baseweb="select"] div {
            color: var(--rw-text) !important;
        }
        [data-baseweb="input"], [data-baseweb="select"] > div {
            background: var(--rw-panel) !important;
            border-color: var(--rw-border) !important;
        }

        .rw-title-row {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 4px;
        }
        .rw-title-row h1 {
            margin: 0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
