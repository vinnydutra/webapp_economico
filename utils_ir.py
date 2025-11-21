import streamlit as st
from typing import List
from collections import Counter, defaultdict
from typing import Dict, Any, Optional
import pandas as pd

import re

from datetime import datetime, date

import time as _time
import time
import os


from decimal import Decimal, ROUND_HALF_UP

# --- Perf helpers (ligados por variável de ambiente IR_PERF) ---
def _perf_enabled() -> bool:
    try:
        v = str(os.getenv("IR_PERF", "1") or "1").strip().lower()
        return v in {"1", "true", "on", "yes"}
    except Exception:
        return False

def _t_now():
    try:
        return time.perf_counter()
    except Exception:
        return 0.0

def _perf(msg: str):
    try:
        if _perf_enabled():
            print(f"[PERF] {msg}")
    except Exception:
        pass

# --- memoização leve por execução da página (evita recomputos custosos) ---
_CARRY_MEMO = {}

# --- debounce por sessão para evitar reruns em loop (controle fino) ---
def _now_s():
    try:
        return _time.time()
    except Exception:
        return 0.0

def _debounce_key(tag: str, window_s: float = 1.5) -> bool:
    """Retorna True se devemos DEBOUNCE (i.e., pular recomputo) para esta tag.
    Usa st.session_state para memorizar o último instante por tag.
    """
    try:
        store = st.session_state.setdefault("_debounce_ir", {})
        last = float(store.get(tag, 0.0) or 0.0)
        now = _now_s()
        if (now - last) < float(window_s):
            return True
        store[tag] = now
        return False
    except Exception:
        return False

def _get_last_result(tag: str):
    """Lê o último resultado bem-sucedido armazenado na sessão para uma tag."""
    try:
        return st.session_state.get("_ir_last_results", {}).get(tag)
    except Exception:
        return None

def _set_last_result(tag: str, value):
    """Grava/atualiza o último resultado na sessão para uma tag."""
    try:
        store = st.session_state.setdefault("_ir_last_results", {})
        store[tag] = value
    except Exception:
        pass

__all__ = [
    "calcular_status_mes",
    "bump_ir_epoch",
    "ler_snapshot_ativo_mes",
    "carregar_ledger_mensal",
    "is_mes_sujo",
    "marcar_mes_calculado",
]

# Epoch global para invalidação imediata de caches entre páginas de IR
# Use bump_ir_epoch() após qualquer ação que altere base/pagamento/consolidação.

def bump_ir_epoch():
    try:
        st.session_state["ir_epoch"] = st.session_state.get("ir_epoch", 0) + 1
        return st.session_state["ir_epoch"]
    except Exception:
        # fallback silencioso
        return None

# --- Helpers de "sujeira" para UX (forçar botão "Calcular este mês") ---
def _get_epoch_safe() -> int:
    try:
        return int(st.session_state.get("ir_epoch", 0) or 0)
    except Exception:
        return 0


def is_mes_sujo(ano: int, mes: int) -> bool:
    """Retorna True quando houve um bump global de epoch **depois** do último
    cálculo confirmado para essa competência (ano/mes).

    A UI pode usar isso para decidir exibir o botão "Calcular este mês".
    """
    try:
        cur = _get_epoch_safe()
        key = f"epoch_calc_{int(ano)}_{int(mes)}"
        last = int(st.session_state.get(key, -1) or -1)
        return cur > last
    except Exception:
        return True  # conservador: se não der para ler, tratar como sujo


def marcar_mes_calculado(ano: int, mes: int) -> int:
    """Marca que a competência (ano/mes) foi **recalculada** com sucesso sob o
    epoch atual, permitindo que a UI considere o mês "limpo" até novo bump.

    Retorna o epoch gravado.
    """
    try:
        cur = _get_epoch_safe()
        st.session_state[f"epoch_calc_{int(ano)}_{int(mes)}"] = cur
        return cur
    except Exception:
        return 0

# =========================
# Arredondamento consistente para cálculos de IR

def calcular_status_mes(supabase, user_id: str, ano: int, mes: int) -> dict:
    """
    Status consolidado da competência para a UI.

    Lógica mínima (não persiste nada):
      - Apura IR devido pós-compensação por regime (NORMAL/DAYTRADE/FII).
      - Abate IRRF de NORMAL/DAYTRADE (FII não tem IRRF).
      - Soma pagamentos DARF registrados no mês (todas as naturezas).
      - Aplica mínimo DARF para rotular o status:
          * total_considerado < mínimo -> "Abaixo do mínimo"
          * total_considerado >= mínimo e (total_considerado - pagos) > 0 -> "Devido"
          * caso contrário -> "Quitado/sem débito"

    Retorna:
      {"rotulo": str, "valor": float, "minimo_aplicado": bool}
    """
    try:
        _epoch_dep = None
        try:
            _epoch_dep = st.session_state.get("ir_epoch", 0)
        except Exception:
            _epoch_dep = None
        bases_pos = apurar_compensacao_mes(supabase, user_id, ano, mes, __dep_epoch=_epoch_dep)  # já contém ir_devido por regime pós-comp.
    except Exception:
        bases_pos = {"NORMAL": {}, "DAYTRADE": {}, "FII": {}}

    # IRRF por regime (tolerante a falhas)
    irrf_norm = irrf_dt = 0.0
    try:
        regs_irrf = agregar_irrf_mes_por_regime(supabase, user_id, ano, mes, modo="abertura_total")
        irrf_norm = float(regs_irrf.get("NORMAL", 0.0) or 0.0)
        irrf_dt = float(regs_irrf.get("DAYTRADE", 0.0) or 0.0)
    except Exception:
        pass

    ir_n = float((bases_pos.get("NORMAL") or {}).get("ir_devido", 0.0) or 0.0)
    ir_d = float((bases_pos.get("DAYTRADE") or {}).get("ir_devido", 0.0) or 0.0)
    ir_f = float((bases_pos.get("FII") or {}).get("ir_devido", 0.0) or 0.0)

    # Abate IRRF de N/D; FII não tem IRRF
    total_considerado = max(ir_n - irrf_norm, 0.0) + max(ir_d - irrf_dt, 0.0) + max(ir_f, 0.0)

    # Pagamentos (todas as naturezas)
    pagos = 0.0
    try:
        pagos += sum_pagamentos_darf(supabase, user_id, ano, mes, "comum", __dep_epoch=_epoch_dep) or 0.0
        pagos += sum_pagamentos_darf(supabase, user_id, ano, mes, "daytrade", __dep_epoch=_epoch_dep) or 0.0
        pagos += sum_pagamentos_darf(supabase, user_id, ano, mes, "fii", __dep_epoch=_epoch_dep) or 0.0
    except Exception:
        pass

    # Mínimo DARF
    try:
        minimo = float(get_param(supabase, "LIMIAR_MINIMO_DARF", ano, mes, default=MINIMO_DARF) or MINIMO_DARF)
    except Exception:
        minimo = MINIMO_DARF

    sujo_flag = is_mes_sujo(ano, mes)

    # Classificação
    if total_considerado <= 0.0:
        return {"rotulo": "Quitado/sem débito", "valor": 0.0, "minimo_aplicado": False, "sujo": sujo_flag}

    if total_considerado < minimo:
        # abaixo do mínimo: nada a pagar; carrega adiante
        return {"rotulo": "Abaixo do mínimo", "valor": 0.0, "minimo_aplicado": True, "sujo": sujo_flag}

    devido = max(total_considerado - pagos, 0.0)
    if devido > 0.0:
        return {"rotulo": "Devido", "valor": round(devido, 2), "minimo_aplicado": False, "sujo": sujo_flag}
    else:
        return {"rotulo": "Quitado/sem débito", "valor": 0.0, "minimo_aplicado": False, "sujo": sujo_flag}

def _br_round(x) -> Decimal:
    """Arredondamento consistente em 2 casas decimais para cálculos de IR."""
    try:
        return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return Decimal("0.00")

# =========================
# ALLOWLIST de ETFs (núcleo do ticker, sem sufixo "11")
# Mantida aqui por ora; idealmente migrar para metadados no banco.
# Regras:
#   - Se o ticker termina com "11", removemos o "11" para obter o "core".
#   - Se core ∈ ALLOWLIST_ETFS -> classifica como ETF.
#   - Senão, se termina com "11" -> assume FII (por padrão).
#   - BDRs são detectados pelos sufixos numéricos (31,32,33,34,35,36,39).
#   - Ações são o fallback.
# Observação: lista extensa mas não exaustiva; pode ser ampliada sem quebrar consumidores.
ALLOWLIST_ETFS: set[str] = {
    # iShares / BlackRock (exemplos mais comuns)
    "BOVA","BOVV","SMAL","IVVB","BRAX","ISUS","ECOO","TECB","IMAT","UTIL","INDX",
    # SP500 / índices internacionais / setoriais
    "SPXI","SPXB","ACWI","EMEG","USTK","DRIV","URA",
    # Ouro / commodities / câmbio
    "GOLD","QGOLD","DOL","USDB","USDU","WDOC",
    # BB / It Now / Trend / outros gestores recorrentes
    "BBOV","BBSD","BBFI","FIND","DIVO","MATB","GOVE","COWC","B5P2","B5MB","B5SD","B5DR",
    # Hashdex / cripto
    "HASH","ETHE","BITH","DEFI","WEB3","NFTS",
    # XP / Mirae / outros (exemplos)
    "XINA","XFIX","GURU","MOSI","ESGD","ESGU","ESGE","CLMA",
    # Diversos conhecidos (pode conter sobreposição)
    "IVVC","IVOG","IVOM","SPXV","SMLL","SMAC","BOVA","BOVX",
}

# Lista explícita de "units 11" que **não** são FIIs (exceções à heurística do sufixo '11')
# Observação: manter os núcleos sem sufixo de mercado (sem '.SA')
NON_FII_UNITS_11: set[str] = {
    "KLBN11",  # Klabin (Unit)
    "TAEE11",  # Taesa (Unit)
    "SANB11",  # Santander (Unit)
    "SULA11",  # SulAmérica (Unit)
    "ALUP11",  # Alupar (Unit)
    "BPAC11",  # BTG Pactual (Unit)
}
def _ticker_core_no_market(t: str) -> str:
    """Remove sufixos de mercado (ex.: '.SA') e espaços; retorna em maiúsculas."""
    core = re.sub(r"\.[A-Z0-9]+$", "", str(t).strip().upper())
    return core

def _core_sem_11(core: str) -> str:
    """Remove sufixo '11' do core (se existir)."""
    return re.sub(r"11$", "", core)

def is_etf_core(core: str) -> bool:
    """
    Determina se o core (sem '11') está na allowlist de ETFs.
    """
    base = _core_sem_11(core)
    return base in ALLOWLIST_ETFS

# =========================
# Helpers públicos de classificação por ticker (para uso pela UI)
# =========================
def is_bdr_ticker(ticker: Optional[str]) -> bool:
    """
    Retorna True se o ticker aparenta ser BDR, com base em sufixos 31/32/33/34/35/36/39.
    Aceita tickers com sufixos de mercado (ex.: '.SA').
    """
    if not ticker:
        return False
    core = _ticker_core_no_market(str(ticker))
    return re.search(r"(31|32|33|34|35|36|39)$", core) is not None

def is_etf_ticker(ticker: Optional[str]) -> bool:
    """
    Retorna True se o ticker aparenta ser ETF.
    Regra:
      - Se termina com '11', checa se o núcleo (sem '11') está na ALLOWLIST_ETFS.
      - Também aceita o caso em que o núcleo já está na allowlist (fallback).
    """
    if not ticker:
        return False
    core = _ticker_core_no_market(str(ticker))
    if re.search(r"11$", core):
        return is_etf_core(core)
    # fallback: alguns aliases podem não ter '11' explicitamente
    base = _core_sem_11(core)
    return base in ALLOWLIST_ETFS

def is_fii_ticker(ticker: Optional[str]) -> bool:
    """
    Retorna True se o ticker aparenta ser FII.
    Regra:
      - Termina com '11' E NÃO está na allowlist de ETFs.
    """
    if not ticker:
        return False
    core = _ticker_core_no_market(str(ticker))
    # Exceção: units que terminam em '11' mas **não** são FIIs
    if core in NON_FII_UNITS_11:
        return False
    # FII somente se termina com '11' e **não** é ETF
    if not re.search(r"11$", core):
        return False
    return not is_etf_core(core)

def classificar_ticker(ticker: Optional[str]) -> str:
    """
    Classifica o ticker em: 'FII' | 'ETF' | 'BDR' | 'ACOES' | 'DESCONHECIDO'.
    Preferir esta função em novas chamadas na UI.
    """
    if not ticker:
        return "DESCONHECIDO"
    if is_bdr_ticker(ticker):
        return "BDR"
    if is_etf_ticker(ticker):
        return "ETF"
    if is_fii_ticker(ticker):
        return "FII"
    # se não for nenhum dos acima e não terminar com '11', assume ações
    return "ACOES"

# ================
# Cache leve (TTL)
# ================

# ===== Feature flag: cache interno leve (competitivo com Streamlit)
# Desative por padrão para evitar conflito com @st.cache_data na camada de página.
# Pode ser reativado via variável de ambiente UTILS_IR_INTERNAL_CACHE ∈ {1,true,on,yes}.
USE_INTERNAL_CACHE = True
def _internal_cache_enabled() -> bool:
    try:
        if USE_INTERNAL_CACHE:
            return True
        v = str(os.getenv("UTILS_IR_INTERNAL_CACHE", "0") or "0").strip().lower()
        return v in {"1", "true", "on", "yes"}
    except Exception:
        return False


