from __future__ import annotations

import math
from typing import Any, Iterable

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from calc import (
    chart_performance_comparison_by_ubs_month_2025,
    chart_sarima_forecast_2026_by_ubs,
    chart_sum_records_by_ubs_month_2025,
    get_filter_options,
    get_schema,
    has_health_food_schema,
    prepare_health_food_dataframe,
)
from settings import get_dataset_by_name, get_dataset_last_update


# =========================================================
# HELPERS GERAIS
# =========================================================

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


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


def _safe_options(options: dict, key: str) -> list:
    """
    Retorna opções de filtro de forma segura.
    """
    value = options.get(key, [])

    if value is None:
        return []

    return list(value)


def _render_dataset_update_caption(dataset_name: str) -> None:
    """
    Mostra a atualização da base analítica.
    """
    last_update = get_dataset_last_update(dataset_name)

    if last_update:
        st.caption(
            f"Fonte oficial: PET Saúde Digital/ Secretária de Saúde do Distrito Federal "
            f"Última sincronização: {last_update}"
        )
    else:
        st.caption(
            "Fonte oficial: PET Saúde Digital/ Secretária de Saúde do Distrito Federal "
            "Última sincronização: não disponível"
        )


def _render_chart_metrics(
    df: pd.DataFrame,
    value_col: str = "Registro",
    label_total: str = "Total de registros",
    percent_col: str | None = None,
) -> None:
    """
    Métricas rápidas para a base do gráfico.
    """
    if df is None or df.empty:
        return

    c1, c2, c3 = st.columns(3)

    total_linhas = len(df)

    total_registros = (
        pd.to_numeric(df[value_col], errors="coerce").fillna(0).sum()
        if value_col in df.columns
        else 0
    )

    media_percentual = None
    if percent_col and percent_col in df.columns:
        media_percentual = pd.to_numeric(
            df[percent_col],
            errors="coerce",
        ).dropna()

    c1.metric("Linhas da base", _format_number(total_linhas, decimals=0))
    c2.metric(label_total, _format_number(total_registros, decimals=0))

    if media_percentual is not None and not media_percentual.empty:
        c3.metric("Média percentual", f"{_format_number(media_percentual.mean(), decimals=2)}%")
    else:
        c3.metric("Maior valor", _format_number(df[value_col].max() if value_col in df.columns else 0, decimals=0))


def _render_dataframe_download(
    df: pd.DataFrame,
    title: str,
    button_label: str,
    file_name: str,
    key: str,
    expanded: bool = False,
) -> None:
    """
    Renderiza a base do gráfico em expander e botão CSV.
    """
    if df is None or df.empty:
        return

    with st.expander(title, expanded=expanded):
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
        )

        csv_data = df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            button_label,
            data=csv_data,
            file_name=file_name,
            mime="text/csv",
            key=key,
            width="stretch",
        )


