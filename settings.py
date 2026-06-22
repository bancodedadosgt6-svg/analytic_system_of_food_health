from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from supabase_client import (
    SUPABASE_REGISTROS_TABLE,
    fetch_registros_saude_alimentar,
    get_supabase_environment_status,
    test_supabase_connection,
)


load_dotenv()


# =========================================================
# CAMINHOS / IDENTIDADE DO APP
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

PARQUET_FILE = DATA_DIR / "base_saude_alimentar.parquet"
METADATA_FILE = DATA_DIR / "_supabase_sync_metadata.json"

APP_TITLE = "Painel de Análise de Dados em Saúde Alimentar"
APP_SUBTITLE = "Projeto de Saúde Alimentar elaborado pela equipe do PET6 de Saúde Digital e Alimentar."

SPONSORS = [
    "PET-Saúde Digital",
    "GT6",
    "Rede de Pesquisa",
]

CONSOLIDATED_DATASET_NAME = "base_consolidada_saude_alimentar"
CONSOLIDATED_DATASET_FILE_NAME = PARQUET_FILE.name
CONSOLIDATED_DATASET_PATH = str(PARQUET_FILE)

DEFAULT_LAT_COLUMNS = ["latitude", "lat", "y", "Latitude", "LATITUDE"]
DEFAULT_LON_COLUMNS = ["longitude", "lon", "lng", "long", "x", "Longitude", "LONGITUDE"]


# =========================================================
# COLUNAS PADRÃO
# =========================================================

EXPECTED_COLUMNS = [
    "Registro ID",
    "UBS ID",
    "Submissão ID",
    "Usuário ID",
    "UBS",
    "Categoria",
    "Tipo",
    "Competência",
    "Valor",
    "Identificados",
    "Não identificados",
    "Arquivo origem",
    "Hash registro",
    "Criado em",
]


# =========================================================
# DIRETÓRIOS / ESTILO
# =========================================================

def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_css(css_file: str = "style.css") -> None:
    """
    Carrega um arquivo CSS local e injeta no app Streamlit.
    """
    css_path = BASE_DIR / css_file

    if not css_path.exists():
        return

    css = css_path.read_text(encoding="utf-8")
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


# =========================================================
# METADATA / CACHE
# =========================================================

@st.cache_data(show_spinner=False)
def load_metadata() -> Dict[str, Any]:
    ensure_data_dir()

    if not METADATA_FILE.exists():
        return {}

    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_metadata(metadata: Dict[str, Any]) -> None:
    ensure_data_dir()

    METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    try:
        load_metadata.clear()
    except Exception:
        pass


def clear_dataset_caches() -> None:
    """
    Limpa caches que dependem dos dados locais.
    """
    for func in [
        read_local_parquet,
        read_dataframe,
        get_datasets_catalog,
    ]:
        try:
            func.clear()
        except Exception:
            pass


def build_dataframe_signature(df: pd.DataFrame) -> str:
    """
    Gera assinatura do DataFrame para saber se o Parquet precisa ser regravado.
    """
    if df is None or df.empty:
        return "empty"

    stable = df.copy()

    if "Registro ID" in stable.columns:
        stable = stable.sort_values("Registro ID")

    stable = stable.reset_index(drop=True)

    for col in stable.columns:
        stable[col] = stable[col].astype(str).fillna("")

    raw = stable.to_json(
        orient="records",
        force_ascii=False,
        date_format="iso",
    )

    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_now_sao_paulo_str() -> str:
    """
    Retorna horário atual formatado no fuso de São Paulo.
    """
    try:
        now = pd.Timestamp.now(tz="UTC").tz_convert("America/Sao_Paulo")
    except Exception:
        now = pd.Timestamp.utcnow()

    return now.strftime("%d/%m/%Y %H:%M")


# =========================================================
# NORMALIZAÇÃO DOS DADOS
# =========================================================

def empty_health_food_dataframe() -> pd.DataFrame:
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