_CACHE_TTL = 60.0  # segundos
_CACHE = {
    "contar_ops": {},
    "ops_mes": {},
    "resumo_mes": {},
    "isencao_mes": {},
    "base_regime_mes": {},
    "comp_mes": {},
    "listar_darf": {},
    "sum_darf": {},
    "snapshot_mes": {},
    "diag_mes": {},
    "params": {},
    "ops_ano": {},
}

# --- Memo rápido e sempre ligado para parametros_fiscais (independente do USE_INTERNAL_CACHE)
_PARAMS_MEMO: dict[tuple[str, str], tuple[float, Any]] = {}
_PARAMS_TTL: float = 180.0  # segundos

def _params_memo_get(ck: tuple[str, str]):
    try:
        ts, val = _PARAMS_MEMO.get(ck, (0.0, None))
        if (_time.time() - float(ts)) <= _PARAMS_TTL:
            return val
        # expirou
        _PARAMS_MEMO.pop(ck, None)
    except Exception:
        pass
    return None


def _params_memo_set(ck: tuple[str, str], value: Any):
    try:
        _PARAMS_MEMO[ck] = (_time.time(), value)
    except Exception:
        pass

def _ck_user(user_id: str) -> tuple:
    return (user_id,)

def _ck_user_month(user_id: str, ano: int, mes: int) -> tuple:
    return (user_id, int(ano), int(mes))

def _ck_user_month_tipo(user_id: str, ano: int, mes: int, tipo: str) -> tuple:
    return (user_id, int(ano), int(mes), str(tipo))

def _cache_get(bucket: str, key: tuple, ttl: float = _CACHE_TTL):
    """
    Lê do cache leve, ou retorna None se o cache estiver desativado (feature flag).
    """
    if not _internal_cache_enabled():
        # No-op: cache desativado por flag.
        return None
    entry = _CACHE.get(bucket, {}).get(key)
    if not entry:
        return None
    ts, value = entry
    if (_time.time() - ts) <= ttl:
        return value
    # expirou
    try:
        del _CACHE[bucket][key]
    except Exception:
        pass
    return None

def _cache_set(bucket: str, key: tuple, value):
    """
    Salva no cache leve, ou faz nada se o cache estiver desativado (feature flag).
    """
    if not _internal_cache_enabled():
        # No-op: cache desativado por flag.
        return
    _CACHE[bucket][key] = (_time.time(), value)


def _cache_invalidate(bucket: str, key: tuple):
    """
    Invalida entrada do cache leve, ou faz nada se o cache estiver desativado (feature flag).
    """
    if not _internal_cache_enabled():
        # No-op: cache desativado por flag.
        return
    try:
        _CACHE[bucket].pop(key, None)
    except Exception:
        pass


# -------------------------
# Cache anual de linhas brutas (reduz I/O entre chamadas no mesmo run)
def _get_rows_vista_ano(_supabase, user_id: str, ano: int) -> list[dict]:
    try:
        _epoch = int(st.session_state.get("ir_epoch", 0) or 0)
    except Exception:
        _epoch = 0
    key = ("vista", str(user_id), int(ano), _epoch)
    bucket = _CACHE.get("ops_ano")
    if _internal_cache_enabled() and isinstance(bucket, dict) and key in bucket:
        return bucket[key]
    try:
        inicio = f"{int(ano)}-01-01"
        fim = f"{int(ano) + 1}-01-01"
        t0 = time.perf_counter()
        resp = (
            _supabase.table("ativos_vendidos")
            .select("data_compra,data_venda,ticker,quantidade,preco_compra,preco_venda,custo_operacional,irrf")
            .eq("user_id", user_id)
            .gte("data_venda", inicio)
            .lt("data_venda", fim)
            .execute()
        )
        t1 = time.perf_counter()
        print(f"[PERF] _get_rows_vista_ano: {(t1 - t0):.3f}s para executar query Supabase")
        rows = getattr(resp, "data", []) or []
    except Exception:
        rows = []
    # Fallback: se a query por intervalo vier vazia (pode acontecer se data_venda estiver como texto),
    # busca todas as linhas do usuário e filtra na camada Python.
    if not rows:
        try:
            resp2 = (
                _supabase.table("ativos_vendidos")
                .select("data_compra,data_venda,ticker,quantidade,preco_compra,preco_venda,custo_operacional,irrf")
                .eq("user_id", user_id)
                .execute()
            )
            rows = getattr(resp2, "data", []) or []
        except Exception:
            rows = []
    # memo anual em memória de processo
    if _internal_cache_enabled() and isinstance(bucket, dict):
        bucket[key] = rows
    return rows

def _get_rows_opcoes_operacoes_ano(_supabase, user_id: str, ano: int) -> list[dict]:
    try:
        _epoch = int(st.session_state.get("ir_epoch", 0) or 0)
    except Exception:
        _epoch = 0
    key = ("op_oper", str(user_id), int(ano), _epoch)
    bucket = _CACHE.get("ops_ano")
    if _internal_cache_enabled() and isinstance(bucket, dict) and key in bucket:
        return bucket[key]
    try:
        inicio = f"{int(ano)}-01-01"
        fim = f"{int(ano) + 1}-01-01"
        # Busca operações finalizadas no ano OU, quando não houver encerramento, as que foram abertas no ano
        t0 = time.perf_counter()
        resp = (
            _supabase.table("opcoes_operacoes")
            .select("data_operacao,data_encerramento,ticker,quantidade,preco_inicial,preco_final,custo,tipo_operacao_inicial,irrf")
            .eq("user_id", user_id)
            .or_(
                f"and(data_encerramento.gte.{inicio},data_encerramento.lt.{fim}),"
                f"and(data_encerramento.is.null,data_operacao.gte.{inicio},data_operacao.lt.{fim})"
            )
            .execute()
        )
        t1 = time.perf_counter()
        print(f"[PERF] _get_rows_opcoes_operacoes_ano: {(t1 - t0):.3f}s para executar query Supabase")
        rows = getattr(resp, "data", []) or []
    except Exception:
        rows = []
    if _internal_cache_enabled() and isinstance(bucket, dict):
        bucket[key] = rows
    return rows

def _get_rows_opcoes_carteira_ano(_supabase, user_id: str, ano: int) -> list[dict]:
    try:
        _epoch = int(st.session_state.get("ir_epoch", 0) or 0)
    except Exception:
        _epoch = 0
    key = ("op_cart", str(user_id), int(ano), _epoch)
    bucket = _CACHE.get("ops_ano")
    if _internal_cache_enabled() and isinstance(bucket, dict) and key in bucket:
        return bucket[key]
    try:
        inicio = f"{int(ano)}-01-01"
        fim = f"{int(ano) + 1}-01-01"
        t0 = time.perf_counter()
        resp = (
            _supabase.table("opcoes_carteira")
            .select("data_operacao,tipo_operacao_inicial,irrf_abertura_total,irrf_abertura_pendente")
            .eq("user_id", user_id)
            .gte("data_operacao", inicio)
            .lt("data_operacao", fim)
            .execute()
        )
        t1 = time.perf_counter()
        print(f"[PERF] _get_rows_opcoes_carteira_ano: {(t1 - t0):.3f}s para executar query Supabase")
        rows = getattr(resp, "data", []) or []
    except Exception:
        rows = []
    if _internal_cache_enabled() and isinstance(bucket, dict):
        bucket[key] = rows
    return rows


# -------------------------
# Invalida o cache leve de parâmetros fiscais ("params") deste módulo.
def invalidate_params_cache(ano: Optional[int] = None, mes: Optional[int] = None) -> int:
    """
    Invalida o cache leve de PARÂMETROS FISCAIS deste módulo.

    Uso:
      - invalidate_params_cache()              -> limpa TODO o bucket "params".
      - invalidate_params_cache(2026, 2)      -> remove entradas SOMENTE da competência 2026-02-01.

    Retorna o número de entradas removidas (inteiro).
    """
    try:
        bucket = _CACHE.get("params")
        # Função também limpa o memo sempre-ligado (_PARAMS_MEMO)
        def _clear_params_memo_all():
            try:
                _PARAMS_MEMO.clear()
            except Exception:
                pass

        def _clear_params_memo_for(comp_iso: str):
            try:
                to_del = [k for k in list(_PARAMS_MEMO.keys()) if isinstance(k, tuple) and len(k) == 2 and k[1] == comp_iso]
                for k in to_del:
                    _PARAMS_MEMO.pop(k, None)
            except Exception:
                pass

        if ano is None or mes is None:
            # Limpa TUDO
            n = 0
            if isinstance(bucket, dict) and bucket:
                n = len(bucket)
                bucket.clear()
            _clear_params_memo_all()
            return n

        # Remove apenas a competência informada
        comp_iso = _competencia_date(int(ano), int(mes)).isoformat()
        removed = 0
        if isinstance(bucket, dict) and bucket:
            to_remove = [ck for ck in list(bucket.keys()) if isinstance(ck, tuple) and len(ck) == 2 and ck[1] == comp_iso]
            for ck in to_remove:
                bucket.pop(ck, None)
            removed = len(to_remove)
        _clear_params_memo_for(comp_iso)
        return removed
    except Exception:
        return 0

# -------------------------
# Feature flag: regras versionadas por vigência
# Controlada por variável de ambiente IRS_RULES_VERSIONED ∈ {"1","true","on","yes"}
# -------------------------
def _flag_rules_versioned() -> bool:
    try:
        v = str(os.getenv("IRS_RULES_VERSIONED", "0") or "0").strip().lower()
        return v in {"1", "true", "on", "yes"}
    except Exception:
        return False

def _competencia_date(ano: Optional[int], mes: Optional[int]):
    """Retorna um datetime.date representando o 1º dia da competência indicada.
    Se não informado, retorna a data de hoje."""
    try:
        if ano and mes:
            return date(int(ano), int(mes), 1)
    except Exception:
        pass
    return date.today()

# Helper: retorna início e fim (exclusivo) do mês da competência (YYYY-MM-01, 1º dia do mês seguinte)
def _month_bounds(ano: int, mes: int) -> tuple[str, str]:
    """
    Retorna (inicio_iso, fim_iso_exclusivo) da competência:
      inicio = YYYY-MM-01
      fim    = primeiro dia do mês seguinte (exclusivo)
    """
    a = int(ano); m = int(mes)
    if m == 12:
        a2, m2 = a + 1, 1
    else:
        a2, m2 = a, m + 1
    inicio = date(a, m, 1).strftime("%Y-%m-%d")
    fim = date(a2, m2, 1).strftime("%Y-%m-%d")
    return inicio, fim

def _parse_date_any(s):
    """Retorna datetime.date a partir de quase qualquer string de data.
    Suporta: objetos date/datetime, ISO com 'T' e timezone (Z/+00:00),
    strings com milissegundos, e formatos BR (dd/mm/yyyy). Também extrai
    a primeira ocorrência de YYYY-MM-DD dentro de strings mais longas.
    """
    if s is None:
        return None
    # Se já for date/datetime, retorna normalizado para date
    if isinstance(s, date):
        return s
    if isinstance(s, datetime):
        return s.date()
    # Normaliza para string
    s = str(s).strip()
    if not s:
        return None
    # 0) Extrai padrão YYYY-MM-DD se presente em string maior (ex.: '2024-12-09T00:00:00Z')
    try:
        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
        if m:
            return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except Exception:
        pass
    # 1) ISO completo com hora/fuso (remove 'Z', milissegundos e offset textual)
    try:
        s_iso = s.replace("T", " ").replace("Z", "").split("+")[0].split(".")[0]
        return datetime.fromisoformat(s_iso).date()
    except Exception:
        pass
    # 2) Formatos comuns (ordem ampla)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def _to_date(x):
    """Wrapper: tenta converter usando _parse_date_any."""
    return _parse_date_any(x)

