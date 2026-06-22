from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional
import html
import math
import re
import unicodedata
import warnings

import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


# =========================================================
# REGRAS DO DOMÍNIO
# =========================================================

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


# =========================================================
# NORMALIZAÇÃO TEXTUAL
# =========================================================

UBS_ALIASES = {
    "gama": "Gama",
    "santa maria": "Santa Maria",
    "santa_maria": "Santa Maria",
    "santa-maria": "Santa Maria",
    "jardins mangueiral": "Jardins Mangueiral",
    "jardins_mangueiral": "Jardins Mangueiral",
    "jardins-mangueiral": "Jardins Mangueiral",
    "jardins mangueral": "Jardins Mangueiral",
    "jardins_mangueral": "Jardins Mangueiral",
    "jardins-mangueral": "Jardins Mangueiral",
}

TIPO_ALIASES = {
    "marcador de consumo alimentar": TIPO_MARCADOR,
    "marcadores de consumo alimentar": TIPO_MARCADOR,
    "marcadores consumo alimentar": TIPO_MARCADOR,
    "marcador consumo alimentar": TIPO_MARCADOR,
    "atendimento individual": TIPO_ATENDIMENTO_INDIVIDUAL,
    "atendimentos individuais": TIPO_ATENDIMENTO_INDIVIDUAL,
    "atendimento individuais": TIPO_ATENDIMENTO_INDIVIDUAL,
}


def _is_missing(value: Any) -> bool:
    try:
        return value is None or pd.isna(value)
    except Exception:
        return value is None


def _clean_text_value(value: Any) -> str | None:
    """
    Limpa espaços, tabs e valores nulos sem transformar NaN em texto.
    """
    if _is_missing(value):
        return None

    text = str(value).replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text).strip()

    if not text or text.lower() in {"nan", "none", "null", "na", "nat"}:
        return None

    return text


def _strip_accents(value: str) -> str:
    value = unicodedata.normalize("NFKD", value)
    return "".join(char for char in value if not unicodedata.combining(char))


def _normalize_key(value: Any) -> str:
    """
    Gera chave textual estável para comparação:
    - minúscula
    - sem acento
    - sem pontuação relevante
    - espaços normalizados
    """
    text = _clean_text_value(value)

    if text is None:
        return ""

    text = _strip_accents(text).lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def normalize_ubs_value(value: Any) -> str | None:
    """
    Padroniza UBS para os nomes oficiais usados no Supabase, Parquet, mapa e dashboard.
    """
    text = _clean_text_value(value)

    if text is None:
        return None

    key = _normalize_key(text)

    return UBS_ALIASES.get(key, text)


def normalize_tipo_value(value: Any) -> str | None:
    """
    Padroniza o tipo de registro para evitar erro estatístico por variação de escrita.
    """
    text = _clean_text_value(value)

    if text is None:
        return None

    key = _normalize_key(text)

    if key in TIPO_ALIASES:
        return TIPO_ALIASES[key]

    if "marcador" in key and "consumo" in key and "alimentar" in key:
        return TIPO_MARCADOR

    if "atendimento" in key and "individual" in key:
        return TIPO_ATENDIMENTO_INDIVIDUAL

    return text


def normalize_categoria_value(value: Any) -> str | None:
    """
    Limpa categoria profissional preservando a escrita original.
    """
    return _clean_text_value(value)


# =========================================================
# NORMALIZAÇÃO NUMÉRICA
# =========================================================

def _coerce_numeric_value(value: Any) -> float | None:
    """
    Converte números em formatos comuns:
    - 1234
    - 1.234
    - 1.234,56
    - 1234,56
    - 1234.56
    """
    if _is_missing(value):
        return None

    if isinstance(value, (int, float)):
        try:
            if math.isnan(float(value)):
                return None
        except Exception:
            pass

        return float(value)

    text = _clean_text_value(value)

    if text is None:
        return None

    text = text.replace("R$", "")
    text = text.replace("%", "")
    text = text.replace(" ", "")

    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    text = re.sub(r"[^0-9\.\-]", "", text)

    if not text or text in {"-", ".", "-."}:
        return None

    try:
        return float(text)
    except Exception:
        return None


