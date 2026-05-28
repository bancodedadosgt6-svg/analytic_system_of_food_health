from __future__ import annotations

import hashlib
import io
import json
import os
import socket
import ssl
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from googleapiclient.errors import HttpError


load_dotenv()


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
METADATA_FILE = DATA_DIR / "_sync_metadata.json"

APP_TITLE = "Painel de Análise de Dados em Saúde Alimentar"
APP_SUBTITLE = "Projeto de Saúde Alimentar elaborado pela equipe do PET6 de Saúde Digital e Alimentar."

SPONSORS = [
    "PET-Saúde Digital",
    "GT6",
    "Rede de Pesquisa",
]

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".parquet", ".geojson", ".json"}

DEFAULT_LAT_COLUMNS = ["latitude", "lat", "y", "Latitude", "LATITUDE"]
DEFAULT_LON_COLUMNS = ["longitude", "lon", "lng", "long", "x", "Longitude", "LONGITUDE"]

GOOGLE_DRIVE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
]

CONSOLIDATED_DATASET_NAME = "base_consolidada_saude_alimentar"
CONSOLIDATED_DATASET_FILE_NAME = "base_consolidada_saude_alimentar.xlsx"
CONSOLIDATED_DATASET_PATH = "__base_consolidada__"

DRIVE_UBS_FOLDERS = {
    "Gama": "Gama",
    "Jardins Mangueiral": "Jardins-Mangueral",
    "Santa Maria": "Santa-Maria",
}

DRIVE_UBS_FILES = {
    "Gama": "banco_gama.xlsx",
    "Jardins Mangueiral": "banco_jardins_mangueral.xlsx",
    "Santa Maria": "banco_santa_maria.xlsx",
}


# =========================================================
# CONFIGURAÇÕES / SECRETS
# =========================================================