# ==============================
# Parâmetros fiscais versionados
# ==============================
def get_param(
    supabase,
    chave: str,
    ano: Optional[int] = None,
    mes: Optional[int] = None,
    default: Optional[float | bool | str] = None,
):
    """
    Lê o parâmetro fiscal para a competência (ano, mes) **priorizando o BANCO**
    (vigência: efetivo_de <= competência <= efetivo_ate). Se não houver linha ou
    ocorrer erro, cai no *fallback* (default ou constantes do módulo).

    Comportamento:
      1) Sempre tenta Supabase primeiro, com cache leve por (chave, competência).
      2) Se achar, normaliza para float/bool quando aplicável e retorna.
      3) Se não achar/der erro, retorna `default` (se fornecido) ou as constantes.
    """
    # 1) Chave e competência normalizadas
    k_req = (str(chave) or "").strip()
    k_upper = k_req.upper()
    comp_dt = _competencia_date(ano, mes)
    ck = (k_req.lower(), comp_dt.isoformat())

    # 2) Memo sempre-ligado (rápido; TTL curto)
    memoed = _params_memo_get(ck)
    if memoed is not None:
        return memoed

    # 3) Cache leve
    cached = _cache_get("params", ck)
    if cached is not None:
        return cached

    # 4) Tenta buscar no banco pela vigência
    try:
        q = (
            supabase.table("parametros_fiscais")
            .select("chave,valor,efetivo_de,efetivo_ate")
            .eq("chave", k_req)
            .lte("efetivo_de", comp_dt.isoformat())
            .gte("efetivo_ate", comp_dt.isoformat())
            .order("efetivo_de", desc=True)
            .limit(1)
            .execute()
        )
        rows = getattr(q, "data", []) or []
        if rows:
            raw = rows[0].get("valor")
            s = str(raw).strip() if raw is not None else ""
            # normaliza bool/float quando fizer sentido
            if s.lower() in {"true", "false"}:
                val = (s.lower() == "true")
            else:
                try:
                    val = float(s.replace(",", ".")) if s != "" else default
                except Exception:
                    val = raw
            _cache_set("params", ck, val)
            _params_memo_set(ck, val)
            return val
    except Exception:
        # silencioso: cai para fallback
        pass

    # 5) Fallback: default ou constantes canônicas
    if default is not None:
        _cache_set("params", ck, default)
        _params_memo_set(ck, default)
        return default

    if k_upper == "ALIQUOTA_NORMAL":
        val = ALIQUOTA_NORMAL
        _params_memo_set(ck, val)
        return val
    if k_upper == "ALIQUOTA_DAYTRADE":
        val = ALIQUOTA_DAYTRADE
        _params_memo_set(ck, val)
        return val
    if k_upper == "ALIQUOTA_FII":
        val = ALIQUOTA_FII
        _params_memo_set(ck, val)
        return val
    if k_upper == "LIMITE_ISENCAO_ACOES":
        val = LIMITE_ISENCAO_ACOES
        _params_memo_set(ck, val)
        return val
    if k_upper in {"LIMIAR_MINIMO_DARF", "MINIMO_DARF"}:
        val = MINIMO_DARF
        _params_memo_set(ck, val)
        return val

    return default

# [R2D2][UtilsIR][HELPERS] =============================

def normalize_val(v) -> float:
    """
    Normaliza valores vindos do banco ou do usuário para float seguro.
    Aceita float, int, str (com vírgula ou ponto decimal) e None.
    Retorna 0.0 em caso de erro.
    """
    if v is None:
        return 0.0
    try:
        if isinstance(v, str):
            return float(v.replace(",", ".").strip())
        return float(v)
    except Exception:
        return 0.0

@st.cache_data(ttl=600, show_spinner=False, persist=True)
def carregar_operacoes_do_mes(_supabase, user_id: str, ano: int, mes: int, __dep_epoch: Optional[int] = None):
    _ = __dep_epoch  # dependency for Streamlit cache invalidation
    ck = _ck_user_month(user_id, ano, mes)
    cached = _cache_get("ops_mes", ck)
    if cached is not None:
        return cached.copy()
    inicio_iso, fim_iso = _month_bounds(ano, mes)
    """
    Carrega operações ENCERRADAS do mês especificado (ano, mes) do usuário,
    vindas de:
      - ativos_vendidos (mercado À vista)
      - opcoes_operacoes (encerradas)
    Retorna DataFrame com colunas (nesta ordem):
      ["data","mercado","ticker","tipo","quantidade","preco_inicial","preco_final","lucro_rs","lucro_pct","custo"]
    Observações:
      - A coluna 'custo' é carregada no backend e incluída aqui, já subtraída de 'lucro_rs'.
      - A coluna 'operacao' foi removida conforme solicitado.
    """
    _t0_total = _t_now()
    rows = []

    # --------------------------
    # À VISTA (ativos_vendidos) — usa cache anual
    # --------------------------
    _t0_vista = _t_now()
    _count_vista_ini = 0
    av_rows: List[dict] = _get_rows_vista_ano(_supabase, user_id, ano)
    _count_vista_ini = len(rows)
    for r in av_rows:
        d = _parse_date_any(r.get("data_venda"))
        data_compra = _parse_date_any(r.get("data_compra"))
        # Filtra pela competência somente após normalizar.
        if not d or d.year != int(ano) or d.month != int(mes):
            continue

        qtd = r.get("quantidade") or 0
        pi = r.get("preco_compra") or 0.0
        pf = r.get("preco_venda") or 0.0

        lucro_rs = (pf - pi) * qtd
        custo = r.get("custo_operacional") or 0.0
        lucro_rs = lucro_rs - custo
        lucro_pct = ((pf / pi - 1) * 100) if (pi and pi != 0) else 0.0

        tipo = "Day Trade" if (data_compra and d and data_compra == d) else "Comum"

        rows.append({
            "data": d,
            "mercado": "À vista",
            "ticker": r.get("ticker"),
            "tipo": tipo,
            "quantidade": qtd,
            "preco_inicial": pi,
            "preco_final": pf,
            "lucro_rs": lucro_rs,
            "lucro_pct": lucro_pct,
            "custo": custo,
        })
    _qtd_vista = len(rows) - _count_vista_ini
    _perf(f"carregar_operacoes_do_mes.vista_loop: {_t_now() - _t0_vista:.3f}s, ops_vista={_qtd_vista}")

    # --------------------------
    # OPÇÕES (opcoes_operacoes) — usa cache anual
    # Critério: competência = data_encerramento se houver; senão data_operacao
    # --------------------------
    _t0_op = _t_now()
    _count_op_ini = len(rows)
    op_rows_all: List[dict] = _get_rows_opcoes_operacoes_ano(_supabase, user_id, ano)
    for r in op_rows_all:
        data_operacao = _to_date(r.get("data_operacao"))
        data_encerramento = _to_date(r.get("data_encerramento"))
        competencia = data_encerramento if data_encerramento else data_operacao
        if not competencia or competencia.year != int(ano) or competencia.month != int(mes):
            continue

        qtd = r.get("quantidade") or 0
        pi = r.get("preco_inicial") or 0.0
        pf = r.get("preco_final") if r.get("preco_final") is not None else pi
        lado_inicial = (r.get("tipo_operacao_inicial") or "").strip().lower()

        # PnL depende do lado inicial:
        # Compra: lucro = (pf - pi) * q
        # Venda:  lucro = (pi - pf) * q
        if lado_inicial == "venda":
            lucro_rs = (pi - pf) * qtd
        else:
            lucro_rs = (pf - pi) * qtd

        custo = r.get("custo") or 0.0
        lucro_rs = lucro_rs - custo

        lucro_pct = ((pf / pi - 1) * 100) if (pi and pi != 0) else 0.0

        tipo = "Day Trade" if (data_encerramento and data_operacao and data_encerramento == data_operacao) else "Comum"

        rows.append({
            "data": competencia,
            "mercado": "Opções",
            "ticker": r.get("ticker"),
            "tipo": tipo,
            "quantidade": qtd,
            "preco_inicial": pi,
            "preco_final": pf,
            "lucro_rs": lucro_rs,
            "lucro_pct": lucro_pct,
            "custo": custo,
        })
    _qtd_op = len(rows) - _count_op_ini
    _perf(f"carregar_operacoes_do_mes.opcoes_loop: {_t_now() - _t0_op:.3f}s, ops_opcoes={_qtd_op}")

    df = pd.DataFrame(
        rows,
        columns=["data","mercado","ticker","tipo","quantidade","preco_inicial","preco_final","lucro_rs","lucro_pct","custo"]
    )
    _perf(f"carregar_operacoes_do_mes.df_build: {_t_now() - _t0_total:.3f}s, total_ops={len(rows)}")
    _cache_set("ops_mes", ck, df)
    _perf(f"carregar_operacoes_do_mes.TOTAL: {_t_now() - _t0_total:.3f}s")
    return df.copy()


# [IRRF-IR-01A]
@st.cache_data(ttl=600, show_spinner=False, persist=True)
def somar_irrf_vista_mes(_supabase, user_id: str, ano: int, mes: int) -> dict:
    """
    [IRRF-IR-01A]
    Soma o IRRF do mês para operações À VISTA (tabela `ativos_vendidos`),
    separado por regime:
      - "NORMAL": swing trade (data_compra != data_venda)
      - "DAYTRADE": day trade (data_compra == data_venda)

    Competência: mês/ano de `data_venda`.
    Campo considerado: `irrf` (numeric no banco; tolerante a None/str).

    Retorna um dicionário:
      {"NORMAL": float, "DAYTRADE": float}
    """
    total = {"NORMAL": 0.0, "DAYTRADE": 0.0}
    inicio_iso, fim_iso = _month_bounds(ano, mes)
    try:
        rows = _get_rows_vista_ano(_supabase, user_id, ano)
    except Exception:
        rows = []

    for r in rows:
        d_venda = _to_date(r.get("data_venda"))
        # Filtra pela competência desejada após normalização da data
        if not d_venda or d_venda.year != int(ano) or d_venda.month != int(mes):
            continue
        d_compra = _to_date(r.get("data_compra"))
        regime = "DAYTRADE" if (d_compra and d_venda and d_compra == d_venda) else "NORMAL"
        try:
            v = r.get("irrf", 0)  # pode vir None/str
            v = float(str(v).replace(",", ".")) if v is not None else 0.0
        except Exception:
            v = 0.0
        total[regime] += float(v)

    # Arredonda leve para evitar ruído de ponto flutuante em exibição
    total["NORMAL"] = round(total["NORMAL"], 2)
    total["DAYTRADE"] = round(total["DAYTRADE"], 2)
    return total



# [IRRF-IR-01B]
@st.cache_data(ttl=600, show_spinner=False, persist=True)
def somar_irrf_opcoes_finalizadas_mes(
    _supabase,
    user_id: str,
    ano: int,
    mes: int,
    modo: str = "abertura_total",
) -> dict:
    """
    [IRRF-IR-01B]
    Soma o IRRF do mês para operações de OPÇÕES **finalizadas** (tabela `opcoes_operacoes`),
    separado por regime:
      - "NORMAL": swing
      - "DAYTRADE": day trade (encerramento no mesmo dia da abertura)

    Competência: `data_encerramento` se existir; caso contrário `data_operacao`.

    Regra para evitar **dupla contagem** com `opcoes_carteira` quando o modo é
    "abertura_total":
      - Nesse modo, **ignoramos** operações cujo `tipo_operacao_inicial == 'venda'`,
        pois o IRRF da venda é agregado a partir de `opcoes_carteira`.
      - No modo "alocado", **consideramos todas** (compra e venda), pois o IRRF será
        contabilizado inteiramente via finalizações.

    Retorna um dicionário:
      {"NORMAL": float, "DAYTRADE": float}
    """
    total = {"NORMAL": 0.0, "DAYTRADE": 0.0}
    inicio_iso, fim_iso = _month_bounds(ano, mes)
    try:
        rows = _get_rows_opcoes_operacoes_ano(_supabase, user_id, ano)
    except Exception:
        rows = []

    modo = (modo or "abertura_total").strip().lower()

    for r in rows:
        data_op = _to_date(r.get("data_operacao"))
        data_fin = _to_date(r.get("data_encerramento"))
        competencia = data_fin if data_fin else data_op
        if not competencia or competencia.year != int(ano) or competencia.month != int(mes):
            continue

        lado_inicial = str(r.get("tipo_operacao_inicial") or "").strip().lower()
        if modo == "abertura_total" and lado_inicial == "venda":
            # Evita dupla contagem: IRRF de vendas será contabilizado via opcoes_carteira.
            continue

        # Regime
        regime = "DAYTRADE" if (data_fin and data_op and data_fin == data_op) else "NORMAL"

        # Valor IRRF
        try:
            v = r.get("irrf", 0)
            v = float(str(v).replace(",", ".")) if v is not None else 0.0
        except Exception:
            v = 0.0

        total[regime] += float(v)

    total["NORMAL"] = round(total["NORMAL"], 2)
    total["DAYTRADE"] = round(total["DAYTRADE"], 2)
    return total


# [IRRF-IR-01C]
@st.cache_data(ttl=600, show_spinner=False, persist=True)
def somar_irrf_opcoes_abertura_mes(
    _supabase,
    user_id: str,
    ano: int,
    mes: int,
    modo: str = "abertura_total",
) -> dict:
    """
    [IRRF-IR-01C]
    Soma o IRRF relacionado à **abertura** de operações de OPÇÕES (tabela `opcoes_carteira`),
    para a competência do mês/ano informados (usa `data_operacao`).

    Regras:
      - Considera **apenas posições cuja abertura foi 'venda'** (`tipo_operacao_inicial == 'venda'`).
      - `modo`:
          * "abertura_total" -> soma `irrf_abertura_total` (crédito integral já na abertura).
          * "alocado"        -> soma `irrf_abertura_total - irrf_abertura_pendente` (apenas o já alocado).
      - Regime: **NORMAL** (a classificação de day trade é tratada nas finalizações, quando aplicável).

    Retorna um dicionário:
      {"NORMAL": float, "DAYTRADE": 0.0}
    """
    total_normal = 0.0

    inicio_iso, fim_iso = _month_bounds(ano, mes)
    try:
        rows = _get_rows_opcoes_carteira_ano(_supabase, user_id, ano)
    except Exception:
        rows = []

    modo = (modo or "abertura_total").strip().lower()

    for r in rows:
        data_op = _to_date(r.get("data_operacao"))
        if not data_op or data_op.year != int(ano) or data_op.month != int(mes):
            continue

        lado_inicial = str(r.get("tipo_operacao_inicial") or "").strip().lower()
        if lado_inicial != "venda":
            # Somente vendas na abertura geram IRRF a considerar aqui
            continue

        irrf_total = normalize_val(r.get("irrf_abertura_total"))
        irrf_pendente = normalize_val(r.get("irrf_abertura_pendente"))

        if modo == "alocado":
            v = max(irrf_total - irrf_pendente, 0.0)
        else:  # "abertura_total"
            v = irrf_total

        total_normal += float(v)

    return {"NORMAL": round(total_normal, 2), "DAYTRADE": 0.0}


