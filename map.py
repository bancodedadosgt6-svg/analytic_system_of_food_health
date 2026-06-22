from __future__ import annotations

import html
from pathlib import Path
from typing import Any, Dict, List, Optional

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from calc import (
    get_filter_options,
    get_schema,
    has_health_food_schema,
    prepare_health_food_dataframe,
)
from settings import get_dataset_by_name


BASE_DIR = Path(__file__).resolve().parent
PIN_ICON_PATH = BASE_DIR / "logos" / "pin_ubs.png"


# =========================================================
# COORDENADAS FIXAS DAS UBS
# =========================================================
# Nomes oficiais alinhados com o Supabase:
# - Gama
# - Santa Maria
# - Jardins Mangueiral
#
# Ajuste as coordenadas se desejar usar pontos mais precisos.
# =========================================================

UBS_COORDS: Dict[str, Dict[str, float]] = {
    "Gama": {
        "lat": -16.02062061175684,
        "lon": -48.08485927435655,
    },
    "Santa Maria": {
        "lat": -16.007567443627305,
        "lon": -47.98995745952408,
    },
    "Jardins Mangueiral": {
        "lat": -15.889149045911136,
        "lon": -47.81349780874119,
    },
}


UBS_ALIASES = {
    "gama": "Gama",
    "santa_maria": "Santa Maria",
    "santa-maria": "Santa Maria",
    "santa maria": "Santa Maria",
    "jardins_mangueiral": "Jardins Mangueiral",
    "jardins-mangueiral": "Jardins Mangueiral",
    "jardins mangueiral": "Jardins Mangueiral",
    "jardins_mangueral": "Jardins Mangueiral",
    "jardins-mangueral": "Jardins Mangueiral",
    "jardins mangueral": "Jardins Mangueiral",
}


# =========================================================
# HELPERS
# =========================================================

def _normalize_text(value: Any) -> str:
    """
    Normaliza texto para comparação simples.
    """
    import unicodedata

    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))

    return text


def normalize_ubs_name(value: Any) -> Optional[str]:
    """
    Padroniza o nome da UBS para bater com o dicionário UBS_COORDS.
    """
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = _normalize_text(text)
    normalized = normalized.replace("_", " ").replace("-", " ")

    aliases_by_space = {
        "gama": "Gama",
        "santa maria": "Santa Maria",
        "jardins mangueiral": "Jardins Mangueiral",
        "jardins mangueral": "Jardins Mangueiral",
    }

    if normalized in aliases_by_space:
        return aliases_by_space[normalized]

    compact = normalized.replace(" ", "_")

    if compact in UBS_ALIASES:
        return UBS_ALIASES[compact]

    return text


def _format_number(value: Any, decimals: int = 0) -> str:
    """
    Formata números no padrão brasileiro.
    """
    try:
        number = float(value)

        if decimals <= 0:
            return f"{number:,.0f}".replace(",", ".")

        return f"{number:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def _ensure_ano_mes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que exista uma coluna ano_mes para agrupamento temporal.

    O calc.prepare_health_food_dataframe normalmente já cria ano_mes.
    Este fallback protege o mapa caso a coluna não exista.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    if "ano_mes" in out.columns:
        out["ano_mes"] = out["ano_mes"].astype(str)
        return out

    if "Competência" not in out.columns:
        out["ano_mes"] = "Sem competência"
        return out

    competencia = out["Competência"].astype(str).str.strip()

    parsed = pd.to_datetime(
        competencia,
        errors="coerce",
        dayfirst=True,
    )

    out["ano_mes"] = parsed.dt.strftime("%Y-%m")
    out.loc[out["ano_mes"].isna(), "ano_mes"] = competencia

    return out


def _prepare_map_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepara DataFrame específico para o mapa.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = prepare_health_food_dataframe(df)
    out = _ensure_ano_mes(out)

    schema = get_schema()

    required_columns = [
        schema.ubs,
        schema.categoria,
        schema.tipo,
        schema.valor,
        "ano_mes",
    ]

    for col in required_columns:
        if col not in out.columns:
            out[col] = None

    out[schema.ubs] = out[schema.ubs].apply(normalize_ubs_name)
    out[schema.valor] = pd.to_numeric(out[schema.valor], errors="coerce").fillna(0)

    out = out[out[schema.ubs].notna()].copy()

    return out