def normalize_column_name(value: Any) -> str:
    """
    Normaliza nome de coluna para comparação.
    """
    import unicodedata

    text = str(value or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))

    replacements = {
        " ": "_",
        "-": "_",
        "/": "_",
        "\\": "_",
        ".": "",
        ",": "",
        ";": "",
        ":": "",
        "(": "",
        ")": "",
        "\n": "_",
        "\r": "_",
        "\t": "_",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    while "__" in text:
        text = text.replace("__", "_")

    return text.strip("_")


def normalize_ubs_name(value: Any) -> str | None:
    """
    Padroniza nomes das UBSs para o painel e mapa.
    """
    if value is None or pd.isna(value):
        return None

    text = str(value).strip()

    if not text:
        return None

    normalized = normalize_column_name(text)

    aliases = {
        "gama": "Gama",
        "santa_maria": "Santa Maria",
        "santa_maría": "Santa Maria",
        "jardins_mangueiral": "Jardins Mangueiral",
        "jardins_mangueral": "Jardins Mangueiral",
    }

    return aliases.get(normalized, text)


def normalize_health_food_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte colunas vindas do Supabase ou do Parquet para o schema esperado pelo dashboard.
    """
    if df is None or df.empty:
        return empty_health_food_dataframe()

    out = df.copy()

    rename_by_normalized = {
        "id": "Registro ID",
        "registro_id": "Registro ID",

        "ubs_id": "UBS ID",

        "submissao_id": "Submissão ID",
        "submissão_id": "Submissão ID",

        "user_id": "Usuário ID",
        "usuario_id": "Usuário ID",
        "usuário_id": "Usuário ID",

        "ubs": "UBS",
        "categoria": "Categoria",
        "tipo": "Tipo",

        "competencia": "Competência",
        "competência": "Competência",

        "valor": "Valor",

        "identificados": "Identificados",
        "identificado": "Identificados",

        "nao_identificados": "Não identificados",
        "não_identificados": "Não identificados",
        "nao_identificado": "Não identificados",
        "não_identificado": "Não identificados",

        "arquivo_origem": "Arquivo origem",

        "hash_registro": "Hash registro",

        "created_at": "Criado em",
        "criado_em": "Criado em",
    }

    rename_map = {}

    for col in out.columns:
        col_norm = normalize_column_name(col)

        if col_norm in rename_by_normalized:
            rename_map[col] = rename_by_normalized[col_norm]

    out = out.rename(columns=rename_map)

    for col in EXPECTED_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out["UBS"] = out["UBS"].apply(normalize_ubs_name)

    for col in ["Valor", "Identificados", "Não identificados"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out["Criado em"] = pd.to_datetime(
        out["Criado em"],
        errors="coerce",
        utc=True,
    )

    out = out[EXPECTED_COLUMNS].copy()

    return out


# =========================================================
# SUPABASE → DATAFRAME → PARQUET
# =========================================================

def fetch_supabase_registros() -> pd.DataFrame:
    """
    Busca todos os registros da tabela registros_saude_alimentar no Supabase.

    A paginação e a conexão ficam em supabase_client.py.
    Aqui apenas transformamos a resposta em DataFrame analítico.
    """
    rows = fetch_registros_saude_alimentar()

    if not rows:
        return empty_health_food_dataframe()

    raw_df = pd.DataFrame(rows)

    return normalize_health_food_columns(raw_df)


def write_parquet_cache(df: pd.DataFrame) -> None:
    """
    Salva a base analítica local em Parquet.
    """
    ensure_data_dir()

    normalized = normalize_health_food_columns(df)

    normalized.to_parquet(
        PARQUET_FILE,
        index=False,
    )


@st.cache_data(show_spinner=False)
def read_local_parquet() -> pd.DataFrame:
    """
    Lê a base analítica local em Parquet.
    """
    ensure_data_dir()

    if not PARQUET_FILE.exists():
        return empty_health_food_dataframe()

    try:
        df = pd.read_parquet(PARQUET_FILE)
        return normalize_health_food_columns(df)
    except Exception:
        return empty_health_food_dataframe()


def sync_supabase_to_parquet(force: bool = False) -> Dict[str, Any]:
    """
    Sincroniza Supabase para uma base Parquet local.

    Supabase é a fonte oficial.
    Parquet é cache analítico local para performance do dashboard.
    """
    ensure_data_dir()

    metadata = load_metadata()
    cache_before = read_local_parquet()
    cache_rows_before = int(len(cache_before))

    try:
        remote_df = fetch_supabase_registros()
    except Exception as e:
        st.warning(
            "Não foi possível consultar o banco neste momento. "
            "O painel continuará usando os dados já coletados, se existir. "
            f"Detalhe: {e}"
        )

        return {
            "success": False,
            "source": "cache",
            "message": str(e),
            "supabase_rows": 0,
            "cache_rows": cache_rows_before,
            "rows": cache_rows_before,
            "ubs_count": int(cache_before["UBS"].nunique()) if "UBS" in cache_before.columns else 0,
            "updated": 0,
            "skipped": 1,
            "checked": 0,
            "downloaded": 0,
            "last_sync": metadata.get("last_sync"),
        }

    supabase_rows = int(len(remote_df))

    ubs_count = (
        int(remote_df["UBS"].dropna().nunique())
        if "UBS" in remote_df.columns and not remote_df.empty
        else 0
    )

    current_signature = build_dataframe_signature(remote_df)
    previous_signature = metadata.get("data_signature")

    should_write = (
        force
        or current_signature != previous_signature
        or not PARQUET_FILE.exists()
    )

    if should_write:
        write_parquet_cache(remote_df)

        metadata = {
            "source": "supabase",
            "table": SUPABASE_REGISTROS_TABLE,
            "parquet_file": str(PARQUET_FILE),
            "data_signature": current_signature,
            "supabase_rows": supabase_rows,
            "ubs_count": ubs_count,
            "last_sync": get_now_sao_paulo_str(),
        }

        save_metadata(metadata)
        clear_dataset_caches()

        return {
            "success": True,
            "source": "supabase",
            "message": "Base já atualizada.",
            "supabase_rows": supabase_rows,
            "cache_rows": supabase_rows,
            "rows": supabase_rows,
            "ubs_count": ubs_count,
            "updated": 1,
            "skipped": 0,
            "checked": supabase_rows,
            "downloaded": 1,
            "last_sync": metadata["last_sync"],
        }

    return {
        "success": True,
        "source": "cache",
        "message": "Base já atualizada",
        "supabase_rows": supabase_rows,
        "cache_rows": cache_rows_before,
        "rows": cache_rows_before,
        "ubs_count": ubs_count,
        "updated": 0,
        "skipped": 1,
        "checked": supabase_rows,
        "downloaded": 0,
        "last_sync": metadata.get("last_sync"),
    }


# Compatibilidade temporária com arquivos antigos.
def sync_google_drive_data() -> Dict[str, Any]:
    return sync_supabase_to_parquet(force=False)


# =========================================================
# LEITURA LOCAL / CATÁLOGO
# =========================================================

@st.cache_data(show_spinner=False)
def list_local_data_files() -> List[Path]:
    """
    Lista apenas a base Parquet analítica do painel.
    """
    ensure_data_dir()

    if PARQUET_FILE.exists():
        return [PARQUET_FILE]

    return []


@st.cache_data(show_spinner=False)
def read_dataframe(path_str: str) -> pd.DataFrame:
    """
    Lê um dataset local.
    Neste novo fluxo, o dataset principal é o Parquet consolidado.
    """
    path = Path(path_str)

    if path == PARQUET_FILE or path.suffix.lower() == ".parquet":
        return read_local_parquet()

    raise ValueError(f"Formato não suportado neste painel: {path.suffix}")


@st.cache_data(show_spinner=False)
def get_datasets_catalog() -> List[dict]:
    """
    Monta o catálogo de datasets.

    O primeiro item é sempre a base consolidada do Supabase em Parquet.
    """
    catalog: List[dict] = []

    df = read_local_parquet()

    if df.empty:
        return catalog

    lat_col, lon_col = detect_lat_lon_columns(df)

    catalog.append(
        {
            "name": CONSOLIDATED_DATASET_NAME,
            "file_name": CONSOLIDATED_DATASET_FILE_NAME,
            "path": CONSOLIDATED_DATASET_PATH,
            "rows": int(len(df)),
            "cols": int(len(df.columns)),
            "is_geospatial": bool(lat_col and lon_col),
            "lat_col": lat_col,
            "lon_col": lon_col,
        }
    )

    return catalog


def detect_lat_lon_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    lat_col = next((c for c in df.columns if c in DEFAULT_LAT_COLUMNS), None)
    lon_col = next((c for c in df.columns if c in DEFAULT_LON_COLUMNS), None)

    return lat_col, lon_col


def get_dataset_by_name(dataset_name: str) -> pd.DataFrame:
    """
    Retorna o dataframe pelo nome do dataset.
    """
    if dataset_name == CONSOLIDATED_DATASET_NAME:
        return read_local_parquet()

    catalog = get_datasets_catalog()
    item = next((d for d in catalog if d["name"] == dataset_name), None)

    if not item:
        return empty_health_food_dataframe()

    return read_dataframe(item["path"])


def get_dataset_last_update(dataset_name: str) -> str | None:
    """
    Retorna a última atualização do cache local gerado a partir do Supabase.
    """
    metadata = load_metadata()

    return metadata.get("last_sync")


# =========================================================
# TIPOS DE COLUNAS
# =========================================================

def get_numeric_columns(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return []

    return df.select_dtypes(include="number").columns.tolist()


def get_categorical_columns(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return []

    return df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()


def get_datetime_columns(df: pd.DataFrame) -> List[str]:
    if df is None or df.empty:
        return []

    candidates: list[str] = []

    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            candidates.append(col)
            continue

        if df[col].dtype == object:
            try:
                converted = pd.to_datetime(df[col], errors="coerce")

                if converted.notna().sum() > 0:
                    candidates.append(col)

            except Exception:
                continue

    return candidates


# =========================================================
# DIAGNÓSTICO
# =========================================================

def get_environment_status() -> Dict[str, Any]:
    """
    Status básico do ambiente sem expor chaves sensíveis.
    """
    metadata = load_metadata()
    df = read_local_parquet()
    supabase_status = get_supabase_environment_status()
    connection_test = test_supabase_connection()

    return {
        **supabase_status,
        "supabase_conexao_ok": bool(connection_test.get("success")),
        "supabase_conexao_msg": connection_test.get("message"),
        "parquet_existe": PARQUET_FILE.exists(),
        "parquet_path": str(PARQUET_FILE),
        "linhas_cache": int(len(df)),
        "ultima_sincronizacao": metadata.get("last_sync"),
    }