from __future__ import annotations

import math

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
from settings import get_dataset_by_name


def render_graphics_tab(dataset_name: str) -> None:
    st.subheader("Gráficos analíticos")

    if not dataset_name:
        st.info("Selecione um dataset analítico na sidebar.")
        return

    df = get_dataset_by_name(dataset_name)
    if df.empty:
        st.warning("O dataset selecionado está vazio ou não pôde ser lido.")
        return

    if not has_health_food_schema(df):
        st.warning(
            "O dataset selecionado não possui o schema esperado para o painel de saúde alimentar."
        )
        return

    df = prepare_health_food_dataframe(df)
    schema = get_schema()
    options = get_filter_options(df)

    competencias_2025 = [c for c in options["competencias"] if str(c).startswith("2025")]

    # =========================================================
    # GRÁFICO 1
    # Soma de registros por UBS em meses no ano de 2025
    # =========================================================
    st.markdown("### Gráfico 1 — Soma de registros por UBS em meses no ano de 2025")

    with st.expander("Filtros do gráfico 1", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_categorias_g1 = st.multiselect(
                "Filtrar profissional",
                options=options["categorias"],
                default=[],
                key="g1_categorias",
            )

            selected_tipos_g1 = st.multiselect(
                "Filtrar Tipo de atendimento",
                options=options["tipos"],
                default=[],
                key="g1_tipos",
            )

        with col2:
            competencia_inicio_g1 = st.selectbox(
                "Competência inicial",
                options=[None] + competencias_2025,
                format_func=lambda x: "Selecione" if x is None else x,
                key="g1_comp_inicio",
            )

            competencia_fim_g1 = st.selectbox(
                "Competência final",
                options=[None] + competencias_2025,
                format_func=lambda x: "Selecione" if x is None else x,
                key="g1_comp_fim",
            )

    chart_df_g1 = chart_sum_records_by_ubs_month_2025(
        df=df,
        categorias=selected_categorias_g1 if selected_categorias_g1 else None,
        tipos=selected_tipos_g1 if selected_tipos_g1 else None,
        competencia_inicio=competencia_inicio_g1,
        competencia_fim=competencia_fim_g1,
    )

    if chart_df_g1.empty:
        st.info("Não há dados para exibir no gráfico 1 com os filtros selecionados.")
    else:
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
        )

        tickvals_g1, ticktext_g1 = _build_mil_ticks(chart_df_g1["Registro"])
        fig_g1.update_yaxes(
            tickmode="array",
            tickvals=tickvals_g1,
            ticktext=ticktext_g1,
        )

        st.plotly_chart(fig_g1, use_container_width=True)

        st.markdown("#### Base do gráfico 1")
        st.dataframe(chart_df_g1, use_container_width=True)

        csv_g1 = chart_df_g1.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Baixar base do gráfico 1 em CSV",
            data=csv_g1,
            file_name=f"grafico1_registros_ubs_2025_{dataset_name}.csv",
            mime="text/csv",
        )

    st.markdown("---")

    # =========================================================
    # GRÁFICO 2
    # Comparativo de desempenho por UBS por mês em 2025 (%)
    # =========================================================
    st.markdown("### Gráfico 2 — Comparativo de desempenho por UBS por mês em 2025 (%)")

    with st.expander("Filtros do gráfico 2", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_categorias_g2 = st.multiselect(
                "Filtrar profissional",
                options=options["categorias"],
                default=[],
                key="g2_categorias",
            )

            selected_tipos_g2 = st.multiselect(
                "Filtrar Tipo de atendimento",
                options=options["tipos"],
                default=[],
                key="g2_tipos",
            )

        with col2:
            competencia_inicio_g2 = st.selectbox(
                "Competência inicial",
                options=[None] + competencias_2025,
                format_func=lambda x: "Selecione" if x is None else x,
                key="g2_comp_inicio",
            )

            competencia_fim_g2 = st.selectbox(
                "Competência final",
                options=[None] + competencias_2025,
                format_func=lambda x: "Selecione" if x is None else x,
                key="g2_comp_fim",
            )

    chart_df_g2 = chart_performance_comparison_by_ubs_month_2025(
        df=df,
        categorias=selected_categorias_g2 if selected_categorias_g2 else None,
        tipos=selected_tipos_g2 if selected_tipos_g2 else None,
        competencia_inicio=competencia_inicio_g2,
        competencia_fim=competencia_fim_g2,
    )

    if chart_df_g2.empty:
        st.info("Não há dados para exibir no gráfico 2 com os filtros selecionados.")
    else:
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
        )

        fig_g2.update_yaxes(ticksuffix="%")

        st.plotly_chart(fig_g2, use_container_width=True)

        st.markdown("#### Base do gráfico 2")
        st.dataframe(chart_df_g2, use_container_width=True)

        csv_g2 = chart_df_g2.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Baixar base do gráfico 2 em CSV",
            data=csv_g2,
            file_name=f"grafico2_desempenho_percentual_ubs_2025_{dataset_name}.csv",
            mime="text/csv",
        )

    st.markdown("---")

    # =========================================================
    # GRÁFICO 3
    # SARIMA - previsão de registros para 2026 por UBS
    # =========================================================
    st.markdown("### Gráfico 3 — Projeção estatística SARIMA de registros para 2026 por UBS")

    with st.expander("Filtros do gráfico 3", expanded=True):
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_categorias_g3 = st.multiselect(
                "Filtrar profissional",
                options=options["categorias"],
                default=[],
                key="g3_categorias",
            )

        with col2:
            selected_tipos_g3 = st.multiselect(
                "Filtrar Tipo de atendimento",
                options=options["tipos"],
                default=[],
                key="g3_tipos",
            )

        with col3:
            preview_df_g3 = chart_sarima_forecast_2026_by_ubs(
                df=df,
                categorias=selected_categorias_g3 if selected_categorias_g3 else None,
                tipos=selected_tipos_g3 if selected_tipos_g3 else None,
            )

            available_ubs_g3 = []
            if not preview_df_g3.empty:
                available_ubs_g3 = sorted(preview_df_g3[schema.ubs].dropna().unique().tolist())

            selected_ubs_g3 = st.selectbox(
                "Selecionar UBS para visualização",
                options=available_ubs_g3 if available_ubs_g3 else [None],
                format_func=lambda x: "Selecione" if x is None else x,
                key="g3_ubs_view",
            )

    if "preview_df_g3" not in locals() or preview_df_g3.empty:
        st.info("Não há dados suficientes para gerar a projeção SARIMA do gráfico 3.")
    elif not selected_ubs_g3:
        st.info("Selecione uma UBS para visualizar a projeção do gráfico 3.")
    else:
        chart_df_g3 = preview_df_g3[preview_df_g3[schema.ubs] == selected_ubs_g3].copy()

        if chart_df_g3.empty:
            st.info("Não há dados suficientes para a UBS selecionada.")
        else:
            hist = chart_df_g3[chart_df_g3["tipo_serie"] == "Histórico 2025"].copy()
            prev = chart_df_g3[chart_df_g3["tipo_serie"] == "Previsão 2026"].copy()

            fig_g3 = go.Figure()

            if not hist.empty:
                fig_g3.add_trace(
                    go.Scatter(
                        x=hist["ano_mes"],
                        y=hist["Registro"],
                        mode="lines+markers",
                        name="Histórico 2025",
                        line=dict(width=3),
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
            )

            tickvals_g3, ticktext_g3 = _build_mil_ticks(chart_df_g3["Registro"])
            fig_g3.update_yaxes(
                tickmode="array",
                tickvals=tickvals_g3,
                ticktext=ticktext_g3,
            )

            st.plotly_chart(fig_g3, use_container_width=True)

            st.markdown("#### Base do gráfico 3")
            st.dataframe(chart_df_g3, use_container_width=True)

            csv_g3 = chart_df_g3.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Baixar base do gráfico 3 em CSV",
                data=csv_g3,
                file_name=f"grafico3_sarima_previsao_2026_{selected_ubs_g3}_{dataset_name}.csv",
                mime="text/csv",
            )

            st.caption(
                "A projeção SARIMA é uma estimativa estatística exploratória baseada na série mensal histórica filtrada. "
                "Como a série disponível é curta, a interpretação deve ser cautelosa."
            )


def _build_mil_ticks(series) -> tuple[list[float], list[str]]:
    """
    Cria ticks do eixo Y com rótulos usando 'mil' em vez de 'k'.
    Exemplo: 0, 5000, 10000, 15000 -> 0, 5 mil, 10 mil, 15 mil
    """
    if series is None:
        return [0], ["0"]

    max_value = float(series.max()) if len(series) > 0 else 0.0
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
    return 20000