def _apply_basic_filters_for_available_ubs(
    df: pd.DataFrame,
    categorias: list[str] | None = None,
    tipos: list[str] | None = None,
) -> pd.DataFrame:
    """
    Aplica filtros simples para identificar UBSs disponíveis antes da previsão.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    base = df.copy()

    if categorias and schema.categoria in base.columns:
        base = base[base[schema.categoria].isin(categorias)]

    if tipos and schema.tipo in base.columns:
        base = base[base[schema.tipo].isin(tipos)]

    return base


def _get_available_ubs(
    df: pd.DataFrame,
    categorias: list[str] | None = None,
    tipos: list[str] | None = None,
) -> list[str]:
    """
    Retorna UBSs disponíveis após filtros básicos.
    """
    schema = get_schema()
    base = _apply_basic_filters_for_available_ubs(
        df=df,
        categorias=categorias,
        tipos=tipos,
    )

    if base.empty or schema.ubs not in base.columns:
        return []

    return sorted(base[schema.ubs].dropna().astype(str).unique().tolist())


def _build_plotly_config() -> dict:
    """
    Configuração padrão dos gráficos Plotly.
    """
    return {
        "displaylogo": False,
        "responsive": True,
        "modeBarButtonsToRemove": [
            "lasso2d",
            "select2d",
        ],
    }


def _sanitize_filename_piece(value: Any) -> str:
    """
    Evita caracteres ruins em nomes de arquivos baixados.
    """
    text = str(value or "").strip().lower()

    replacements = {
        " ": "_",
        "/": "_",
        "\\": "_",
        "-": "_",
        ":": "_",
        ";": "_",
        ",": "_",
        ".": "_",
        "(": "",
        ")": "",
        "[": "",
        "]": "",
        "{": "",
        "}": "",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    while "__" in text:
        text = text.replace("__", "_")

    return text.strip("_") or "dataset"


def _build_mil_ticks(series: Iterable[Any]) -> tuple[list[float], list[str]]:
    """
    Cria ticks do eixo Y com rótulos usando 'mil' em vez de 'k'.

    Exemplo:
    0, 5000, 10000, 15000 -> 0, 5 mil, 10 mil, 15 mil
    """
    if series is None:
        return [0], ["0"]

    try:
        s = pd.to_numeric(pd.Series(series), errors="coerce").dropna()
    except Exception:
        return [0], ["0"]

    if s.empty:
        return [0], ["0"]

    max_value = float(s.max())

    if max_value <= 0:
        return [0], ["0"]

    step = _choose_tick_step(max_value)
    upper = math.ceil(max_value / step) * step

    tickvals = list(range(0, int(upper + step), int(step)))
    ticktext = []

    for value in tickvals:
        if value == 0:
            ticktext.append("0")
        elif value >= 1000 and value % 1000 == 0:
            ticktext.append(f"{int(value / 1000)} mil")
        else:
            ticktext.append(f"{int(value)}")

    return tickvals, ticktext


def _choose_tick_step(max_value: float) -> int:
    """
    Escolhe passo do eixo Y de forma simples e legível.
    """
    if max_value <= 5000:
        return 1000
    if max_value <= 10000:
        return 2000
    if max_value <= 20000:
        return 5000
    if max_value <= 50000:
        return 10000
    if max_value <= 100000:
        return 20000
    return 50000


# =========================================================
# GRÁFICO 1
# =========================================================

def _render_chart_1(
    df: pd.DataFrame,
    dataset_name: str,
    options: dict,
    competencias_2025: list[str],
) -> None:
    schema = get_schema()

    st.markdown("### Gráfico 1 — Soma de registros por UBS em meses no ano de 2025")

    if not competencias_2025:
        st.info("Não foram encontradas competências de 2025 na base analítica.")
        return

    with st.expander("Filtros do gráfico 1", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_categorias_g1 = st.multiselect(
                "Filtrar profissional",
                options=_safe_options(options, "categorias"),
                default=[],
                key="g1_categorias",
            )

            selected_tipos_g1 = st.multiselect(
                "Filtrar tipo de atendimento",
                options=_safe_options(options, "tipos"),
                default=[],
                key="g1_tipos",
            )

        with col2:
            competencia_inicio_g1 = st.selectbox(
                "Competência inicial",
                options=[None] + competencias_2025,
                format_func=lambda x: "Todas" if x is None else x,
                key="g1_comp_inicio",
            )

            competencia_fim_g1 = st.selectbox(
                "Competência final",
                options=[None] + competencias_2025,
                format_func=lambda x: "Todas" if x is None else x,
                key="g1_comp_fim",
            )

    try:
        chart_df_g1 = chart_sum_records_by_ubs_month_2025(
            df=df,
            categorias=selected_categorias_g1 if selected_categorias_g1 else None,
            tipos=selected_tipos_g1 if selected_tipos_g1 else None,
            competencia_inicio=competencia_inicio_g1,
            competencia_fim=competencia_fim_g1,
        )
    except Exception as e:
        st.error(f"Erro ao montar o gráfico 1: {e}")
        return

    if chart_df_g1 is None or chart_df_g1.empty:
        st.info("Não há dados para exibir no gráfico 1 com os filtros selecionados.")
        return

    _render_chart_metrics(
        df=chart_df_g1,
        value_col="Registro",
        label_total="Soma dos registros",
    )

    fig_g1 = px.bar(
        chart_df_g1,
        x="ano_mes",
        y="Registro",
        color=schema.ubs,
        barmode="group",
        title="Soma de registros por UBS em meses no ano de 2025",
        labels={
            "ano_mes": "Competência",
            "Registro": "Registro",
            schema.ubs: "UBS",
        },
    )

    fig_g1.update_layout(
        xaxis_title="Competência",
        yaxis_title="Registro",
        legend_title="UBS",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    fig_g1.update_traces(
        hovertemplate="<b>%{x}</b><br>Registros: %{y:,.0f}<extra></extra>"
    )

    tickvals_g1, ticktext_g1 = _build_mil_ticks(chart_df_g1["Registro"])

    fig_g1.update_yaxes(
        tickmode="array",
        tickvals=tickvals_g1,
        ticktext=ticktext_g1,
    )

    st.plotly_chart(
        fig_g1,
        use_container_width=True,
        config=_build_plotly_config(),
    )

    safe_dataset = _sanitize_filename_piece(dataset_name)

    _render_dataframe_download(
        df=chart_df_g1,
        title="Base do gráfico 1",
        button_label="Baixar base do gráfico 1 em CSV",
        file_name=f"grafico1_registros_ubs_2025_{safe_dataset}.csv",
        key="download_grafico_1",
    )


# =========================================================
# GRÁFICO 2
# =========================================================

def _render_chart_2(
    df: pd.DataFrame,
    dataset_name: str,
    options: dict,
    competencias_2025: list[str],
) -> None:
    schema = get_schema()

    st.markdown("### Gráfico 2 — Comparativo de desempenho por UBS por mês em 2025 (%)")

    if not competencias_2025:
        st.info("Não foram encontradas competências de 2025 na base analítica.")
        return

    with st.expander("Filtros do gráfico 2", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_categorias_g2 = st.multiselect(
                "Filtrar profissional",
                options=_safe_options(options, "categorias"),
                default=[],
                key="g2_categorias",
            )

            selected_tipos_g2 = st.multiselect(
                "Filtrar tipo de atendimento",
                options=_safe_options(options, "tipos"),
                default=[],
                key="g2_tipos",
            )

        with col2:
            competencia_inicio_g2 = st.selectbox(
                "Competência inicial",
                options=[None] + competencias_2025,
                format_func=lambda x: "Todas" if x is None else x,
                key="g2_comp_inicio",
            )

            competencia_fim_g2 = st.selectbox(
                "Competência final",
                options=[None] + competencias_2025,
                format_func=lambda x: "Todas" if x is None else x,
                key="g2_comp_fim",
            )

    try:
        chart_df_g2 = chart_performance_comparison_by_ubs_month_2025(
            df=df,
            categorias=selected_categorias_g2 if selected_categorias_g2 else None,
            tipos=selected_tipos_g2 if selected_tipos_g2 else None,
            competencia_inicio=competencia_inicio_g2,
            competencia_fim=competencia_fim_g2,
        )
    except Exception as e:
        st.error(f"Erro ao montar o gráfico 2: {e}")
        return

    if chart_df_g2 is None or chart_df_g2.empty:
        st.info("Não há dados para exibir no gráfico 2 com os filtros selecionados.")
        return

    _render_chart_metrics(
        df=chart_df_g2,
        value_col="Registro" if "Registro" in chart_df_g2.columns else "percentual_desempenho",
        label_total="Total da base",
        percent_col="percentual_desempenho",
    )

    fig_g2 = px.line(
        chart_df_g2,
        x="ano_mes",
        y="percentual_desempenho",
        color=schema.ubs,
        markers=True,
        title="Comparativo de desempenho por UBS por mês em 2025 (%)",
        labels={
            "ano_mes": "Competência",
            "percentual_desempenho": "Desempenho (%)",
            schema.ubs: "UBS",
        },
    )

    fig_g2.update_layout(
        xaxis_title="Competência",
        yaxis_title="Desempenho (%)",
        legend_title="UBS",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    fig_g2.update_traces(
        hovertemplate="<b>%{x}</b><br>Desempenho: %{y:.2f}%<extra></extra>"
    )

    fig_g2.update_yaxes(ticksuffix="%")

    st.plotly_chart(
        fig_g2,
        use_container_width=True,
        config=_build_plotly_config(),
    )

    safe_dataset = _sanitize_filename_piece(dataset_name)

    _render_dataframe_download(
        df=chart_df_g2,
        title="Base do gráfico 2",
        button_label="Baixar base do gráfico 2 em CSV",
        file_name=f"grafico2_desempenho_percentual_ubs_2025_{safe_dataset}.csv",
        key="download_grafico_2",
    )


# =========================================================
# GRÁFICO 3 — SARIMA
# =========================================================

def _render_chart_3(
    df: pd.DataFrame,
    dataset_name: str,
    options: dict,
) -> None:
    schema = get_schema()

    st.markdown("### Gráfico 3 — Projeção estatística SARIMA de registros para 2026 por UBS")

    with st.expander("Filtros do gráfico 3", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_categorias_g3 = st.multiselect(
                "Filtrar profissional",
                options=_safe_options(options, "categorias"),
                default=[],
                key="g3_categorias",
            )

        with col2:
            selected_tipos_g3 = st.multiselect(
                "Filtrar tipo de atendimento",
                options=_safe_options(options, "tipos"),
                default=[],
                key="g3_tipos",
            )

        available_ubs_g3 = _get_available_ubs(
            df=df,
            categorias=selected_categorias_g3 if selected_categorias_g3 else None,
            tipos=selected_tipos_g3 if selected_tipos_g3 else None,
        )

        with col3:
            selected_ubs_g3 = st.selectbox(
                "Selecionar UBS para visualização",
                options=available_ubs_g3 if available_ubs_g3 else [None],
                format_func=lambda x: "Selecione" if x is None else x,
                key="g3_ubs_view",
            )

    if not selected_ubs_g3:
        st.info("Selecione uma UBS para visualizar a projeção do gráfico 3.")
        return

    with st.spinner("Calculando projeção SARIMA..."):
        try:
            forecast_df = chart_sarima_forecast_2026_by_ubs(
                df=df,
                categorias=selected_categorias_g3 if selected_categorias_g3 else None,
                tipos=selected_tipos_g3 if selected_tipos_g3 else None,
            )
        except Exception as e:
            st.error(f"Erro ao calcular a projeção SARIMA: {e}")
            return

    if forecast_df is None or forecast_df.empty:
        st.info("Não há dados suficientes para gerar a projeção SARIMA do gráfico 3.")
        return

    chart_df_g3 = forecast_df[forecast_df[schema.ubs] == selected_ubs_g3].copy()

    if chart_df_g3.empty:
        st.info("Não há dados suficientes para a UBS selecionada.")
        return

    hist = chart_df_g3[chart_df_g3["tipo_serie"] == "Histórico 2025"].copy()
    prev = chart_df_g3[chart_df_g3["tipo_serie"] == "Previsão 2026"].copy()

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Pontos históricos",
        _format_number(len(hist), decimals=0),
    )
    c2.metric(
        "Pontos previstos",
        _format_number(len(prev), decimals=0),
    )
    c3.metric(
        "Total previsto 2026",
        _format_number(prev["Registro"].sum() if not prev.empty and "Registro" in prev.columns else 0, decimals=0),
    )

    fig_g3 = go.Figure()

    if not hist.empty:
        fig_g3.add_trace(
            go.Scatter(
                x=hist["ano_mes"],
                y=hist["Registro"],
                mode="lines+markers",
                name="Histórico 2025",
                line=dict(width=3),
                hovertemplate="<b>%{x}</b><br>Histórico: %{y:,.0f}<extra></extra>",
            )
        )

    if not prev.empty:
        fig_g3.add_trace(
            go.Scatter(
                x=prev["ano_mes"],
                y=prev["Registro"],
                mode="lines+markers",
                name="Previsão 2026",
                line=dict(width=3, dash="dash"),
                hovertemplate="<b>%{x}</b><br>Previsão: %{y:,.0f}<extra></extra>",
            )
        )

        if (
            "limite_inferior" in prev.columns
            and "limite_superior" in prev.columns
            and prev["limite_inferior"].notna().any()
            and prev["limite_superior"].notna().any()
        ):
            fig_g3.add_trace(
                go.Scatter(
                    x=prev["ano_mes"],
                    y=prev["limite_superior"],
                    mode="lines",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
            )

            fig_g3.add_trace(
                go.Scatter(
                    x=prev["ano_mes"],
                    y=prev["limite_inferior"],
                    mode="lines",
                    line=dict(width=0),
                    fill="tonexty",
                    fillcolor="rgba(128,128,128,0.18)",
                    name="Faixa de incerteza",
                    hoverinfo="skip",
                )
            )

    fig_g3.update_layout(
        title=f"Projeção SARIMA de registros para 2026 — {selected_ubs_g3}",
        xaxis_title="Competência",
        yaxis_title="Registro previsto",
        legend_title="Série",
        hovermode="x unified",
        margin=dict(l=20, r=20, t=60, b=20),
    )

    tickvals_g3, ticktext_g3 = _build_mil_ticks(chart_df_g3["Registro"])

    fig_g3.update_yaxes(
        tickmode="array",
        tickvals=tickvals_g3,
        ticktext=ticktext_g3,
    )

    st.plotly_chart(
        fig_g3,
        use_container_width=True,
        config=_build_plotly_config(),
    )

    safe_dataset = _sanitize_filename_piece(dataset_name)
    safe_ubs = _sanitize_filename_piece(selected_ubs_g3)

    _render_dataframe_download(
        df=chart_df_g3,
        title="Base do gráfico 3",
        button_label="Baixar base do gráfico 3 em CSV",
        file_name=f"grafico3_sarima_previsao_2026_{safe_ubs}_{safe_dataset}.csv",
        key="download_grafico_3",
    )

    st.caption(
        "A projeção SARIMA é uma estimativa estatística exploratória baseada na série mensal histórica filtrada. "
        "Como a série disponível ainda é curta, a interpretação deve ser cautelosa e usada como apoio analítico, "
        "não como previsão determinística."
    )


# =========================================================
# RENDER PRINCIPAL
# =========================================================

def render_graphics_tab(dataset_name: str) -> None:
    st.subheader("Gráficos analíticos")

    if not dataset_name:
        st.info("Base analítica não selecionada.")
        return

    df = get_dataset_by_name(dataset_name)

    if df is None or df.empty:
        st.warning("A base analítica está vazia ou não pôde ser lida.")
        return

    if not has_health_food_schema(df):
        st.warning(
            "A base selecionada não possui o schema esperado para o painel de saúde alimentar."
        )

        with st.expander("Ver colunas encontradas"):
            st.write(list(df.columns))

        return

    try:
        df = prepare_health_food_dataframe(df)
    except Exception as e:
        st.error(f"Erro ao preparar a base para os gráficos: {e}")
        return

    if df.empty:
        st.warning("A base preparada para os gráficos está vazia.")
        return

    schema = get_schema()
    options = get_filter_options(df)

    competencias = _safe_options(options, "competencias")
    competencias_2025 = [c for c in competencias if str(c).startswith("2025")]

    _render_dataset_update_caption(dataset_name)

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Linhas na base", _format_number(len(df), decimals=0))
    c2.metric(
        "UBSs",
        _format_number(df[schema.ubs].nunique() if schema.ubs in df.columns else 0, decimals=0),
    )
    c3.metric(
        "Categorias",
        _format_number(df[schema.categoria].nunique() if schema.categoria in df.columns else 0, decimals=0),
    )
    c4.metric(
        "Competências",
        _format_number(len(competencias), decimals=0),
    )

    st.markdown("---")

    _render_chart_1(
        df=df,
        dataset_name=dataset_name,
        options=options,
        competencias_2025=competencias_2025,
    )

    st.markdown("---")

    _render_chart_2(
        df=df,
        dataset_name=dataset_name,
        options=options,
        competencias_2025=competencias_2025,
    )

    st.markdown("---")

    _render_chart_3(
        df=df,
        dataset_name=dataset_name,
        options=options,
    )