def _coerce_numeric_series(
    series: pd.Series,
    fill_value: float | None = 0.0,
    clip_lower: float | None = 0.0,
) -> pd.Series:
    converted = series.apply(_coerce_numeric_value)
    converted = pd.to_numeric(converted, errors="coerce")

    if fill_value is not None:
        converted = converted.fillna(fill_value)

    if clip_lower is not None:
        converted = converted.clip(lower=clip_lower)

    return converted


def _safe_percent(numerator: Any, denominator: Any) -> pd.Series:
    """
    Calcula percentual com proteção contra divisão por zero.

    Retorna NaN quando o denominador é zero/ausente, evitando transformar
    ausência de base populacional em 0% artificial.
    """
    num = pd.to_numeric(numerator, errors="coerce").astype(float)
    den = pd.to_numeric(denominator, errors="coerce").astype(float)

    den = den.where(den != 0)

    return (num / den) * 100


def _safe_scalar_percent(numerator: float, denominator: float) -> float:
    try:
        numerator = float(numerator or 0)
        denominator = float(denominator or 0)

        if denominator == 0:
            return 0.0

        return (numerator / denominator) * 100
    except Exception:
        return 0.0


# =========================================================
# UTILIDADES BASE
# =========================================================

def has_health_food_schema(df: pd.DataFrame) -> bool:
    """
    Verifica se o DataFrame possui o schema mínimo esperado.
    """
    if df is None or df.empty:
        return False

    schema = get_schema()
    required = {
        schema.ubs,
        schema.categoria,
        schema.tipo,
        schema.competencia,
        schema.valor,
    }

    return required.issubset(set(df.columns))


def prepare_health_food_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Padroniza tipos, textos e cria colunas auxiliares para os cálculos do painel.

    Saídas auxiliares:
    - competencia_dt: datetime no primeiro dia do mês
    - ano_mes: YYYY-MM
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    out = df.copy()

    if schema.ubs in out.columns:
        out[schema.ubs] = out[schema.ubs].apply(normalize_ubs_value)

    if schema.categoria in out.columns:
        out[schema.categoria] = out[schema.categoria].apply(normalize_categoria_value)

    if schema.tipo in out.columns:
        out[schema.tipo] = out[schema.tipo].apply(normalize_tipo_value)

    if schema.competencia in out.columns:
        competencia_original = out[schema.competencia].apply(_clean_text_value)
        out["competencia_dt"] = _parse_competencia(competencia_original)
        out["ano_mes"] = out["competencia_dt"].dt.strftime("%Y-%m")

        out[schema.competencia] = out["ano_mes"].where(
            out["ano_mes"].notna(),
            competencia_original,
        )
    else:
        out["competencia_dt"] = pd.NaT
        out["ano_mes"] = None

    if schema.valor in out.columns:
        out[schema.valor] = _coerce_numeric_series(
            out[schema.valor],
            fill_value=0.0,
            clip_lower=0.0,
        )

    if schema.identificados in out.columns:
        out[schema.identificados] = _coerce_numeric_series(
            out[schema.identificados],
            fill_value=0.0,
            clip_lower=0.0,
        )

    if schema.nao_identificados in out.columns:
        out[schema.nao_identificados] = _coerce_numeric_series(
            out[schema.nao_identificados],
            fill_value=0.0,
            clip_lower=0.0,
        )

    return out


