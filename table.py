from __future__ import annotations

from typing import Any

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


# =========================================================
# HELPERS
# =========================================================

def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _format_number(value: Any) -> str:
    """
    Formata número para exibição amigável.
    """
    try:
        number = float(value)

        if number.is_integer():
            return f"{int(number):,}".replace(",", ".")

        return f"{number:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return str(value)


def _apply_text_filter(df: pd.DataFrame, text_filter: str) -> pd.DataFrame:
    """
    Aplica busca textual global de forma segura.

    Usa regex=False para evitar erro quando o usuário digitar caracteres
    especiais como [], (), ?, +, * etc.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    text_filter = str(text_filter or "").strip()

    if not text_filter:
        return df

    mask = df.astype(str).apply(
        lambda col: col.str.contains(
            text_filter,
            case=False,
            na=False,
            regex=False,
        )
    )

    return df[mask.any(axis=1)]


def _paginate_dataframe(
    df: pd.DataFrame,
    default_page_size: int,
    key_prefix: str,
) -> pd.DataFrame:
    """
    Paginação simples para não sobrecarregar a renderização da tabela.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    total_rows = len(df)

    page_size_options = [10, 25, 50, 100, 250, 500]
    default_page_size = default_page_size if default_page_size in page_size_options else 25

    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        page_size = st.selectbox(
            "Linhas por página",
            options=page_size_options,
            index=page_size_options.index(default_page_size),
            key=f"{key_prefix}_page_size",
        )

    total_pages = max((total_rows - 1) // page_size + 1, 1)

    with col2:
        current_page = st.number_input(
            "Página",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key=f"{key_prefix}_page",
        )

    start = (current_page - 1) * page_size
    end = start + page_size

    with col3:
        st.caption(
            f"Exibindo {start + 1 if total_rows else 0}–{min(end, total_rows)} "
            f"de {total_rows} registros filtrados."
        )

    return df.iloc[start:end].copy()


def _render_dataset_update_caption(dataset_name: str) -> None:
    """
    Mostra a atualização da base analítica.
    """
    last_update = get_dataset_last_update(dataset_name)

    if last_update:
        st.caption(
            f"Última sincronização: {last_update}"
        )
    else:
        st.caption(
            "Última sincronização: não disponível"
        )


def _render_quick_metrics(df: pd.DataFrame, schema) -> None:
    """
    Métricas rápidas da base filtrada.
    """
    total_registros = len(df)

    total_ubs = (
        df[schema.ubs].nunique()
        if not df.empty and schema.ubs in df.columns
        else 0
    )

    total_categorias = (
        df[schema.categoria].nunique()
        if not df.empty and schema.categoria in df.columns
        else 0
    )

    soma_registros = (
        pd.to_numeric(df[schema.valor], errors="coerce").fillna(0).sum()
        if not df.empty and schema.valor in df.columns
        else 0
    )

    c1, c2, c3, c4 = st.columns(4)

    c1.metric("Linhas filtradas", _format_number(total_registros))
    c2.metric("UBSs", _format_number(total_ubs))
    c3.metric("Categorias profissionais", _format_number(total_categorias))
    c4.metric("Total de registros", _format_number(soma_registros))


def _build_display_dataframe(df: pd.DataFrame, schema) -> pd.DataFrame:
    """
    Monta a tabela principal no padrão visual do painel.
    """
    display_columns = [
        schema.ubs,
        schema.categoria,
        schema.tipo,
        schema.competencia,
        schema.valor,
    ]

    available_columns = [col for col in display_columns if col in df.columns]

    if not available_columns:
        return pd.DataFrame()

    display_df = df[available_columns].copy()

    rename_map = {
        schema.ubs: "UBS",
        schema.categoria: "Categoria profissional",
        schema.tipo: "Tipo",
        schema.competencia: "Competência",
        schema.valor: "Registro",
    }

    display_df = display_df.rename(columns=rename_map)

    if "Registro" in display_df.columns:
        display_df["Registro"] = pd.to_numeric(
            display_df["Registro"],
            errors="coerce",
        ).fillna(0)

    return display_df


def _render_download_button(
    label: str,
    df: pd.DataFrame,
    file_name: str,
    key: str,
) -> None:
    """
    Botão de download CSV com encoding adequado para Excel.
    """
    if df is None or df.empty:
        return

    csv_data = df.to_csv(index=False).encode("utf-8-sig")

    st.download_button(
        label,
        data=csv_data,
        file_name=file_name,
        mime="text/csv",
        key=key,
        width="stretch",
    )


# =========================================================
# TABELA DINÂMICA
# =========================================================

def render_table_tab(dataset_name: str, page_size: int = 25) -> None:
    st.subheader("Tabela dinâmica")

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

    df = prepare_health_food_dataframe(df)
    schema = get_schema()

    _render_dataset_update_caption(dataset_name)

    # =====================================================
    # FILTROS
    # =====================================================

    options = get_filter_options(df)

    with st.expander("Filtros da tabela dinâmica", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            selected_ubs = st.multiselect(
                "Filtrar UBS",
                options=options.get("ubs", []),
                default=[],
                key="table_filter_ubs",
            )

            selected_categorias = st.multiselect(
                "Filtrar categoria profissional",
                options=options.get("categorias", []),
                default=[],
                key="table_filter_categorias",
            )

        with col2:
            selected_tipos = st.multiselect(
                "Filtrar tipo",
                options=options.get("tipos", []),
                default=[],
                key="table_filter_tipos",
            )

            competencias = options.get("competencias", [])

            comp_col1, comp_col2 = st.columns(2)

            with comp_col1:
                competencia_inicio = st.selectbox(
                    "Competência inicial",
                    options=[None] + competencias,
                    format_func=lambda x: "Todas" if x is None else x,
                    key="table_filter_comp_inicio",
                )

            with comp_col2:
                competencia_fim = st.selectbox(
                    "Competência final",
                    options=[None] + competencias,
                    format_func=lambda x: "Todas" if x is None else x,
                    key="table_filter_comp_fim",
                )

        text_filter = st.text_input(
            "Busca textual global",
            placeholder="Digite uma UBS, categoria, tipo, competência ou valor...",
            key="table_text_filter",
        )

    base_filtered = apply_filters(
        df=df,
        ubs=selected_ubs if selected_ubs else None,
        categorias=selected_categorias if selected_categorias else None,
        tipos=selected_tipos if selected_tipos else None,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    base_filtered = _apply_text_filter(base_filtered, text_filter)

    if base_filtered.empty:
        st.info("Nenhum registro encontrado com os filtros selecionados.")
        return

    # =====================================================
    # MÉTRICAS RÁPIDAS
    # =====================================================

    _render_quick_metrics(base_filtered, schema)

    # =====================================================
    # TABELA PRINCIPAL
    # =====================================================

    st.markdown("### Registros filtrados")

    display_df = _build_display_dataframe(base_filtered, schema)

    if display_df.empty:
        st.warning("Não foi possível montar a tabela principal.")
        return

    paginated_df = _paginate_dataframe(
        df=display_df,
        default_page_size=page_size,
        key_prefix="main_table",
    )

    st.dataframe(
        paginated_df,
        width="stretch",
        height=500,
        hide_index=True,
        column_config={
            "Registro": st.column_config.NumberColumn(
                "Registro",
                format="%.0f",
            )
        } if "Registro" in paginated_df.columns else None,
    )

    _render_download_button(
        label="Baixar tabela filtrada em CSV",
        df=display_df,
        file_name=f"tabela_filtrada_{dataset_name}.csv",
        key="download_tabela_filtrada",
    )

    # =====================================================
    # AGREGAÇÃO RÁPIDA
    # =====================================================

    st.markdown("---")
    st.subheader("Agregação rápida")

    group_options = [
        schema.ubs,
        schema.categoria,
        schema.tipo,
        schema.competencia,
    ]

    group_options = [col for col in group_options if col in base_filtered.columns]

    if not group_options:
        st.warning("Não há colunas disponíveis para agregação.")
        return

    group_label_map = {
        schema.ubs: "UBS",
        schema.categoria: "Categoria profissional",
        schema.tipo: "Tipo",
        schema.competencia: "Competência",
    }

    col_group, col_func = st.columns(2)

    with col_group:
        group_col = st.selectbox(
            "Agrupar por",
            options=group_options,
            format_func=lambda x: group_label_map.get(x, x),
            key="table_group_col",
        )

    with col_func:
        agg_func = st.selectbox(
            "Função estatística",
            options=["sum", "mean", "median", "count", "min", "max"],
            format_func=lambda x: {
                "sum": "Soma",
                "mean": "Média",
                "median": "Mediana",
                "count": "Contagem",
                "min": "Mínimo",
                "max": "Máximo",
            }.get(x, x),
            key="table_agg",
        )

    try:
        pivot = (
            base_filtered.groupby(group_col, dropna=False)[schema.valor]
            .agg(agg_func)
            .reset_index()
            .rename(
                columns={
                    group_col: group_label_map.get(group_col, group_col),
                    schema.valor: "Registro",
                }
            )
            .sort_values(by="Registro", ascending=False)
        )

        if "Registro" in pivot.columns:
            pivot["Registro"] = pd.to_numeric(
                pivot["Registro"],
                errors="coerce",
            ).fillna(0)

    except KeyError as e:
        st.error(f"Erro de coluna na agregação: {e}")
        return
    except Exception as e:
        st.error(f"Erro ao calcular agregação: {e}")
        return

    if pivot.empty:
        st.info("A agregação não retornou resultados.")
        return

    paginated_pivot = _paginate_dataframe(
        df=pivot,
        default_page_size=page_size,
        key_prefix="pivot_table",
    )

    st.dataframe(
        paginated_pivot,
        width="stretch",
        hide_index=True,
        column_config={
            "Registro": st.column_config.NumberColumn(
                "Registro",
                format="%.2f" if agg_func in ["mean", "median"] else "%.0f",
            )
        } if "Registro" in paginated_pivot.columns else None,
    )

    _render_download_button(
        label="Baixar agregação em CSV",
        df=pivot,
        file_name=f"agregacao_{dataset_name}.csv",
        key="download_agregacao",
    )