# [IRRF-IR-01D]
@st.cache_data(ttl=600, show_spinner=False, persist=True)
def agregar_irrf_mes_por_regime(
    _supabase,
    user_id: str,
    ano: int,
    mes: int,
    modo: str = "abertura_total",
) -> dict:
    """
    [IRRF-IR-01D]
    Agrega o IRRF do mês por regime, somando as três fontes:
      1) À vista (ativos_vendidos)
      2) Opções finalizadas (opcoes_operacoes)
      3) Opções abertura (opcoes_carteira)

    O parâmetro `modo` controla a interação entre (2) e (3):
      - "abertura_total" -> evita dupla contagem ignorando, nas finalizadas, os
        lançamentos cuja abertura foi VENDA (o IRRF vem de `opcoes_carteira`).
      - "alocado"        -> ignora `opcoes_carteira` e usa apenas o que já foi
        alocado nas finalizações (compra e venda) em `opcoes_operacoes`.

    Retorna:
      {"NORMAL": float, "DAYTRADE": float, "TOTAL": float}
    """
    modo_norm = (modo or "abertura_total").strip().lower()

    vista = somar_irrf_vista_mes(_supabase, user_id, ano, mes)
    if modo_norm == "alocado":
        ops_fin = somar_irrf_opcoes_finalizadas_mes(_supabase, user_id, ano, mes, modo="alocado")
        ops_ab = {"NORMAL": 0.0, "DAYTRADE": 0.0}
    else:
        ops_fin = somar_irrf_opcoes_finalizadas_mes(_supabase, user_id, ano, mes, modo="abertura_total")
        ops_ab = somar_irrf_opcoes_abertura_mes(_supabase, user_id, ano, mes, modo="abertura_total")

    normal = float(vista.get("NORMAL", 0.0)) + float(ops_fin.get("NORMAL", 0.0)) + float(ops_ab.get("NORMAL", 0.0))
    dt = float(vista.get("DAYTRADE", 0.0)) + float(ops_fin.get("DAYTRADE", 0.0)) + float(ops_ab.get("DAYTRADE", 0.0))

    out = {
        "NORMAL": round(normal, 2),
        "DAYTRADE": round(dt, 2),
        "TOTAL": round(normal + dt, 2),
    }
    return out

def classificar_ativo(ticker: Optional[str], meta: Optional[dict] = None) -> str:
    """
    Classifica um ticker de À vista em:
      - "acoes"
      - "bdrefffii" (BDR, ETF, FII)
      - "desconhecido"
    Regras:
      1) Se houver metadado explícito em `meta` (ex.: meta["categoria"]), usar.
      2) Fallback por heurística de ticker:
         - FII/ETF: termina com '11'  -> "bdrefffii"
         - BDR: termina com sufixos '31','32','33','34','35','36','39' -> "bdrefffii"
         - Caso contrário -> "acoes"
    """
    if not ticker:
        return "desconhecido"
    t = str(ticker).strip().upper()

    # 1) Metadado explícito (caso exista no futuro)
    if isinstance(meta, dict):
        cat = (meta.get("categoria") or meta.get("classe") or meta.get("tipo_ativo") or "").strip().lower()
        if cat in {"acao", "ações", "acoes", "stock"}:
            return "acoes"
        if cat in {"bdr", "etf", "fii", "fiis", "bdrefffii"}:
            return "bdrefffii"

    # Normaliza: remove sufixos de mercado (ex.: .SA, .B3, .BMFBOVESPA)
    core = re.sub(r"\.[A-Z0-9]+$", "", t)
    # Exceção: units '11' que **não** são FIIs
    if core in NON_FII_UNITS_11:
        return "acoes"
    # 2) Heurística pelo núcleo do ticker
    if re.search(r"11$", core):
        return "bdrefffii"  # FIIs/ETFs
    if re.search(r"(31|32|33|34|35|36|39)$", core):
        return "bdrefffii"  # BDRs
    return "acoes"


# Classificador detalhado: 'acoes' | 'bdr' | 'etf' | 'fii' | 'desconhecido'
def classificar_ativo_detalhado(ticker: Optional[str], meta: Optional[dict] = None) -> str:
    """
    Classificador detalhado: 'acoes' | 'bdr' | 'etf' | 'fii' | 'desconhecido'

    Regras:
      1) Metadado explícito (se houver) prevalece: meta['categoria'|'classe'|'tipo_ativo'].
      2) Núcleo do ticker (remove .SA, etc). Heurísticas:
         - BDR: termina com 31/32/33/34/35/36/39  -> 'bdr'
         - Termina com '11':
             * se core (sem '11') ∈ ALLOWLIST_ETFS -> 'etf'
             * senão -> 'fii'
         - Caso contrário -> 'acoes'
    """
    if not ticker:
        return "desconhecido"

    t = str(ticker).strip().upper()
    core = _ticker_core_no_market(t)

    # 1) Metadado explícito
    if isinstance(meta, dict):
        cat = (meta.get("categoria") or meta.get("classe") or meta.get("tipo_ativo") or "").strip().lower()
        if cat in {"acao", "ações", "acoes", "stock"}:
            return "acoes"
        if cat in {"bdr"}:
            return "bdr"
        if cat in {"etf"}:
            return "etf"
        if cat in {"fii", "fiis"}:
            return "fii"

    # 2) Heurísticas por sufixo
    # BDRs: 31|32|33|34|35|36|39
    if re.search(r"(31|32|33|34|35|36|39)$", core):
        return "bdr"

    # FIIs/ETFs: geralmente terminam com '11'
    if re.search(r"11$", core):
        # Exceção: units '11' que **não** são FIIs
        if core in NON_FII_UNITS_11:
            return "acoes"
        if is_etf_core(core):
            return "etf"
        return "fii"

    # Ações (fallback)
    return "acoes"


@st.cache_data(ttl=600, show_spinner=False, persist=True)
def obter_resumo_categorias_mes(_supabase, user_id: str, ano: int, mes: int, __dep_epoch: Optional[int] = None) -> dict:
    _ = __dep_epoch  # dependency for Streamlit cache invalidation
    ck = _ck_user_month(user_id, ano, mes)
    cached = _cache_get("resumo_mes", ck)
    if cached is not None:
        return dict(cached)
    _t0 = _t_now()
    """
    Consolida lucros líquidos do mês por categoria (Ações, BDR/ETF, FII, Opções)
    e por tipo (Comum / Day Trade). Também devolve total de VENDAS em ações
    (à vista) no mês (usado depois para isenção 20k).

    Retorna:
    {
      "comum": {"acoes": float, "bdrefffii": float, "fiis": float, "opcoes": float, "vendas_acoes_total": float},
      "dt":    {"acoes": float, "bdrefffii": float, "fiis": float, "opcoes": float}
    }

    Observações:
      - O lucro retornado já é LÍQUIDO (custo descontado), pois vem de carregar_operacoes_do_mes.
      - `bdrefffii` mantém compatibilidade com o legado e agora contempla apenas BDR+ETF (FIIs ficam em `fiis`).
    """
    try:
        _epoch = int(st.session_state.get("ir_epoch", 0) if __dep_epoch is None else __dep_epoch)
    except Exception:
        _epoch = 0
    df = carregar_operacoes_do_mes(_supabase, user_id, ano, mes, __dep_epoch=_epoch)

    # Inicializa acumuladores
    res = {
        "comum": {"acoes": 0.0, "bdrefffii": 0.0, "fiis": 0.0, "opcoes": 0.0, "vendas_acoes_total": 0.0},
        "dt":    {"acoes": 0.0, "bdrefffii": 0.0, "fiis": 0.0, "opcoes": 0.0},
    }

    if df.empty:
        _cache_set("resumo_mes", ck, res)
        _perf(f"obter_resumo_categorias_mes.TOTAL: {_t_now() - _t0:.3f}s")
        return res

    # 1) Agregar lucros por categoria e tipo
    for _, row in df.iterrows():
        mercado = (row.get("mercado") or "").strip()
        tipo = (row.get("tipo") or "Comum").strip().title()  # "Comum" | "Day Trade"
        lucro = float(row.get("lucro_rs") or 0.0)

        chave_tipo = "dt" if tipo == "Day Trade" else "comum"
        if mercado == "Opções":
            res[chave_tipo]["opcoes"] += lucro
        else:
            # À vista -> classificar ticker usando classificador detalhado
            cat_det = classificar_ativo_detalhado(row.get("ticker"))
            if cat_det == "acoes":
                res[chave_tipo]["acoes"] += lucro
            elif cat_det == "bdr" or cat_det == "etf":
                res[chave_tipo]["bdrefffii"] += lucro  # compat: BDR+ETF ficam aqui
            elif cat_det == "fii":
                res[chave_tipo]["fiis"] += lucro
            else:
                # desconhecido -> por segurança, considera em "acoes"
                res[chave_tipo]["acoes"] += lucro

    # 2) Vendas totais em AÇÕES (somente Comum/swing, não Day Trade)
    vendas_total = 0.0
    for _, row in df.iterrows():
        if row.get("mercado") != "À vista":
            continue
        if row.get("tipo") != "Comum":
            continue
        if classificar_ativo_detalhado(row.get("ticker")) != "acoes":
            continue
        q = row.get("quantidade") or 0
        pv = row.get("preco_final") or 0.0
        vendas_total += float(q) * float(pv)

    res["comum"]["vendas_acoes_total"] = vendas_total
    _cache_set("resumo_mes", ck, res)
    _perf(f"obter_resumo_categorias_mes.TOTAL: {_t_now() - _t0:.3f}s")
    return res


# Alias retrocompatibilidade
get_resumo_ir_mes = obter_resumo_categorias_mes


@st.cache_data(ttl=600, show_spinner=False, persist=True)
def apurar_isencao_20k_mes(_supabase, user_id: str, ano: int, mes: int, __dep_epoch: Optional[int] = None) -> dict:
    _ = __dep_epoch  # dependency for Streamlit cache invalidation
    ck = _ck_user_month(user_id, ano, mes)
    cached = _cache_get("isencao_mes", ck)
    if cached is not None:
        return dict(cached)
    _t0 = _t_now()
    """
    Apura a regra de isenção de 20k para AÇÕES à vista (apenas operações COMUM/swing).
    Usa o resumo de categorias do mês para obter:
      - vendas totais de ações (swing) no mês
      - lucro líquido em ações (swing) no mês
    Regras:
      - Se vendas_acoes_total <= 20.000: lucro_isento = max(lucro_acoes, 0)
        e lucro_tributavel = lucro_acoes - lucro_isento (permite negativo)
      - Caso contrário: lucro_isento = 0, lucro_tributavel = lucro_acoes
    Retorna:
      {
        "isencao_aplicada": bool,
        "vendas_acoes_total": float,
        "lucro_acoes": float,
        "lucro_isento_acoes": float,
        "lucro_tributavel_acoes": float,
      }
    """
    try:
        _epoch = int(st.session_state.get("ir_epoch", 0) if __dep_epoch is None else __dep_epoch)
    except Exception:
        _epoch = 0
    resumo = obter_resumo_categorias_mes(_supabase, user_id, ano, mes, __dep_epoch=_epoch)
    vendas = float(resumo.get("comum", {}).get("vendas_acoes_total", 0.0) or 0.0)
    lucro_acoes = float(resumo.get("comum", {}).get("acoes", 0.0) or 0.0)

    limite_20k = get_param(_supabase, "LIMITE_ISENCAO_ACOES", ano, mes, default=LIMITE_ISENCAO_ACOES)
    isencao = vendas <= limite_20k
    lucro_isento = max(lucro_acoes, 0.0) if isencao else 0.0
    lucro_tributavel = lucro_acoes - lucro_isento  # pode ser negativo

    out = {
        "isencao_aplicada": bool(isencao),
        "vendas_acoes_total": vendas,
        "lucro_acoes": lucro_acoes,
        "lucro_isento_acoes": lucro_isento,
        "lucro_tributavel_acoes": lucro_tributavel,
    }
    _cache_set("isencao_mes", ck, out)
    _perf(f"apurar_isencao_20k_mes.TOTAL: {_t_now() - _t0:.3f}s")
    return out


# =========================
# Grupos e Alíquotas (A1)
# =========================
ALIQUOTA_NORMAL = 0.15   # Comum (swing): Ações, BDR, ETF, Opções (sem FII)
ALIQUOTA_DAYTRADE = 0.20 # Day Trade (qualquer mercado)
ALIQUOTA_FII = 0.20      # FIIs/Fiagros: base própria, sem isenção 20k

# Regras fiscais canônicas (evitar números mágicos espalhados)

MINIMO_DARF = 10.0               # mínimo para emissão de DARF
LIMITE_ISENCAO_ACOES = 20000.0   # isenção mensal para ações à vista (COMUM)


# ==============================
# Parâmetros fiscais – helpers & wrappers (edição / exclusão)
# ==============================