def _filter_map_dataframe(
    df: pd.DataFrame,
    selected_ubs: Optional[List[str]] = None,
    categorias: Optional[List[str]] = None,
    tipos: Optional[List[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Aplica filtros do mapa.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    base = df.copy()

    if selected_ubs:
        base = base[base[schema.ubs].isin(selected_ubs)]

    if categorias:
        base = base[base[schema.categoria].isin(categorias)]

    if tipos:
        base = base[base[schema.tipo].isin(tipos)]

    if competencia_inicio:
        base = base[base["ano_mes"].astype(str) >= str(competencia_inicio)]

    if competencia_fim:
        base = base[base["ano_mes"].astype(str) <= str(competencia_fim)]

    return base.copy()


def _build_ubs_monthly_totals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega os registros totais por UBS e competência.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    required_cols = {
        schema.ubs,
        "ano_mes",
        schema.valor,
    }

    if not required_cols.issubset(df.columns):
        return pd.DataFrame()

    out = (
        df.groupby([schema.ubs, "ano_mes"], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(
            columns={
                schema.ubs: "UBS",
                schema.valor: "Registro",
            }
        )
        .sort_values(["UBS", "ano_mes"])
    )

    out["Registro"] = pd.to_numeric(out["Registro"], errors="coerce").fillna(0)

    return out


def _build_ubs_summary(df: pd.DataFrame) -> pd.DataFrame:
    """
    Monta resumo por UBS para exibição abaixo do mapa.
    """
    if df is None or df.empty:
        return pd.DataFrame(
            columns=[
                "UBS",
                "Total de registros",
                "Categorias profissionais",
                "Tipos de atendimento",
                "Competências",
            ]
        )

    schema = get_schema()

    summary = (
        df.groupby(schema.ubs, dropna=False)
        .agg(
            **{
                "Total de registros": (schema.valor, "sum"),
                "Categorias profissionais": (schema.categoria, "nunique"),
                "Tipos de atendimento": (schema.tipo, "nunique"),
                "Competências": ("ano_mes", "nunique"),
            }
        )
        .reset_index()
        .rename(columns={schema.ubs: "UBS"})
        .sort_values("Total de registros", ascending=False)
    )

    summary["Total de registros"] = pd.to_numeric(
        summary["Total de registros"],
        errors="coerce",
    ).fillna(0)

    return summary


def _get_coords_validas(selected_ubs: Optional[List[str]] = None) -> Dict[str, Dict[str, float]]:
    """
    Retorna coordenadas válidas, respeitando filtro de UBS quando aplicado.
    """
    coords = {
        nome: coord
        for nome, coord in UBS_COORDS.items()
        if coord.get("lat") is not None and coord.get("lon") is not None
    }

    if selected_ubs:
        coords = {
            nome: coord
            for nome, coord in coords.items()
            if nome in selected_ubs
        }

    return coords


def _get_map_center(coords_validas: Dict[str, Dict[str, float]]) -> tuple[float, float]:
    """
    Calcula centro do mapa com base nas coordenadas das UBSs.
    """
    if not coords_validas:
        return -15.9000, -47.9500

    center_lat = sum(item["lat"] for item in coords_validas.values()) / len(coords_validas)
    center_lon = sum(item["lon"] for item in coords_validas.values()) / len(coords_validas)

    return center_lat, center_lon


def _build_icon() -> folium.Icon | folium.CustomIcon:
    """
    Retorna ícone customizado, se existir.
    """
    if PIN_ICON_PATH.exists():
        return folium.CustomIcon(
            icon_image=str(PIN_ICON_PATH),
            icon_size=(42, 42),
            icon_anchor=(21, 42),
            popup_anchor=(0, -36),
        )

    return folium.Icon(color="blue", icon="plus-sign")


def _build_ubs_tooltip_html(
    monthly_df: pd.DataFrame,
    ubs_name: str,
    max_rows: int = 24,
) -> str:
    """
    Monta o HTML do tooltip do mapa para uma UBS.

    Exibe competência e total de registros por mês.
    """
    safe_ubs_name = html.escape(str(ubs_name))

    if monthly_df is None or monthly_df.empty:
        return f"""
        <div style="min-width:240px;">
            <div style="font-weight:700; margin-bottom:6px;">{safe_ubs_name}</div>
            <div>Sem dados disponíveis para os filtros atuais.</div>
        </div>
        """

    subset = monthly_df[monthly_df["UBS"] == ubs_name].copy()

    if subset.empty:
        return f"""
        <div style="min-width:240px;">
            <div style="font-weight:700; margin-bottom:6px;">{safe_ubs_name}</div>
            <div>Sem dados disponíveis para os filtros atuais.</div>
        </div>
        """

    total_periodo = subset["Registro"].sum()

    subset = subset.sort_values("ano_mes", ascending=False).head(max_rows)
    subset = subset.sort_values("ano_mes", ascending=True)

    rows_html = ""

    for _, row in subset.iterrows():
        comp = html.escape(str(row.get("ano_mes", "")))
        registro = _format_number(row.get("Registro", 0), decimals=0)

        rows_html += (
            "<tr>"
            f"<td style='padding:3px 10px 3px 0;'><b>{comp}</b></td>"
            f"<td style='padding:3px 0; text-align:right;'>{registro}</td>"
            "</tr>"
        )

    total_fmt = _format_number(total_periodo, decimals=0)

    return f"""
    <div style="min-width:285px;">
        <div style="font-weight:800; font-size:14px; margin-bottom:6px;">
            {safe_ubs_name}
        </div>
        <div style="margin-bottom:7px;">
            <b>Total no período:</b> {total_fmt}
        </div>
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


def _build_ubs_popup_html(summary_df: pd.DataFrame, ubs_name: str) -> str:
    """
    Popup exibido ao clicar no pin.
    """
    safe_ubs_name = html.escape(str(ubs_name))

    if summary_df is None or summary_df.empty:
        return f"""
        <div style="min-width:230px;">
            <h4 style="margin-bottom:8px;">{safe_ubs_name}</h4>
            <p>Sem resumo disponível.</p>
        </div>
        """

    subset = summary_df[summary_df["UBS"] == ubs_name]

    if subset.empty:
        return f"""
        <div style="min-width:230px;">
            <h4 style="margin-bottom:8px;">{safe_ubs_name}</h4>
            <p>Sem resumo disponível para os filtros atuais.</p>
        </div>
        """

    row = subset.iloc[0]

    total = _format_number(row.get("Total de registros", 0), decimals=0)
    categorias = _format_number(row.get("Categorias profissionais", 0), decimals=0)
    tipos = _format_number(row.get("Tipos de atendimento", 0), decimals=0)
    competencias = _format_number(row.get("Competências", 0), decimals=0)

    return f"""
    <div style="min-width:245px;">
        <h4 style="margin:0 0 8px 0;">{safe_ubs_name}</h4>
        <p style="margin:4px 0;"><b>Total de registros:</b> {total}</p>
        <p style="margin:4px 0;"><b>Categorias:</b> {categorias}</p>
        <p style="margin:4px 0;"><b>Tipos:</b> {tipos}</p>
        <p style="margin:4px 0;"><b>Competências:</b> {competencias}</p>
    </div>
    """


def _render_map_metrics(filtered_df: pd.DataFrame) -> None:
    """
    Métricas superiores do mapa.
    """
    schema = get_schema()

    total_registros = (
        filtered_df[schema.valor].sum()
        if not filtered_df.empty and schema.valor in filtered_df.columns
        else 0
    )

    total_ubs = (
        filtered_df[schema.ubs].nunique()
        if not filtered_df.empty and schema.ubs in filtered_df.columns
        else 0
    )

    total_competencias = (
        filtered_df["ano_mes"].nunique()
        if not filtered_df.empty and "ano_mes" in filtered_df.columns
        else 0
    )

    c1, c2, c3 = st.columns(3)

    c1.metric("Registros no mapa", _format_number(total_registros, decimals=0))
    c2.metric("UBSs com dados", _format_number(total_ubs, decimals=0))
    c3.metric("Competências", _format_number(total_competencias, decimals=0))


# =========================================================
# RENDER PRINCIPAL
# =========================================================

def render_map_tab(dataset_name: str, map_height: int = 550) -> None:
    st.subheader("Mapa das UBSs")

    if not dataset_name:
        st.info("Base analítica não selecionada.")
        return

    df = get_dataset_by_name(dataset_name)

    if df is None or df.empty:
        st.warning("A base analítica está vazia ou não pôde ser lida.")
        return

    if not has_health_food_schema(df):
        st.warning("A base selecionada não possui o schema esperado para o mapa das UBSs.")

        with st.expander("Ver colunas encontradas"):
            st.write(list(df.columns))

        return

    df = _prepare_map_dataframe(df)

    if df.empty:
        st.warning("Não há dados válidos para montar o mapa.")
        return

    schema = get_schema()
    options = get_filter_options(df)

    with st.expander("Filtros do mapa", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_ubs = st.multiselect(
                "Filtrar UBS",
                options=sorted([ubs for ubs in df[schema.ubs].dropna().unique().tolist()]),
                default=[],
                key="map_ubs",
            )

            selected_categorias = st.multiselect(
                "Filtrar profissional",
                options=options.get("categorias", []),
                default=[],
                key="map_categorias",
            )

        with col2:
            selected_tipos = st.multiselect(
                "Filtrar tipo de atendimento",
                options=options.get("tipos", []),
                default=[],
                key="map_tipos",
            )

            competencias = options.get("competencias", [])

            comp_col1, comp_col2 = st.columns(2)

            with comp_col1:
                competencia_inicio = st.selectbox(
                    "Competência inicial",
                    options=[None] + competencias,
                    format_func=lambda x: "Todas" if x is None else x,
                    key="map_comp_inicio",
                )

            with comp_col2:
                competencia_fim = st.selectbox(
                    "Competência final",
                    options=[None] + competencias,
                    format_func=lambda x: "Todas" if x is None else x,
                    key="map_comp_fim",
                )

    filtered_df = _filter_map_dataframe(
        df=df,
        selected_ubs=selected_ubs if selected_ubs else None,
        categorias=selected_categorias if selected_categorias else None,
        tipos=selected_tipos if selected_tipos else None,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    if filtered_df.empty:
        st.info("Nenhum registro encontrado para os filtros selecionados.")
        return

    _render_map_metrics(filtered_df)

    monthly_df = _build_ubs_monthly_totals(filtered_df)
    summary_df = _build_ubs_summary(filtered_df)

    coords_validas = _get_coords_validas(selected_ubs if selected_ubs else None)

    if not coords_validas:
        st.warning(
            "Nenhuma coordenada válida encontrada para as UBSs selecionadas. "
            "Revise o dicionário UBS_COORDS no map.py."
        )
        return

    center_lat, center_lon = _get_map_center(coords_validas)

    fmap = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=11,
        tiles="OpenStreetMap",
        zoom_control=True,
        control_scale=True,
    )

    for ubs_name, coord in coords_validas.items():
        tooltip_html = _build_ubs_tooltip_html(
            monthly_df=monthly_df,
            ubs_name=ubs_name,
        )

        popup_html = _build_ubs_popup_html(
            summary_df=summary_df,
            ubs_name=ubs_name,
        )

        folium.Marker(
            location=[coord["lat"], coord["lon"]],
            icon=_build_icon(),
            tooltip=folium.Tooltip(tooltip_html, sticky=True),
            popup=folium.Popup(popup_html, max_width=320),
        ).add_to(fmap)

    st_folium(
        fmap,
        use_container_width=True,
        height=map_height,
        returned_objects=["last_clicked", "zoom", "center"],
    )

    st.markdown("#### Resumo das UBSs no mapa")

    st.dataframe(
        summary_df,
        width="stretch",
        hide_index=True,
        column_config={
            "Total de registros": st.column_config.NumberColumn(
                "Total de registros",
                format="%.0f",
            ),
            "Categorias profissionais": st.column_config.NumberColumn(
                "Categorias profissionais",
                format="%d",
            ),
            "Tipos de atendimento": st.column_config.NumberColumn(
                "Tipos de atendimento",
                format="%d",
            ),
            "Competências": st.column_config.NumberColumn(
                "Competências",
                format="%d",
            ),
        },
    )

    with st.expander("Ver base mensal usada no mapa"):
        st.dataframe(
            monthly_df,
            width="stretch",
            hide_index=True,
            column_config={
                "Registro": st.column_config.NumberColumn(
                    "Registro",
                    format="%.0f",
                )
            },
        )

    st.caption(
        "Cada icone representa uma UBS. O tooltip mostra a evolução mensal dos registros "
    )