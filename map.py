from __future__ import annotations

import pandas as pd
import streamlit as st
import folium
from streamlit_folium import st_folium

from settings import detect_lat_lon_columns, get_dataset_by_name, get_numeric_columns



def render_map_tab(dataset_name: str, map_height: int = 550) -> None:
    st.subheader("Mapa")

    if not dataset_name:
        st.info("Selecione um dataset geoespacial na sidebar.")
        return

    df = get_dataset_by_name(dataset_name)
    if df.empty:
        st.warning("O dataset selecionado está vazio ou não pôde ser lido.")
        return

    lat_col, lon_col = detect_lat_lon_columns(df)
    if not lat_col or not lon_col:
        st.warning("O dataset não possui colunas reconhecidas de latitude e longitude.")
        return

    map_df = df.copy()
    map_df[lat_col] = pd.to_numeric(map_df[lat_col], errors="coerce")
    map_df[lon_col] = pd.to_numeric(map_df[lon_col], errors="coerce")
    map_df = map_df.dropna(subset=[lat_col, lon_col])

    if map_df.empty:
        st.warning("Não há coordenadas válidas para renderizar o mapa.")
        return

    numeric_cols = get_numeric_columns(map_df)
    popup_columns = st.multiselect(
        "Campos no popup",
        options=map_df.columns.tolist(),
        default=map_df.columns.tolist()[: min(6, len(map_df.columns))],
    )
    size_metric = st.selectbox(
        "Métrica para tamanho do ponto",
        options=[None] + numeric_cols,
        format_func=lambda x: "Tamanho fixo" if x is None else x,
    )

    center_lat = float(map_df[lat_col].median())
    center_lon = float(map_df[lon_col].median())
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=10, tiles="CartoDB positron")

    for _, row in map_df.iterrows():
        popup_html = "<br>".join(
            f"<b>{col}:</b> {row[col]}" for col in popup_columns if col in row.index
        )
        radius = 6
        if size_metric:
            try:
                value = float(row[size_metric]) if pd.notna(row[size_metric]) else 0
                radius = max(4, min(20, abs(value) / 10))
            except Exception:
                radius = 6

        folium.CircleMarker(
            location=[row[lat_col], row[lon_col]],
            radius=radius,
            popup=folium.Popup(popup_html, max_width=350),
            fill=True,
            fill_opacity=0.7,
            weight=1,
        ).add_to(fmap)

    st_folium(fmap, use_container_width=True, height=map_height)

    st.dataframe(map_df.head(50), use_container_width=True)
