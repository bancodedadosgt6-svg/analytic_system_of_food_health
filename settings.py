from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
METADATA_FILE = DATA_DIR / "_sync_metadata.json"

APP_TITLE = "Painel de Análise de Dados em Saúde Alimentar"
APP_SUBTITLE = "MVP analítico com sincronização local de dados, tabela dinâmica, gráficos e mapas"

SPONSORS = [
    "PET-Saúde Digital",
    "GT6",
    "Rede de Pesquisa",
]

GOOGLE_DRIVE_ENABLED = os.getenv("GOOGLE_DRIVE_ENABLED", "false").lower() == "true"
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv(
    "GOOGLE_SERVICE_ACCOUNT_FILE", str(BASE_DIR / "service_account.json")
)

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".geojson", ".json"}

DEFAULT_LAT_COLUMNS = ["latitude", "lat", "y", "Latitude", "LATITUDE"]
DEFAULT_LON_COLUMNS = ["longitude", "lon", "lng", "long", "x", "Longitude", "LONGITUDE"]


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


@st.cache_data(show_spinner=False)
def load_metadata() -> Dict[str, dict]:
    ensure_data_dir()
    if not METADATA_FILE.exists():
        return {}
    try:
        return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_metadata(metadata: Dict[str, dict]) -> None:
    ensure_data_dir()
    METADATA_FILE.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    load_metadata.clear()


def build_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@st.cache_resource(show_spinner=False)
def get_google_drive_service():
    if not GOOGLE_DRIVE_ENABLED:
        return None

    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build

    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    credentials = Credentials.from_service_account_file(
        GOOGLE_SERVICE_ACCOUNT_FILE,
        scopes=scopes,
    )
    return build("drive", "v3", credentials=credentials)


def list_drive_files() -> List[dict]:
    service = get_google_drive_service()
    if service is None:
        return []
    if not GOOGLE_DRIVE_FOLDER_ID:
        raise ValueError("Defina GOOGLE_DRIVE_FOLDER_ID no ambiente.")

    query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed = false"
    response = (
        service.files()
        .list(
            q=query,
            fields="files(id, name, modifiedTime, mimeType)",
            pageSize=1000,
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
    )
    return response.get("files", [])


def download_drive_file(file_id: str) -> bytes:
    service = get_google_drive_service()
    if service is None:
        raise RuntimeError("Google Drive não está habilitado.")

    from googleapiclient.http import MediaIoBaseDownload

    request = service.files().get_media(fileId=file_id, supportsAllDrives=True)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)

    done = False
    while not done:
        _, done = downloader.next_chunk()

    return buffer.getvalue()


def sync_google_drive_data() -> Dict[str, int]:
    ensure_data_dir()

    if not GOOGLE_DRIVE_ENABLED:
        return {"checked": 0, "downloaded": 0, "updated": 0, "skipped": 0}

    remote_files = list_drive_files()
    metadata = load_metadata()

    checked = downloaded = updated = skipped = 0

    for remote in remote_files:
        checked += 1
        file_name = remote["name"]
        suffix = Path(file_name).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            skipped += 1
            continue

        content = download_drive_file(remote["id"])
        content_hash = build_file_hash(content)
        local_path = DATA_DIR / file_name
        previous_hash = metadata.get(file_name, {}).get("hash")

        if previous_hash == content_hash and local_path.exists():
            skipped += 1
            continue

        local_path.write_bytes(content)

        is_update = file_name in metadata
        metadata[file_name] = {
            "hash": content_hash,
            "file_id": remote["id"],
            "modifiedTime": remote.get("modifiedTime"),
            "mimeType": remote.get("mimeType"),
        }

        if is_update:
            updated += 1
        else:
            downloaded += 1

    save_metadata(metadata)
    return {
        "checked": checked,
        "downloaded": downloaded,
        "updated": updated,
        "skipped": skipped,
    }


@st.cache_data(show_spinner=False)
def list_local_data_files() -> List[Path]:
    ensure_data_dir()
    files: List[Path] = []
    for path in DATA_DIR.iterdir():
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return sorted(files, key=lambda p: p.name.lower())


@st.cache_data(show_spinner=False)
def read_dataframe(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix in {".geojson", ".json"}:
        try:
            import geopandas as gpd

            gdf = gpd.read_file(path)
            if gdf.empty:
                return pd.DataFrame()
            if "geometry" in gdf.columns:
                centroids = gdf.geometry.centroid
                gdf["latitude"] = centroids.y
                gdf["longitude"] = centroids.x
            return pd.DataFrame(gdf.drop(columns=[c for c in ["geometry"] if c in gdf.columns]))
        except Exception:
            return pd.read_json(path)

    raise ValueError(f"Formato não suportado: {suffix}")


@st.cache_data(show_spinner=False)
def get_datasets_catalog() -> List[dict]:
    catalog: List[dict] = []
    for path in list_local_data_files():
        try:
            df = read_dataframe(str(path))
            lat_col, lon_col = detect_lat_lon_columns(df)
            catalog.append(
                {
                    "name": path.stem,
                    "file_name": path.name,
                    "path": str(path),
                    "rows": int(len(df)),
                    "cols": int(len(df.columns)),
                    "is_geospatial": bool(lat_col and lon_col),
                    "lat_col": lat_col,
                    "lon_col": lon_col,
                }
            )
        except Exception:
            catalog.append(
                {
                    "name": path.stem,
                    "file_name": path.name,
                    "path": str(path),
                    "rows": 0,
                    "cols": 0,
                    "is_geospatial": False,
                    "lat_col": None,
                    "lon_col": None,
                }
            )
    return catalog


def detect_lat_lon_columns(df: pd.DataFrame) -> tuple[Optional[str], Optional[str]]:
    lat_col = next((c for c in df.columns if c in DEFAULT_LAT_COLUMNS), None)
    lon_col = next((c for c in df.columns if c in DEFAULT_LON_COLUMNS), None)
    return lat_col, lon_col


def get_dataset_by_name(dataset_name: str) -> pd.DataFrame:
    catalog = get_datasets_catalog()
    item = next((d for d in catalog if d["name"] == dataset_name), None)
    if not item:
        return pd.DataFrame()
    return read_dataframe(item["path"])


def get_numeric_columns(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(include="number").columns.tolist()


def get_categorical_columns(df: pd.DataFrame) -> List[str]:
    return df.select_dtypes(include=["object", "category", "bool"]).columns.tolist()


def get_datetime_columns(df: pd.DataFrame) -> List[str]:
    candidates = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            candidates.append(col)
            continue
        if df[col].dtype == object:
            try:
                converted = pd.to_datetime(df[col], errors="raise")
                if converted.notna().sum() > 0:
                    candidates.append(col)
            except Exception:
                continue
    return candidates


def get_dataset_last_update(dataset_name: str) -> str | None:
    """
    Retorna a data/hora de atualização do arquivo no Google Drive
    com base no metadata local de sincronização.
    """
    metadata = load_metadata()
    catalog = get_datasets_catalog()

    item = next((d for d in catalog if d["name"] == dataset_name), None)
    if not item:
        return None

    file_name = item["file_name"]
    modified_time = metadata.get(file_name, {}).get("modifiedTime")

    if not modified_time:
        return None

    try:
        dt = pd.to_datetime(modified_time, utc=True).tz_convert("America/Sao_Paulo")
        return dt.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(modified_time)