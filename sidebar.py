from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import streamlit as st

from settings import (
    APP_SUBTITLE,
    APP_TITLE,
    SPONSORS,
    clear_dataset_caches,
    sync_supabase_to_parquet,
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

    .sidebar-sync-status strong {
        color: #ffffff !important;
        font-weight: 800;
    }

    .sidebar-mini-muted {
        color: rgba(255,255,255,0.62) !important;
        font-size: 0.72rem;
        line-height: 1.1rem;
        margin-top: 0.35rem;
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


def _as_int(value: Any, default: int = 0) -> int:
    """
    Converte valor para inteiro de forma segura.
    """
    try:
        return int(value or default)
    except Exception:
        return default


def _render_last_sync_feedback() -> None:
    """
    Mostra o resultado da última atualização manual acionada pela sidebar.
    """
    sync_result: Dict[str, Any] | None = st.session_state.get("sidebar_last_sync_result")

    if not sync_result:
        return

    success = bool(sync_result.get("success", False))
    source = sync_result.get("source", "cache")

    supabase_rows = _as_int(sync_result.get("supabase_rows", 0))
    cache_rows = _as_int(sync_result.get("cache_rows", sync_result.get("rows", 0)))
    ubs_count = _as_int(sync_result.get("ubs_count", 0))
    last_sync = sync_result.get("last_sync") or "Não sincronizado"

    if success and source == "supabase":
        status_text = "Atualização concluída pelo banco de dados."
    elif success and source == "cache":
        status_text = "Cache local já estava atualizado."
    else:
        status_text = "Falha na consulta. Usando cache local, se existir."

    st.markdown(
        f"""
        <div class="sidebar-sync-status">
            Última atualização manual:<br>
            <strong>{status_text}</strong><br><br>
            Supabase: <strong>{supabase_rows}</strong> registros<br>
            Parquet local: <strong>{cache_rows}</strong> registros<br>
            UBSs: <strong>{ubs_count}</strong><br>
            Atualizado em: <strong>{last_sync}</strong>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _atualizar_base_analitica() -> None:
    """
    Limpa os caches locais do Streamlit, consulta o Supabase
    e recria o Parquet local da base analítica.
    """
    clear_dataset_caches()

    with st.spinner("Coletando dados..."):
        sync_result = sync_supabase_to_parquet(force=True)

    clear_dataset_caches()

    st.session_state["sidebar_last_sync_result"] = sync_result
    st.session_state["sidebar_sync_success"] = bool(sync_result.get("success", False))


def render_sidebar() -> dict:
    """
    Renderiza a sidebar principal do painel analítico.
    """
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
                Consulta o banco de dados, recria o arquivo no sistema e atualiza os dashboards.
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
                _atualizar_base_analitica()
                st.toast("Base analítica atualizada com sucesso.", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao atualizar dados: {e}")

        _render_last_sync_feedback()

        st.markdown(
            """
            <div class="sidebar-mini-muted">
                Fonte oficial: SES-DF<br>
                Cache analítico: Parquet local
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("</div>", unsafe_allow_html=True)

    return {}