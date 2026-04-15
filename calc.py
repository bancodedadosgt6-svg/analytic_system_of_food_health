from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import warnings

import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


# =========================
# Regras do domínio
# =========================

TIPO_MARCADOR = "Marcadores de consumo alimentar"
TIPO_ATENDIMENTO_INDIVIDUAL = "Atendimento individual"

COL_UBS = "UBS"
COL_CATEGORIA = "Categoria"
COL_TIPO = "Tipo"
COL_COMPETENCIA = "Competência"
COL_VALOR = "Valor"
COL_IDENTIFICADOS = "Identificados"
COL_NAO_IDENTIFICADOS = "Não identificados"


@dataclass
class HealthFoodSchema:
    ubs: str = COL_UBS
    categoria: str = COL_CATEGORIA
    tipo: str = COL_TIPO
    competencia: str = COL_COMPETENCIA
    valor: str = COL_VALOR
    identificados: str = COL_IDENTIFICADOS
    nao_identificados: str = COL_NAO_IDENTIFICADOS


def get_schema() -> HealthFoodSchema:
    return HealthFoodSchema()


# =========================
# Utilidades base
# =========================

def has_health_food_schema(df: pd.DataFrame) -> bool:
    schema = get_schema()
    required = {schema.ubs, schema.categoria, schema.tipo, schema.competencia, schema.valor}
    return required.issubset(set(df.columns))


def prepare_health_food_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza tipos e cria colunas auxiliares para os cálculos do painel.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    out = df.copy()

    for col in [schema.ubs, schema.categoria, schema.tipo, schema.competencia]:
        if col in out.columns:
            out[col] = out[col].astype(str).str.strip()

    if schema.valor in out.columns:
        out[schema.valor] = pd.to_numeric(out[schema.valor], errors="coerce").fillna(0)

    if schema.identificados in out.columns:
        out[schema.identificados] = pd.to_numeric(out[schema.identificados], errors="coerce")

    if schema.nao_identificados in out.columns:
        out[schema.nao_identificados] = pd.to_numeric(out[schema.nao_identificados], errors="coerce")

    if schema.competencia in out.columns:
        out["competencia_dt"] = _parse_competencia(out[schema.competencia])
        out["ano_mes"] = out["competencia_dt"].dt.strftime("%Y-%m")
    else:
        out["competencia_dt"] = pd.NaT
        out["ano_mes"] = None

    return out


def _parse_competencia(series: pd.Series) -> pd.Series:
    """
    Tenta converter competência em datetime mensal.
    Suporta formatos como:
    - 2025-01
    - 2025/01
    - 01/2025
    - datas completas
    """
    s = series.astype(str).str.strip()

    dt = pd.to_datetime(s, errors="coerce")

    mask = dt.isna()
    if mask.any():
        dt2 = pd.to_datetime(s[mask].str.replace("/", "-", regex=False) + "-01", errors="coerce")
        dt.loc[mask] = dt2

    mask = dt.isna()
    if mask.any():
        dt3 = pd.to_datetime("01/" + s[mask], format="%d/%m/%Y", errors="coerce")
        dt.loc[mask] = dt3

    return dt