def normalizar_valor_parametro(chave: str, valor_in) -> str:
    """
    Normaliza o valor digitado para um formato canônico de string numérica.
    - Para *alíquotas* (chaves contendo "ALIQUOTA"), aceita "17%", "0,17", "0.17" e
      retorna decimal fracionário (ex.: 0.17).
    - Para valores monetários/numéricos (ex.: limites), retorna com ponto decimal.
    """
    s = str(valor_in if valor_in is not None else "").strip()
    if s == "":
        return s
    s = s.replace("%", "").replace(" ", "").replace(",", ".")
    s = re.sub(r"[^0-9.\-]", "", s)
    try:
        x = float(s)
        if "ALIQUOTA" in (chave or "").upper():
            # Se vier como 17 (percentual), converte para 0.17
            if x > 1:
                x = x / 100.0
            out = ("%0.4f" % x).rstrip("0").rstrip(".")
        else:
            out = ("%0.2f" % x).rstrip("0").rstrip(".")
        return out
    except Exception:
        return s


def pf_set_vigencia_rpc(supabase, chave: str, valor, inicio, fim):
    """
    Wrapper para RPC `pf_set_vigencia` (cria/ajusta vigência sem sobreposição).
    Aceita datas como date/datetime/string e normaliza para YYYY-MM-DD.
    """
    d0 = _to_date(inicio)
    d1 = _to_date(fim)
    payload = {
        "p_chave": str(chave or "").strip(),
        "p_valor": normalizar_valor_parametro(chave, valor),
        "p_inicio": d0.strftime("%Y-%m-%d") if d0 else None,
        "p_fim": d1.strftime("%Y-%m-%d") if d1 else None,
    }
    return supabase.rpc("pf_set_vigencia", payload).execute()


def pf_can_delete(supabase, vigencia_id: int, hoje: Optional[date] = None) -> tuple[bool, str]:
    """
    Regras mínimas para permitir exclusão de vigência:
      1) Não pode ser a ÚNICA vigência da mesma chave.
      2) Se a vigência cobre HOJE, só pode excluir se houver outra vigência da mesma chave que também cubra HOJE.

    Retorna (ok: bool, reason: str).
    """
    try:
        # 1) Ler o registro alvo
        r = (
            supabase.table("parametros_fiscais")
            .select("id,chave,efetivo_de,efetivo_ate")
            .eq("id", vigencia_id)
            .single()
            .execute()
        )
        row = getattr(r, "data", None) or {}
        if not row:
            return False, "Vigência não encontrada."
        chave = (row.get("chave") or "").strip()
        de = _to_date(row.get("efetivo_de"))
        ate = _to_date(row.get("efetivo_ate"))
    except Exception as e:
        return False, f"Falha ao ler vigência: {e}"

    # 2) Verificar se é a única vigência da chave
    try:
        q = (
            supabase.table("parametros_fiscais")
            .select("id", count="exact")
            .eq("chave", chave)
            .neq("id", vigencia_id)
            .execute()
        )
        others = int(getattr(q, "count", 0) or 0)
        if others <= 0:
            return False, f"Não é possível excluir: seria a última vigência para a chave {chave}."
    except Exception:
        # Se não conseguir contar, seja conservador
        return False, "Não foi possível validar quantidade de vigências desta chave."

    # 3) Se cobre hoje, precisa haver outra cobertura hoje
    try:
        hoje = hoje or date.today()
        cobre_hoje = (de is not None and ate is not None and de <= hoje <= ate)
        if cobre_hoje:
            q2 = (
                supabase.table("parametros_fiscais")
                .select("id", count="exact")
                .eq("chave", chave)
                .lte("efetivo_de", hoje.strftime("%Y-%m-%d"))
                .gte("efetivo_ate", hoje.strftime("%Y-%m-%d"))
                .neq("id", vigencia_id)
                .execute()
            )
            outros_ativos = int(getattr(q2, "count", 0) or 0)
            if outros_ativos <= 0:
                return False, (
                    "Não é possível excluir: esta vigência está ativa hoje e não há outra cobertura para a chave."
                )
    except Exception:
        return False, "Não foi possível validar cobertura de hoje para esta chave."

    return True, "ok"

def pf_update_vigencia(supabase, vigencia_id: int, valor=None, efetivo_de=None, efetivo_ate=None):
    """
    Atualiza campos de uma vigência existente (update direto na tabela).
    Atenção: manter intervalos **sem sobreposição** para não violar a EXCLUDE.
    """
    payload = {}
    if valor is not None:
        # Precisa da chave para saber se é alíquota; se não tivermos, atualizamos cru
        try:
            q = supabase.table("parametros_fiscais").select("chave").eq("id", vigencia_id).single().execute()
            k = (getattr(q, "data", {}) or {}).get("chave")
        except Exception:
            k = None
        payload["valor"] = normalizar_valor_parametro(k or "", valor)
    if efetivo_de is not None:
        d0 = _to_date(efetivo_de)
        payload["efetivo_de"] = d0.strftime("%Y-%m-%d") if d0 else None
    if efetivo_ate is not None:
        d1 = _to_date(efetivo_ate)
        payload["efetivo_ate"] = d1.strftime("%Y-%m-%d") if d1 else None
    return supabase.table("parametros_fiscais").update(payload).eq("id", vigencia_id).execute()


def pf_delete_vigencia(supabase, vigencia_id: int):
    """
    Exclui uma vigência.
    Primeiro tenta via RPC `pf_delete_vigencia`.
    Se a função não existir ou não estiver no schema cache, faz DELETE direto na tabela.
    """
    # Guardião: não permitir exclusão que deixe a chave sem vigência útil
    ok, reason = pf_can_delete(supabase, vigencia_id)
    if not ok:
        raise Exception(reason)

    try:
        return supabase.rpc("pf_delete_vigencia", {"p_id": int(vigencia_id)}).execute()
    except Exception as e:
        msg = str(e)
        if "schema cache" in msg or "not find the function" in msg or "does not exist" in msg:
            # Fallback: delete direto
            return supabase.table("parametros_fiscais").delete().eq("id", vigencia_id).execute()
        raise


def mapear_grupo_e_aliquota(row) -> tuple[str, float]:
    """
    Mapeia uma linha de operação para (grupo, aliquota).

    Regras iniciais (parametrizadas):
      - Se tipo == "Day Trade" -> grupo "DAYTRADE", alíquota 20%
      - Caso contrário -> grupo "NORMAL", alíquota 15%

    Observação:
      - Futuramente podemos especializar por categoria (ex.: FIIs em grupo próprio),
        usando `mercado` + `classificar_ativo(row['ticker'])`.
    """
    try:
        tipo = (row.get("tipo") or "").strip().title()
    except Exception:
        # compatível com pandas Series
        tipo = str(row.get("tipo") if hasattr(row, "get") else getattr(row, "tipo", "")).strip().title()

    if tipo == "Day Trade":
        return "DAYTRADE", ALIQUOTA_DAYTRADE

    return "NORMAL", ALIQUOTA_NORMAL


# =========================
# Apuração Base Tributável e IR por Regime no mês
# =========================
@st.cache_data(ttl=600, persist=True)
def apurar_base_regime_mes(_supabase, user_id: str, ano: int, mes: int, __dep_epoch: Optional[int] = None) -> dict:
    ck = _ck_user_month(user_id, ano, mes)
    cached = _cache_get("base_regime_mes", ck)
    if cached is not None:
        return dict(cached)
    _t0 = _t_now()
    """
    Consolida a base tributável e IR devido por regime no mês:
      - NORMAL  (15%): Ações (após isenção 20k) + BDR/ETF + Opções
      - DAYTRADE (20%): Ações + BDR/ETF + Opções (marcados como Day Trade)
      - FII     (20%): FIIs (comum + day trade), sem isenção 20k

    Observações:
      - FIIs **não** compõem a base NORMAL nem DAYTRADE; possuem base própria (20%).
      - A isenção 20k aplica-se **somente** a ações à vista (comum).
    Retorna:
      {
        "NORMAL":   {"base_tributavel": float, "ir_devido": float},
        "DAYTRADE": {"base_tributavel": float, "ir_devido": float},
        "FII":      {"base_tributavel": float, "ir_devido": float},
      }
    """
    # --- Memoização por execução (evita recomputos no mesmo rerun) ---
    try:
        _epoch = __dep_epoch if __dep_epoch is not None else (st.session_state.get("ir_epoch", 0) if hasattr(st, "session_state") else 0)
    except Exception:
        _epoch = 0
    _memo_tag = f"base_regime_mes:{user_id}:{int(ano)}:{int(mes)}:{_epoch}"
    _memo_hit = _get_last_result(_memo_tag)
    if _memo_hit is not None:
        return dict(_memo_hit)
    # Dependência de cache por epoch (invalidação barata via bump_ir_epoch)
    if __dep_epoch is None:
        try:
            __dep_epoch = st.session_state.get("ir_epoch", 0)
        except Exception:
            __dep_epoch = 0
    resumo = obter_resumo_categorias_mes(_supabase, user_id, ano, mes, __dep_epoch=__dep_epoch)
    isencao = apurar_isencao_20k_mes(_supabase, user_id, ano, mes, __dep_epoch=__dep_epoch)

    # Parâmetros de alíquotas
    aliquota_normal = get_param(_supabase, "ALIQUOTA_NORMAL", ano, mes, default=ALIQUOTA_NORMAL)
    aliquota_daytrade = get_param(_supabase, "ALIQUOTA_DAYTRADE", ano, mes, default=ALIQUOTA_DAYTRADE)
    aliquota_fii = get_param(_supabase, "ALIQUOTA_FII", ano, mes, default=ALIQUOTA_FII)

    # Base NORMAL: lucro tributável de ações (após isenção) + BDR/ETF + opções
    lucro_trib_acoes = float(isencao.get("lucro_tributavel_acoes", 0.0) or 0.0)
    lucro_bdrefffii = float(resumo.get("comum", {}).get("bdrefffii", 0.0) or 0.0)  # BDR+ETF apenas
    lucro_opcoes = float(resumo.get("comum", {}).get("opcoes", 0.0) or 0.0)
    base_normal = lucro_trib_acoes + lucro_bdrefffii + lucro_opcoes
    ir_normal = base_normal * aliquota_normal if base_normal > 0 else 0.0

    # Base DAYTRADE: soma direta (exclui FIIs)
    lucro_dt_acoes = float(resumo.get("dt", {}).get("acoes", 0.0) or 0.0)
    lucro_dt_bdrefffii = float(resumo.get("dt", {}).get("bdrefffii", 0.0) or 0.0)  # BDR+ETF
    lucro_dt_opcoes = float(resumo.get("dt", {}).get("opcoes", 0.0) or 0.0)
    base_dt = lucro_dt_acoes + lucro_dt_bdrefffii + lucro_dt_opcoes
    ir_dt = base_dt * aliquota_daytrade if base_dt > 0 else 0.0

    # Base FII (20%): comum + day trade (sem isenção 20k)
    lucro_fii_comum = float(resumo.get("comum", {}).get("fiis", 0.0) or 0.0)
    lucro_fii_dt = float(resumo.get("dt", {}).get("fiis", 0.0) or 0.0)
    base_fii = lucro_fii_comum + lucro_fii_dt
    ir_fii = base_fii * aliquota_fii if base_fii > 0 else 0.0

    out = {
        "NORMAL":   {"base_tributavel": base_normal, "ir_devido": ir_normal},
        "DAYTRADE": {"base_tributavel": base_dt, "ir_devido": ir_dt},
        "FII":      {"base_tributavel": base_fii, "ir_devido": ir_fii},
    }
    _cache_set("base_regime_mes", ck, out)
    _set_last_result(_memo_tag, out)
    _perf(f"apurar_base_regime_mes.TOTAL: {_t_now() - _t0:.3f}s")
    return out


# =========================
# Helpers para compensação de prejuízo (carry-in, apuração mensal)
# =========================

