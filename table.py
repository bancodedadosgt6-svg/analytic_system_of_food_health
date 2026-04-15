from __future__ import annotations

import pandas as pd
import streamlit as st

from calc import (
    apply_filters,
    get_filter_options,
    get_schema,
    has_health_food_schema,
    prepare_health_food_dataframe,
)
from settings import get_dataset_by_name, get_dataset_last_update


def render_table_tab(dataset_name: str, page_size: int = 25) -> None:
    st.subheader("Tabela dinâmica")

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

    # =========================
    # Data de atualização do arquivo
    # =========================
    last_update = get_dataset_last_update(dataset_name)
    if last_update:
        st.caption(f"Última atualização no Google Drive: {last_update}")
    else:
        st.caption("Última atualização no Google Drive: não disponível")

    # =========================
    # Filtros da tabela dinâmica
    # =========================
    options = get_filter_options(df)

    with st.expander("Filtros da tabela dinâmica", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_ubs = st.multiselect(
                "Filtrar UBS",
                options=options["ubs"],
                default=[],
            )

            selected_categorias = st.multiselect(
                "Filtrar Categoria profissional",
                options=options["categorias"],
                default=[],
            )

        with col2:
            selected_tipos = st.multiselect(
                "Filtrar Tipo",
                options=options["tipos"],
                default=[],
            )

            competencias = options["competencias"]
            competencia_inicio = st.selectbox(
                "Competência inicial",
                options=[None] + competencias,
                format_func=lambda x: "Selecione" if x is None else x,
            )

            competencia_fim = st.selectbox(
                "Competência final",
                options=[None] + competencias,
                format_func=lambda x: "Selecione" if x is None else x,
            )

        text_filter = st.text_input("Busca textual global")

    base_filtered = apply_filters(
        df=df,
        ubs=selected_ubs if selected_ubs else None,
        categorias=selected_categorias if selected_categorias else None,
        tipos=selected_tipos if selected_tipos else None,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    if text_filter:
        mask = base_filtered.astype(str).apply(
            lambda col: col.str.contains(text_filter, case=False, na=False)
        )
        base_filtered = base_filtered[mask.any(axis=1)]

    # =========================
    # Métricas rápidas
    # =========================
    c1, c2, c3 = st.columns(3)
    c1.metric("Registros", len(base_filtered))
    c2.metric("UBSs", base_filtered[schema.ubs].nunique() if not base_filtered.empty else 0)
    c3.metric(
        "Categorias profissionais",
        base_filtered[schema.categoria].nunique() if not base_filtered.empty else 0,
    )

    # =========================
    # Tabela principal
    # UBS | Categoria | Tipo | Competência | Registro
    # =========================
    display_columns = [
        schema.ubs,
        schema.categoria,
        schema.tipo,
        schema.competencia,
        schema.valor,
    ]

    display_df = base_filtered[display_columns].copy()
    display_df = display_df.rename(columns={schema.valor: "Registro"})

    st.dataframe(display_df.head(page_size), use_container_width=True, height=500)

    csv_main = display_df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar tabela principal em CSV",
        data=csv_main,
        file_name=f"tabela_principal_{dataset_name}.csv",
        mime="text/csv",
    )

    st.markdown("---")
    st.subheader("Agregação rápida")

    group_col = st.selectbox(
        "Agrupar por",
        options=[schema.ubs, schema.categoria, schema.competencia],
        format_func=lambda x: {
            schema.ubs: "UBS",
            schema.categoria: "Categoria profissional",
            schema.competencia: "Competência",
        }.get(x, x),
        key="table_group_col",
    )

    agg_func = st.selectbox(
        "Função",
        options=["sum", "mean", "count", "min", "max"],
        key="table_agg",
    )

    try:
        pivot = (
            base_filtered.groupby(group_col, dropna=False)[schema.valor]
            .agg(agg_func)
            .reset_index()
            .rename(columns={schema.valor: "Registro"})
            .sort_values(by="Registro", ascending=False)
        )
    except KeyError as e:
        st.error(f"Erro de coluna na agregação: {e}")
        return

    st.dataframe(pivot.head(page_size), use_container_width=True)

    csv_pivot = pivot.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Baixar agregação em CSV",
        data=csv_pivot,
        file_name=f"agregacao_{dataset_name}.csv",
        mime="text/csv",
    )