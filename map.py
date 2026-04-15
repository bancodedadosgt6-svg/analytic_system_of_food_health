from __future__ import annotations

from pathlib import Path

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from calc import get_filter_options, has_health_food_schema, prepare_health_food_dataframe
from settings import get_dataset_by_name


BASE_DIR = Path(__file__).resolve().parent
PIN_ICON_PATH = BASE_DIR / "logos" / "pin_ubs.png"

# =========================================================
# COORDENADAS FIXAS DAS UBS
# SUBSTITUA pelos valores reais quando tiver
# =========================================================
UBS_COORDS = {
    "Jardins-Mangueral": {"lat": -15.889149045911136, "lon": -47.81349780874119},
    "Gama": {"lat": -16.02062061175684, "lon": -48.08485927435655},
    "Santa-Maria": {"lat": -16.007567443627305, "lon": -47.98995745952408},
}


def render_map_tab(dataset_name: str, map_height: int = 550) -> None:
    st.subheader("Mapa das UBSs")

    if not dataset_name:
        st.info("Selecione um dataset analítico na sidebar.")
        return

    df = get_dataset_by_name(dataset_name)
    if df.empty:
        st.warning("O dataset selecionado está vazio ou não pôde ser lido.")
        return

    if not has_health_food_schema(df):
        st.warning("O dataset selecionado não possui o schema esperado para o mapa das UBSs.")
        return

    df = prepare_health_food_dataframe(df)
    options = get_filter_options(df)

    with st.expander("Filtros do mapa", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_categorias = st.multiselect(
                "Filtrar profissional",
                options=options["categorias"],
                default=[],
                key="map_categorias",
            )

        with col2:
            selected_tipos = st.multiselect(
                "Filtrar Tipo de atendimento",
                options=options["tipos"],
                default=[],
                key="map_tipos",
            )

        competencias = options["competencias"]

        competencia_inicio = st.selectbox(
            "Competência inicial",
            options=[None] + competencias,
            format_func=lambda x: "Selecione" if x is None else x,
            key="map_comp_inicio",
        )

        competencia_fim = st.selectbox(
            "Competência final",
            options=[None] + competencias,
            format_func=lambda x: "Selecione" if x is None else x,
            key="map_comp_fim",
        )

    monthly_df = _build_ubs_monthly_totals(
        df=df,
        categorias=selected_categorias if selected_categorias else None,
        tipos=selected_tipos if selected_tipos else None,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    coords_validas = {
        nome: coord
        for nome, coord in UBS_COORDS.items()
        if coord["lat"] is not None and coord["lon"] is not None
    }

    if not coords_validas:
        st.warning(
            "As coordenadas das UBS ainda não foram definidas em UBS_COORDS no map.py. "
            "Preencha latitude e longitude das 3 UBSs."
        )
        return

    center_lat = sum(item["lat"] for item in coords_validas.values()) / len(coords_validas)
    center_lon = sum(item["lon"] for item in coords_validas.values()) / len(coords_validas)

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
        zoom_control=True,
        boxZoom=True
    )

    has_custom_icon = PIN_ICON_PATH.exists()

    for ubs_name, coord in coords_validas.items():
        tooltip_html = _build_ubs_tooltip_html(
            monthly_df=monthly_df,
            ubs_name=ubs_name,
        )

        if has_custom_icon:
            icon = folium.CustomIcon(
                icon_image=str(PIN_ICON_PATH),
                icon_size=(42, 42),
                icon_anchor=(21, 42),
                popup_anchor=(0, -36),
            )
        else:
            icon = folium.Icon(color="blue", icon="info-sign")

        folium.Marker(
            location=[coord["lat"], coord["lon"]],
            icon=icon,
            tooltip=folium.Tooltip(tooltip_html, sticky=True),
        ).add_to(fmap)

    map_data = st_folium(
    fmap,
    use_container_width=True,
    height=map_height,
    returned_objects=["last_clicked", "zoom", "center"],
)

    st.markdown("#### Base resumida do mapa")
    st.dataframe(monthly_df, use_container_width=True)

    st.caption(
        "Cada pin representa uma UBS. O tooltip mostra a competência e o total de registros por mês, "
        "considerando os filtros aplicados."
    )


def _build_ubs_monthly_totals(
    df: pd.DataFrame,
    categorias: list[str] | None = None,
    tipos: list[str] | None = None,
    competencia_inicio: str | None = None,
    competencia_fim: str | None = None,
) -> pd.DataFrame:
    """
    Agrega os registros totais por UBS e por competência (ano_mes),
    para uso no mapa.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    required_cols = {"UBS", "Categoria", "Tipo", "ano_mes", "Valor"}
    if not required_cols.issubset(df.columns):
        return pd.DataFrame()

    base = df.copy()

    if categorias:
        base = base[base["Categoria"].isin(categorias)]

    if tipos:
        base = base[base["Tipo"].isin(tipos)]

    if competencia_inicio:
        base = base[base["ano_mes"] >= competencia_inicio]

    if competencia_fim:
        base = base[base["ano_mes"] <= competencia_fim]

    if base.empty:
        return pd.DataFrame()

    out = (
        base.groupby(["UBS", "ano_mes"], dropna=False)["Valor"]
        .sum()
        .reset_index()
        .rename(columns={"Valor": "Registro"})
        .sort_values(["UBS", "ano_mes"])
    )

    return out


def _build_ubs_tooltip_html(
    monthly_df: pd.DataFrame,
    ubs_name: str,
    max_rows: int = 24,
) -> str:
    """
    Monta o HTML do tooltip do mapa para uma UBS.
    Exibe somente competência e total de registros por mês.
    """
    if monthly_df is None or monthly_df.empty:
        return f"""
        <div style="min-width:240px;">
            <div style="font-weight:700; margin-bottom:6px;">{ubs_name}</div>
            <div>Sem dados disponíveis.</div>
        </div>
        """

    subset = monthly_df[monthly_df["UBS"] == ubs_name].copy()

    if subset.empty:
        return f"""
        <div style="min-width:240px;">
            <div style="font-weight:700; margin-bottom:6px;">{ubs_name}</div>
            <div>Sem dados disponíveis.</div>
        </div>
        """

    subset = subset.head(max_rows)

    linhas = []
    for _, row in subset.iterrows():
        comp = row.get("ano_mes", "")
        registro = row.get("Registro", 0)
        try:
            registro_fmt = f"{float(registro):,.0f}".replace(",", ".")
        except Exception:
            registro_fmt = str(registro)

        linhas.append(
            f"<tr>"
            f"<td style='padding:2px 8px 2px 0;'><b>{comp}</b></td>"
            f"<td style='padding:2px 0; text-align:right;'>{registro_fmt}</td>"
            f"</tr>"
        )

    total_geral = subset["Registro"].sum()
    try:
        total_fmt = f"{float(total_geral):,.0f}".replace(",", ".")
    except Exception:
        total_fmt = str(total_geral)

    rows_html = "".join(linhas)

    return f"""
    <div style="min-width:270px;">
        <div style="font-weight:700; margin-bottom:6px;">{ubs_name}</div>
        <div style="margin-bottom:6px;"><b>Total no período:</b> {total_fmt}</div>
        <table style="width:100%; border-collapse:collapse; font-size:12px;">
            <thead>
                <tr>
                    <th style="text-align:left; padding-bottom:4px;">Competência</th>
                    <th style="text-align:right; padding-bottom:4px;">Registros</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    """