def get_secret_or_env(key: str, default=None):
    """
    Busca primeiro no Streamlit Secrets e depois no .env.
    Funciona localmente e no deploy.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return os.getenv(key, default)


GOOGLE_DRIVE_ENABLED = str(
    get_secret_or_env("GOOGLE_DRIVE_ENABLED", "false")
).lower() == "true"

# Opcional:
# Se GOOGLE_DRIVE_FOLDER_ID existir, o sistema lê uma pasta única.
# Se não existir, lê automaticamente as pastas das UBSs.
GOOGLE_DRIVE_FOLDER_ID = str(
    get_secret_or_env("GOOGLE_DRIVE_FOLDER_ID", "")
).strip()

GOOGLE_OAUTH_CREDENTIALS_FILE = get_secret_or_env(
    "GOOGLE_OAUTH_CREDENTIALS_FILE",
    "credentials.json",
)

GOOGLE_OAUTH_TOKEN_FILE = get_secret_or_env(
    "GOOGLE_OAUTH_TOKEN_FILE",
    "token.json",
)


def get_secret_json(key: str) -> dict | None:
    """
    Lê um JSON armazenado como string no secrets.toml.

    Exemplo:
    GOOGLE_OAUTH_TOKEN_JSON = \"\"\"
    { ... }
    \"\"\"
    """
    try:
        value = st.secrets.get(key)
    except Exception:
        return None

    if not value:
        return None

    if isinstance(value, dict):
        return dict(value)

    try:
        return json.loads(str(value))
    except json.JSONDecodeError as e:
        raise ValueError(
            f"O segredo {key} não contém um JSON válido. "
            f"Revise aspas, vírgulas e chaves no secrets.toml. Erro: {e}"
        ) from e


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
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    load_metadata.clear()


def build_file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_remote_signature(remote: dict) -> str:
    """
    Assinatura leve do arquivo remoto.

    Usa md5Checksum quando disponível.
    Como fallback, usa modifiedTime + size.
    """
    md5 = remote.get("md5Checksum")

    if md5:
        return f"md5:{md5}"

    modified = remote.get("modifiedTime", "")
    size = remote.get("size", "")

    return f"modified:{modified}|size:{size}"


def is_remote_file_changed(
    file_name: str,
    remote: dict,
    metadata: Dict[str, dict],
) -> bool:
    """
    Verifica se o arquivo remoto mudou em relação ao cache local.
    """
    previous = metadata.get(file_name, {})
    previous_signature = previous.get("remote_signature")
    current_signature = build_remote_signature(remote)

    local_path = DATA_DIR / file_name

    if not local_path.exists():
        return True

    return previous_signature != current_signature


def clear_dataset_caches() -> None:
    """
    Limpa caches que dependem dos arquivos locais.
    """
    try:
        list_local_data_files.clear()
    except Exception:
        pass

    try:
        read_dataframe.clear()
    except Exception:
        pass

    try:
        read_consolidated_health_food_dataframe.clear()
    except Exception:
        pass

    try:
        get_datasets_catalog.clear()
    except Exception:
        pass


# =========================================================
# GOOGLE DRIVE - RETRY / OAUTH
# =========================================================

def execute_drive_request(request, context: str = "requisição Google Drive", retries: int = 4):
    """
    Executa uma requisição da API do Google Drive com retry.

    Protege o app contra falhas intermitentes no deploy:
    - ssl.SSLError
    - socket timeout
    - connection reset
    - HTTP 429 / 5xx
    """
    last_error = None

    for attempt in range(1, retries + 1):
        try:
            return request.execute(num_retries=2)

        except HttpError as e:
            status = getattr(e.resp, "status", None)
            last_error = e

            if status in [429, 500, 502, 503, 504]:
                time.sleep(min(2 * attempt, 10))
                continue

            raise

        except (
            ssl.SSLError,
            socket.timeout,
            TimeoutError,
            ConnectionError,
            OSError,
        ) as e:
            last_error = e
            time.sleep(min(2 * attempt, 10))
            continue

    raise RuntimeError(
        f"Falha ao executar {context} após {retries} tentativas: {last_error}"
    )


@st.cache_resource(show_spinner=False)
def get_google_drive_service():
    """
    Cria o serviço do Google Drive.

    Prioridade:
    1. Usa GOOGLE_OAUTH_TOKEN_JSON do Streamlit Secrets.
    2. Usa token.json local, se existir.
    3. Se não houver token válido, usa credentials.json local ou
       GOOGLE_OAUTH_CREDENTIALS_JSON para abrir OAuth local.

    No deploy, o ideal é já existir GOOGLE_OAUTH_TOKEN_JSON.
    """
    if not GOOGLE_DRIVE_ENABLED:
        return None

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None

    token_from_secrets = get_secret_json("GOOGLE_OAUTH_TOKEN_JSON")
    credentials_from_secrets = get_secret_json("GOOGLE_OAUTH_CREDENTIALS_JSON")

    if token_from_secrets:
        creds = Credentials.from_authorized_user_info(
            token_from_secrets,
            GOOGLE_DRIVE_SCOPES,
        )

    elif os.path.exists(GOOGLE_OAUTH_TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(
            GOOGLE_OAUTH_TOKEN_FILE,
            GOOGLE_DRIVE_SCOPES,
        )

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds or not creds.valid:
        if credentials_from_secrets:
            flow = InstalledAppFlow.from_client_config(
                credentials_from_secrets,
                GOOGLE_DRIVE_SCOPES,
            )
        else:
            if not os.path.exists(GOOGLE_OAUTH_CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Arquivo de credenciais OAuth não encontrado: {GOOGLE_OAUTH_CREDENTIALS_FILE}. "
                    "No local, coloque credentials.json na raiz. "
                    "No deploy, configure GOOGLE_OAUTH_CREDENTIALS_JSON e "
                    "GOOGLE_OAUTH_TOKEN_JSON nos secrets do Streamlit."
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                GOOGLE_OAUTH_CREDENTIALS_FILE,
                GOOGLE_DRIVE_SCOPES,
            )

        creds = flow.run_local_server(
            port=0,
            prompt="consent",
        )

        with open(GOOGLE_OAUTH_TOKEN_FILE, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())

    return build(
        "drive",
        "v3",
        credentials=creds,
        cache_discovery=False,
    )


def escape_drive_query_value(value: str) -> str:
    """
    Escapa aspas simples para consultas na API do Drive.
    """
    return str(value).replace("'", "\\'")


def buscar_pasta_por_nome(service, folder_name: str) -> str | None:
    """
    Busca uma pasta pelo nome no Google Drive.
    """
    folder_name_safe = escape_drive_query_value(folder_name)

    query = (
        "mimeType='application/vnd.google-apps.folder' "
        f"and name='{folder_name_safe}' "
        "and trashed=false"
    )

    request = service.files().list(
        q=query,
        fields="files(id, name)",
        spaces="drive",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    )

    response = execute_drive_request(
        request,
        context=f"buscar pasta '{folder_name}'",
    )

    files = response.get("files", [])

    if not files:
        return None

    return files[0]["id"]


def buscar_arquivo_na_pasta(service, folder_id: str, file_name: str) -> dict | None:
    """
    Busca um arquivo específico dentro de uma pasta.
    """
    file_name_safe = escape_drive_query_value(file_name)

    query = (
        f"'{folder_id}' in parents "
        f"and name='{file_name_safe}' "
        "and trashed=false"
    )

    request = service.files().list(
        q=query,
        fields="files(id, name, modifiedTime, mimeType, md5Checksum, size)",
        spaces="drive",
        pageSize=10,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    )

    response = execute_drive_request(
        request,
        context=f"buscar arquivo '{file_name}'",
    )

    files = response.get("files", [])

    if not files:
        return None

    return files[0]


def list_drive_files_from_configured_folder() -> List[dict]:
    """
    Modo legado opcional:
    lista arquivos de uma pasta única por GOOGLE_DRIVE_FOLDER_ID.
    """
    service = get_google_drive_service()

    if service is None:
        return []

    if not GOOGLE_DRIVE_FOLDER_ID:
        return []

    query = f"'{GOOGLE_DRIVE_FOLDER_ID}' in parents and trashed=false"

    request = service.files().list(
        q=query,
        fields="files(id, name, modifiedTime, mimeType, md5Checksum, size)",
        pageSize=1000,
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    )

    response = execute_drive_request(
        request,
        context="listar arquivos da pasta configurada",
    )

    return response.get("files", [])


def list_drive_files_from_ubs_folders() -> List[dict]:
    """
    Lista os bancos XLSX das UBSs nas pastas esperadas.
    Se uma pasta/arquivo falhar por instabilidade de rede, o app continua.
    """
    service = get_google_drive_service()

    if service is None:
        return []

    files: List[dict] = []

    for ubs_name, folder_name in DRIVE_UBS_FOLDERS.items():
        expected_file_name = DRIVE_UBS_FILES[ubs_name]

        try:
            folder_id = buscar_pasta_por_nome(
                service=service,
                folder_name=folder_name,
            )

            if not folder_id:
                continue

            remote_file = buscar_arquivo_na_pasta(
                service=service,
                folder_id=folder_id,
                file_name=expected_file_name,
            )

            if not remote_file:
                continue

            remote_file["ubs_name"] = ubs_name
            remote_file["folder_name"] = folder_name
            remote_file["folder_id"] = folder_id

            files.append(remote_file)

        except Exception as e:
            st.warning(
                f"Não foi possível consultar a UBS {ubs_name} no Google Drive agora. "
                f"O painel continuará usando o cache local, se existir. Detalhe: {e}"
            )
            continue

    return files


def list_drive_files() -> List[dict]:
    """
    Lista arquivos do Drive.

    Prioridade:
    1. Se GOOGLE_DRIVE_FOLDER_ID estiver definido, lista essa pasta.
    2. Caso contrário, busca automaticamente os bancos nas pastas das UBSs.
    """
    if GOOGLE_DRIVE_FOLDER_ID:
        return list_drive_files_from_configured_folder()

    return list_drive_files_from_ubs_folders()


def download_drive_file(file_id: str) -> bytes:
    """
    Baixa arquivo do Google Drive com retry.
    """
    service = get_google_drive_service()

    if service is None:
        raise RuntimeError("Google Drive não está habilitado.")

    from googleapiclient.http import MediaIoBaseDownload

    last_error = None

    for attempt in range(1, 5):
        try:
            request = service.files().get_media(
                fileId=file_id,
                supportsAllDrives=True,
            )

            buffer = io.BytesIO()
            downloader = MediaIoBaseDownload(buffer, request)

            done = False

            while not done:
                _, done = downloader.next_chunk(num_retries=2)

            return buffer.getvalue()

        except (
            ssl.SSLError,
            socket.timeout,
            TimeoutError,
            ConnectionError,
            OSError,
            HttpError,
        ) as e:
            last_error = e
            time.sleep(min(2 * attempt, 10))
            continue

    raise RuntimeError(f"Falha ao baixar arquivo do Google Drive: {last_error}")


def sync_google_drive_data() -> Dict[str, int]:
    """
    Sincroniza dados do Google Drive para a pasta local data/.

    Regra:
    - consulta metadados primeiro;
    - se assinatura remota não mudou, não baixa;
    - se mudou, baixa e substitui cache local;
    - atualiza _sync_metadata.json;
    - se o Drive falhar por instabilidade, o app continua usando cache local.
    """
    ensure_data_dir()

    if not GOOGLE_DRIVE_ENABLED:
        return {"checked": 0, "downloaded": 0, "updated": 0, "skipped": 0}

    try:
        remote_files = list_drive_files()
    except Exception as e:
        st.warning(
            f"Não foi possível consultar o Google Drive neste momento. "
            f"O painel continuará usando os dados em cache local, se existirem. Detalhe: {e}"
        )
        return {"checked": 0, "downloaded": 0, "updated": 0, "skipped": 0}

    metadata = load_metadata()

    checked = downloaded = updated = skipped = 0
    changed_any = False

    for remote in remote_files:
        checked += 1

        file_name = remote["name"]
        suffix = Path(file_name).suffix.lower()

        if suffix not in SUPPORTED_EXTENSIONS:
            skipped += 1
            continue

        local_path = DATA_DIR / file_name
        is_update = file_name in metadata

        if not is_remote_file_changed(file_name, remote, metadata):
            skipped += 1
            continue

        try:
            content = download_drive_file(remote["id"])
            content_hash = build_file_hash(content)
            local_path.write_bytes(content)

            metadata[file_name] = {
                "hash": content_hash,
                "remote_signature": build_remote_signature(remote),
                "file_id": remote["id"],
                "folder_id": remote.get("folder_id"),
                "folder_name": remote.get("folder_name"),
                "ubs_name": remote.get("ubs_name"),
                "modifiedTime": remote.get("modifiedTime"),
                "mimeType": remote.get("mimeType"),
                "md5Checksum": remote.get("md5Checksum"),
                "size": remote.get("size"),
            }

            if is_update:
                updated += 1
            else:
                downloaded += 1

            changed_any = True

        except Exception as e:
            st.warning(
                f"Não foi possível baixar/atualizar o arquivo {file_name}. "
                f"O painel continuará usando o cache local, se existir. Detalhe: {e}"
            )
            skipped += 1
            continue

    if changed_any:
        save_metadata(metadata)
        clear_dataset_caches()

    return {
        "checked": checked,
        "downloaded": downloaded,
        "updated": updated,
        "skipped": skipped,
    }


# =========================================================
# LEITURA LOCAL / NORMALIZAÇÃO DE DATAFRAME
# =========================================================

@st.cache_data(show_spinner=False)
def list_local_data_files() -> List[Path]:
    """
    Lista apenas arquivos reais de dados.

    Importante:
    - ignora _sync_metadata.json;
    - ignora qualquer arquivo iniciado com "_";
    - evita que arquivos internos de cache apareçam como dataset no painel.
    """
    ensure_data_dir()

    files: List[Path] = []

    for path in DATA_DIR.iterdir():
        if not path.is_file():
            continue

        if path.name == METADATA_FILE.name:
            continue

        if path.name.startswith("_"):
            continue

        if path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)

    return sorted(files, key=lambda p: p.name.lower())


def is_health_food_bank_file(path: Path) -> bool:
    """
    Identifica bancos alimentados pelo sistema de submissão.
    """
    if not path.is_file():
        return False

    if path.name == METADATA_FILE.name:
        return False

    if path.name.startswith("_"):
        return False

    if path.suffix.lower() not in {".csv", ".xlsx", ".xls"}:
        return False

    return path.name.lower().startswith("banco_")


def normalize_column_name(value: Any) -> str:
    """
    Normaliza nome de coluna para comparação.
    """
    import unicodedata

    text = str(value).strip().lower()
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


def normalize_health_food_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    Converte colunas do banco alimentado para o schema esperado pelo dashboard.

    Entrada típica:
    - ubs
    - categoria
    - tipo
    - competencia
    - valor
    - identificados
    - nao_identificados

    Saída esperada:
    - UBS
    - Categoria
    - Tipo
    - Competência
    - Valor
    - Identificados
    - Não identificados
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    rename_by_normalized = {
        "ubs": "UBS",
        "categoria": "Categoria",
        "tipo": "Tipo",
        "competencia": "Competência",
        "valor": "Valor",
        "identificados": "Identificados",
        "identificado": "Identificados",
        "nao_identificados": "Não identificados",
        "nao_identificado": "Não identificados",
    }

    rename_map = {}

    for col in out.columns:
        col_norm = normalize_column_name(col)

        if col_norm in rename_by_normalized:
            rename_map[col] = rename_by_normalized[col_norm]

    out = out.rename(columns=rename_map)

    return out


def read_excel_safely(path: Path) -> pd.DataFrame:
    """
    Lê XLSX/XLS tentando primeiro a aba 'dados'.
    Se a aba não existir, usa a primeira aba disponível.
    """
    try:
        return pd.read_excel(path, sheet_name="dados")
    except ValueError:
        return pd.read_excel(path)


@st.cache_data(show_spinner=False)
def read_dataframe(path_str: str) -> pd.DataFrame:
    path = Path(path_str)
    suffix = path.suffix.lower()

    if suffix == ".csv":
        df = pd.read_csv(path)

    elif suffix in {".xlsx", ".xls"}:
        df = read_excel_safely(path)

    elif suffix == ".parquet":
        df = pd.read_parquet(path)

    elif suffix in {".geojson", ".json"}:
        try:
            import geopandas as gpd

            gdf = gpd.read_file(path)

            if gdf.empty:
                return pd.DataFrame()

            if "geometry" in gdf.columns:
                centroids = gdf.geometry.centroid
                gdf["latitude"] = centroids.y
                gdf["longitude"] = centroids.x

            df = pd.DataFrame(
                gdf.drop(columns=[c for c in ["geometry"] if c in gdf.columns])
            )

        except Exception:
            df = pd.read_json(path)

    else:
        raise ValueError(f"Formato não suportado: {suffix}")

    return normalize_health_food_columns(df)


@st.cache_data(show_spinner=False)
def read_consolidated_health_food_dataframe() -> pd.DataFrame:
    """
    Consolida todos os bancos locais das UBSs em um único DataFrame.

    Lê todos os arquivos:
    - banco_gama.xlsx
    - banco_jardins_mangueral.xlsx
    - banco_santa_maria.xlsx
    - ou qualquer outro banco_*.xlsx/csv/xls
    """
    ensure_data_dir()

    frames: list[pd.DataFrame] = []

    for path in sorted(DATA_DIR.iterdir(), key=lambda p: p.name.lower()):
        if not is_health_food_bank_file(path):
            continue

        try:
            df = read_dataframe(str(path))

            if df is None or df.empty:
                continue

            df = df.copy()
            df["_arquivo_origem"] = path.name

            frames.append(df)

        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    consolidated = pd.concat(frames, ignore_index=True)

    return consolidated


@st.cache_data(show_spinner=False)
def get_datasets_catalog() -> List[dict]:
    """
    Monta o catálogo de datasets.

    Primeiro item:
    - base consolidada com todos os bancos das UBSs.

    Demais itens:
    - arquivos individuais locais.
    """
    catalog: List[dict] = []

    consolidated_df = read_consolidated_health_food_dataframe()

    if not consolidated_df.empty:
        lat_col, lon_col = detect_lat_lon_columns(consolidated_df)

        catalog.append(
            {
                "name": CONSOLIDATED_DATASET_NAME,
                "file_name": CONSOLIDATED_DATASET_FILE_NAME,
                "path": CONSOLIDATED_DATASET_PATH,
                "rows": int(len(consolidated_df)),
                "cols": int(len(consolidated_df.columns)),
                "is_geospatial": bool(lat_col and lon_col),
                "lat_col": lat_col,
                "lon_col": lon_col,
            }
        )

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
    """
    Retorna o dataframe pelo nome do dataset.

    Se for a base consolidada, retorna a união de todos os bancos das UBSs.
    """
    if dataset_name == CONSOLIDATED_DATASET_NAME:
        return read_consolidated_health_food_dataframe()

    catalog = get_datasets_catalog()

    item = next((d for d in catalog if d["name"] == dataset_name), None)

    if not item:
        return pd.DataFrame()

    if item.get("path") == CONSOLIDATED_DATASET_PATH:
        return read_consolidated_health_food_dataframe()

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

    Para a base consolidada, retorna a atualização mais recente entre os bancos.
    """
    metadata = load_metadata()

    if dataset_name == CONSOLIDATED_DATASET_NAME:
        modified_times = []

        for file_name, item in metadata.items():
            if not str(file_name).lower().startswith("banco_"):
                continue

            modified_time = item.get("modifiedTime")

            if modified_time:
                modified_times.append(modified_time)

        if not modified_times:
            return None

        try:
            latest = max(pd.to_datetime(modified_times, utc=True))
            dt = latest.tz_convert("America/Sao_Paulo")
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return str(max(modified_times))

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