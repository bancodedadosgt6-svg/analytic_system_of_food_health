from __future__ import annotations

from pathlib import Path

import streamlit as st

from settings import APP_SUBTITLE, APP_TITLE, SPONSORS


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
</style>
"""


def render_sidebar() -> dict:
    st.markdown(DEFAULT_THEME_CSS, unsafe_allow_html=True)

    with st.sidebar:
        if LOGO_PATH.exists():
            st.markdown('<div class="sidebar-logo-wrap">', unsafe_allow_html=True)
            st.image(str(LOGO_PATH), use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.title(APP_TITLE)
        st.caption(APP_SUBTITLE)

        st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Parceiros / Equipes")
        for sponsor in SPONSORS:
            st.write(f"• {sponsor}")
        st.markdown("</div>", unsafe_allow_html=True)

    return {}