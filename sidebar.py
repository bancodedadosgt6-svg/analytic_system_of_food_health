from __future__ import annotations

import streamlit as st

from settings import APP_SUBTITLE, APP_TITLE, SPONSORS, get_datasets_catalog


DEFAULT_THEME_CSS = """
<style>
    .block-container {padding-top: 1.2rem;}
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
</style>
"""


def render_sidebar() -> dict:
    st.markdown(DEFAULT_THEME_CSS, unsafe_allow_html=True)

    catalog = get_datasets_catalog()
    dataset_names = [item["name"] for item in catalog]
    geo_names = [item["name"] for item in catalog if item["is_geospatial"]]

    with st.sidebar:
        st.title(APP_TITLE)
        st.caption(APP_SUBTITLE)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Base de dados")
        if dataset_names:
            selected_dataset = st.selectbox(
                "Dataset analítico",
                options=dataset_names,
                index=0,
            )
        else:
            st.selectbox("Dataset analítico", options=[], disabled=True)
            selected_dataset = None

        if geo_names:
            selected_geo_dataset = st.selectbox(
                "Dataset geoespacial",
                options=geo_names,
                index=0,
            )
        else:
            st.selectbox("Dataset geoespacial", options=[], disabled=True)
            selected_geo_dataset = None
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Configurações visuais")
        page_size = st.slider("Linhas por página", min_value=10, max_value=200, value=25, step=5)
        map_height = st.slider("Altura do mapa", min_value=350, max_value=900, value=550, step=50)
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Patrocinadores / Rede")
        for sponsor in SPONSORS:
            st.write(f"• {sponsor}")
        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="sidebar-card">', unsafe_allow_html=True)
        st.subheader("Catálogo local")
        st.caption(f"Datasets disponíveis: {len(catalog)}")
        for item in catalog:
            badge = "🗺️" if item["is_geospatial"] else "📊"
            st.write(f"{badge} {item['file_name']} ({item['rows']} linhas)")
        st.markdown('</div>', unsafe_allow_html=True)

    return {
        "selected_dataset": selected_dataset,
        "selected_geo_dataset": selected_geo_dataset,
        "page_size": page_size,
        "map_height": map_height,
    }
