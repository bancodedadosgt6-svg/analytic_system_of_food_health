from __future__ import annotations

from pathlib import Path

import streamlit as st

from settings import (
    APP_SUBTITLE,
    APP_TITLE,
    SPONSORS,
    clear_dataset_caches,
    sync_google_drive_data,
)


BASE_DIR = Path(__file__).resolve().parent
LOGO_PATH = BASE_DIR / "logos" / "logo.png"


DEFAULT_THEME_CSS = """
<style>
    .block-container {
        padding-top: 1.2rem;
    }

    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0f172a 0%, #111827 100%);
    }

    [data-testid="stSidebar"] * {
        color: white !important;
    }

    .sidebar-card {
        border: 1px solid rgba(255,255,255,0.15);
        border-radius: 12px;
        padding: 12px;
        margin-bottom: 12px;
        background: rgba(255,255,255,0.05);
    }

    .sidebar-logo-wrap {
        display: flex;
        justify-content: center;
        margin-bottom: 0.8rem;
        margin-top: 0.2rem;
    }

    .sidebar-divider {
        height: 1px;
        background: rgba(255,255,255,0.12);
        margin: 0.8rem 0 1rem 0;
        border-radius: 999px;
    }

    .sidebar-bottom-spacer {
        height: 2rem;
    }

    .sidebar-update-card {
        position: sticky;
        bottom: 0.8rem;
        z-index: 10;
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 14px;
        padding: 12px;
        margin-top: 1.2rem;
        background: linear-gradient(
            180deg,
            rgba(15, 23, 42, 0.96) 0%,
            rgba(17, 24, 39, 0.96) 100%
        );
        box-shadow: 0 12px 28px rgba(0,0,0,0.28);
        backdrop-filter: blur(4px);
    }

    .sidebar-update-title {
        font-size: 0.95rem;
        font-weight: 800;
        margin-bottom: 0.35rem;
        color: #ffffff !important;
    }

    .sidebar-update-text {
        font-size: 0.78rem;
        line-height: 1.25rem;
        color: rgba(255,255,255,0.72) !important;
        margin-bottom: 0.65rem;
    }

    .sidebar-sync-status {
        font-size: 0.76rem;
        line-height: 1.2rem;
        color: rgba(255,255,255,0.78) !important;
        margin-top: 0.45rem;
    }

    [data-testid="stSidebar"] .stButton > button {
        width: 100%;
        border: none !important;
        border-radius: 12px !important;
        padding: 0.72rem 0.9rem !important;
        font-weight: 800 !important;
        color: #0f172a !important;
        background: linear-gradient(90deg, #f2d878 0%, #8abc63 55%, #3aa964 100%) !important;
        box-shadow: 0 8px 18px rgba(0,0,0,0.22);
        transition: all 0.2s ease !important;
    }

    [data-testid="stSidebar"] .stButton > button:hover {
        transform: translateY(-1px);
        filter: brightness(1.04);
        box-shadow: 0 12px 26px rgba(0,0,0,0.30);
    }
</style>
"""


def _render_last_sync_feedback() -> None:
    """
    Mostra o resultado da última atualização manual acionada pela sidebar.
    """
    sync_result = st.session_state.get("sidebar_last_sync_result")

    if not sync_result:
        return

    checked = sync_result.get("checked", 0)
    downloaded = sync_result.get("downloaded", 0)
    updated = sync_result.get("updated", 0)
    skipped = sync_result.get("skipped", 0)

    st.markdown(
        f"""
        <div class="sidebar-sync-status">
            Última atualização manual:<br>
            Verificados: <strong>{checked}</strong><br>
            Novos: <strong>{downloaded}</strong> |
            Atualizados: <strong>{updated}</strong> |
            Ignorados: <strong>{skipped}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _atualizar_dados_nuvem() -> None:
    """
    Limpa os caches locais do Streamlit e refaz a consulta na nuvem.

    A função sync_google_drive_data() só baixa novamente quando o arquivo
    remoto mudou em relação ao metadata local.
    """
    clear_dataset_caches()

    with st.spinner("Atualizando dados na nuvem..."):
        sync_result = sync_google_drive_data()

    clear_dataset_caches()

    st.session_state["sidebar_last_sync_result"] = sync_result
    st.session_state["sidebar_sync_success"] = True


def render_sidebar() -> dict:
    st.markdown(DEFAULT_THEME_CSS, unsafe_allow_html=True)

    with st.sidebar:
        if LOGO_PATH.exists():
            st.markdown('<div class="sidebar-logo-wrap">', unsafe_allow_html=True)
            st.image(str(LOGO_PATH), width="stretch")
            st.markdown("</div>", unsafe_allow_html=True)

        st.title(APP_TITLE)
        st.caption(APP_SUBTITLE)

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Parceiros / Equipes")
        for sponsor in SPONSORS:
            st.write(f"• {sponsor}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="sidebar-bottom-spacer"></div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-update-card">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="sidebar-update-title">Atualização da base</div>
            <div class="sidebar-update-text">
                Recarrega os novos dados.
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button(
            "Atualizar dados",
            type="primary",
            width="stretch",
            key="sidebar_btn_atualizar_dados",
        ):
            try:
                _atualizar_dados_nuvem()
                st.toast("Dados atualizados com sucesso.", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar dados: {e}")

        _render_last_sync_feedback()

        st.markdown("</div>", unsafe_allow_html=True)

    return {}