def _parse_competencia(series: pd.Series) -> pd.Series:
    """
    Converte competência para datetime mensal.

    Suporta:
    - 2025-01
    - 2025/01
    - 01/2025
    - 1/2025
    - 2025-01-01
    - 01/01/2025
    """
    if series is None:
        return pd.Series(dtype="datetime64[ns]")

    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    cleaned = series.apply(_clean_text_value)

    for idx, value in cleaned.items():
        if value is None:
            continue

        text = str(value).strip()

        parsed = None

        match_ym = re.match(r"^(\d{4})[-/](\d{1,2})$", text)
        if match_ym:
            year = int(match_ym.group(1))
            month = int(match_ym.group(2))

            if 1 <= month <= 12:
                parsed = pd.Timestamp(year=year, month=month, day=1)

        if parsed is None:
            match_my = re.match(r"^(\d{1,2})[-/](\d{4})$", text)
            if match_my:
                month = int(match_my.group(1))
                year = int(match_my.group(2))

                if 1 <= month <= 12:
                    parsed = pd.Timestamp(year=year, month=month, day=1)

        if parsed is None:
            try:
                dt = pd.to_datetime(text, errors="coerce", dayfirst=True)

                if not pd.isna(dt):
                    parsed = pd.Timestamp(
                        year=int(dt.year),
                        month=int(dt.month),
                        day=1,
                    )
            except Exception:
                parsed = None

        if parsed is not None:
            out.loc[idx] = parsed

    return out


def _ensure_prepared(df: pd.DataFrame) -> pd.DataFrame:
    """
    Garante que o DataFrame esteja pronto para cálculo.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()

    required_aux = {"ano_mes", "competencia_dt"}

    if required_aux.issubset(set(df.columns)):
        return df.copy()

    if has_health_food_schema(df):
        return prepare_health_food_dataframe(df)

    return df.copy()


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
    out = _ensure_prepared(df)

    if out.empty:
        return pd.DataFrame()

    if ubs and schema.ubs in out.columns:
        ubs_norm = [normalize_ubs_value(item) for item in ubs]
        out = out[out[schema.ubs].isin(ubs_norm)]

    if categorias and schema.categoria in out.columns:
        categorias_norm = [normalize_categoria_value(item) for item in categorias]
        out = out[out[schema.categoria].isin(categorias_norm)]

    if tipos and schema.tipo in out.columns:
        tipos_norm = [normalize_tipo_value(item) for item in tipos]
        out = out[out[schema.tipo].isin(tipos_norm)]

    if "ano_mes" in out.columns and competencia_inicio:
        out = out[out["ano_mes"].astype(str) >= str(competencia_inicio)]

    if "ano_mes" in out.columns and competencia_fim:
        out = out[out["ano_mes"].astype(str) <= str(competencia_fim)]

    return out.copy()


def get_filter_options(df: pd.DataFrame) -> dict:
    """
    Retorna opções limpas para filtros.
    """
    if df is None or df.empty:
        return {"ubs": [], "categorias": [], "tipos": [], "competencias": []}

    schema = get_schema()
    out = _ensure_prepared(df)

    def clean_options(column: str) -> list[str]:
        if column not in out.columns:
            return []

        values = (
            out[column]
            .dropna()
            .astype(str)
            .map(lambda x: x.strip())
        )

        values = values[~values.isin(["", "nan", "None", "NaT"])]

        return sorted(values.unique().tolist())

    return {
        "ubs": clean_options(schema.ubs),
        "categorias": clean_options(schema.categoria),
        "tipos": clean_options(schema.tipo),
        "competencias": clean_options("ano_mes"),
    }


def filter_year(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """
    Restringe a base a um ano específico usando ano_mes.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = _ensure_prepared(df)

    if "ano_mes" not in out.columns:
        return pd.DataFrame()

    return out[out["ano_mes"].astype(str).str.startswith(str(year))].copy()


def filter_year_2025(df: pd.DataFrame) -> pd.DataFrame:
    """
    Restringe a base ao ano de 2025 usando a coluna ano_mes.
    """
    return filter_year(df, 2025)


# =========================================================
# BASES DERIVADAS CENTRAIS
# =========================================================