def apply_filters(
    df: pd.DataFrame,
    ubs: Optional[list[str]] = None,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Aplica filtros globais do domínio.
    competencia_inicio e competencia_fim devem estar em YYYY-MM.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    out = df.copy()

    if ubs:
        out = out[out[schema.ubs].isin(ubs)]

    if categorias:
        out = out[out[schema.categoria].isin(categorias)]

    if tipos:
        out = out[out[schema.tipo].isin(tipos)]

    if "ano_mes" in out.columns and competencia_inicio:
        out = out[out["ano_mes"] >= competencia_inicio]

    if "ano_mes" in out.columns and competencia_fim:
        out = out[out["ano_mes"] <= competencia_fim]

    return out


def get_filter_options(df: pd.DataFrame) -> dict:
    """
    Retorna opções limpas para a sidebar.
    """
    if df is None or df.empty:
        return {"ubs": [], "categorias": [], "tipos": [], "competencias": []}

    schema = get_schema()

    return {
        "ubs": sorted(df[schema.ubs].dropna().astype(str).unique().tolist()) if schema.ubs in df.columns else [],
        "categorias": sorted(df[schema.categoria].dropna().astype(str).unique().tolist()) if schema.categoria in df.columns else [],
        "tipos": sorted(df[schema.tipo].dropna().astype(str).unique().tolist()) if schema.tipo in df.columns else [],
        "competencias": sorted(df["ano_mes"].dropna().astype(str).unique().tolist()) if "ano_mes" in df.columns else [],
    }


def filter_year_2025(df: pd.DataFrame) -> pd.DataFrame:
    """
    Restringe a base ao ano de 2025 usando a coluna ano_mes.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    if "ano_mes" not in df.columns:
        return pd.DataFrame()

    out = df[df["ano_mes"].astype(str).str.startswith("2025")].copy()
    return out


# =========================
# Bases derivadas centrais
# =========================

def get_marker_df(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    if df.empty:
        return pd.DataFrame()
    return df[df[schema.tipo] == TIPO_MARCADOR].copy()


def get_individual_attendance_df(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    if df.empty:
        return pd.DataFrame()
    return df[df[schema.tipo] == TIPO_ATENDIMENTO_INDIVIDUAL].copy()


def build_marker_coverage_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Base principal para calcular cobertura dos marcadores:
    cobertura = marcadores / atendimento individual * 100

    Resultado por:
    - UBS
    - Categoria
    - ano_mes
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    marker = get_marker_df(df)
    attend = get_individual_attendance_df(df)

    group_cols = [schema.ubs, schema.categoria, "ano_mes"]

    marker_agg = (
        marker.groupby(group_cols, dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "marcadores"})
    )

    attend_agg = (
        attend.groupby(group_cols, dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "atendimentos_individuais"})
    )

    base = marker_agg.merge(attend_agg, on=group_cols, how="outer")

    base["marcadores"] = pd.to_numeric(base["marcadores"], errors="coerce").fillna(0)
    base["atendimentos_individuais"] = pd.to_numeric(
        base["atendimentos_individuais"], errors="coerce"
    ).fillna(0)

    base["cobertura_percentual"] = (
        base["marcadores"] / base["atendimentos_individuais"].replace(0, pd.NA)
    ) * 100

    return base


# =========================
# Cards / KPIs
# =========================

def build_summary_cards(df: pd.DataFrame) -> dict:
    """
    Cards principais do painel.
    """
    if df is None or df.empty:
        return {
            "total_marcadores": 0,
            "cobertura_media": 0.0,
            "melhor_ubs": None,
            "melhor_categoria": None,
        }

    schema = get_schema()
    coverage = build_marker_coverage_base(df)
    marker = get_marker_df(df)

    total_marcadores = float(marker[schema.valor].sum()) if not marker.empty else 0.0

    coverage_by_ubs = coverage.groupby(schema.ubs, dropna=False)["cobertura_percentual"].mean().reset_index()
    melhor_ubs = None
    if not coverage_by_ubs.empty:
        melhor_ubs = coverage_by_ubs.sort_values("cobertura_percentual", ascending=False).iloc[0][schema.ubs]

    cat_rank = (
        marker.groupby(schema.categoria, dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .sort_values(schema.valor, ascending=False)
    )
    melhor_categoria = None
    if not cat_rank.empty:
        melhor_categoria = cat_rank.iloc[0][schema.categoria]

    cobertura_media = float(coverage["cobertura_percentual"].mean()) if not coverage.empty else 0.0

    return {
        "total_marcadores": round(total_marcadores, 0),
        "cobertura_media": round(cobertura_media, 2),
        "melhor_ubs": melhor_ubs,
        "melhor_categoria": melhor_categoria,
    }


# =========================
# Tabelas
# =========================

def table_coverage_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = build_marker_coverage_base(df)
    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby(schema.ubs, dropna=False)[["marcadores", "atendimentos_individuais"]]
        .sum()
        .reset_index()
    )

    out["cobertura_percentual"] = (
        out["marcadores"] / out["atendimentos_individuais"].replace(0, pd.NA)
    ) * 100

    return out.sort_values("cobertura_percentual", ascending=False)


def table_coverage_by_month(df: pd.DataFrame) -> pd.DataFrame:
    coverage = build_marker_coverage_base(df)
    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby("ano_mes", dropna=False)[["marcadores", "atendimentos_individuais"]]
        .sum()
        .reset_index()
        .sort_values("ano_mes")
    )

    out["cobertura_percentual"] = (
        out["marcadores"] / out["atendimentos_individuais"].replace(0, pd.NA)
    ) * 100

    return out


def table_coverage_by_ubs_and_month(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = build_marker_coverage_base(df)
    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby([schema.ubs, "ano_mes"], dropna=False)[["marcadores", "atendimentos_individuais"]]
        .sum()
        .reset_index()
        .sort_values([schema.ubs, "ano_mes"])
    )

    out["cobertura_percentual"] = (
        out["marcadores"] / out["atendimentos_individuais"].replace(0, pd.NA)
    ) * 100

    return out


def table_top_professionals_by_ubs(df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    schema = get_schema()
    marker = get_marker_df(df)
    if marker.empty:
        return pd.DataFrame()

    ranking = (
        marker.groupby([schema.ubs, schema.categoria], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "marcadores"})
    )

    ranking["rank"] = ranking.groupby(schema.ubs)["marcadores"].rank(
        method="dense", ascending=False
    )

    ranking = ranking[ranking["rank"] <= top_n].copy()
    return ranking.sort_values([schema.ubs, "rank", "marcadores"], ascending=[True, True, False])


def table_best_and_worst_month_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = table_coverage_by_ubs_and_month(df)
    if coverage.empty:
        return pd.DataFrame()

    coverage = coverage.copy()

    best = (
        coverage.sort_values("cobertura_percentual", ascending=False)
        .groupby(schema.ubs, as_index=False)
        .first()
        .rename(
            columns={
                "ano_mes": "melhor_mes",
                "cobertura_percentual": "melhor_cobertura_percentual",
            }
        )[[schema.ubs, "melhor_mes", "melhor_cobertura_percentual"]]
    )

    worst = (
        coverage.sort_values("cobertura_percentual", ascending=True)
        .groupby(schema.ubs, as_index=False)
        .first()
        .rename(
            columns={
                "ano_mes": "pior_mes",
                "cobertura_percentual": "pior_cobertura_percentual",
            }
        )[[schema.ubs, "pior_mes", "pior_cobertura_percentual"]]
    )

    return best.merge(worst, on=schema.ubs, how="outer")


def table_identification_quality(df: pd.DataFrame) -> pd.DataFrame:
    """
    Qualidade de identificação dentro dos marcadores.
    Só usa linhas de marcadores.
    """
    schema = get_schema()
    marker = get_marker_df(df)

    if marker.empty:
        return pd.DataFrame()

    if schema.identificados not in marker.columns or schema.nao_identificados not in marker.columns:
        return pd.DataFrame()

    out = (
        marker.groupby(schema.ubs, dropna=False)[[schema.identificados, schema.nao_identificados]]
        .sum(min_count=1)
        .reset_index()
    )

    total = out[schema.identificados].fillna(0) + out[schema.nao_identificados].fillna(0)
    out["percentual_identificados"] = (out[schema.identificados] / total.replace(0, pd.NA)) * 100

    return out.sort_values("percentual_identificados", ascending=False)


# =========================
# Bases para gráficos
# =========================

def chart_timeseries_markers(df: pd.DataFrame) -> pd.DataFrame:
    out = table_coverage_by_month(df)
    if out.empty:
        return pd.DataFrame()
    return out[["ano_mes", "marcadores", "cobertura_percentual"]].copy()


def chart_timeseries_markers_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    out = table_coverage_by_ubs_and_month(df)
    if out.empty:
        return pd.DataFrame()
    return out[[schema.ubs, "ano_mes", "marcadores", "cobertura_percentual"]].copy()


def chart_coverage_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    out = table_coverage_by_ubs(df)
    if out.empty:
        return pd.DataFrame()
    return out[[schema.ubs, "cobertura_percentual"]].copy()


def chart_professional_participation(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    marker = get_marker_df(df)
    if marker.empty:
        return pd.DataFrame()

    out = (
        marker.groupby(schema.categoria, dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "marcadores"})
        .sort_values("marcadores", ascending=False)
    )

    total = out["marcadores"].sum()
    out["participacao_percentual"] = (out["marcadores"] / total.replace(0, pd.NA)) * 100

    return out


def chart_top_professionals_by_ubs(df: pd.DataFrame, top_n: int = 3) -> pd.DataFrame:
    schema = get_schema()
    out = table_top_professionals_by_ubs(df, top_n=top_n)
    if out.empty:
        return pd.DataFrame()
    return out[[schema.ubs, schema.categoria, "marcadores", "rank"]].copy()


def chart_sum_records_by_ubs_month_2025(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Retorna a soma de registros por UBS e mês, restrita ao ano de 2025.

    Filtros aceitos:
    - Categoria profissional
    - Tipo
    - Competência inicial
    - Competência final

    Saída:
    - UBS
    - ano_mes
    - Registro
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    base = apply_filters(
        df=df,
        ubs=None,
        categorias=categorias,
        tipos=tipos,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    if base.empty:
        return pd.DataFrame()

    base = filter_year_2025(base)

    if base.empty:
        return pd.DataFrame()

    out = (
        base.groupby([schema.ubs, "ano_mes"], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "Registro"})
        .sort_values(["ano_mes", schema.ubs])
    )

    return out


def chart_performance_comparison_by_ubs_month_2025(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Comparativo padronizado de desempenho por UBS por mês em 2025.

    Regra de padronização:
    - soma os registros de cada UBS no mês
    - soma o total geral do mês considerando os filtros aplicados
    - calcula o percentual de participação da UBS no total do mês

    Fórmula:
    percentual_desempenho = (registro_ubs_mes / total_mes) * 100

    Filtros aceitos:
    - Categoria profissional
    - Tipo
    - Competência inicial
    - Competência final

    Saída:
    - UBS
    - ano_mes
    - Registro
    - total_mes
    - percentual_desempenho
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    base = apply_filters(
        df=df,
        ubs=None,
        categorias=categorias,
        tipos=tipos,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    if base.empty:
        return pd.DataFrame()

    base = filter_year_2025(base)

    if base.empty:
        return pd.DataFrame()

    registros_ubs_mes = (
        base.groupby([schema.ubs, "ano_mes"], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "Registro"})
    )

    total_mes = (
        base.groupby("ano_mes", dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "total_mes"})
    )

    out = registros_ubs_mes.merge(total_mes, on="ano_mes", how="left")

    out["percentual_desempenho"] = (
        out["Registro"] / out["total_mes"].replace(0, pd.NA)
    ) * 100

    out = out.sort_values(["ano_mes", schema.ubs]).reset_index(drop=True)

    return out


def chart_sarima_forecast_2026_by_ubs(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Previsão SARIMA dos registros para 2026 por UBS.

    Regras:
    - usa os dados históricos mensais de 2025
    - aplica filtros por categoria profissional e tipo de atendimento
    - agrega registros por UBS e mês
    - ajusta um modelo SARIMA conservador por UBS
    - projeta 12 meses de 2026

    Observação metodológica:
    - com apenas 12 pontos em 2025, a série é curta para sazonalidade forte
    - então o modelo tenta uma especificação SARIMA conservadora
    - se falhar, cai para uma configuração mais simples
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    base = apply_filters(
        df=df,
        ubs=None,
        categorias=categorias,
        tipos=tipos,
        competencia_inicio=None,
        competencia_fim=None,
    )

    if base.empty:
        return pd.DataFrame()

    base = filter_year_2025(base)
    if base.empty:
        return pd.DataFrame()

    monthly_index_2025 = pd.date_range("2025-01-01", "2025-12-01", freq="MS")
    monthly_index_2026 = pd.date_range("2026-01-01", "2026-12-01", freq="MS")

    all_ubs = sorted(base[schema.ubs].dropna().astype(str).unique().tolist())
    if not all_ubs:
        return pd.DataFrame()

    result_frames = []

    for ubs_name in all_ubs:
        ubs_df = base[base[schema.ubs] == ubs_name].copy()

        series = (
            ubs_df.groupby("competencia_dt", dropna=False)[schema.valor]
            .sum()
            .sort_index()
        )

        series = series[~series.index.isna()]
        series = series.reindex(monthly_index_2025, fill_value=0.0)
        series = pd.to_numeric(series, errors="coerce").fillna(0.0)

        if series.empty:
            continue

        historical_df = pd.DataFrame({
            schema.ubs: ubs_name,
            "ano_mes": monthly_index_2025.strftime("%Y-%m"),
            "competencia_dt": monthly_index_2025,
            "Registro": series.values,
            "tipo_serie": "Histórico 2025",
            "limite_inferior": pd.NA,
            "limite_superior": pd.NA,
        })
        result_frames.append(historical_df)

        # Modelo SARIMA
        forecast_values = None
        lower_ci = None
        upper_ci = None

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")

                # Tenta uma configuração conservadora
                model = SARIMAX(
                    series,
                    order=(1, 1, 1),
                    seasonal_order=(0, 0, 0, 0),
                    trend="c",
                    enforce_stationarity=False,
                    enforce_invertibility=False,
                )
                fit = model.fit(disp=False)

                forecast_res = fit.get_forecast(steps=12)
                forecast_values = forecast_res.predicted_mean

                conf_int = forecast_res.conf_int()
                lower_ci = conf_int.iloc[:, 0]
                upper_ci = conf_int.iloc[:, 1]

        except Exception:
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")

                    # Fallback ainda mais simples
                    model = SARIMAX(
                        series,
                        order=(1, 0, 0),
                        seasonal_order=(0, 0, 0, 0),
                        trend="c",
                        enforce_stationarity=False,
                        enforce_invertibility=False,
                    )
                    fit = model.fit(disp=False)

                    forecast_res = fit.get_forecast(steps=12)
                    forecast_values = forecast_res.predicted_mean

                    conf_int = forecast_res.conf_int()
                    lower_ci = conf_int.iloc[:, 0]
                    upper_ci = conf_int.iloc[:, 1]

            except Exception:
                # fallback final: média histórica mensal
                mean_value = float(series.mean()) if len(series) > 0 else 0.0
                forecast_values = pd.Series([mean_value] * 12, index=monthly_index_2026)
                lower_ci = pd.Series([pd.NA] * 12, index=monthly_index_2026)
                upper_ci = pd.Series([pd.NA] * 12, index=monthly_index_2026)

        forecast_series = pd.Series(forecast_values, index=monthly_index_2026)
        forecast_series = pd.to_numeric(forecast_series, errors="coerce").fillna(0.0)
        forecast_series = forecast_series.clip(lower=0)

        if lower_ci is not None:
            lower_ci = pd.Series(lower_ci, index=monthly_index_2026)
            lower_ci = pd.to_numeric(lower_ci, errors="coerce").clip(lower=0)
        else:
            lower_ci = pd.Series([pd.NA] * 12, index=monthly_index_2026)

        if upper_ci is not None:
            upper_ci = pd.Series(upper_ci, index=monthly_index_2026)
            upper_ci = pd.to_numeric(upper_ci, errors="coerce").clip(lower=0)
        else:
            upper_ci = pd.Series([pd.NA] * 12, index=monthly_index_2026)

        forecast_df = pd.DataFrame({
            schema.ubs: ubs_name,
            "ano_mes": monthly_index_2026.strftime("%Y-%m"),
            "competencia_dt": monthly_index_2026,
            "Registro": forecast_series.values,
            "tipo_serie": "Previsão 2026",
            "limite_inferior": lower_ci.values,
            "limite_superior": upper_ci.values,
        })
        result_frames.append(forecast_df)

    if not result_frames:
        return pd.DataFrame()

    out = pd.concat(result_frames, ignore_index=True)
    out = out.sort_values([schema.ubs, "competencia_dt", "tipo_serie"]).reset_index(drop=True)

    return out

def build_ubs_monthly_totals_for_map(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Agrega os registros totais por UBS e por competência (ano_mes),
    para uso no mapa.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    base = apply_filters(
        df=df,
        ubs=None,
        categorias=categorias,
        tipos=tipos,
        competencia_inicio=competencia_inicio,
        competencia_fim=competencia_fim,
    )

    if base.empty:
        return pd.DataFrame()

    if "ano_mes" not in base.columns:
        return pd.DataFrame()

    out = (
        base.groupby([schema.ubs, "ano_mes"], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "Registro"})
        .sort_values([schema.ubs, "ano_mes"])
    )

    return out


def build_ubs_tooltip_html(
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
        <div style="min-width:220px;">
            <b>{ubs_name}</b><br>
            Sem dados disponíveis.
        </div>
        """

    subset = monthly_df[monthly_df[get_schema().ubs] == ubs_name].copy()

    if subset.empty:
        return f"""
        <div style="min-width:220px;">
            <b>{ubs_name}</b><br>
            Sem dados disponíveis.
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
            f"<tr><td style='padding:2px 8px 2px 0;'><b>{comp}</b></td>"
            f"<td style='padding:2px 0;text-align:right;'>{registro_fmt}</td></tr>"
        )

    rows_html = "".join(linhas)

    return f"""
    <div style="min-width:260px;">
        <div style="font-weight:700; margin-bottom:6px;">{ubs_name}</div>
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