from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from settings import (
    get_categorical_columns,
    get_dataset_by_name,
    get_datetime_columns,
    get_numeric_columns,
)



def render_graphics_tab(dataset_name: str) -> None:
    st.subheader("Gráficos analíticos")

    if not dataset_name:
        st.info("Selecione um dataset analítico na sidebar.")
        return

    df = get_dataset_by_name(dataset_name)
    if df.empty:
        st.warning("O dataset selecionado está vazio ou não pôde ser lido.")
        return

    numeric_cols = get_numeric_columns(df)
    categorical_cols = get_categorical_columns(df)
    datetime_cols = get_datetime_columns(df)

    if not numeric_cols:
        st.info("Não há colunas numéricas suficientes para gerar gráficos.")
        return

    bar_col, line_col = st.columns(2)

    with bar_col:
        st.markdown("### Gráfico de barras")
        if categorical_cols:
            cat_col = st.selectbox("Categoria", options=categorical_cols, key="bar_cat")
            val_col = st.selectbox("Métrica", options=numeric_cols, key="bar_val")
            agg_func = st.selectbox("Agregação", options=["sum", "mean", "count"], key="bar_agg")

            bar_df = (
                df.groupby(cat_col, dropna=False)[val_col]
                .agg(agg_func)
                .reset_index()
                .sort_values(by=val_col, ascending=False)
                .head(20)
            )
            fig = px.bar(bar_df, x=cat_col, y=val_col, title=f"{agg_func} de {val_col} por {cat_col}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem colunas categóricas para gráfico de barras.")

    with line_col:
        st.markdown("### Gráfico em linha")
        if datetime_cols:
            date_col = st.selectbox("Data", options=datetime_cols, key="line_date")
            metric_col = st.selectbox("Métrica numérica", options=numeric_cols, key="line_metric")

            temp = df.copy()
            temp[date_col] = pd.to_datetime(temp[date_col], errors="coerce")
            temp = temp.dropna(subset=[date_col])
            temp = (
                temp.groupby(date_col)[metric_col]
                .mean()
                .reset_index()
                .sort_values(by=date_col)
            )
            fig = px.line(temp, x=date_col, y=metric_col, title=f"Evolução temporal de {metric_col}")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem colunas de data para gráfico em linha.")

    st.markdown("### Tendência")
    if datetime_cols:
        trend_date_col = st.selectbox("Data da tendência", options=datetime_cols, key="trend_date")
        trend_metric_col = st.selectbox("Métrica da tendência", options=numeric_cols, key="trend_metric")

        trend = df.copy()
        trend[trend_date_col] = pd.to_datetime(trend[trend_date_col], errors="coerce")
        trend = trend.dropna(subset=[trend_date_col])
        trend = trend.sort_values(trend_date_col)
        trend["media_movel_3"] = trend[trend_metric_col].rolling(window=3, min_periods=1).mean()

        fig = px.line(
            trend,
            x=trend_date_col,
            y=[trend_metric_col, "media_movel_3"],
            title=f"Tendência de {trend_metric_col} com média móvel",
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sem coluna temporal para análise de tendência.")

    st.markdown("### Comparativo")
    if categorical_cols and len(numeric_cols) >= 2:
        compare_cat = st.selectbox("Categoria comparativa", options=categorical_cols, key="compare_cat")
        compare_metrics = st.multiselect(
            "Métricas comparadas",
            options=numeric_cols,
            default=numeric_cols[: min(2, len(numeric_cols))],
            key="compare_metrics",
        )
        if compare_metrics:
            comp = df.groupby(compare_cat, dropna=False)[compare_metrics].mean().reset_index()
            melted = comp.melt(id_vars=[compare_cat], var_name="métrica", value_name="valor")
            fig = px.bar(
                melted,
                x=compare_cat,
                y="valor",
                color="métrica",
                barmode="group",
                title="Comparativo de métricas por categoria",
            )
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("É preciso ter categoria e ao menos duas métricas numéricas para comparação.")