def get_marker_df(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()

    if df is None or df.empty:
        return pd.DataFrame()

    out = _ensure_prepared(df)

    if schema.tipo not in out.columns:
        return pd.DataFrame()

    return out[out[schema.tipo] == TIPO_MARCADOR].copy()


def get_individual_attendance_df(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()

    if df is None or df.empty:
        return pd.DataFrame()

    out = _ensure_prepared(df)

    if schema.tipo not in out.columns:
        return pd.DataFrame()

    return out[out[schema.tipo] == TIPO_ATENDIMENTO_INDIVIDUAL].copy()


def _aggregate_sum(
    df: pd.DataFrame,
    group_cols: list[str],
    value_col: str,
    output_col: str,
) -> pd.DataFrame:
    """
    Agregação segura por soma.
    """
    if df is None or df.empty:
        return pd.DataFrame(columns=group_cols + [output_col])

    missing = [col for col in group_cols + [value_col] if col not in df.columns]

    if missing:
        return pd.DataFrame(columns=group_cols + [output_col])

    out = (
        df.groupby(group_cols, dropna=False)[value_col]
        .sum()
        .reset_index()
        .rename(columns={value_col: output_col})
    )

    out[output_col] = pd.to_numeric(out[output_col], errors="coerce").fillna(0.0)

    return out


def build_marker_coverage_base(df: pd.DataFrame) -> pd.DataFrame:
    """
    Base principal para calcular cobertura dos marcadores.

    Indicador:
    cobertura = marcadores / atendimentos individuais * 100

    Resultado por:
    - UBS
    - Categoria
    - ano_mes
    """
    if df is None or df.empty:
        return pd.DataFrame()

    schema = get_schema()
    out = _ensure_prepared(df)

    required = {
        schema.ubs,
        schema.categoria,
        schema.tipo,
        "ano_mes",
        schema.valor,
    }

    if not required.issubset(out.columns):
        return pd.DataFrame()

    marker = get_marker_df(out)
    attend = get_individual_attendance_df(out)

    group_cols = [schema.ubs, schema.categoria, "ano_mes"]

    marker_agg = _aggregate_sum(
        df=marker,
        group_cols=group_cols,
        value_col=schema.valor,
        output_col="marcadores",
    )

    attend_agg = _aggregate_sum(
        df=attend,
        group_cols=group_cols,
        value_col=schema.valor,
        output_col="atendimentos_individuais",
    )

    base = marker_agg.merge(
        attend_agg,
        on=group_cols,
        how="outer",
    )

    if base.empty:
        return pd.DataFrame()

    base["marcadores"] = pd.to_numeric(
        base["marcadores"],
        errors="coerce",
    ).fillna(0.0)

    base["atendimentos_individuais"] = pd.to_numeric(
        base["atendimentos_individuais"],
        errors="coerce",
    ).fillna(0.0)

    base["cobertura_percentual"] = _safe_percent(
        base["marcadores"],
        base["atendimentos_individuais"],
    )

    base = base.sort_values([schema.ubs, schema.categoria, "ano_mes"]).reset_index(drop=True)

    return base


# =========================================================
# CARDS / KPIS
# =========================================================

def build_summary_cards(df: pd.DataFrame) -> dict:
    """
    Cards principais do painel.

    Ajuste estatístico:
    - cobertura geral usa razão ponderada dos totais:
      soma(marcadores) / soma(atendimentos_individuais) * 100
    - evita média simples das coberturas, que pode distorcer UBSs com volumes diferentes.
    """
    if df is None or df.empty:
        return {
            "total_marcadores": 0,
            "cobertura_media": 0.0,
            "melhor_ubs": None,
            "melhor_categoria": None,
        }

    schema = get_schema()
    out = _ensure_prepared(df)

    coverage = build_marker_coverage_base(out)
    marker = get_marker_df(out)

    total_marcadores = (
        float(marker[schema.valor].sum())
        if not marker.empty and schema.valor in marker.columns
        else 0.0
    )

    total_atendimentos = (
        float(coverage["atendimentos_individuais"].sum())
        if not coverage.empty and "atendimentos_individuais" in coverage.columns
        else 0.0
    )

    cobertura_geral = _safe_scalar_percent(total_marcadores, total_atendimentos)

    coverage_by_ubs = table_coverage_by_ubs(out)

    melhor_ubs = None
    if not coverage_by_ubs.empty:
        valid = coverage_by_ubs.dropna(subset=["cobertura_percentual"])
        if not valid.empty:
            melhor_ubs = (
                valid.sort_values("cobertura_percentual", ascending=False)
                .iloc[0][schema.ubs]
            )

    melhor_categoria = None
    if not marker.empty and schema.categoria in marker.columns:
        cat_rank = (
            marker.groupby(schema.categoria, dropna=False)[schema.valor]
            .sum()
            .reset_index()
            .sort_values(schema.valor, ascending=False)
        )

        if not cat_rank.empty:
            melhor_categoria = cat_rank.iloc[0][schema.categoria]

    return {
        "total_marcadores": round(total_marcadores, 0),
        "cobertura_media": round(cobertura_geral, 2),
        "melhor_ubs": melhor_ubs,
        "melhor_categoria": melhor_categoria,
    }


# =========================================================
# TABELAS ANALÍTICAS
# =========================================================

def table_coverage_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = build_marker_coverage_base(df)

    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby(schema.ubs, dropna=False)[
            ["marcadores", "atendimentos_individuais"]
        ]
        .sum()
        .reset_index()
    )

    out["cobertura_percentual"] = _safe_percent(
        out["marcadores"],
        out["atendimentos_individuais"],
    )

    return out.sort_values(
        "cobertura_percentual",
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)


def table_coverage_by_month(df: pd.DataFrame) -> pd.DataFrame:
    coverage = build_marker_coverage_base(df)

    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby("ano_mes", dropna=False)[
            ["marcadores", "atendimentos_individuais"]
        ]
        .sum()
        .reset_index()
        .sort_values("ano_mes")
    )

    out["cobertura_percentual"] = _safe_percent(
        out["marcadores"],
        out["atendimentos_individuais"],
    )

    return out.reset_index(drop=True)