# Bulk carry-in fetcher for multiple types
def _buscar_carry_bulk(_supabase, user_id: str, ano: int, mes: int) -> dict:
    try:
        resp = (
            _supabase.table("compensacoes_ir")
            .select("ano,mes,prejuizo_restante_fim,is_active,tipo")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .in_("tipo", ["comum", "daytrade", "fii"])
            .order("ano", desc=True)
            .order("mes", desc=True)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        res = {"comum": 0.0, "daytrade": 0.0, "fii": 0.0}
        for tipo in res.keys():
            for r in rows:
                a = int(r.get("ano") or 0)
                m = int(r.get("mes") or 0)
                if r.get("tipo") == tipo and ((a < ano) or (a == ano and m < mes)):
                    res[tipo] = float(r.get("prejuizo_restante_fim") or 0.0)
                    break
        return res
    except Exception:
        return {"comum": 0.0, "daytrade": 0.0, "fii": 0.0}


@st.cache_data(ttl=600, show_spinner=False, persist=True)
def apurar_compensacao_mes(_supabase, user_id: str, ano: int, mes: int, __dep_epoch: Optional[int] = None) -> dict:
    ck = _ck_user_month(user_id, ano, mes)
    cached = _cache_get("comp_mes", ck)
    if cached is not None:
        return dict(cached)
    _t0 = _t_now()
    """
    Calcula compensação de prejuízo por regime no mês, sem persistir.
    Usa as bases de `apurar_base_regime_mes` e o carry-in vindo de `compensacoes_ir`.

    Retorna:
    {
      "NORMAL": {
          "carry_in": float, "compensado": float,
          "base_pos": float, "prejuizo_restante": float,
          "ir_devido": float
      },
      "DAYTRADE": {
          "carry_in": float, "compensado": float,
          "base_pos": float, "prejuizo_restante": float,
          "ir_devido": float
      },
      "FII": {
          "carry_in": float, "compensado": float,
          "base_pos": float, "prejuizo_restante": float,
          "ir_devido": float
      }
    }
    """
    # --- Memoização por execução (evita recomputos no mesmo rerun) ---
    try:
        _epoch = __dep_epoch if __dep_epoch is not None else (st.session_state.get("ir_epoch", 0) if hasattr(st, "session_state") else 0)
    except Exception:
        _epoch = 0
    _memo_tag = f"comp_mes:{user_id}:{int(ano)}:{int(mes)}:{_epoch}"
    _memo_hit = _get_last_result(_memo_tag)
    if _memo_hit is not None:
        return dict(_memo_hit)
    # Dependência de cache por epoch (invalidação barata via bump_ir_epoch)
    if __dep_epoch is None:
        try:
            __dep_epoch = st.session_state.get("ir_epoch", 0)
        except Exception:
            __dep_epoch = 0
    bases = apurar_base_regime_mes(_supabase, user_id, ano, mes, __dep_epoch=__dep_epoch)
    # Busca carry-ins em bulk
    carrys = _buscar_carry_bulk(_supabase, user_id, ano, mes)
    carry_normal = carrys["comum"]
    carry_dt = carrys["daytrade"]
    carry_fii = carrys["fii"]

    base_normal = float((bases.get("NORMAL") or {}).get("base_tributavel", 0.0) or 0.0)
    base_dt = float((bases.get("DAYTRADE") or {}).get("base_tributavel", 0.0) or 0.0)
    base_fii = float((bases.get("FII") or {}).get("base_tributavel", 0.0) or 0.0)

    # Pré-carregar alíquotas para o mês (evita chamadas repetidas a get_param)
    aliquota_normal = get_param(_supabase, "ALIQUOTA_NORMAL", ano, mes, default=ALIQUOTA_NORMAL)
    aliquota_daytrade = get_param(_supabase, "ALIQUOTA_DAYTRADE", ano, mes, default=ALIQUOTA_DAYTRADE)
    aliquota_fii = get_param(_supabase, "ALIQUOTA_FII", ano, mes, default=ALIQUOTA_FII)

    # --- NORMAL ---
    if base_normal <= 0:
        comp_n = 0.0
        base_pos_n = 0.0
        prejuizo_restante_n = carry_normal + abs(base_normal)
        ir_n = 0.0
    else:
        comp_n = min(base_normal, carry_normal)
        base_pos_n = base_normal - comp_n
        prejuizo_restante_n = carry_normal - comp_n
        ir_n = base_pos_n * float(aliquota_normal) if base_pos_n > 0 else 0.0

    # --- DAYTRADE ---
    if base_dt <= 0:
        comp_dt = 0.0
        base_pos_dt = 0.0
        prejuizo_restante_dt = carry_dt + abs(base_dt)
        ir_dt = 0.0
    else:
        comp_dt = min(base_dt, carry_dt)
        base_pos_dt = base_dt - comp_dt
        prejuizo_restante_dt = carry_dt - comp_dt
        ir_dt = base_pos_dt * float(aliquota_daytrade) if base_pos_dt > 0 else 0.0

    # --- FII (20%) ---
    if base_fii <= 0:
        comp_fii = 0.0
        base_pos_fii = 0.0
        prejuizo_restante_fii = carry_fii + abs(base_fii)
        ir_fii = 0.0
    else:
        comp_fii = min(base_fii, carry_fii)
        base_pos_fii = base_fii - comp_fii
        prejuizo_restante_fii = carry_fii - comp_fii
        ir_fii = base_pos_fii * float(aliquota_fii) if base_pos_fii > 0 else 0.0

    out = {
        "NORMAL": {
            "carry_in": carry_normal,
            "compensado": comp_n,
            "base_pos": base_pos_n,
            "prejuizo_restante": prejuizo_restante_n,
            "ir_devido": ir_n,
        },
        "DAYTRADE": {
            "carry_in": carry_dt,
            "compensado": comp_dt,
            "base_pos": base_pos_dt,
            "prejuizo_restante": prejuizo_restante_dt,
            "ir_devido": ir_dt,
        },
        "FII": {
            "carry_in": carry_fii,
            "compensado": comp_fii,
            "base_pos": base_pos_fii,
            "prejuizo_restante": prejuizo_restante_fii,
            "ir_devido": ir_fii,
        },
    }
    _cache_set("comp_mes", ck, out)
    _set_last_result(_memo_tag, out)
    _perf(f"apurar_compensacao_mes.TOTAL: {_t_now() - _t0:.3f}s")
    return out


# Consolida contagem de operações por ano e mês
def contar_operacoes_por_ano_mes(supabase, user_id: str) -> Dict[str, Any]:
    ck = _ck_user(user_id)
    cached = _cache_get("contar_ops", ck)
    if cached is not None:
        return cached
    """
    Consolida contagem de operações por ano e mês a partir de:
      - ativos_vendidos: usa data_venda
      - opcoes_operacoes: competência = data_encerramento se houver; senão data_operacao
    Retorna:
    {
      "total": int,
      "years": {YYYY: total_no_ano, ...},
      "months": {YYYY: {1: n, ..., 12: n}, ...},
      "src": {"vista": int, "opcoes": int}
    }
    """
    # À vista
    av_resp = supabase.table("ativos_vendidos").select("data_venda").eq("user_id", user_id).execute()
    av_rows: List[dict] = getattr(av_resp, "data", []) or []
    av_dates = [_parse_date_any(r.get("data_venda")) for r in av_rows if r.get("data_venda")]

    # Opções
    op_resp = supabase.table("opcoes_operacoes").select("data_operacao,data_encerramento").eq("user_id", user_id).execute()
    op_rows: List[dict] = getattr(op_resp, "data", []) or []
    op_dates = []
    for r in op_rows:
        d = _to_date(r.get("data_encerramento")) or _to_date(r.get("data_operacao"))
        if d:
            op_dates.append(d)

    all_dates = [d for d in av_dates + op_dates if d]
    year_counts = Counter(d.year for d in all_dates)
    months_counts = defaultdict(Counter)
    for d in all_dates:
        months_counts[d.year][d.month] += 1

    out = {
        "total": len(all_dates),
        "years": dict(sorted(year_counts.items())),
        "months": {y: dict(months_counts[y]) for y in months_counts},
        "src": {"vista": len([d for d in av_dates if d]), "opcoes": len([d for d in op_dates if d])},
    }
    _cache_set("contar_ops", ck, out)
    return out


def inserir_pagamento_darf(supabase, user_id: str, ano: int, mes: int, tipo: str, valor_pago: float, data_pagamento, obs: str = ""):
    """
    Insere um novo pagamento DARF na tabela 'pagamentos_darf' com os dados fornecidos.

    Args:
        supabase: Instância do cliente Supabase.
        user_id (str): ID do usuário.
        ano (int): Ano do pagamento.
        mes (int): Mês do pagamento.
        tipo (str): Tipo aplicável.
        valor_pago (float): Valor pago do pagamento.
        data_pagamento: Data do pagamento (date/datetime/string).
        obs (str, opcional): Observações adicionais. Default é "".

    Returns:
        list: Dados retornados pela execução do insert.
    """
    data_pag = _to_date(data_pagamento)
    data_str = data_pag.strftime("%Y-%m-%d") if isinstance(data_pag, (date, datetime)) else (str(data_pag) if data_pag else None)
    # Normaliza tipo para minúsculo ("comum" | "daytrade" | "fii")
    tipo_norm = (tipo or "").strip().lower()
    if tipo_norm not in {"comum", "daytrade", "fii"}:
        tipo_norm = "comum"
    payload = {
        "user_id": user_id,
        "ano": ano,
        "mes": mes,
        "tipo": tipo_norm,
        "valor_pago": valor_pago,
        "data_pagamento": data_str,
        "obs": obs,
    }
    resp = supabase.table("pagamentos_darf").insert(payload).execute()
    ck_um = _ck_user_month(user_id, ano, mes)
    _cache_invalidate("snapshot_mes", ck_um)
    _cache_invalidate("sum_darf", (user_id, ano, mes, tipo_norm))
    _cache_invalidate("listar_darf", (user_id, ano, mes, tipo_norm))
    _cache_invalidate("diag_mes", _ck_user_month_tipo(user_id, ano, mes, tipo_norm))
    # Invalida cache persistente do Streamlit
    try:
        import streamlit as _st
        if hasattr(_st, "cache_data") and callable(getattr(_st.cache_data, "clear", None)):
            _st.cache_data.clear()
        # Bump epoch para invalidar caches que dependem de __dep_epoch
        bump_ir_epoch()
    except Exception:
        pass
    return getattr(resp, "data", None)


def listar_pagamentos_darf(supabase, user_id: str, ano: int, mes: int, tipo: str, __dep_epoch: Optional[int] = None):
    # normaliza tipo para evitar inconsistências
    tipo_norm = (str(tipo) or "").strip().lower()
    ck = (user_id, int(ano), int(mes), tipo_norm)
    cached = _cache_get("listar_darf", ck)
    if cached is not None:
        return list(cached)
    """
    Lista os pagamentos DARF para o usuário, ano, mês e tipo especificados.
    Aceita variações de caixa no banco ("comum", "Comum", "COMUM", etc.).
    """
    resp = (
        supabase.table("pagamentos_darf")
        .select("*")
        .eq("user_id", user_id)
        .eq("ano", ano)
        .eq("mes", mes)
        .in_("tipo", [tipo_norm, tipo_norm.title(), tipo_norm.upper()])
        .order("data_pagamento", desc=True)
        .order("id", desc=True)
        .execute()
    )
    data = getattr(resp, "data", None) or []
    _cache_set("listar_darf", ck, data)
    return data


def atualizar_pagamento_darf(supabase, pagamento_id: Any, dados_atualizados: dict):
    """
    Atualiza os campos do pagamento DARF identificado pelo pagamento_id e invalida caches relacionados.
    """
    # Cópia defensiva
    payload = dict(dados_atualizados or {})

    # Normaliza data_pagamento se presente
    if "data_pagamento" in payload:
        dp = _to_date(payload.get("data_pagamento"))
        payload["data_pagamento"] = dp.strftime("%Y-%m-%d") if isinstance(dp, (date, datetime)) else (str(dp) if dp else None)

    # Normaliza tipo se presente
    if "tipo" in payload:
        tnorm = (str(payload.get("tipo")) or "").strip().lower()
        if tnorm in {"comum", "daytrade", "fii"}:
            payload["tipo"] = tnorm

    resp = (
        supabase.table("pagamentos_darf")
        .update(payload)
        .eq("id", pagamento_id)
        .execute()
    )

    # Lê o registro atualizado para invalidar caches com precisão
    try:
        r2 = (
            supabase.table("pagamentos_darf")
            .select("user_id,ano,mes,tipo")
            .eq("id", pagamento_id)
            .single()
            .execute()
        )
        row = getattr(r2, "data", None) or {}
        uid = row.get("user_id")
        a = int(row.get("ano") or 0)
        m = int(row.get("mes") or 0)
        t = (row.get("tipo") or "").strip().lower()
        if uid and a and m and t:
            ck_um = _ck_user_month(uid, a, m)
            _cache_invalidate("sum_darf", (uid, a, m, t))
            _cache_invalidate("listar_darf", (uid, a, m, t))
            _cache_invalidate("diag_mes", _ck_user_month_tipo(uid, a, m, t))
            _cache_invalidate("snapshot_mes", ck_um)
    except Exception:
        pass

    # Invalida cache persistente do Streamlit
    try:
        import streamlit as _st
        if hasattr(_st, "cache_data") and callable(getattr(_st.cache_data, "clear", None)):
            _st.cache_data.clear()
        # Bump epoch para invalidar caches que dependem de __dep_epoch
        bump_ir_epoch()
    except Exception:
        pass

    return getattr(resp, "data", None)


def excluir_pagamento_darf(supabase, pagamento_id: Any):
    """
    Exclui o pagamento DARF identificado pelo pagamento_id da tabela e invalida caches relacionados.
    """
    # Lê primeiro para obter chaves de invalidação
    uid = None
    a = m = 0
    t = ""
    try:
        r0 = (
            supabase.table("pagamentos_darf")
            .select("user_id,ano,mes,tipo")
            .eq("id", pagamento_id)
            .single()
            .execute()
        )
        row0 = getattr(r0, "data", None) or {}
        uid = row0.get("user_id")
        a = int(row0.get("ano") or 0)
        m = int(row0.get("mes") or 0)
        t = (row0.get("tipo") or "").strip().lower()
    except Exception:
        pass

    resp = (
        supabase.table("pagamentos_darf")
        .delete()
        .eq("id", pagamento_id)
        .execute()
    )

    # Invalida caches específicos (se conseguimos identificar as chaves)
    try:
        if uid and a and m and t:
            ck_um = _ck_user_month(uid, a, m)
            _cache_invalidate("sum_darf", (uid, a, m, t))
            _cache_invalidate("listar_darf", (uid, a, m, t))
            _cache_invalidate("diag_mes", _ck_user_month_tipo(uid, a, m, t))
            _cache_invalidate("snapshot_mes", ck_um)
    except Exception:
        pass

    # Invalida cache persistente do Streamlit
    try:
        import streamlit as _st
        if hasattr(_st, "cache_data") and callable(getattr(_st.cache_data, "clear", None)):
            _st.cache_data.clear()
        # Bump epoch para invalidar caches que dependem de __dep_epoch
        bump_ir_epoch()
    except Exception:
        pass

    return getattr(resp, "data", None)


# =========================
# Sumário e Consolidação de DARF e Compensações
# =========================
def sum_pagamentos_darf(supabase, user_id: str, ano: int, mes: int, tipo: str, __dep_epoch: Optional[int] = None) -> float:
    ck = (user_id, int(ano), int(mes), str(tipo))
    cached = _cache_get("sum_darf", ck)
    if cached is not None:
        return float(cached)
    """
    Soma o valor pago em DARFs para (user_id, ano, mes, tipo) na tabela `pagamentos_darf`.
    Retorna 0.0 se não houver registros.
    """
    try:
        resp = (
            supabase.table("pagamentos_darf")
            .select("valor_pago")
            .eq("user_id", user_id)
            .eq("ano", ano)
            .eq("mes", mes)
            .in_("tipo", [str(tipo).lower(), str(tipo).title(), str(tipo).upper()])
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        total = 0.0
        for r in rows:
            total += float(r.get("valor_pago") or 0.0)
        _cache_set("sum_darf", ck, total)
        return total
    except Exception:
        return 0.0


#
# =========================
# Carry de IR < 10 (sem alterar schema)
# =========================
def _mes_anterior(ano: int, mes: int) -> tuple[int, int]:
    """Retorna (ano, mes) do mês imediatamente anterior."""
    if int(mes) == 1:
        return int(ano) - 1, 12
    return int(ano), int(mes) - 1


def _snapshot_ativo_tipo(supabase, user_id: str, ano: int, mes: int, tipo: str):
    """
    Lê o snapshot ativo (maior versão) para (user, ano, mes, tipo) em `compensacoes_ir`.
    Retorna o dicionário do registro ou None.
    """
    try:
        resp = (
            supabase.table("compensacoes_ir")
            .select("*")
            .eq("user_id", user_id)
            .eq("ano", ano)
            .eq("mes", mes)
            .eq("tipo", tipo)
            .eq("is_active", True)
            .order("versao", desc=True)
            .limit(1)
            .execute()
        )
        rows = getattr(resp, "data", []) or []
        return rows[0] if rows else None
    except Exception:
        return None


# Helper para detectar rollover de dezembro: carry < 10 de dezembro não pago, carregado para janeiro
def _houve_rollover_dezembro(supabase, user_id: str, ano: int, mes: int, tipo: str) -> bool:
    """
    Retorna True se (e somente se):
      - o mês corrente é janeiro (mes == 1),
      - existe snapshot ATIVO de dezembro do ano anterior para o mesmo tipo,
      - o IR devido de dezembro (ir_devido_tipo) está entre (0, 10),
      - e não houve pagamento DARF em dezembro para esse tipo.
    """
    try:
        if int(mes) != 1:
            return False
        a_prev, m_prev = ano - 1, 12
        snap = _snapshot_ativo_tipo(supabase, user_id, a_prev, m_prev, tipo)
        if not snap:
            return False
        ir_dev_prev = float(snap.get("ir_devido_tipo") or 0.0)
        if ir_dev_prev <= 0.0 or ir_dev_prev >= 10.0:
            return False
        pagos_prev = sum_pagamentos_darf(supabase, user_id, a_prev, m_prev, tipo)
        if pagos_prev and pagos_prev > 0:
            return False
        return True
    except Exception:
        return False


def calcular_carry_ir_sub10(supabase, user_id: str, ano: int, mes: int, tipo: str, max_back_months: int = 36) -> float:
    _t0 = _t_now()
    _iters = 0
    """
    Soma, para trás, os meses consecutivos em que:
      - o IR devido pós-compensação do regime (por competência) MENOS o IRRF do próprio mês
        resulta em valor líquido em (0, mínimo_DARF),
      - e NÃO houve pagamento DARF no mês,
    parando quando encontrar um mês com pagamento (>0), com total líquido >= mínimo,
    total líquido <= 0, ou quando acabar a janela de busca.

    Observação:
      - Calcula o valor **líquido de IRRF** do próprio mês, evitando carregar valores brutos.
      - Não altera schema. Usa pagamentos reais (pagamentos_darf) para interromper a cadeia.
    """
    # --- memoização leve por execução da página (evita recomputos custosos) ---
    global _CARRY_MEMO
    try:
        _key = (str(user_id), int(ano), int(mes), (str(tipo) or "").strip().lower())
        if _key in _CARRY_MEMO:
            return _CARRY_MEMO[_key]
    except Exception:
        _key = None

    total = 0.0
    a, m = _mes_anterior(ano, mes)

    # normaliza tipo para grupos da apuração
    tipo_norm = (str(tipo) or "").strip().lower()
    if tipo_norm not in {"comum", "daytrade", "fii"}:
        return 0.0
    grupo = "NORMAL" if tipo_norm == "comum" else ("DAYTRADE" if tipo_norm == "daytrade" else "FII")

    for _ in range(max_back_months):
        _iters += 1
        # 1) Pagamentos do mês (se houve, encerra cadeia)
        pagos = sum_pagamentos_darf(supabase, user_id, a, m, tipo_norm)
        if pagos and pagos > 0:
            break
        # 2) IR devido pós-compensação do mês
        comp_prev = apurar_compensacao_mes(supabase, user_id, a, m) or {}
        ir_dev_prev = float((comp_prev.get(grupo) or {}).get("ir_devido", 0.0) or 0.0)
        # 3) IRRF do mês, por regime (FII = 0)
        irrf_prev = 0.0
        if grupo in {"NORMAL", "DAYTRADE"}:
            try:
                regs_prev = agregar_irrf_mes_por_regime(supabase, user_id, a, m, modo="abertura_total") or {}
                if grupo == "NORMAL":
                    irrf_prev = float(regs_prev.get("NORMAL", 0.0) or 0.0)
                else:
                    irrf_prev = float(regs_prev.get("DAYTRADE", 0.0) or 0.0)
            except Exception:
                irrf_prev = 0.0
        # 4) Valor líquido do mês (pós-IRRF do próprio mês)
        liquido_prev = max(ir_dev_prev - irrf_prev, 0.0)
        # 5) Mínimo DARF vigente na competência anterior
        minimo_prev = float(get_param(supabase, "LIMIAR_MINIMO_DARF", a, m, default=MINIMO_DARF) or MINIMO_DARF)
        # 6) Regras de parada / acumulação
        if liquido_prev <= 0.0:
            # Não interrompe a cadeia; segue buscando meses anteriores.
            a, m = _mes_anterior(a, m)
            continue
        if liquido_prev >= minimo_prev:
            # Encontrou um mês que, sozinho, já atingiria o mínimo — para a cadeia.
            break
        total += liquido_prev
        a, m = _mes_anterior(a, m)

    total_rounded = round(total, 2)
    try:
        if _key is not None:
            _CARRY_MEMO[_key] = total_rounded
    except Exception:
        pass
    _perf(f"calcular_carry_ir_sub10[{tipo}].iters={_iters} TOTAL: {_t_now() - _t0:.3f}s, total={total_rounded:.2f}")
    return total_rounded

def consolidar_competencia_mes(supabase, user_id: str, ano: int, mes: int) -> dict:
    """
    Gera e persiste snapshot da competência do mês na tabela `compensacoes_ir` para
    os tipos 'comum', 'daytrade' e 'fii', aplicando superseding (desativa versões anteriores).

    Campos preenchidos por tipo:
      - total_vendido_mes: 0.0 (placeholder, pode ser aprimorado depois)
      - total_vendido_tipo: 0.0 (placeholder)
      - lucro_bruto_tipo: base tributável BRUTA do regime (após isenções mas antes de compensação)
      - compensado_tipo: valor compensado no mês
      - ir_devido_tipo: IR devido sobre a BASE PÓS-COMPENSAÇÃO
      - irrf_retido_tipo: 0.0 (não estamos tratando IRRF por enquanto)
      - ir_a_recolher_tipo: max(ir_devido_tipo - pagamentos_darf, 0)
      - prejuizo_restante_fim: carry-out após compensação
      - is_active: True
      - versao: (máximo anterior + 1) por (user_id, ano, mes, tipo)
      - nota: texto curto informando versão gerada via app
      - ops_hash: vazio por ora (pode ser usado no futuro para idempotência)

    Retorna:
      {
        "comum": <registro inserido>,
        "daytrade": <registro inserido>,
        "fii": <registro inserido>
      }
    """
    from datetime import datetime as _dt
    bases = apurar_base_regime_mes(supabase, user_id, ano, mes)
    comp = apurar_compensacao_mes(supabase, user_id, ano, mes)

    resultados = {}
    for grupo, tipo in [("NORMAL", "comum"), ("DAYTRADE", "daytrade"), ("FII", "fii")]:
        base_bruta = float((bases.get(grupo) or {}).get("base_tributavel", 0.0) or 0.0)
        ir_devido_pos = float((comp.get(grupo) or {}).get("ir_devido", 0.0) or 0.0)
        compensado = float((comp.get(grupo) or {}).get("compensado", 0.0) or 0.0)
        prej_restante = float((comp.get(grupo) or {}).get("prejuizo_restante", 0.0) or 0.0)

        # Pagamentos DARF do mês/tipo
        pagos = sum_pagamentos_darf(supabase, user_id, ano, mes, tipo)
        irrf = 0.0  # por enquanto não tratamos IRRF

        # Regra de acúmulo: somar carry de meses anteriores com IR < 10 e sem pagamento
        carry_sub10 = calcular_carry_ir_sub10(supabase, user_id, ano, mes, tipo)
        ir_considerado = ir_devido_pos + carry_sub10

        minimo_darf = get_param(supabase, "LIMIAR_MINIMO_DARF", ano, mes, default=MINIMO_DARF)
        # Se total ficar < mínimo, não recolhe e carrega adiante (ir_a_recolher = 0)
        if ir_considerado < minimo_darf:
            ir_a_recolher = 0.0
        else:
            ir_a_recolher = max(ir_considerado - pagos - irrf, 0.0)

        # Superseding: desativa registros ativos anteriores deste (user, ano, mes, tipo)
        try:
            # Descobrir próxima versão
            resp_versions = (
                supabase.table("compensacoes_ir")
                .select("versao,is_active,ano,mes,tipo")
                .eq("user_id", user_id)
                .eq("ano", ano)
                .eq("mes", mes)
                .eq("tipo", tipo)
                .order("versao", desc=True)
                .execute()
            )
            rows_v = getattr(resp_versions, "data", []) or []
            next_version = 1
            if rows_v:
                try:
                    next_version = (int(rows_v[0].get("versao") or 0) + 1)
                except Exception:
                    next_version = 1

            # Desativa registros ativos anteriores
            now_iso = _dt.utcnow().isoformat()
            supabase.table("compensacoes_ir") \
                .update({"is_active": False, "superseded_at": now_iso}) \
                .eq("user_id", user_id) \
                .eq("ano", ano) \
                .eq("mes", mes) \
                .eq("tipo", tipo) \
                .eq("is_active", True) \
                .execute()

            # Parâmetros vigentes para registrar na nota (sem alterar schema)
            _params_aplicados = _coletar_parametros_aplicados(supabase, ano, mes)
            _params_str = (
                f"norm={_params_aplicados.get('ALIQUOTA_NORMAL'):.2f}; "
                f"dt={_params_aplicados.get('ALIQUOTA_DAYTRADE'):.2f}; "
                f"fii={_params_aplicados.get('ALIQUOTA_FII'):.2f}; "
                f"lim20k={_params_aplicados.get('LIMITE_ISENCAO_ACOES'):.0f}; "
                f"min={_params_aplicados.get('LIMIAR_MINIMO_DARF'):.0f}; "
                f"ver={'on' if _params_aplicados.get('versioned') else 'off'}"
            )

            payload = {
                "user_id": user_id,
                "ano": ano,
                "mes": mes,
                "tipo": tipo,
                "total_vendido_mes": 0.0,
                "total_vendido_tipo": 0.0,
                "lucro_bruto_tipo": base_bruta,
                "compensado_tipo": compensado,
                "ir_devido_tipo": ir_devido_pos,
                "irrf_retido_tipo": irrf,
                "ir_a_recolher_tipo": ir_a_recolher,
                "prejuizo_restante_fim": prej_restante,
                "is_active": True,
                "versao": next_version,
                "nota": (
                    f"Snapshot v{next_version} | carry<10: {carry_sub10:.2f} | params: {_params_str}"
                ),
                "ops_hash": "",
            }
            resp_ins = supabase.table("compensacoes_ir").insert(payload).execute()
            resultados[tipo] = (getattr(resp_ins, "data", None) or [payload])[0]
        except Exception as e:
            resultados[tipo] = {"error": str(e)}

    # --- Pós-consolidação: garantir que a UI reflita imediatamente o fechamento ---
    # Limpamos caches do Streamlit e "bumpamos" o epoch para invalidar dependências.
    try:
        if hasattr(st, "cache_data") and callable(getattr(st, "cache_data", None)):
            st.cache_data.clear()
    except Exception:
        pass
    try:
        # Atualiza epoch de IR (invalidação barata usada pelos caches dependentes)
        bump_ir_epoch()
    except Exception:
        pass

    return resultados


# =========================
# Auditoria: coleta de parâmetros e trilha de cálculo
# =========================

def _coletar_parametros_aplicados(supabase, ano: int, mes: int) -> dict:
    """Retorna um dicionário com os parâmetros fiscais aplicados na competência."""
    try:
        return {
            "versioned": bool(_flag_rules_versioned()),
            "ALIQUOTA_NORMAL": float(get_param(supabase, "ALIQUOTA_NORMAL", ano, mes, default=ALIQUOTA_NORMAL) or ALIQUOTA_NORMAL),
            "ALIQUOTA_DAYTRADE": float(get_param(supabase, "ALIQUOTA_DAYTRADE", ano, mes, default=ALIQUOTA_DAYTRADE) or ALIQUOTA_DAYTRADE),
            "ALIQUOTA_FII": float(get_param(supabase, "ALIQUOTA_FII", ano, mes, default=ALIQUOTA_FII) or ALIQUOTA_FII),
            "LIMITE_ISENCAO_ACOES": float(get_param(supabase, "LIMITE_ISENCAO_ACOES", ano, mes, default=LIMITE_ISENCAO_ACOES) or LIMITE_ISENCAO_ACOES),
            "LIMIAR_MINIMO_DARF": float(get_param(supabase, "LIMIAR_MINIMO_DARF", ano, mes, default=MINIMO_DARF) or MINIMO_DARF),
        }
    except Exception:
        return {
            "versioned": False,
            "ALIQUOTA_NORMAL": ALIQUOTA_NORMAL,
            "ALIQUOTA_DAYTRADE": ALIQUOTA_DAYTRADE,
            "ALIQUOTA_FII": ALIQUOTA_FII,
            "LIMITE_ISENCAO_ACOES": LIMITE_ISENCAO_ACOES,
            "LIMIAR_MINIMO_DARF": MINIMO_DARF,
        }


def montar_auditoria_mes(supabase, user_id: str, ano: int, mes: int) -> dict:
    _t0 = _t_now()
    """
    Monta um JSON detalhando o cálculo do mês para auditoria/explicabilidade.
    Inclui: resumo, isenção, bases, compensações, IRRF por regime, pagamentos,
    carry < 10, mínimo aplicável, parâmetros vigentes e deltas vs snapshot.
    """
    params = _coletar_parametros_aplicados(supabase, ano, mes)

    # Blocos principais
    resumo = obter_resumo_categorias_mes(supabase, user_id, ano, mes)
    isencao = apurar_isencao_20k_mes(supabase, user_id, ano, mes)
    bases = apurar_base_regime_mes(supabase, user_id, ano, mes)
    comp = apurar_compensacao_mes(supabase, user_id, ano, mes)

    try:
        irrf_regs = agregar_irrf_mes_por_regime(supabase, user_id, ano, mes, modo="abertura_total")
    except Exception:
        irrf_regs = {"NORMAL": 0.0, "DAYTRADE": 0.0, "TOTAL": 0.0}

    # Pagamentos e carry<10 por tipo
    pagamentos = {
        "comum": sum_pagamentos_darf(supabase, user_id, ano, mes, "comum"),
        "daytrade": sum_pagamentos_darf(supabase, user_id, ano, mes, "daytrade"),
        "fii": sum_pagamentos_darf(supabase, user_id, ano, mes, "fii"),
    }
    carry_sub10 = {
        "comum": calcular_carry_ir_sub10(supabase, user_id, ano, mes, "comum"),
        "daytrade": calcular_carry_ir_sub10(supabase, user_id, ano, mes, "daytrade"),
        "fii": calcular_carry_ir_sub10(supabase, user_id, ano, mes, "fii"),
    }

    # Totais considerados por regime (pós IRRF) apenas para auditoria
    def _tot_cons(grupo: str, tipo_ui: str) -> float:
        base_pos_ir = float((comp.get(grupo) or {}).get("ir_devido", 0.0) or 0.0)
        if grupo == "NORMAL":
            irrf = float(irrf_regs.get("NORMAL", 0.0) or 0.0)
        elif grupo == "DAYTRADE":
            irrf = float(irrf_regs.get("DAYTRADE", 0.0) or 0.0)
        else:
            irrf = 0.0
        return max(base_pos_ir + float(carry_sub10.get(tipo_ui, 0.0)) - irrf, 0.0)

    total_cons = {
        "comum": _tot_cons("NORMAL", "comum"),
        "daytrade": _tot_cons("DAYTRADE", "daytrade"),
        "fii": _tot_cons("FII", "fii"),
    }

    minimo = float(params.get("LIMIAR_MINIMO_DARF", MINIMO_DARF) or MINIMO_DARF)

    # Snapshot atual para comparar
    snap = ler_snapshot_ativo_mes(supabase, user_id, ano, mes) or {}
    snap_ir = {
        "comum": float((snap.get("comum") or {}).get("ir_a_recolher_tipo", 0.0) or 0.0) if snap.get("comum") else None,
        "daytrade": float((snap.get("daytrade") or {}).get("ir_a_recolher_tipo", 0.0) or 0.0) if snap.get("daytrade") else None,
        "fii": float((snap.get("fii") or {}).get("ir_a_recolher_tipo", 0.0) or 0.0) if snap.get("fii") else None,
    }

    deltas = {
        k: ( (max(total_cons[k] - float(pagamentos.get(k) or 0.0), 0.0)) - (snap_ir[k] or 0.0) )
        for k in ("comum", "daytrade", "fii")
    }

    _perf(f"montar_auditoria_mes.TOTAL: {_t_now() - _t0:.3f}s")
    return {
        "params": params,
        "resumo": resumo,
        "isencao": isencao,
        "bases": bases,
        "compensacao": comp,
        "irrf": irrf_regs,
        "pagamentos": pagamentos,
        "carry_sub10": carry_sub10,
        "minimo_darf": minimo,
        "total_considerado": total_cons,
        "snapshot_ir_a_recolher": snap_ir,
        "deltas_vs_snapshot": deltas,
    }

# =========================
# Ler snapshot ativo de compensações_ir para competência do mês
# =========================

def ler_snapshot_ativo_mes(supabase, user_id: str, ano: int, mes: int) -> Optional[dict]:
    """
    Lê os snapshots ATIVOS de `compensacoes_ir` da competência (ano, mes) para os três tipos
    ("comum", "daytrade", "fii") e retorna um dicionário com o que existir.

    Formato de retorno:
      {
        "comum":   <row dict> | None,
        "daytrade":<row dict> | None,
        "fii":     <row dict> | None,
      }

    Observações:
      - Usa o helper interno `_snapshot_ativo_tipo` para cada tipo.
      - Se nada existir, retorna `{}` (mantendo compatibilidade com chamadas que usam `or {}`).
    """
    try:
        out = {}
        for tipo in ("comum", "daytrade", "fii"):
            row = _snapshot_ativo_tipo(supabase, user_id, int(ano), int(mes), tipo)
            if row:
                out[tipo] = row
        return out
    except Exception:
        # Conservador: se houver erro de leitura, devolve dicionário vazio
        return {}

# =========================
# Ledger mensal consolidado (leitura de snapshots ativos)
# =========================

def carregar_ledger_mensal(supabase, user_id: str, ano_ini: int, ano_fim: int, _cache_epoch: Optional[int | str] = None) -> dict:
    """
    Parâmetros:
      - _cache_epoch: argumento opcional e ignorado; mantido apenas por retrocompatibilidade com chamadas cacheadas.
    Lê, para o intervalo [ano_ini, ano_fim], os snapshots ATIVOS por competência (mês) e
    retorna um dicionário indexado por (ano, mes):

      {
        (YYYY, M): {
          "comum":   <row dict> | None,
          "daytrade":<row dict> | None,
          "fii":     <row dict> | None,
        },
        ...
      }

    Observações:
      - Usa `ler_snapshot_ativo_mes` para cada competência; se nada existir no mês,
        mapeia para `None` nos tipos ausentes.
      - Não persiste nada; apenas leitura tolerante a falhas (try/except por mês).
      - Retorna `{}` se `ano_ini > ano_fim` ou em caso de erro grave.
    """
    try:
        a0 = int(ano_ini)
        a1 = int(ano_fim)
    except Exception:
        return {}

    if a0 > a1:
        return {}

    ledger: dict[tuple[int, int], dict] = {}

    for ano in range(a0, a1 + 1):
        for mes in range(1, 13):
            try:
                snap = ler_snapshot_ativo_mes(supabase, user_id, ano, mes) or {}
                if snap:
                    # Garante as três chaves, preenchendo ausentes com None
                    entry = {
                        "comum": snap.get("comum"),
                        "daytrade": snap.get("daytrade"),
                        "fii": snap.get("fii"),
                    }
                else:
                    entry = {"comum": None, "daytrade": None, "fii": None}
                ledger[(ano, mes)] = entry
            except Exception:
                # Em caso de falha pontual, mantém a chave com None para todos os tipos
                ledger[(ano, mes)] = {"comum": None, "daytrade": None, "fii": None}
    return ledger
# =========================
# Prévia de IR do mês (diagnóstico DARF)
# =========================
def diagnostico_darf_mes(supabase, user_id: str, ano: int, mes: int, tipo: str) -> dict:
    """
    Prévia de IR do mês por `tipo` ("comum" | "daytrade" | "fii"), sem gravar snapshot.
    Contrato da UI (chaves do retorno):
      - ir_devido_mes (float): IR devido do mês pós-compensação (card).
      - irrf_mes (float): IRRF do mês aplicável ao tipo (FII = 0).
      - carry_sub10 (float): soma de IR < 10 de meses anteriores (sem pagamentos).
      - total_considerado (float): max(ir_devido_mes - irrf_mes + carry_sub10, 0).
      - pagos_mes (float): soma dos DARFs do mês para o tipo.
      - minimo_darf (float): limiar vigente para emissão de DARF.
      - sugerido (float): valor sugerido a recolher considerando a regra do mínimo.
      - status (str): "Abaixo do mínimo" | "Devido" | "Quitado/sem débito".
    """
    
    # Normaliza tipo para as chaves de tabela
    tipo_norm = (str(tipo) or "").strip().lower()
    if tipo_norm not in {"comum", "daytrade", "fii"}:
        return {
            "ir_devido_mes": 0.0,
            "irrf_mes": 0.0,
            "carry_sub10": 0.0,
            "total_considerado": 0.0,
            "pagos_mes": 0.0,
            "minimo_darf": float(get_param(supabase, "LIMIAR_MINIMO_DARF", ano, mes, default=MINIMO_DARF) or MINIMO_DARF),
            "sugerido": 0.0,
            "status": "Quitado/sem débito",
        }

    # 1) IR devido do mês pós-compensação por regime
    comp = apurar_compensacao_mes(supabase, user_id, ano, mes)
    if tipo_norm == "comum":
        ir_devido_mes = float((comp.get("NORMAL") or {}).get("ir_devido", 0.0) or 0.0)
    elif tipo_norm == "daytrade":
        ir_devido_mes = float((comp.get("DAYTRADE") or {}).get("ir_devido", 0.0) or 0.0)
    else:  # "fii"
        ir_devido_mes = float((comp.get("FII") or {}).get("ir_devido", 0.0) or 0.0)

    # 2) IRRF aplicável ao tipo
    try:
        irrf_regs = agregar_irrf_mes_por_regime(supabase, user_id, ano, mes, modo="abertura_total")
    except Exception:
        irrf_regs = {"NORMAL": 0.0, "DAYTRADE": 0.0}
    if tipo_norm == "comum":
        irrf_mes = float(irrf_regs.get("NORMAL", 0.0) or 0.0)
    elif tipo_norm == "daytrade":
        irrf_mes = float(irrf_regs.get("DAYTRADE", 0.0) or 0.0)
    else:
        irrf_mes = 0.0  # FIIs não possuem IRRF a abater aqui

    # 3) Carry de meses com IR < 10 sem pagamento
    carry = calcular_carry_ir_sub10(supabase, user_id, ano, mes, tipo_norm)

    # O carry_sub10 já representa valor líquido de IRRF; não deve ser tratado como bruto.
    total_considerado = max(ir_devido_mes - irrf_mes + float(carry), 0.0)

    # 5) Pagamentos no mês para o tipo
    pagos_mes = sum_pagamentos_darf(supabase, user_id, ano, mes, tipo_norm)

    # 6) Mínimo DARF vigente
    minimo_darf = float(get_param(supabase, "LIMIAR_MINIMO_DARF", ano, mes, default=MINIMO_DARF) or MINIMO_DARF)

    # 7) Sugerido e status conforme a regra
    if total_considerado <= 0.0:
        sugerido = 0.0
        status = "Quitado/sem débito"
    elif total_considerado < minimo_darf:
        sugerido = 0.0
        status = "Abaixo do mínimo"
    else:
        sugerido = max(total_considerado - pagos_mes, 0.0)
        status = "Devido" if sugerido > 0 else "Quitado/sem débito"

    return {
        "ir_devido_mes": round(ir_devido_mes, 2),
        "irrf_mes": round(irrf_mes, 2),
        "carry_sub10": round(float(carry), 2),
        "total_considerado": round(total_considerado, 2),
        "pagos_mes": round(float(pagos_mes or 0.0), 2),
        "minimo_darf": round(minimo_darf, 2),
        "sugerido": round(sugerido, 2),
        "status": status,
    }