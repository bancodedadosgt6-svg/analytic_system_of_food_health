from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from graphic import render_graphics_tab
from map import render_map_tab
from settings import (
    APP_SUBTITLE,
    APP_TITLE,
    get_datasets_catalog,
    load_css,
    sync_google_drive_data,
)
from sidebar import render_sidebar
from table import render_table_tab


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="logos/logo_vazado.png",
    layout="wide",
)


DEFAULT_PAGE_SIZE = 25
DEFAULT_MAP_HEIGHT = 550

BASE_DIR = Path(__file__).resolve().parent
FUNDO_PATH = BASE_DIR / "logos" / "fundo.png"


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
        </style>
        """,
        unsafe_allow_html=True,
    )


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


def render_sync_metrics(sync_result: dict) -> None:
    """
    Renderiza as métricas de sincronização da base local.
    """
    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Arquivos verificados", sync_result.get("checked", 0))
    c2.metric("Novos downloads", sync_result.get("downloaded", 0))
    c3.metric("Atualizados", sync_result.get("updated", 0))
    c4.metric("Ignorados", sync_result.get("skipped", 0))


def main() -> None:
    load_css("style.css")
    aplicar_fundo_sistema()

    render_header()

    with st.spinner("Sincronizando base local..."):
        sync_result = sync_google_drive_data()

    render_sync_metrics(sync_result)

    render_sidebar()

    catalog = get_datasets_catalog()

    if not catalog:
        st.warning("Nenhum dado encontrado.")
        return

    selected_dataset = catalog[0]["name"]

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


if __name__ == "__main__":
    main()