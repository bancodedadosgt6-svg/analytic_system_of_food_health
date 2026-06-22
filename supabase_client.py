from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import streamlit as st
from dotenv import load_dotenv


load_dotenv()


# =========================================================
# CONFIGURAÇÕES SUPABASE
# =========================================================

SUPABASE_REGISTROS_TABLE = str(
    os.getenv("SUPABASE_REGISTROS_TABLE", "registros_saude_alimentar")
).strip()

SUPABASE_PAGE_SIZE = int(
    os.getenv("SUPABASE_PAGE_SIZE", "1000")
)

SUPABASE_REGISTROS_COLUMNS = (
    "id,ubs_id,submissao_id,user_id,ubs,categoria,tipo,competencia,"
    "valor,identificados,nao_identificados,arquivo_origem,hash_registro,created_at"
)


def get_secret_or_env(key: str, default: Any = None) -> Any:
    """
    Busca primeiro no Streamlit Secrets e depois no .env.
    """
    try:
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass

    return os.getenv(key, default)


def get_supabase_url() -> str:
    return str(get_secret_or_env("SUPABASE_URL", "") or "").strip()


def get_supabase_anon_key() -> str:
    return str(get_secret_or_env("SUPABASE_ANON_KEY", "") or "").strip()


def get_supabase_service_role_key() -> str:
    """
    Chave opcional para painel analítico interno.

    Use somente no Streamlit Secrets ou .env local.
    Nunca envie para GitHub.
    """
    return str(get_secret_or_env("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()


def get_supabase_key_in_use() -> str:
    """
    Prioridade:
    1. Service role, se configurada.
    2. Anon key, caso contrário.
    """
    service_role = get_supabase_service_role_key()
    anon_key = get_supabase_anon_key()

    if service_role:
        return service_role

    return anon_key


def get_supabase_key_mode() -> str:
    if get_supabase_service_role_key():
        return "service_role"

    if get_supabase_anon_key():
        return "anon"

    return "nenhuma"


def validate_supabase_settings() -> None:
    """
    Valida variáveis necessárias para conexão com Supabase.
    """
    missing: list[str] = []

    if not get_supabase_url():
        missing.append("SUPABASE_URL")

    if not get_supabase_anon_key() and not get_supabase_service_role_key():
        missing.append("SUPABASE_ANON_KEY ou SUPABASE_SERVICE_ROLE_KEY")

    if missing:
        raise RuntimeError(
            "Configuração Supabase incompleta. Variáveis ausentes: "
            + ", ".join(missing)
            + ". Configure no .env local ou no Streamlit Secrets."
        )


# =========================================================
# CLIENTE SUPABASE
# =========================================================

@st.cache_resource(show_spinner=False)
def get_supabase_client():
    """
    Cria o cliente Supabase do painel analítico.

    Para leitura consolidada do painel:
    - se SUPABASE_SERVICE_ROLE_KEY existir, ela será usada;
    - caso contrário, usa SUPABASE_ANON_KEY e depende das policies SELECT.
    """
    validate_supabase_settings()

    from supabase import create_client

    return create_client(
        get_supabase_url(),
        get_supabase_key_in_use(),
    )


def clear_supabase_client_cache() -> None:
    """
    Limpa o cache do cliente Supabase.
    Útil após alterar secrets em ambiente local/deploy.
    """
    try:
        get_supabase_client.clear()
    except Exception:
        pass


# =========================================================
# CONSULTAS
# =========================================================

def fetch_paginated_table_rows(
    table_name: str,
    columns: str = "*",
    order_by: Optional[str] = None,
    desc: bool = False,
    page_size: int = SUPABASE_PAGE_SIZE,
) -> List[Dict[str, Any]]:
    """
    Busca todos os registros de uma tabela Supabase com paginação.

    A paginação evita o limite padrão de 1000 linhas por consulta.
    """
    client = get_supabase_client()

    rows: list[dict] = []
    start = 0

    while True:
        end = start + page_size - 1

        query = (
            client.table(table_name)
            .select(columns)
            .range(start, end)
        )

        if order_by:
            query = query.order(order_by, desc=desc)

        response = query.execute()

        batch = response.data or []
        rows.extend(batch)

        if len(batch) < page_size:
            break

        start += page_size

    return rows


def fetch_registros_saude_alimentar() -> List[Dict[str, Any]]:
    """
    Busca todos os registros da tabela principal do painel:
    public.registros_saude_alimentar.
    """
    return fetch_paginated_table_rows(
        table_name=SUPABASE_REGISTROS_TABLE,
        columns=SUPABASE_REGISTROS_COLUMNS,
        order_by="created_at",
        desc=False,
        page_size=SUPABASE_PAGE_SIZE,
    )


def fetch_active_ubs() -> List[Dict[str, Any]]:
    """
    Busca UBSs ativas, útil para diagnóstico ou filtros futuros.
    """
    client = get_supabase_client()

    response = (
        client.table("ubs")
        .select("id,nome,slug,ativa,created_at")
        .eq("ativa", True)
        .order("nome")
        .execute()
    )

    return response.data or []


def test_supabase_connection() -> Dict[str, Any]:
    """
    Teste leve de conexão com o Supabase sem expor chaves.
    """
    try:
        client = get_supabase_client()

        response = (
            client.table(SUPABASE_REGISTROS_TABLE)
            .select("id", count="exact")
            .limit(1)
            .execute()
        )

        return {
            "success": True,
            "message": "Conexão com Supabase realizada com sucesso.",
            "table": SUPABASE_REGISTROS_TABLE,
            "key_mode": get_supabase_key_mode(),
            "count": getattr(response, "count", None),
        }

    except Exception as e:
        return {
            "success": False,
            "message": str(e),
            "table": SUPABASE_REGISTROS_TABLE,
            "key_mode": get_supabase_key_mode(),
            "count": None,
        }


def get_supabase_environment_status() -> Dict[str, Any]:
    """
    Status do ambiente Supabase sem expor chaves sensíveis.
    """
    return {
        "supabase_url_configurada": bool(get_supabase_url()),
        "supabase_anon_key_configurada": bool(get_supabase_anon_key()),
        "supabase_service_role_configurada": bool(get_supabase_service_role_key()),
        "supabase_key_em_uso": get_supabase_key_mode(),
        "tabela_registros": SUPABASE_REGISTROS_TABLE,
        "page_size": SUPABASE_PAGE_SIZE,
    }