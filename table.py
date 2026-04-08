from __future__ import annotations

import pandas as pd
import streamlit as st

from settings import get_categorical_columns, get_dataset_by_name, get_numeric_columns


def render_table_tab(dataset_name: str, page_size: int = 25) -> None:
    st.subheader("Tabela dinâmica")

    if not dataset_name:
        st.info("Selecione um dataset analítico na sidebar.")
        return

    df = get_dataset_by_name(dataset_name)
    if df.empty:
        st.warning("O dataset selecionado está vazio ou não pôde ser lido.")
        return

    with st.expander("Filtros da tabela", expanded=True):
        columns = df.columns.tolist()

        visible_columns = st.multiselect(
            "Colunas visíveis",
            options=columns,
            default=columns[: min(len(columns), 12)] if columns else [],
        )

        text_filter = st.text_input("Busca textual global")

        categorical_cols = get_categorical_columns(df)
        category_filter_col = st.selectbox(
            "Filtrar categoria",
            options=[None] + categorical_cols,
            format_func=lambda x: "Selecione" if x is None else x,
        )

        category_values = []
        if category_filter_col:
            category_values = st.multiselect(
                "Valores da categoria",
                options=sorted(df[category_filter_col].dropna().astype(str).unique().tolist()),
            )

    # dataset base com filtros aplicados
    base_filtered = df.copy()

    if text_filter:
        mask = base_filtered.astype(str).apply(
            lambda col: col.str.contains(text_filter, case=False, na=False)
        )
        base_filtered = base_filtered[mask.any(axis=1)]

    if category_filter_col and category_values:
        base_filtered = base_filtered[
            base_filtered[category_filter_col].astype(str).isin(category_values)
        ]

    # dataset apenas para exibição
    if visible_columns:
        valid_visible_columns = [col for col in visible_columns if col in base_filtered.columns]
        display_df = base_filtered[valid_visible_columns].copy()
    else:
        display_df = base_filtered.copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(base_filtered))
    c2.metric("Colunas", len(display_df.columns))
    c3.metric("Campos numéricos", len(get_numeric_columns(base_filtered)))

    st.dataframe(display_df, use_container_width=True, height=500)

    st.markdown("---")
    st.subheader("Agregação rápida")

    numeric_cols = get_numeric_columns(base_filtered)
    categorical_cols = get_categorical_columns(base_filtered)

    if not numeric_cols or not categorical_cols:
        st.info("É preciso ter ao menos uma coluna categórica e uma numérica para a agregação.")
        return

    group_col = st.selectbox(
        "Agrupar por",
        options=categorical_cols,
        key="table_group_col",
    )

    value_col = st.selectbox(
        "Valor numérico",
        options=numeric_cols,
        key="table_value_col",
    )

    agg_func = st.selectbox(
        "Função",
        options=["sum", "mean", "count", "min", "max"],
        key="table_agg",
    )

    if group_col not in base_filtered.columns:
        st.error(f"A coluna de agrupamento '{group_col}' não existe mais no dataframe filtrado.")
        return

    if agg_func != "count" and value_col not in base_filtered.columns:
        st.error(f"A coluna numérica '{value_col}' não existe mais no dataframe filtrado.")
        return

    try:
        pivot = (
            base_filtered.groupby(group_col, dropna=False)[value_col]
            .agg(agg_func)
            .reset_index()
            .sort_values(by=value_col, ascending=False)
        )
    except KeyError as e:
        st.error(f"Erro de coluna na agregação: {e}")
        return

    st.dataframe(pivot.head(page_size), use_container_width=True)

    csv = pivot.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Baixar agregação em CSV",
        data=csv,
        file_name=f"agregacao_{dataset_name}.csv",
        mime="text/csv",
    )