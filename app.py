from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict

import streamlit as st

from graphic import render_graphics_tab
from map import render_map_tab
from settings import (
    APP_SUBTITLE,
    APP_TITLE,
    get_datasets_catalog,
    load_css,
    sync_supabase_to_parquet,
)
from sidebar import render_sidebar
from table import render_table_tab


# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
FUNDO_PATH = BASE_DIR / "logos" / "fundo.png"
LOGO_ICON_PATH = BASE_DIR / "logos" / "logo_vazado.png"

DEFAULT_PAGE_SIZE = 25
DEFAULT_MAP_HEIGHT = 550


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=str(LOGO_ICON_PATH) if LOGO_ICON_PATH.exists() else "📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================================================
# ESTILO / FUNDO
# =========================================================

def aplicar_fundo_sistema() -> None:
    """
    Aplica a imagem logos/fundo.png como fundo principal do sistema.

    A imagem é convertida para base64 para funcionar corretamente
    tanto localmente quanto no deploy do Streamlit.
    """
    if not FUNDO_PATH.exists():
        return

    fundo_base64 = base64.b64encode(FUNDO_PATH.read_bytes()).decode("utf-8")

    st.markdown(
        f"""
        <style>
            .stApp {{
                background-image: url("data:image/png;base64,{fundo_base64}") !important;
                background-size: cover !important;
                background-position: center center !important;
                background-repeat: no-repeat !important;
                background-attachment: fixed !important;
            }}

            .block-container {{
                background: transparent !important;
            }}

            [data-testid="stHeader"] {{
                background: transparent !important;
            }}

            [data-testid="stToolbar"] {{
                background: transparent !important;
            }}

            [data-testid="stDecoration"] {{
                background: transparent !important;
            }}

            section.main > div {{
                background: transparent !important;
            }}

            main {{
                background: transparent !important;
            }}

            .sync-status-card {{
                background: rgba(255, 255, 255, 0.90);
                border: 1px solid rgba(148, 163, 184, 0.25);
                border-radius: 16px;
                padding: 0.95rem 1.1rem;
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
                margin-bottom: 1rem;
            }}

            .sync-status-title {{
                font-size: 0.88rem;
                font-weight: 800;
                color: #0f172a;
                margin-bottom: 0.15rem;
            }}

            .sync-status-text {{
                font-size: 0.82rem;
                color: #475569;
                line-height: 1.25rem;
                margin: 0;
            }}

            .dashboard-alert-card {{
                background: rgba(255, 255, 255, 0.94);
                border: 1px solid rgba(245, 158, 11, 0.25);
                border-radius: 16px;
                padding: 1.2rem 1.3rem;
                box-shadow: 0 14px 30px rgba(15, 23, 42, 0.08);
                margin-top: 1rem;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# CABEÇALHO
# =========================================================

def render_header() -> None:
    """
    Renderiza o cabeçalho principal do painel.
    """
    st.markdown(
        """
        <div class="main-header-card">
        """,
        unsafe_allow_html=True,
    )

    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    st.markdown(
        """
        </div>
        """,
        unsafe_allow_html=True,
    )


# =========================================================
# SINCRONIZAÇÃO / MÉTRICAS
# =========================================================

def render_sync_status(sync_result: Dict[str, Any]) -> None:
    """
    Renderiza uma mensagem curta sobre a sincronização Supabase → Parquet.
    """
    success = bool(sync_result.get("success", False))
    source = sync_result.get("source", "cache")
    message = sync_result.get("message") or ""

    if success and source == "supabase":
        title = "Base analítica atualizada"
    elif success and source == "cache":
        title = "Base analítica no sistema"
    else:
        title = "Usando cache local"

    st.markdown(
        f"""
        <div class="sync-status-card">
            <div class="sync-status-title">{title}</div>
            <p class="sync-status-text">
                {message}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sync_metrics(sync_result: Dict[str, Any]) -> None:
    """
    Renderiza métricas da sincronização Supabase → Parquet.
    """
    supabase_rows = int(sync_result.get("supabase_rows", 0) or 0)
    cache_rows = int(sync_result.get("cache_rows", sync_result.get("rows", 0)) or 0)
    ubs_count = int(sync_result.get("ubs_count", 0) or 0)
    last_sync = sync_result.get("last_sync") or "Não sincronizado"

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Registros do Banco", supabase_rows)
    c2.metric("Dados já coletados", cache_rows)
    c3.metric("Total de UBS", ubs_count)
    c4.metric("Última atualização", last_sync)


def sincronizar_base_analitica() -> Dict[str, Any]:
    """
    Sincroniza os dados do Supabase para o Parquet local.

    Supabase é a fonte oficial.
    Parquet é o cache analítico local usado pelo dashboard.
    """
    with st.spinner("Sincronizando dados..."):
        return sync_supabase_to_parquet(force=False)


# =========================================================
# RENDERIZAÇÃO DO DASHBOARD
# =========================================================

def render_empty_state() -> None:
    """
    Renderiza aviso quando não há dados disponíveis.
    """
    st.markdown(
        """
        <div class="dashboard-alert-card">
            <h3 style="margin-top:0; color:#0f172a;">Nenhum dado encontrado</h3>
            <p style="color:#475569; margin-bottom:0;">
                O painel ainda não encontrou registros no banco ou não conseguiu gerar
                o arquivo análitico. Verifique se existem dados na tabela
                <strong>registros_saude_alimentar</strong> e se as variáveis
                <strong>SUPABASE_URL</strong> e <strong>SUPABASE_ANON_KEY</strong>
                estão configuradas corretamente.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard_tabs(selected_dataset: str) -> None:
    """
    Renderiza as abas principais do painel.
    """
    tab1, tab2, tab3 = st.tabs(["Tabela", "Gráficos", "Mapas"])

    with tab1:
        render_table_tab(
            dataset_name=selected_dataset,
            page_size=DEFAULT_PAGE_SIZE,
        )

    with tab2:
        render_graphics_tab(dataset_name=selected_dataset)

    with tab3:
        render_map_tab(
            dataset_name=selected_dataset,
            map_height=DEFAULT_MAP_HEIGHT,
        )


# =========================================================
# MAIN
# =========================================================

def main() -> None:
    load_css("style.css")
    aplicar_fundo_sistema()

    render_header()

    sync_result = sincronizar_base_analitica()

    render_sync_status(sync_result)
    render_sync_metrics(sync_result)

    render_sidebar()

    catalog = get_datasets_catalog()

    if not catalog:
        render_empty_state()
        return

    selected_dataset = catalog[0]["name"]

    render_dashboard_tabs(selected_dataset)


if __name__ == "__main__":
    main()