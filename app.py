from __future__ import annotations

import streamlit as st

from graphic import render_graphics_tab
from map import render_map_tab
from settings import APP_SUBTITLE, APP_TITLE, sync_google_drive_data
from sidebar import render_sidebar
from table import render_table_tab

st.set_page_config(page_title=APP_TITLE, layout="wide")


def main() -> None:
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    with st.spinner("Sincronizando base local..."):
        sync_result = sync_google_drive_data()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Arquivos verificados", sync_result["checked"])
    c2.metric("Novos downloads", sync_result["downloaded"])
    c3.metric("Atualizados", sync_result["updated"])
    c4.metric("Ignorados", sync_result["skipped"])

    sidebar_state = render_sidebar()

    tab1, tab2, tab3 = st.tabs(["Tabela", "Gráficos", "Mapas"])

    with tab1:
        render_table_tab(
            dataset_name=sidebar_state["selected_dataset"],
            page_size=sidebar_state["page_size"],
        )

    with tab2:
        render_graphics_tab(dataset_name=sidebar_state["selected_dataset"])

    with tab3:
        render_map_tab(
            dataset_name=sidebar_state["selected_geo_dataset"],
            map_height=sidebar_state["map_height"],
        )


if __name__ == "__main__":
    main()