def table_coverage_by_ubs_and_month(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = build_marker_coverage_base(df)

    if coverage.empty:
        return pd.DataFrame()

    out = (
        coverage.groupby([schema.ubs, "ano_mes"], dropna=False)[
            ["marcadores", "atendimentos_individuais"]
        ]
        .sum()
        .reset_index()
        .sort_values([schema.ubs, "ano_mes"])
    )

    out["cobertura_percentual"] = _safe_percent(
        out["marcadores"],
        out["atendimentos_individuais"],
    )

    return out.reset_index(drop=True)


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
        method="dense",
        ascending=False,
    )

    ranking = ranking[ranking["rank"] <= int(top_n)].copy()

    return ranking.sort_values(
        [schema.ubs, "rank", "marcadores"],
        ascending=[True, True, False],
    ).reset_index(drop=True)


def table_best_and_worst_month_by_ubs(df: pd.DataFrame) -> pd.DataFrame:
    schema = get_schema()
    coverage = table_coverage_by_ubs_and_month(df)

    if coverage.empty:
        return pd.DataFrame()

    valid = coverage.dropna(subset=["cobertura_percentual"]).copy()

    if valid.empty:
        return pd.DataFrame()

    best = (
        valid.sort_values("cobertura_percentual", ascending=False)
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
        valid.sort_values("cobertura_percentual", ascending=True)
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

    Usa apenas linhas de marcadores.
    """
    schema = get_schema()
    marker = get_marker_df(df)

    if marker.empty:
        return pd.DataFrame()

    if (
        schema.identificados not in marker.columns
        or schema.nao_identificados not in marker.columns
    ):
        return pd.DataFrame()

    out = (
        marker.groupby(schema.ubs, dropna=False)[
            [schema.identificados, schema.nao_identificados]
        ]
        .sum(min_count=1)
        .reset_index()
    )

    total = (
        out[schema.identificados].fillna(0)
        + out[schema.nao_identificados].fillna(0)
    )

    out["percentual_identificados"] = _safe_percent(
        out[schema.identificados],
        total,
    )

    return out.sort_values(
        "percentual_identificados",
        ascending=False,
        na_position="last",
    ).reset_index(drop=True)


# =========================================================
# BASES PARA GRÁFICOS
# =========================================================

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
    """
    Participação percentual de cada categoria profissional no total de marcadores.

    Correção:
    - evita total.replace(), pois total é escalar, não Series.
    """
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

    total = float(out["marcadores"].sum())

    if total > 0:
        out["participacao_percentual"] = (out["marcadores"] / total) * 100
    else:
        out["participacao_percentual"] = 0.0

    return out.reset_index(drop=True)


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
    Soma de registros por UBS e mês, restrita ao ano de 2025.

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

    out["Registro"] = pd.to_numeric(out["Registro"], errors="coerce").fillna(0.0)

    return out.reset_index(drop=True)


def chart_performance_comparison_by_ubs_month_2025(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Comparativo de participação relativa por UBS por mês em 2025.

    Regra estatística:
    - soma os registros de cada UBS no mês;
    - soma o total geral do mês;
    - calcula a participação percentual da UBS no total do mês.

    Fórmula:
    percentual_desempenho = registro_ubs_mes / total_mes * 100

    Observação:
    A coluna permanece como percentual_desempenho para manter compatibilidade
    com o graphic.py, mas estatisticamente ela representa participação relativa.
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

    out["percentual_desempenho"] = _safe_percent(
        out["Registro"],
        out["total_mes"],
    )

    out["percentual_participacao"] = out["percentual_desempenho"]

    out = out.sort_values(["ano_mes", schema.ubs]).reset_index(drop=True)

    return out


# =========================================================
# SARIMA / PREVISÃO
# =========================================================

def _series_to_12_values(values: Any, fallback_value: float = 0.0) -> list[float]:
    """
    Converte qualquer saída de previsão em lista com 12 valores.
    """
    try:
        series = pd.Series(values)
        series = pd.to_numeric(series, errors="coerce")
    except Exception:
        series = pd.Series(dtype=float)

    if series.empty:
        series = pd.Series([fallback_value] * 12)

    series = series.reset_index(drop=True)

    if len(series) < 12:
        last_value = series.dropna().iloc[-1] if series.dropna().size else fallback_value
        extension = pd.Series([last_value] * (12 - len(series)))
        series = pd.concat([series, extension], ignore_index=True)

    series = series.iloc[:12].fillna(fallback_value)

    return [float(max(value, 0.0)) for value in series.tolist()]


def _fallback_forecast(series_model: pd.Series, steps: int = 12) -> tuple[list[float], list[Any], list[Any]]:
    """
    Fallback estatístico simples para série curta ou modelo SARIMA instável.

    Usa nível suavizado por média móvel exponencial e tendência amortecida.
    """
    series = pd.to_numeric(series_model, errors="coerce").fillna(0.0)

    if series.empty:
        return [0.0] * steps, [pd.NA] * steps, [pd.NA] * steps

    ewma_level = float(series.ewm(span=3, adjust=False).mean().iloc[-1])

    if len(series) >= 2:
        trend = float((series.iloc[-1] - series.iloc[0]) / max(len(series) - 1, 1))
    else:
        trend = 0.0

    damping = 0.35

    forecast = []
    for step in range(1, steps + 1):
        value = ewma_level + (trend * damping * step)
        forecast.append(float(max(value, 0.0)))

    return forecast, [pd.NA] * steps, [pd.NA] * steps


def _fit_sarima_or_fallback(series_model: pd.Series) -> tuple[list[float], list[Any], list[Any]]:
    """
    Tenta SARIMA conservador. Se a série for curta, constante ou instável,
    usa fallback estatístico simples.
    """
    series_model = pd.to_numeric(series_model, errors="coerce").fillna(0.0)
    series_model = series_model.asfreq("MS")

    observed_count = int(series_model.notna().sum())
    unique_values = int(series_model.nunique(dropna=True))

    if observed_count < 6 or unique_values <= 1:
        return _fallback_forecast(series_model, steps=12)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            model = SARIMAX(
                series_model,
                order=(1, 1, 1),
                seasonal_order=(0, 0, 0, 0),
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            )

            fit = model.fit(disp=False)
            forecast_res = fit.get_forecast(steps=12)

            forecast_values = _series_to_12_values(
                forecast_res.predicted_mean,
                fallback_value=float(series_model.mean()),
            )

            conf_int = forecast_res.conf_int()

            lower_ci = _series_to_12_values(
                conf_int.iloc[:, 0],
                fallback_value=0.0,
            )

            upper_ci = _series_to_12_values(
                conf_int.iloc[:, 1],
                fallback_value=float(series_model.mean()),
            )

            upper_ci = [
                max(upper_ci[idx], forecast_values[idx], lower_ci[idx])
                for idx in range(12)
            ]

            lower_ci = [
                min(lower_ci[idx], forecast_values[idx], upper_ci[idx])
                for idx in range(12)
            ]

            return forecast_values, lower_ci, upper_ci

    except Exception:
        pass

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            model = SARIMAX(
                series_model,
                order=(1, 0, 0),
                seasonal_order=(0, 0, 0, 0),
                trend="c",
                enforce_stationarity=False,
                enforce_invertibility=False,
            )

            fit = model.fit(disp=False)
            forecast_res = fit.get_forecast(steps=12)

            forecast_values = _series_to_12_values(
                forecast_res.predicted_mean,
                fallback_value=float(series_model.mean()),
            )

            conf_int = forecast_res.conf_int()

            lower_ci = _series_to_12_values(
                conf_int.iloc[:, 0],
                fallback_value=0.0,
            )

            upper_ci = _series_to_12_values(
                conf_int.iloc[:, 1],
                fallback_value=float(series_model.mean()),
            )

            upper_ci = [
                max(upper_ci[idx], forecast_values[idx], lower_ci[idx])
                for idx in range(12)
            ]

            lower_ci = [
                min(lower_ci[idx], forecast_values[idx], upper_ci[idx])
                for idx in range(12)
            ]

            return forecast_values, lower_ci, upper_ci

    except Exception:
        return _fallback_forecast(series_model, steps=12)


def chart_sarima_forecast_2026_by_ubs(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Previsão dos registros para 2026 por UBS.

    Regras:
    - usa dados mensais de 2025;
    - aplica filtros por categoria profissional e tipo;
    - agrega registros por UBS e mês;
    - tenta SARIMA conservador;
    - se a série for curta/instável, usa fallback suavizado.

    Observação metodológica:
    Com apenas 12 pontos mensais, a projeção é exploratória.
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

    result_frames: list[pd.DataFrame] = []

    for ubs_name in all_ubs:
        ubs_df = base[base[schema.ubs] == ubs_name].copy()

        if ubs_df.empty:
            continue

        series_observed = (
            ubs_df.groupby("competencia_dt", dropna=False)[schema.valor]
            .sum()
            .sort_index()
        )

        series_observed = series_observed[~series_observed.index.isna()]
        series_observed = pd.to_numeric(series_observed, errors="coerce")

        series_observed = series_observed.reindex(monthly_index_2025)

        # Para modelagem, meses ausentes são imputados por interpolação.
        # Se a UBS realmente não teve registro, o valor original 0 permanece como 0.
        series_model = (
            series_observed
            .interpolate(limit_direction="both")
            .fillna(0.0)
            .clip(lower=0)
        )

        historical_df = pd.DataFrame(
            {
                schema.ubs: ubs_name,
                "ano_mes": monthly_index_2025.strftime("%Y-%m"),
                "competencia_dt": monthly_index_2025,
                "Registro": series_observed.fillna(0.0).clip(lower=0).values,
                "tipo_serie": "Histórico 2025",
                "limite_inferior": pd.NA,
                "limite_superior": pd.NA,
                "mes_observado": series_observed.notna().values,
            }
        )

        result_frames.append(historical_df)

        forecast_values, lower_ci, upper_ci = _fit_sarima_or_fallback(series_model)

        forecast_df = pd.DataFrame(
            {
                schema.ubs: ubs_name,
                "ano_mes": monthly_index_2026.strftime("%Y-%m"),
                "competencia_dt": monthly_index_2026,
                "Registro": forecast_values,
                "tipo_serie": "Previsão 2026",
                "limite_inferior": lower_ci,
                "limite_superior": upper_ci,
                "mes_observado": False,
            }
        )

        forecast_df["Registro"] = pd.to_numeric(
            forecast_df["Registro"],
            errors="coerce",
        ).fillna(0.0).clip(lower=0)

        result_frames.append(forecast_df)

    if not result_frames:
        return pd.DataFrame()

    out = pd.concat(result_frames, ignore_index=True)

    out = out.sort_values(
        [schema.ubs, "competencia_dt", "tipo_serie"]
    ).reset_index(drop=True)

    return out


# =========================================================
# FUNÇÕES DE MAPA / COMPATIBILIDADE
# =========================================================

def build_ubs_monthly_totals_for_map(
    df: pd.DataFrame,
    categorias: Optional[list[str]] = None,
    tipos: Optional[list[str]] = None,
    competencia_inicio: Optional[str] = None,
    competencia_fim: Optional[str] = None,
) -> pd.DataFrame:
    """
    Agrega os registros totais por UBS e por competência para uso no mapa.
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

    if base.empty or "ano_mes" not in base.columns:
        return pd.DataFrame()

    out = (
        base.groupby([schema.ubs, "ano_mes"], dropna=False)[schema.valor]
        .sum()
        .reset_index()
        .rename(columns={schema.valor: "Registro"})
        .sort_values([schema.ubs, "ano_mes"])
    )

    out["Registro"] = pd.to_numeric(out["Registro"], errors="coerce").fillna(0.0)

    return out.reset_index(drop=True)


def build_ubs_tooltip_html(
    monthly_df: pd.DataFrame,
    ubs_name: str,
    max_rows: int = 24,
) -> str:
    """
    Monta o HTML do tooltip do mapa para uma UBS.
    """
    safe_ubs_name = html.escape(str(ubs_name))

    if monthly_df is None or monthly_df.empty:
        return f"""
        <div style="min-width:220px;">
            <b>{safe_ubs_name}</b><br>
            Sem dados disponíveis.
        </div>
        """

    schema = get_schema()
    ubs_col = schema.ubs if schema.ubs in monthly_df.columns else "UBS"

    subset = monthly_df[monthly_df[ubs_col] == ubs_name].copy()

    if subset.empty:
        return f"""
        <div style="min-width:220px;">
            <b>{safe_ubs_name}</b><br>
            Sem dados disponíveis.
        </div>
        """

    subset = subset.sort_values("ano_mes").head(max_rows)

    linhas = []

    for _, row in subset.iterrows():
        comp = html.escape(str(row.get("ano_mes", "")))
        registro = row.get("Registro", 0)

        try:
            registro_fmt = f"{float(registro):,.0f}".replace(",", ".")
        except Exception:
            registro_fmt = html.escape(str(registro))

        linhas.append(
            f"<tr>"
            f"<td style='padding:2px 8px 2px 0;'><b>{comp}</b></td>"
            f"<td style='padding:2px 0;text-align:right;'>{registro_fmt}</td>"
            f"</tr>"
        )

    rows_html = "".join(linhas)

    return f"""
    <div style="min-width:260px;">
        <div style="font-weight:700; margin-bottom:6px;">{safe_ubs_name}</div>
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