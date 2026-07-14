import datetime
# -------- Cached helpers (reduzem recomputo pesado) --------
# --------- Funções utilitárias para competência consolidada e próxima não consolidada ---------
def ultimo_mes_consolidado(df_compensacoes):
    if df_compensacoes.empty:
        return None
    df_compensacoes = df_compensacoes[df_compensacoes['is_active'] == True]
    if df_compensacoes.empty:
        return None
    df_compensacoes = df_compensacoes.sort_values(by=['ano', 'mes'])
    ultimo = df_compensacoes.iloc[-1]
    return int(ultimo['ano']), int(ultimo['mes'])

# Versão que considera apenas meses com operações (baseada em ops_count)
# Evita abrir anos "vazios" (ex.: 2014 sem operações) como padrão após consolidar dezembro.
def proxima_competencia_nao_consolidada(df_compensacoes):
    ultimo = ultimo_mes_consolidado(df_compensacoes)
    if not ultimo:
        hoje = datetime.date.today()
        return hoje.year, hoje.month
    ano, mes = ultimo
    for _ in range(120):
        mes += 1
        if mes > 12:
            mes = 1
            ano += 1
        if not ((df_compensacoes['ano'] == ano) & (df_compensacoes['mes'] == mes) & (df_compensacoes['is_active'] == True)).any():
            return ano, mes
    return ano, mes

# Versão que considera apenas meses com operações (baseada em ops_count)
# Evita abrir anos "vazios" (ex.: 2014 sem operações) como padrão após consolidar dezembro.
def proxima_competencia_nao_consolidada_com_ops(df_compensacoes, ops_count: dict):
    try:
        # Conjunto de competências já consolidadas ativas
        dfc = df_compensacoes.copy()
        if dfc is None:
            dfc = []
        import pandas as _pd
        dfc = _pd.DataFrame(dfc)
        if not dfc.empty:
            dfc = dfc[dfc.get('is_active', True) == True]
        consol_set = set()
        if not dfc.empty:
            for _, r in dfc.iterrows():
                try:
                    consol_set.add((int(r.get('ano')), int(r.get('mes'))))
                except Exception:
                    pass
        # Último mês consolidado (se existir)
        ultimo = ultimo_mes_consolidado(dfc)
        # Lista ordenada de (ano, mes) que **têm operações**
        anos_keys = sorted((ops_count or {}).get('months', {}).keys())
        meses_com_ops = []
        for a in anos_keys:
            mm = (ops_count or {}).get('months', {}).get(a, {}) or {}
            for m in range(1, 13):
                try:
                    if int(mm.get(m, 0) or 0) > 0:
                        meses_com_ops.append((int(a), int(m)))
                except Exception:
                    continue
        if not meses_com_ops:
            # Fallback para a versão antiga
            return proxima_competencia_nao_consolidada(dfc)
        # Se nunca consolidou nada, retorna o primeiro mês com operações
        if not ultimo:
            return meses_com_ops[0]
        ua, um = ultimo
        # Encontra o primeiro (ano,mes) > último consolidado e que ainda **não** esteja consolidado
        for a, m in meses_com_ops:
            if (a, m) > (ua, um) and ((a, m) not in consol_set):
                return a, m
        # Se todos após o último já estão consolidados, fica no primeiro mês com ops do próximo ano disponível
        # ou então volta para o último par da lista (mais recente com ops)
        return meses_com_ops[-1]
    except Exception:
        # Segurança: se algo falhar, cai no comportamento anterior
        return proxima_competencia_nao_consolidada(df_compensacoes)
# [R2D2][Pag8][TOP-UI] =============================
import streamlit as st
import datetime as _dt_perf
from postgrest.exceptions import APIError as PostgrestAPIError
from utils import supabase_autenticado, redirecionar_para_login, tratar_erro_autenticacao
from utils_style import apply_global_dark_theme
from utils_ir import (
    contar_operacoes_por_ano_mes,
    carregar_operacoes_do_mes,
    obter_resumo_categorias_mes,
    apurar_isencao_20k_mes,
    apurar_base_regime_mes,
    apurar_compensacao_mes,
    consolidar_competencia_mes,
    ler_snapshot_ativo_mes,
    inserir_pagamento_darf,
    listar_pagamentos_darf,
    atualizar_pagamento_darf,
    excluir_pagamento_darf,
    calcular_carry_ir_sub10,
    sum_pagamentos_darf,
    diagnostico_darf_mes,
    calcular_status_mes,
    is_bdr_ticker,
    is_etf_ticker,
    is_fii_ticker,
    classificar_ticker,
    _houve_rollover_dezembro,
    agregar_irrf_mes_por_regime,
    montar_auditoria_mes,
    invalidate_params_cache,
    get_param,
    is_mes_sujo,
    marcar_mes_calculado,
)

# --- [Pag8][PAY-EPOCH WRAPPERS] Atualiza epoch e memo após qualquer mudança em pagamentos ---
# Reimporta originais com alias para não perdermos a referência
from utils_ir import (
    inserir_pagamento_darf as _ir__inserir_pagamento_darf_orig,
    atualizar_pagamento_darf as _ir__atualizar_pagamento_darf_orig,
    excluir_pagamento_darf as _ir__excluir_pagamento_darf_orig,
)

apply_global_dark_theme()

def _pag8__bump_after_payment(ano: int, mes: int):
    """Incrementa o epoch específico de pagamentos e limpa o memo local
    para forçar o refresh dos cards (inclui SITUAÇÃO) nesta página.
    """
    try:
        import streamlit as _st
        _st.session_state["pag8_pay_epoch"] = int(_st.session_state.get("pag8_pay_epoch", 0)) + 1
        # Limpa memo local desta página para o (ano, mes) afetado
        try:
            _run = _st.session_state.get("_pag8_run", {})
            if isinstance(_run, dict):
                keys_to_drop = []
                for k in list(_run.keys()):
                    if not isinstance(k, tuple):
                        continue
                    # Chaves padrões usadas nesta página
                    if (len(k) >= 3 and k[0] in ("diag_both", "snapshot", "listar_pag_both", "irrf") and k[1] == ano and k[2] == mes):
                        keys_to_drop.append(k)
                        continue
                    if (len(k) >= 4 and k[0] in ("diag", "listar_pag", "previa_corrigida_regime") and k[1] == ano and k[2] == mes):
                        keys_to_drop.append(k)
                        continue
                    # NEW: também invalida o cache do ledger do ano (impacta o card SITUAÇÃO)
                    if (len(k) >= 2 and k[0] == "ledger" and k[1] == ano):
                        keys_to_drop.append(k)
                        continue
                    # NEW: invalida prévia total corrigida, se existir chave local
                    if (len(k) >= 4 and k[0] in ("previa_corrigida_total",) and k[1] == ano and k[2] == mes):
                        keys_to_drop.append(k)
                        continue
                    # NEW: invalida prévia corrigida por regime (usada nos badges do card SITUAÇÃO e Resumo)
                    if (len(k) >= 5 and k[0] == "previa_corrigida_regime" and k[1] == ano and k[2] == mes):
                        keys_to_drop.append(k)
                        continue
                    # Fallback genérico: se o tuple contém ano e mês em qualquer posição
                    if (ano in k) and (mes in k):
                        keys_to_drop.append(k)
                for k in keys_to_drop:
                    _run.pop(k, None)
                _st.session_state["_pag8_run"] = _run
                # Além do memo leve, limpe caches @st.cache_data específicos de pagamentos
                try:
                    _cached_listar_pag.clear()
                except Exception:
                    pass
                try:
                    _cached_listar_pag_both.clear()
                except Exception:
                    pass
        except Exception:
            pass
    except Exception:
        pass

# Wrappers com a MESMA assinatura usada na página (pass-through + bump de epoch)


def inserir_pagamento_darf(*args, **kwargs):
    """Wrapper local: chama o original e incrementa o epoch de pagamentos.
    Espera assinatura (sb, uid, ano, mes, tipo, ...).
    """
    res = _ir__inserir_pagamento_darf_orig(*args, **kwargs)
    try:
        # tenta extrair ano/mes dos args posicionais
        if len(args) >= 4:
            _ano = int(args[2]); _mes = int(args[3])
            _pag8__bump_after_payment(_ano, _mes)
    except Exception:
        pass
    # Atualiza override local de pagamentos para refletir imediatamente na UI
    try:
        import streamlit as _st
        # extrai regime a partir do 5º argumento posicional (tipo)
        _reg = None
        if len(args) >= 5:
            _tipo_raw = str(args[4]).lower()
            if _tipo_raw in ("comum", "normal", "avista", "swing"):
                _reg = "comum"
            elif _tipo_raw in ("daytrade", "dt", "day"):
                _reg = "daytrade"
            elif _tipo_raw == "fii":
                _reg = "fii"
            else:
                # fallback: usa o valor bruto informado
                _reg = _tipo_raw
        if _reg and ("_ano" in locals()) and ("_mes" in locals()):
            try:
                from utils_ir import listar_pagamentos_darf as _ir__listar
                _uid = None
                if len(args) >= 2:
                    _uid = args[1]
                else:
                    _uid = kwargs.get("uid") or kwargs.get("user_id")
                _lst = _ir__listar(supabase_autenticado(), _uid, int(_ano), int(_mes), _reg) or []
                _st.session_state[f"pag8_pay_override_{int(_ano)}_{int(_mes)}_{_reg}"] = _lst
            except Exception:
                pass
    except Exception:
        pass
    return res


def atualizar_pagamento_darf(*args, **kwargs):
    res = _ir__atualizar_pagamento_darf_orig(*args, **kwargs)
    try:
        if len(args) >= 4:
            _ano = int(args[2]); _mes = int(args[3])
            _pag8__bump_after_payment(_ano, _mes)
    except Exception:
        pass
    # Atualiza override local de pagamentos para refletir imediatamente na UI
    try:
        import streamlit as _st
        # extrai regime a partir do 5º argumento posicional (tipo)
        _reg = None
        if len(args) >= 5:
            _tipo_raw = str(args[4]).lower()
            if _tipo_raw in ("comum", "normal", "avista", "swing"):
                _reg = "comum"
            elif _tipo_raw in ("daytrade", "dt", "day"):
                _reg = "daytrade"
            elif _tipo_raw == "fii":
                _reg = "fii"
            else:
                # fallback: usa o valor bruto informado
                _reg = _tipo_raw
        if _reg and ("_ano" in locals()) and ("_mes" in locals()):
            try:
                from utils_ir import listar_pagamentos_darf as _ir__listar
                _uid = None
                if len(args) >= 2:
                    _uid = args[1]
                else:
                    _uid = kwargs.get("uid") or kwargs.get("user_id")
                _lst = _ir__listar(supabase_autenticado(), _uid, int(_ano), int(_mes), _reg) or []
                _st.session_state[f"pag8_pay_override_{int(_ano)}_{int(_mes)}_{_reg}"] = _lst
            except Exception:
                pass
    except Exception:
        pass
    return res


def excluir_pagamento_darf(*args, **kwargs):
    res = _ir__excluir_pagamento_darf_orig(*args, **kwargs)
    try:
        if len(args) >= 4:
            _ano = int(args[2]); _mes = int(args[3])
            _pag8__bump_after_payment(_ano, _mes)
    except Exception:
        pass
    # Atualiza override local de pagamentos para refletir imediatamente na UI
    try:
        import streamlit as _st
        # extrai regime a partir do 5º argumento posicional (tipo)
        _reg = None
        if len(args) >= 5:
            _tipo_raw = str(args[4]).lower()
            if _tipo_raw in ("comum", "normal", "avista", "swing"):
                _reg = "comum"
            elif _tipo_raw in ("daytrade", "dt", "day"):
                _reg = "daytrade"
            elif _tipo_raw == "fii":
                _reg = "fii"
            else:
                # fallback: usa o valor bruto informado
                _reg = _tipo_raw
        if _reg and ("_ano" in locals()) and ("_mes" in locals()):
            try:
                from utils_ir import listar_pagamentos_darf as _ir__listar
                _uid = None
                if len(args) >= 2:
                    _uid = args[1]
                else:
                    _uid = kwargs.get("uid") or kwargs.get("user_id")
                _lst = _ir__listar(supabase_autenticado(), _uid, int(_ano), int(_mes), _reg) or []
                _st.session_state[f"pag8_pay_override_{int(_ano)}_{int(_mes)}_{_reg}"] = _lst
            except Exception:
                pass
    except Exception:
        pass
    return res



# --- [Pag8] Garantir que chamadas qualificadas usem os wrappers desta página ---

try:
    import utils_ir as _utils_ir_mod
    _utils_ir_mod.inserir_pagamento_darf = inserir_pagamento_darf
    _utils_ir_mod.atualizar_pagamento_darf = atualizar_pagamento_darf
    _utils_ir_mod.excluir_pagamento_darf = excluir_pagamento_darf
except Exception:
    pass

# Invalida flags e memo leve após consolidar um mês, para forçar recálculo ao voltar para o mês consolidado
def _pag8__invalidate_after_consolidation(ano: int, mes: int):
    """
    Limpa flags e o memo leve desta página para (ano, mes) após consolidar.
    Garante que, ao voltar para o mês consolidado, a UI mostre 'Calcular este mês'
    e que nenhum valor stale de _pag8_run seja reutilizado.
    """
    try:
        import streamlit as _st
        # 1) força que o mês recém-consolidado precise de recálculo manual na UI
        try:
            _st.session_state[f"pag8_calc_{ano}_{mes}"] = False
        except Exception:
            pass

        # 2) limpa o memo leve desta página (_pag8_run) para chaves relacionadas
        try:
            _run = _st.session_state.get("_pag8_run", {})
            if isinstance(_run, dict):
                keys_to_drop = []
                for k in list(_run.keys()):
                    if not isinstance(k, tuple):
                        continue
                    # ledger por ano (com ou sem epoch na chave)
                    if len(k) >= 2 and k[0] == "ledger" and k[1] == ano:
                        keys_to_drop.append(k)
                        continue
                    # snapshot / diag / listar_pag / irrf / diag_both / listar_pag_both para (ano, mes)
                    if (len(k) >= 3 and k[1] == ano and k[2] == mes and k[0] in ("snapshot","irrf","diag_both","listar_pag_both")):
                        keys_to_drop.append(k)
                        continue
                    if (len(k) >= 4 and k[1] == ano and k[2] == mes and k[0] in ("diag","listar_pag","previa_corrigida_total")):
                        keys_to_drop.append(k)
                        continue
                    if (len(k) >= 5 and k[0] == "previa_corrigida_regime" and k[1] == ano and k[2] == mes):
                        keys_to_drop.append(k)
                        continue
                    # fallback: qualquer tupla contendo ano e mês
                    if (ano in k) and (mes in k):
                        keys_to_drop.append(k)
                for k in keys_to_drop:
                    _run.pop(k, None)
                _st.session_state["_pag8_run"] = _run
        except Exception:
            pass
    except Exception:
        pass

# Epoch para invalidar cache local desta página
if "pag8_cache_epoch" not in st.session_state:
    st.session_state["pag8_cache_epoch"] = 0

# Epoch adicional acionado por mudanças em pagamentos (força refresh do SITUAÇÃO/prévias)
if "pag8_pay_epoch" not in st.session_state:
    st.session_state["pag8_pay_epoch"] = 0

def _epoch():
    # usa cache_epoch + pay_epoch
    try:
        return int(st.session_state.get("pag8_cache_epoch", 0)) + int(st.session_state.get("pag8_pay_epoch", 0))
    except Exception:
        return int(st.session_state.get("pag8_cache_epoch", 0))

# CSS para aumentar fonte dos rótulos de abas
st.markdown("""
<style>
/* Aumenta o tamanho e o peso dos títulos das abas nesta página */
div[data-testid="stTabs"] button[role="tab"] p {
  font-size: 1.0rem;  /* ajuste fino: 0.95–1.05rem */
  font-weight: 600;   /* 500–700 para mais destaque */
  margin: 0;
}
/* Cards e layout da aba Resumo */
.ir-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}
.ir-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.10);border-radius:10px;padding:12px 14px;}
.ir-head{display:flex;align-items:center;gap:.5rem;margin-bottom:.4rem;}
.ir-title{font-size:0.95rem;font-weight:700;letter-spacing:.01em;}
.ir-pill{display:inline-block;padding:.12rem .5rem;border:1px solid rgba(255,255,255,.25);border-radius:999px;font-size:.72rem;font-weight:600;letter-spacing:.02em;opacity:.9}
.ir-row{display:flex;align-items:center;justify-content:space-between;padding:.36rem 0;border-top:1px dashed rgba(255,255,255,.08);}
.ir-row:first-of-type{border-top:0;}
.ir-label{font-size:.9rem;color:rgba(255,255,255,.80);}
.ir-value{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600;}
.ir-section{margin-top:.4rem;margin-bottom:.2rem;font-size:.80rem;letter-spacing:.02em;color:rgba(255,255,255,.7);font-weight:700;text-transform:uppercase;}
.ir-inline{display:flex;align-items:center;justify-content:space-between;}
.ir-badge{display:inline-block;margin-left:.5rem;padding:.08rem .45rem;border:1px solid rgba(255,255,255,.25);border-radius:999px;font-size:.70rem;font-weight:600;letter-spacing:.02em;}
.ir-expander-pad { padding: 8px 12px 18px 12px; }
</style>
""", unsafe_allow_html=True)


def _handle_auth_error(exc):
    if tratar_erro_autenticacao(exc):
        st.stop()


# Sessão alinhada ao padrão do app (vide 7_Opções.py)
if "uid" not in st.session_state or not st.session_state.get("usuario"):
    redirecionar_para_login()

# --- Memoização local para chamadas pesadas (por sessão) ---
supabase = supabase_autenticado()
user_id = st.session_state["uid"]
_run = st.session_state.setdefault("_pag8_run", {})
def run_memo(key, fn):
    if key not in _run:
        _run[key] = fn()
    return _run[key]
# [IR-P2] Mensagem pós-ação (mostra no novo ciclo após st.rerun)
_last_action_msg = st.session_state.pop("_last_action", None)
if _last_action_msg:
    st.success(_last_action_msg)



# -------- Cached helpers (reduzem recomputo pesado) --------
# Chamada com retry automático em caso de JWT expirado
# -------- Cached helpers (reduzem recomputo pesado) --------
# Chamada com retry automático em caso de JWT expirado
#
# Versão do cache de contagem de operações (incrementar para invalidar cache persistente)
_OPS_COUNT_VER = 2

# [IR-LEDGER-P1] Ledger único cacheado
@st.cache_data(ttl=300, show_spinner=False, persist=True)
def _cached_ledger(uid: str, ano_ini: int, ano_fim: int, epoch: int):
    from utils_ir import carregar_ledger_mensal
    return carregar_ledger_mensal(supabase_autenticado(), uid, ano_ini, ano_fim, epoch)

def _retry_jwt(fn):
    try:
        return fn(supabase_autenticado())
    except Exception as e:
        # Se o token expirou, tenta renovar o client e refazer uma vez
        if "JWT expired" in str(e) or getattr(e, "code", None) == "PGRST301":
            return fn(supabase_autenticado())
        raise
# -------- Cached helpers (reduzem recomputo pesado) --------
@st.cache_data(ttl=30, show_spinner=False, persist=True)
def _cached_apurar_base(uid: str, ano: int, mes: int, epoch: int):
    return _retry_jwt(lambda sb: apurar_base_regime_mes(sb, uid, ano, mes, dep_epoch=epoch))

@st.cache_data(ttl=30, show_spinner=False, persist=True)
def _cached_apurar_comp(uid: str, ano: int, mes: int, epoch: int):
    return _retry_jwt(lambda sb: apurar_compensacao_mes(sb, uid, ano, mes, dep_epoch=epoch))

@st.cache_data(ttl=30, show_spinner=False, persist=True)
def _cached_carregar_ops(uid: str, ano: int, mes: int, epoch: int):
    import pandas as _pd
    df = _retry_jwt(lambda sb: carregar_operacoes_do_mes(sb, uid, ano, mes))
    return df.to_dict(orient="list")

@st.cache_data(ttl=30, show_spinner=False)
def _cached_diag(uid: str, ano: int, mes: int, tipo: str, epoch: int):
    return _retry_jwt(lambda sb: diagnostico_darf_mes(sb, uid, ano, mes, tipo))

@st.cache_data(ttl=30, show_spinner=False, persist=True)
def _cached_snapshot(uid: str, ano: int, mes: int, epoch: int):
    return _retry_jwt(lambda sb: ler_snapshot_ativo_mes(sb, uid, ano, mes))

@st.cache_data(ttl=30, show_spinner=False)
def _cached_listar_pag(uid: str, ano: int, mes: int, tipo: str, epoch: int):
    return _retry_jwt(lambda sb: listar_pagamentos_darf(sb, uid, ano, mes, tipo))

# --------- Helper para somar pagamentos de DARFs ---------
def _sum_val(itens, key="valor_pago"):
    try:
        return sum(float(x.get(key, 0) or 0) for x in itens)
    except Exception:
        return 0.0


# Diag para ambos os regimes em uma tacada só
@st.cache_data(ttl=120, show_spinner=False)
def _cached_diag_both(uid: str, ano: int, mes: int, epoch: int):
    return _retry_jwt(lambda sb: {
        "comum": diagnostico_darf_mes(sb, uid, ano, mes, "comum"),
        "daytrade": diagnostico_darf_mes(sb, uid, ano, mes, "daytrade"),
    })

# Listagem de pagamentos para ambos os regimes
@st.cache_data(ttl=120, show_spinner=False)
def _cached_listar_pag_both(uid: str, ano: int, mes: int, epoch: int):
    return _retry_jwt(lambda sb: {
        "comum": listar_pagamentos_darf(sb, uid, ano, mes, "comum") or [],
        "daytrade": listar_pagamentos_darf(sb, uid, ano, mes, "daytrade") or [],
    })

# [IRRF-IR-02] Cached helper for IRRF aggregation

@st.cache_data(ttl=30, show_spinner=False, persist=True)
def _cached_irrf(uid: str, ano: int, mes: int, modo: str, epoch: int):
    return _retry_jwt(lambda sb: agregar_irrf_mes_por_regime(sb, uid, ano, mes, modo))


# [IRRF-IR-ACUMULADO] Cached helper para saldo acumulado de IRRF e consumo do mês
@st.cache_data(ttl=60, show_spinner=False, persist=True)
def _irrf_acumulado_e_consumo(uid: str, ano: int, mes: int, reg: str, epoch: int):
    """
    Retorna (saldo_acumulado_apos, consumo_mes), onde:
      - saldo_acumulado_apos: saldo de IRRF remanescente ao final do mês `mes`
      - consumo_mes: quanto de IRRF foi consumido no mês `mes` (limitado ao IR devido do mês)
    Agora o cálculo **carrega entre anos**, acumulando o saldo desde os anos anteriores
    em ordem cronológica (FIFO) por mês.
    """
    try:
        regime_key = "NORMAL" if reg == "comum" else ("DAYTRADE" if reg == "daytrade" else None)
        if regime_key is None:
            return (0.0, 0.0)

        # 1) Determina os anos com operações para percorrer antes do ano corrente
        saldo = 0.0
        consumo_mes = 0.0
        try:
            ops = _cached_ops_count(uid, epoch) or {}
            anos_disponiveis = sorted((ops.get("years", {}) or {}).keys())
            anos_anteriores = [y for y in anos_disponiveis if isinstance(y, int) and y < int(ano) and (ops.get("years", {}).get(y, 0) or 0) > 0]
        except Exception:
            anos_anteriores = []

        # 2) Processa todos os meses dos anos anteriores (carrega saldo entre anos)
        for y in anos_anteriores:
            for k in range(1, 13):
                irrf_regs_k = _cached_irrf(uid, int(y), int(k), "abertura_total", epoch) or {}
                irrf_k = float((irrf_regs_k.get(regime_key, 0.0) or 0.0))
                diag_k = _cached_diag(uid, int(y), int(k), reg, epoch) or {}
                ir_dev_k = float((diag_k.get("ir_devido_mes", 0.0) or 0.0))
                consumo_k = min(ir_dev_k, saldo + irrf_k)
                saldo = (saldo + irrf_k) - consumo_k

        # 3) Processa meses do ano corrente até `mes`
        for k in range(1, int(mes) + 1):
            irrf_regs_k = _cached_irrf(uid, int(ano), int(k), "abertura_total", epoch) or {}
            irrf_k = float((irrf_regs_k.get(regime_key, 0.0) or 0.0))
            diag_k = _cached_diag(uid, int(ano), int(k), reg, epoch) or {}
            ir_dev_k = float((diag_k.get("ir_devido_mes", 0.0) or 0.0))
            consumo_k = min(ir_dev_k, saldo + irrf_k)
            if k == int(mes):
                consumo_mes = consumo_k
            saldo = (saldo + irrf_k) - consumo_k

        return (saldo, consumo_mes)
    except Exception:
        return (0.0, 0.0)

# [IRRF-BREAKDOWN] Helper: month-by-month breakdown for IRRF disponível (for tooltip)

@st.cache_data(ttl=60, show_spinner=False, persist=True)
def _irrf_breakdown_disponivel(uid: str, ano: int, mes: int, reg: str, epoch: int):
    """Retorna um dict {mes:int -> valor:float} dos meses que compõem o IRRF disponível exibido:
    saldo remanescente após consumos até (mes-1) + IRRF do mês `mes`.
    Agora considera **anos anteriores** também (FIFO entre anos). OBS: meses com o mesmo número
    de diferentes anos são agregados sob a mesma chave (Jan, Fev, ...).
    """
    try:
        regime_key = "NORMAL" if reg == "comum" else ("DAYTRADE" if reg == "daytrade" else None)
        if regime_key is None:
            return {}

        # Fila FIFO de (mes, valor) acumulada entre anos e meses
        fila = []

        # 1) Anos anteriores: adiciona IRRF e consome contra IR devido mês a mês
        try:
            ops = _cached_ops_count(uid, epoch) or {}
            anos_disponiveis = sorted((ops.get("years", {}) or {}).keys())
            anos_anteriores = [y for y in anos_disponiveis if isinstance(y, int) and y < int(ano) and (ops.get("years", {}).get(y, 0) or 0) > 0]
        except Exception:
            anos_anteriores = []

        for y in anos_anteriores:
            for k in range(1, 13):
                irrf_regs_k = _cached_irrf(uid, int(y), int(k), "abertura_total", epoch) or {}
                irrf_k = float((irrf_regs_k.get(regime_key, 0.0) or 0.0))
                if irrf_k > 0:
                    fila.append([int(k), irrf_k])
                diag_k = _cached_diag(uid, int(y), int(k), reg, epoch) or {}
                ir_dev_k = float((diag_k.get("ir_devido_mes", 0.0) or 0.0))
                consumir = ir_dev_k
                i = 0
                while consumir > 1e-9 and i < len(fila):
                    disp = fila[i][1]
                    take = min(disp, consumir)
                    fila[i][1] = disp - take
                    consumir -= take
                    if fila[i][1] <= 1e-9:
                        fila.pop(i)
                    else:
                        i += 1

        # 2) Ano corrente até (mes-1)
        for k in range(1, max(int(mes) - 1, 0) + 1):
            irrf_regs_k = _cached_irrf(uid, int(ano), int(k), "abertura_total", epoch) or {}
            irrf_k = float((irrf_regs_k.get(regime_key, 0.0) or 0.0))
            if irrf_k > 0:
                fila.append([int(k), irrf_k])
            diag_k = _cached_diag(uid, int(ano), int(k), reg, epoch) or {}
            ir_dev_k = float((diag_k.get("ir_devido_mes", 0.0) or 0.0))
            consumir = ir_dev_k
            i = 0
            while consumir > 1e-9 and i < len(fila):
                disp = fila[i][1]
                take = min(disp, consumir)
                fila[i][1] = disp - take
                consumir -= take
                if fila[i][1] <= 1e-9:
                    fila.pop(i)
                else:
                    i += 1

        # 3) Breakdown agregado por número do mês (nota: anos diferentes somam na mesma chave)
        breakdown = {}
        for k, val in fila:
            if val > 1e-9:
                breakdown[int(k)] = breakdown.get(int(k), 0.0) + float(val)

        # 4) Soma o IRRF do mês atual integralmente
        irrf_regs_m = _cached_irrf(uid, int(ano), int(mes), "abertura_total", epoch) or {}
        irrf_m = float((irrf_regs_m.get(regime_key, 0.0) or 0.0))
        if irrf_m > 1e-9:
            breakdown[int(mes)] = breakdown.get(int(mes), 0.0) + irrf_m
        return breakdown
    except Exception:
        return {}


# [IRRF-DARF-HTML] Helper para exibir IRRF disponível (saldo anterior + mês) com tooltip (HTML pronto)
@st.cache_data(ttl=60, show_spinner=False, persist=True)
def _irrf_disp_fmt_html(uid: str, ano: int, mes: int, reg: str, epoch: int) -> str:
    try:
        if reg not in ("comum", "daytrade"):
            return ''
        regime_key = "NORMAL" if reg == "comum" else "DAYTRADE"
        regs = _cached_irrf(uid, int(ano), int(mes), "abertura_total", epoch) or {}
        irrf_mes_val = float((regs.get(regime_key, 0.0) or 0.0))
        saldo_prev = 0.0
        if int(mes) > 1:
            saldo_prev, _ = _irrf_acumulado_e_consumo(uid, int(ano), int(mes) - 1, reg, epoch) or (0.0, 0.0)
        val = max((saldo_prev or 0.0) + (irrf_mes_val or 0.0), 0.0)
        out = _fmt_brl(val)
        # Tooltip de composição (apenas se houver >1 mês compondo)
        bd = _irrf_breakdown_disponivel(uid, int(ano), int(mes), reg, epoch) or {}
        _mes_abrev = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
        itens = [(k, v) for k, v in sorted(bd.items()) if v > 1e-9]
        if len(itens) > 1:
            tip = " | ".join([f"{_mes_abrev.get(int(k), k)}: {_fmt_brl(float(v))}" for k, v in itens])
            out = f'<span title="{tip}">{out}</span>'
        return out
    except Exception:
        return _fmt_brl(0.0)

# [IRRF-TOTAL-HTML] Helper para exibir IRRF disponível TOTAL (Comum + Day Trade) com tooltip (HTML pronto)
@st.cache_data(ttl=60, show_spinner=False, persist=True)
def _irrf_disp_fmt_total_html(uid: str, ano: int, mes: int, epoch: int) -> str:
    try:
        # Valor disponível por regime: saldo_prev(m-1) + irrf_mes(m), limitado a ≥0
        def _disp_reg(reg: str) -> float:
            regime_key = "NORMAL" if reg == "comum" else "DAYTRADE"
            regs = _cached_irrf(uid, int(ano), int(mes), "abertura_total", epoch) or {}
            irrf_m = float((regs.get(regime_key, 0.0) or 0.0))
            saldo_prev = 0.0
            if int(mes) > 1:
                saldo_prev, _ = _irrf_acumulado_e_consumo(uid, int(ano), int(mes) - 1, reg, epoch) or (0.0, 0.0)
            return max((saldo_prev or 0.0) + (irrf_m or 0.0), 0.0)

        val_c  = _disp_reg("comum")
        val_dt = _disp_reg("daytrade")
        total  = float(val_c) + float(val_dt)
        out = _fmt_brl(total)

        # Tooltip único: soma por mês dos breakdowns de ambos os regimes
        bd_c  = _irrf_breakdown_disponivel(uid, int(ano), int(mes), "comum", epoch) or {}
        bd_dt = _irrf_breakdown_disponivel(uid, int(ano), int(mes), "daytrade", epoch) or {}
        bd_tot = {}
        for k, v in (bd_c.items() if isinstance(bd_c, dict) else []):
            try:
                bd_tot[int(k)] = bd_tot.get(int(k), 0.0) + float(v or 0.0)
            except Exception:
                pass
        for k, v in (bd_dt.items() if isinstance(bd_dt, dict) else []):
            try:
                bd_tot[int(k)] = bd_tot.get(int(k), 0.0) + float(v or 0.0)
            except Exception:
                pass
        _mes_abrev = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
        itens = [(k, v) for k, v in sorted(bd_tot.items()) if v > 1e-9]
        if len(itens) > 1:
            tip = " | ".join([f"{_mes_abrev.get(int(k), k)}: {_fmt_brl(float(v))}" for k, v in itens])
            out = f'<span title="{tip}">{out}</span>'
        return out
    except Exception:
        return _fmt_brl(0.0)


# [IRRF-IR-PRÉVIA-CORRIGIDA] Helper: cálculo da prévia corrigida pelo ledger do IRRF para um regime
@st.cache_data(ttl=60, show_spinner=False)
def _previa_corrigida_regime(uid: str, ano: int, mes: int, reg: str, epoch: int):
    """Retorna um dicionário com a prévia corrigida por regime usando o ledger do IRRF.
    Campos:
      - ir_mes: IR devido bruto do mês (antes de IRRF)
      - consumo_irrf_mes: quanto de IRRF é consumido no mês (inclui o do mês)
      - base_pos_irrf: max(ir_mes - consumo, 0)
      - carry_sub10: carry acumulado (<10) do diagnóstico
      - total_cons_corr: base_pos_irrf com regra do mínimo (>=10) + carry_sub10
      - pagos_mes: soma de pagamentos de DARF do mês para o regime (com fallbacks)
      - sugerido_agora: max(total_cons_corr - pagos_mes, 0)
    """
    try:
        # Diagnóstico do mês para o regime
        diag = _cached_diag(uid, int(ano), int(mes), reg, epoch) or {}
        ir_mes = float((diag.get("ir_devido_mes", 0.0) or 0.0))
        carry_sub10 = float((diag.get("carry_sub10", 0.0) or 0.0))
        # Consumo IRRF acumulado (inclui o do mês)
        _, consumo_irrf_mes = _irrf_acumulado_e_consumo(uid, int(ano), int(mes), reg, epoch)
        base_pos_irrf = max(ir_mes - consumo_irrf_mes, 0.0)
        # Regra do mínimo: somente partes >= 10 entram como devido; o restante vira carry_sub10 (já fornecido pelo diag)
        parte_minima = base_pos_irrf if base_pos_irrf >= 10.0 else 0.0
        total_cons_corr = parte_minima + carry_sub10
        # Pagamentos do mês – mesma ordem de fontes usada no restante do app
        pagos_val = 0.0
        try:
            pagos_val = float(sum_pagamentos_darf(supabase_autenticado(), uid, int(ano), int(mes), reg) or 0.0)
        except Exception:
            pagos_val = 0.0
        if pagos_val <= 0.0:
            try:
                pagos_val = float((diag.get("pagos_mes", 0.0) or 0.0))
            except Exception:
                pass
        if pagos_val <= 0.0:
            try:
                # Reaproveita listagem leve (cacheada) de pagamentos
                _both = _cached_listar_pag_both(uid, int(ano), int(mes), epoch) or {}
                lst = (_both.get(reg, []) if isinstance(_both, dict) else []) or []
                pagos_val = _sum_val(lst, key="valor_pago")
            except Exception:
                pass
        sugerido_agora = max(total_cons_corr - (pagos_val or 0.0), 0.0)
        return {
            "ir_mes": ir_mes,
            "consumo_irrf_mes": float(consumo_irrf_mes or 0.0),
            "base_pos_irrf": base_pos_irrf,
            "carry_sub10": carry_sub10,
            "total_cons_corr": total_cons_corr,
            "pagos_mes": float(pagos_val or 0.0),
            "sugerido_agora": sugerido_agora,
        }
    except Exception:
        return {
            "ir_mes": 0.0,
            "consumo_irrf_mes": 0.0,
            "base_pos_irrf": 0.0,
            "carry_sub10": 0.0,
            "total_cons_corr": 0.0,
            "pagos_mes": 0.0,
            "sugerido_agora": 0.0,
        }

# [IRRF-IR-PRÉVIA-CORRIGIDA-TOTAL] Helper: calcula a PRÉVIA (Total) corrigida somando Comum, Day Trade e FII
@st.cache_data(ttl=60, show_spinner=False)
def _previa_corrigida_total(uid: str, ano: int, mes: int, epoch: int):
    """
    Agrega a prévia corrigida por regime para compor o card PRÉVIA DE IR (Total).
    Para FII, mantém a lógica atual (sem IRRF).
    Campos retornados:
      - ir_mes_total
      - total_cons_corr_total
      - pagos_total
      - sugerido_total
    """
    try:
        pc  = _previa_corrigida_regime(uid, int(ano), int(mes), "comum",    epoch) or {}
        pdt = _previa_corrigida_regime(uid, int(ano), int(mes), "daytrade", epoch) or {}
        # FII: usa diagnóstico do mês (sem IRRF)
        diag_fii = _cached_diag(uid, int(ano), int(mes), "fii", epoch) or {}
        ir_fii   = float((diag_fii.get("ir_devido_mes", 0.0) or 0.0))
        carry_f  = float((diag_fii.get("carry_sub10", 0.0) or 0.0))
        # total_considerado FII já vem do diag (regra do mínimo aplicada no backend)
        tot_fii  = float((diag_fii.get("total_considerado", 0.0) or 0.0))
        # pagamentos FII
        pagos_f  = 0.0
        try:
            pagos_f = float(sum_pagamentos_darf(supabase_autenticado(), uid, int(ano), int(mes), "fii") or 0.0)
        except Exception:
            pagos_f = 0.0
        if pagos_f <= 0.0:
            try:
                pagos_f = float((diag_fii.get("pagos_mes", 0.0) or 0.0))
            except Exception:
                pass
        if pagos_f <= 0.0:
            try:
                lst_f = _cached_listar_pag(uid, int(ano), int(mes), "fii", epoch) or []
                pagos_f = _sum_val(lst_f, key="valor_pago")
            except Exception:
                pass

        ir_mes_total          = float(pc.get("ir_mes", 0.0)) + float(pdt.get("ir_mes", 0.0)) + ir_fii
        total_cons_corr_total = float(pc.get("total_cons_corr", 0.0)) + float(pdt.get("total_cons_corr", 0.0)) + tot_fii
        pagos_total           = float(pc.get("pagos_mes", 0.0)) + float(pdt.get("pagos_mes", 0.0)) + pagos_f
        sugerido_total        = max(total_cons_corr_total - pagos_total, 0.0)

        return {
            "ir_mes_total": ir_mes_total,
            "total_cons_corr_total": total_cons_corr_total,
            "pagos_total": pagos_total,
            "sugerido_total": sugerido_total,
        }
    except Exception:
        return {
            "ir_mes_total": 0.0,
            "total_cons_corr_total": 0.0,
            "pagos_total": 0.0,
            "sugerido_total": 0.0,
        }

# --- Caches leves para carga inicial da página (evitam custo repetido na abertura) ---
@st.cache_data(ttl=300, show_spinner=False, persist=True)
def _cached_ops_count(uid: str, epoch: int, ver: int = _OPS_COUNT_VER):
    # NÃO passe o client como argumento cacheado para evitar hashing do _supabase
    sb = supabase_autenticado()
    try:
        return contar_operacoes_por_ano_mes(sb, uid)
    except Exception as exc:
        _handle_auth_error(exc)
        return {}

@st.cache_data(ttl=300, show_spinner=False, persist=True)
def _cached_compensacoes(uid: str, epoch: int):
    sb = supabase_autenticado()
    try:
        return sb.table("compensacoes_ir").select("*").eq("user_id", uid).execute().data
    except Exception as exc:
        _handle_auth_error(exc)
        return []

import pandas as pd
# --- Prefer real tab bar component if available ---

# Contagem consolidada (à vista + opções)
ops_count = _cached_ops_count(user_id, st.session_state["pag8_cache_epoch"], _OPS_COUNT_VER)

# Carrega compensações consolidadas (cache leve) para definir mês padrão
try:
    df_compensacoes = pd.DataFrame(_cached_compensacoes(user_id, st.session_state["pag8_cache_epoch"]))
except Exception:
    df_compensacoes = pd.DataFrame()

# Define ano e mês padrão para exibição inicial (considerando apenas meses com operações)
try:
    ano_padrao, mes_padrao = proxima_competencia_nao_consolidada_com_ops(df_compensacoes, ops_count)
except Exception:
    ano_padrao, mes_padrao = proxima_competencia_nao_consolidada(df_compensacoes)

# Warm-up dos principais caches para o mês/ano padrão
_ = run_memo(("diag_both", ano_padrao, mes_padrao, _epoch()), lambda: _cached_diag_both(user_id, ano_padrao, mes_padrao, _epoch()))
_ = run_memo(("irrf", ano_padrao, mes_padrao, _epoch()),     lambda: _cached_irrf(user_id, ano_padrao, mes_padrao, "abertura_total", _epoch()))
_ = run_memo(("ledger", ano_padrao, _epoch()),     lambda: _cached_ledger(user_id, ano_padrao, ano_padrao, _epoch()))

# Abas de ano (ordem crescente)
anos_ops = sorted(ops_count["years"].keys(), reverse=False)

def _year_has_ops(_ops_count: dict, _ano: int) -> bool:
    try:
        return sum(((_ops_count or {}).get("months", {}).get(_ano, {}) or {}).values()) > 0
    except Exception:
        return False

# Só força presença do ano padrão se ele realmente tiver operações
if isinstance(ano_padrao, int) and _year_has_ops(ops_count, ano_padrao):
    anos = sorted(set(list(nanos_ops := anos_ops) + [ano_padrao]), reverse=False)
else:
    anos = anos_ops

# Rótulos mostram a contagem de operações quando houver; caso contrário, 0
ano_labels = [f"{a} ({ops_count['years'].get(a, 0)})" for a in anos]

if not anos:
    st.info(
        "Você ainda não tem operações registradas para este usuário, "
        "então não há nada para calcular de Imposto de Renda.\n\n"
        "Assim que você lançar compras e vendas nas outras páginas do app, "
        "esta tela passará a exibir o resumo do IR mês a mês."
    )
    st.stop()

_default_year_label = (
    f"{ano_padrao} ({ops_count['years'].get(ano_padrao, 0)})"
    if (isinstance(ano_padrao, int) and (ano_padrao in anos)) else ano_labels[0]
)
tabs_anos = st.tabs(ano_labels, default=_default_year_label)

MESES = ["Janeiro","Fevereiro","Março","Abril","Maio","Junho","Julho",
         "Agosto","Setembro","Outubro","Novembro","Dezembro"]

# Helper para exibir competência em formato amigável ("Março 2022")
def _fmt_competencia_humana(ano: int, mes: int) -> str:
    try:
        return f"{MESES[int(mes)-1]} {int(ano)}"
    except Exception:
        # Fallback seguro
        try:
            return f"{int(ano)}-{int(mes):02d}"
        except Exception:
            return str(ano)

_today_perf = _dt_perf.date.today()
_curr_year_perf, _curr_month_perf = _today_perf.year, _today_perf.month

for idx, (tab, ano) in enumerate(zip(tabs_anos, anos)):
    with tab:
        mesi = ops_count["months"].get(ano, {})  # dict {1:n, 2:n, ...}
        # Mantém ordem natural dos meses (1..12); seleção inicial é feita via `default` do st.tabs
        ordem_meses = list(range(1, 13))

        mes_labels = [f"{MESES[mm-1]}".strip() for mm in ordem_meses]
        default_month_label = (
            mes_labels[mes_padrao - 1]
            if (ano == ano_padrao and (mes_padrao in ordem_meses))
            else mes_labels[0]
        )
        tabs_meses = st.tabs(mes_labels, default=default_month_label)
        _meses_iter = list(zip(tabs_meses, ordem_meses))

        if ano == ano_padrao:
            st.session_state.setdefault(f"pag8_calc_{ano}_{mes_padrao}", True)

        for idx_mes, (tmes, m) in enumerate(_meses_iter):
            with tmes:
                is_default_month = (ano == ano_padrao and m == mes_padrao)
                compute_key = f"pag8_calc_{ano}_{m}"
                compute_now = bool(st.session_state.get(compute_key, False))
                # Flag de "sujeira" (quando a base pode estar desatualizada e devemos forçar recálculo explícito)
                sujo = False
                try:
                    sujo = bool(is_mes_sujo(ano, m))
                except Exception:
                    sujo = False

                # Se não for o mês padrão E não tiver sido solicitado cálculo, ou se estiver "sujo", mostra o botão de calcular
                should_calculate = is_default_month or compute_now
                if not should_calculate:
                    st.caption("Carregamento sob demanda: esta aba ainda não foi calculada." if not sujo else "Este mês mudou desde o último cálculo. Clique para recalcular.")
                    btn_txt = "Calcular este mês" if not sujo else "Calcular Mês"
                    if st.button(btn_txt, key=f"btn_calc_{ano}_{m}"):
                        st.session_state[compute_key] = True
                        st.rerun()
                    continue
                import pandas as _pd
                # Marca o mês como calculado nesta sessão (limpa a "sujeira" de UI)
                try:
                    marcar_mes_calculado(ano, m)
                except Exception:
                    pass
                # [REFATORADO] Carrega operações do mês: sempre tenta nocache se cache vazio,
                # e atualiza ops_count local se encontrar dados.
                _df_label_dict = _cached_carregar_ops(user_id, ano, m, st.session_state["pag8_cache_epoch"]) or {}
                df = _pd.DataFrame(_df_label_dict)
                try:
                    n_ops_hint = int(((ops_count or {}).get("months", {}).get(ano, {}) or {}).get(m, 0) or 0)
                except Exception:
                    n_ops_hint = 0

                # Se o cache veio vazio, SEMPRE tenta um carregamento direto (sem cache),
                # independente de n_ops_hint, para capturar operações recentes ou contagem desatualizada.
                def _reload_ops_from_db():
                    try:
                        from utils_ir import carregar_operacoes_do_mes as _carregar_ops_nocache
                        _sb = supabase_autenticado()
                        dep_epoch = _epoch()
                        return _carregar_ops_nocache(_sb, user_id, ano, m, dep_epoch, force_refresh=True)
                    except Exception:
                        return None

                # Recarrega quando o cache veio vazio ou quando o contador indica mais operações do que o DataFrame atual.
                if df.empty or (n_ops_hint > 0 and df.shape[0] < n_ops_hint):
                    df_nc = _reload_ops_from_db()
                    if df_nc is not None and hasattr(df_nc, "empty") and (not df_nc.empty):
                        df = df_nc.copy()
                        # Atualiza o ops_count local para este mês/ano (evita rótulo incorreto na aba)
                        try:
                            ops_count.setdefault("months", {}).setdefault(ano, {})[m] = int(df.shape[0])
                            _months_map = ops_count.get("months", {}).get(ano, {}) or {}
                            ops_count.setdefault("years", {})[ano] = int(sum(int(v or 0) for v in _months_map.values()))
                        except Exception:
                            pass

                n_ops_eff = 0 if df.empty else int(df.shape[0])
                _is_current_month = (ano == _curr_year_perf and m == _curr_month_perf)

                # NEW: prova de vida por resumo (captura operações à vista/BDR/FII quando o df de operações vier vazio)
                _has_resumo_mov = False
                try:
                    _resumo_probe = obter_resumo_categorias_mes(supabase, user_id, ano, m) or {}
                    def _sum_vals(d):
                        try:
                            return float(d.get("acoes", 0.0)) + float(d.get("bdrefffii", 0.0)) + float(d.get("opcoes", 0.0)) + float(d.get("fiis", 0.0))
                        except Exception:
                            try:
                                return sum(float(v or 0.0) for v in (d or {}).values())
                            except Exception:
                                return 0.0
                    _has_resumo_mov = (_sum_vals(_resumo_probe.get("comum", {})) + _sum_vals(_resumo_probe.get("dt", {}))) != 0.0
                except Exception:
                    _has_resumo_mov = False

                # Só mostra "Sem operações" se não houver df nem movimento detectado pelo resumo
                if (n_ops_eff == 0) and (not _has_resumo_mov) and (not _is_current_month):
                    st.caption("Sem operações neste mês.")
                    _sub_tabs_placeholder = st.tabs(["Resumo", f"Operações (0)", "DARF"])
                    with _sub_tabs_placeholder[0]:
                        st.empty()
                    with _sub_tabs_placeholder[1]:
                        st.empty()
                    with _sub_tabs_placeholder[2]:
                        st.empty()
                    continue
                # Memoize ledger, diag_both, pags_both, snapshot
                ledger_cache = run_memo(("ledger", ano, _epoch()), lambda: _cached_ledger(user_id, ano, ano, _epoch())) or {}
                snap = run_memo(("snapshot", ano, m, _epoch()), lambda: _cached_snapshot(user_id, ano, m, _epoch()))
                _diag_both = run_memo(("diag_both", ano, m, _epoch()), lambda: _cached_diag_both(user_id, ano, m, _epoch())) or {}
                _pags_both = run_memo(("listar_pag_both", ano, m, _epoch()), lambda: _cached_listar_pag_both(user_id, ano, m, _epoch())) or {}

                lcol, rcol = st.columns([1.6, 1])

                # --- Mini-card SITUAÇÃO (esquerda) ---
                with lcol:
                    # Fonte única de verdade para SITUAÇÃO/Badges
                    status = (ledger_cache.get((ano, m)) or {}).get("status", {"rotulo": "–", "valor": 0.0})

                    # Badge de Consolidação: baseado na existência de snapshot ativo para qualquer regime
                    _snap_local = snap if isinstance(snap, dict) else {}
                    _has_snapshot_local = bool(_snap_local.get("comum")) or bool(_snap_local.get("daytrade")) or bool(_snap_local.get("fii"))
                    consol_text = "Fechado" if _has_snapshot_local else "Aberto"
                    consol_color = "#43A047" if _has_snapshot_local else "#FDD835"
                    consol_title = ""

                    # [IR-P31] Badge "Recalcular" quando prévia ≠ snapshot (base mudou)
                    try:
                        diag_c = (_diag_both.get("comum") if isinstance(_diag_both, dict) else {}) or {}
                        diag_dt = (_diag_both.get("daytrade") if isinstance(_diag_both, dict) else {}) or {}
                        diag_fii = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", _epoch())) or {}

                        def _diverge_reg(d, reg: str):
                            try:
                                snap_reg = (_snap_local.get(reg) if isinstance(_snap_local, dict) else None)
                                if not snap_reg:
                                    return False
                                ir_mes = float(d.get("ir_devido_mes", 0.0) or 0.0)
                                snap_ir_dev = float(snap_reg.get("ir_devido_tipo", 0.0) or 0.0)
                                return abs(ir_mes - snap_ir_dev) >= 0.01
                            except Exception:
                                return False

                        diverge_now = _diverge_reg(diag_c, "comum") or _diverge_reg(diag_dt, "daytrade") or _diverge_reg(diag_fii, "fii")
                        if diverge_now:
                            consol_text = "Recalcular"
                            consol_color = "#FB8C00"  # laranja
                            consol_title = "Prévia difere do snapshot. Clique em Recalcular Mês."
                    except Exception:
                        pass

                    # [IR-P53] Badges por regime com estados: Devido / Pago – / Isento / Pago / Pago +
                    def _fmt_brl_local(v: float) -> str:
                        try:
                            return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")
                        except Exception:
                            return "R$ 0,00"

                    def _sum_pagos(lst):
                        try:
                            return sum(float(r.get("valor_pago", 0.0) or 0.0) for r in (lst or []))
                        except Exception:
                            return 0.0

                    # Coleta diagnósticos e pagamentos por regime
                    diag_c  = (_diag_both.get("comum") if isinstance(_diag_both, dict) else {}) or {}
                    diag_dt = (_diag_both.get("daytrade") if isinstance(_diag_both, dict) else {}) or {}
                    diag_fii = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", _epoch())) or {}

                    # Preferência: override local (pós-ação) -> cache both -> cache unitário
                    _ovr_key_c  = f"pag8_pay_override_{ano}_{m}_comum"
                    _ovr_key_dt = f"pag8_pay_override_{ano}_{m}_daytrade"
                    _ovr_key_f  = f"pag8_pay_override_{ano}_{m}_fii"

                    pags_c = []
                    if _ovr_key_c in st.session_state:
                        pags_c = st.session_state.get(_ovr_key_c) or []
                    if not pags_c:
                        pags_c = (_pags_both.get("comum") if isinstance(_pags_both, dict) else []) or []
                    if not pags_c:
                        pags_c = run_memo(("listar_pag", ano, m, "comum"), lambda: _cached_listar_pag(user_id, ano, m, "comum", _epoch())) or []

                    pags_dt = []
                    if _ovr_key_dt in st.session_state:
                        pags_dt = st.session_state.get(_ovr_key_dt) or []
                    if not pags_dt:
                        pags_dt = (_pags_both.get("daytrade") if isinstance(_pags_both, dict) else []) or []
                    if not pags_dt:
                        pags_dt = run_memo(("listar_pag", ano, m, "daytrade"), lambda: _cached_listar_pag(user_id, ano, m, "daytrade", _epoch())) or []

                    pags_f = []
                    if _ovr_key_f in st.session_state:
                        pags_f = st.session_state.get(_ovr_key_f) or []
                    if not pags_f:
                        pags_f = run_memo(("listar_pag", ano, m, "fii"), lambda: _cached_listar_pag(user_id, ano, m, "fii", _epoch())) or []

                    def _badge_reg(diag: dict, pagamentos: list, regime: str):
                        """Gera o badge de situação usando a PRÉVIA CORRIGIDA pelo ledger de IRRF.
                        Mantém a mesma semântica dos rótulos (Isento, Abaixo do mínimo, Devido, Pago –, Pago, Pago +).
                        """
                        # Fonte única: prévia corrigida por regime (já líquida de IRRF e com regra do mínimo)
                        try:
                            pc = run_memo(("previa_corrigida_regime", ano, m, regime, _epoch()), lambda: _previa_corrigida_regime(user_id, ano, m, regime, _epoch())) or {}
                        except Exception:
                            pc = {}

                        total_cons = float(pc.get("total_cons_corr", 0.0) or 0.0)
                        pagos      = float(pc.get("pagos_mes", 0.0) or 0.0)

                        # 1) Isento: nenhum imposto devido (total_cons <= 0)
                        if total_cons <= 0.0:
                            return ("Isento", "#9e9e9e", "Sem imposto devido")

                        # 2) Abaixo do mínimo: 0 < total_cons < 10 (independe de pagamentos)
                        if 0.0 < total_cons < 10.0:
                            return ("Abaixo do mínimo", "#9e9e9e", "Transportado para o próximo mês")

                        # 3) total_cons ≥ 10: calcular saldo em aberto com base no que já foi pago
                        devido_now = max(total_cons - pagos, 0.0)

                        # 3.1) Nenhum pagamento e saldo ≥ 10 → Devido (vermelho)
                        if devido_now >= 10.0 and pagos <= 0.0:
                            return ("Devido", "#e53935", f"Nenhum pagamento. Devido agora: {_fmt_brl_local(devido_now)}")

                        # 3.2) Já houve pagamento e ainda falta ≥ 10 → Pago – (laranja)
                        if devido_now >= 10.0 and pagos > 0.0:
                            return ("Pago –", "#FB8C00", f"Devido agora: {_fmt_brl_local(devido_now)} (já pago: {_fmt_brl_local(pagos)})")

                        # 3.3) Quitado ~0 → Pago (verde)
                        if abs(devido_now) < 0.01:
                            return ("Pago", "#43A047", ("Quitado por DARF" if pagos > 0.0 else "Quitado por IRRF (sem DARF)"))

                        # 3.4) Crédito (pagou a maior) → só se houve DARF
                        if devido_now < -0.01 and pagos > 0.0:
                            return ("Pago +", "#7E57C2", f"Crédito: {_fmt_brl_local(abs(devido_now))}")

                        # Caso restante (saldo entre 0 e 10 após pagamentos): abaixo do mínimo
                        if 0.0 < devido_now < 10.0:
                            return ("Abaixo do mínimo", "#9e9e9e", "Transportado para o próximo mês")

                        # Fallback seguro
                        return ("Pago", "#43A047", "Sem saldo relevante")

                    b_comum_text, b_comum_color, b_comum_tip = _badge_reg(diag_c, pags_c, "comum")
                    b_dt_text,    b_dt_color,    b_dt_tip    = _badge_reg(diag_dt, pags_dt, "daytrade")
                    b_fii_text,   b_fii_color,   b_fii_tip   = _badge_reg(diag_fii, pags_f, "fii")

                    st.markdown(
                        f"""
                        <div class="ir-card" style="margin-bottom:.5rem;">
                          <div class="ir-head">
                            <div class="ir-title">SITUAÇÃO</div>
                          </div>
                          <div class="ir-inline" style="gap:.25rem; flex-wrap:nowrap; align-items:center;">
                            <div class="ir-label">Consolidação</div>
                            <span class="ir-pill" title="{consol_title}" style="border-color:{consol_color}; color:{consol_color};">{consol_text}</span>
                            <div class="ir-label" style="margin-left:.25rem;">Comum</div>
                            <span class="ir-pill" title="{b_comum_tip}" style="border-color:{b_comum_color}; color:{b_comum_color};">{b_comum_text}</span>
                            <div class="ir-label" style="margin-left:.25rem;">Day Trade</div>
                            <span class="ir-pill" title="{b_dt_tip}" style="border-color:{b_dt_color}; color:{b_dt_color};">{b_dt_text}</span>
                            <div class="ir-label" style="margin-left:.25rem;">FII</div>
                            <span class="ir-pill" title="{b_fii_tip}" style="border-color:{b_fii_color}; color:{b_fii_color};">{b_fii_text}</span>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                # [IR-P07] Alerta global de divergência snapshot vs prévia (baseado em diagnósticos)
                try:
                    # Usa os mesmos sinais já utilizados na aba DARF
                    diag_c = (_diag_both.get("comum") if isinstance(_diag_both, dict) else {}) or {}
                    diag_dt = (_diag_both.get("daytrade") if isinstance(_diag_both, dict) else {}) or {}
                    diag_fii = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", _epoch())) or {}

                    def _diverge(d, reg: str):
                        try:
                            snap_reg = (snap.get(reg) if isinstance(snap, dict) else None)
                            if not snap_reg:
                                return False
                            ir_mes = float(d.get("ir_devido_mes", 0.0) or 0.0)
                            snap_ir_dev = float(snap_reg.get("ir_devido_tipo", 0.0) or 0.0)
                            return abs(ir_mes - snap_ir_dev) >= 0.01
                        except Exception:
                            return False

                    if _diverge(diag_c, "comum") or _diverge(diag_dt, "daytrade") or _diverge(diag_fii, "fii"):
                        st.warning("A base de cálculo mudou desde a última consolidação.", icon="⚠️")
                except Exception:
                    pass

                # --- Ações (direita) ---
                with rcol:
                    # Se já existe snapshot ativo (comum ou daytrade), trocar o rótulo
                    has_snapshot = False
                    if isinstance(snap, dict):
                        has_snapshot = bool(snap.get("comum")) or bool(snap.get("daytrade")) or bool(snap.get("fii"))
                    btn_label_base = "Recalcular Mês" if has_snapshot else "Consolidar Mês"
                    btn_label = "💾 " + btn_label_base

                    confirm_key = f"confirm_consol_{ano}_{m}"

                    if st.button(btn_label, key=f"consol_{ano}_{m}"):
                        try:
                            # Usa PRÉVIA oficial para confirmação (SEM cache: chamada direta ao backend)
                            def _diag_nocache(_reg: str):
                                return _retry_jwt(lambda sb: diagnostico_darf_mes(sb, user_id, ano, m, _reg)) or {}

                            diag_comum = _diag_nocache("comum")
                            diag_dt    = _diag_nocache("daytrade")
                            diag_fii   = _diag_nocache("fii")

                            dados_comum = {
                                "ir_devido_mes": float(diag_comum.get("ir_devido_mes", 0.0)),
                                "carry_sub10": float(diag_comum.get("carry_sub10", 0.0)),
                                "total_considerado": float(diag_comum.get("total_considerado", 0.0)),
                                "pagos_mes": float(diag_comum.get("pagos_mes", 0.0)),
                            }
                            dados_dt = {
                                "ir_devido_mes": float(diag_dt.get("ir_devido_mes", 0.0)),
                                "carry_sub10": float(diag_dt.get("carry_sub10", 0.0)),
                                "total_considerado": float(diag_dt.get("total_considerado", 0.0)),
                                "pagos_mes": float(diag_dt.get("pagos_mes", 0.0)),
                            }
                            dados_fii = {
                                "ir_devido_mes": float(diag_fii.get("ir_devido_mes", 0.0)) if diag_fii else 0.0,
                                "carry_sub10": float(diag_fii.get("carry_sub10", 0.0)) if diag_fii else 0.0,
                                "total_considerado": float(diag_fii.get("total_considerado", 0.0)) if diag_fii else 0.0,
                                "pagos_mes": float(diag_fii.get("pagos_mes", 0.0)) if diag_fii else 0.0,
                            }

                            need_confirm = (
                                (dados_comum["total_considerado"] >= 10.0 and (dados_comum["pagos_mes"] or 0.0) == 0.0)
                                or
                                (dados_dt["total_considerado"]    >= 10.0 and (dados_dt["pagos_mes"] or 0.0)    == 0.0)
                                or
                                (dados_fii["total_considerado"]   >= 10.0 and (dados_fii["pagos_mes"] or 0.0)   == 0.0)
                            )

                            if need_confirm and not st.session_state.get(confirm_key):
                                # Armazena contexto e solicita confirmação
                                st.session_state[confirm_key] = {
                                    "comum": dados_comum,
                                    "daytrade": dados_dt,
                                    "fii": dados_fii,
                                }
                            else:
                                # Prossegue com a consolidação diretamente
                                with st.spinner("Consolidando..."):
                                    consolidar_competencia_mes(supabase, user_id, ano, m)
                                # Invalida memo leve e força recálculo manual ao voltar para o mês
                                _pag8__invalidate_after_consolidation(ano, m)
                                st.session_state["_last_action"] = f"Competência consolidada com sucesso — {_fmt_competencia_humana(ano, m)}"
                                st.session_state["pag8_cache_epoch"] += 1
                                st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao consolidar: {e}")

                # --- Confirmação global (aparece abaixo dos cards e do botão) ---
                if st.session_state.get(confirm_key):
                    with st.container(border=True):
                        st.markdown(
                            "<div class='ir-head'><div class='ir-title'>Confirmação</div><span class='ir-pill'>Ação necessária</span></div>",
                            unsafe_allow_html=True
                        )
                        st.markdown(
                            "Você ainda não registrou pagamento de DARF para este mês. "
                            "A ordem recomendada é registrar a DARF primeiro e consolidar em seguida. "
                            "Caso prefira, você pode prosseguir mesmo assim."
                        )
                        cbtn1, cbtn2, _ = st.columns([1, 1, 2])
                        with cbtn1:
                            if st.button('✅ Consolidar agora', key=f'confirm_yes_{ano}_{m}'):
                                try:
                                    with st.spinner('Consolidando...'):
                                        consolidar_competencia_mes(supabase, user_id, ano, m)
                                    # Invalida memo leve e força recálculo manual ao voltar para o mês
                                    _pag8__invalidate_after_consolidation(ano, m)
                                    # Evita re-render pesado duplo
                                    st.session_state['_last_action'] = f"Competência consolidada com sucesso — {_fmt_competencia_humana(ano, m)}"
                                    st.session_state['pag8_cache_epoch'] += 1
                                    st.session_state.pop(confirm_key, None)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f'Erro ao consolidar: {e}')
                        with cbtn2:
                            if st.button('❌ Cancelar', key=f'confirm_no_{ano}_{m}'):
                                st.session_state.pop(confirm_key, None)
                                st.rerun()

                # Usa o df já pré-carregado acima e sua contagem real
                sub_tabs = st.tabs(["Resumo", f"Operações ({n_ops_eff})", "DARF"])

                # [P2c] Fonte única para listagem de pagamentos (usa override → cache both → cache unitário)
                def _pag8_pags_for(uid: str, ano: int, mes: int, reg: str, _pags_both_dict: dict):
                    import streamlit as _st
                    try:
                        _ovr_key = f"pag8_pay_override_{int(ano)}_{int(mes)}_{reg}"
                    except Exception:
                        _ovr_key = f"pag8_pay_override_{ano}_{mes}_{reg}"
                    # 1) Preferência: override local (pós-ação)
                    if _ovr_key in _st.session_state:
                        _lst = _st.session_state.get(_ovr_key) or []
                        if isinstance(_lst, list) and _lst:
                            return _lst
                    # 2) Fallback: cache leve de ambos regimes
                    try:
                        _lst = (_pags_both_dict.get(reg) if isinstance(_pags_both_dict, dict) else []) or []
                        if isinstance(_lst, list) and _lst:
                            return _lst
                    except Exception:
                        pass
                    # 3) Fallback final: cache unitário
                    try:
                        return _cached_listar_pag(uid, int(ano), int(mes), reg, _epoch()) or []
                    except Exception:
                        try:
                            return _cached_listar_pag(uid, ano, mes, reg, _epoch()) or []
                        except Exception:
                            return []

                # [PAY-LIST][SOURCE] Fonte única para listagem com override → cache both → cache unitário
                # (inserido logo após sub_tabs para garantir padrão em todas as abas)
                _pags_both = run_memo(("listar_pag_both", ano, m, _epoch()), lambda: _cached_listar_pag_both(user_id, ano, m, _epoch())) or {}
                pags_c  = _pag8_pags_for(user_id, ano, m, "comum", _pags_both)
                pags_dt = _pag8_pags_for(user_id, ano, m, "daytrade", _pags_both)
                pags_f  = _pag8_pags_for(user_id, ano, m, "fii", _pags_both)
                with sub_tabs[0]:
                    # ===== UI da aba Resumo (somente layout; sem cálculos) =====
                    # Carrega CSS apenas uma vez por sessão
                    if not st.session_state.get("pag8_resumo_css_loaded"):
                        st.markdown("""
                        <style>
                        /* Cards e layout da aba Resumo */
                        .ir-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;}
                        .ir-card{background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.10);border-radius:10px;padding:12px 14px;}
                        .ir-head{display:flex;align-items:center;gap:.5rem;margin-bottom:.4rem;}
                        .ir-title{font-size:0.95rem;font-weight:700;letter-spacing:.01em;}
                        .ir-pill{display:inline-block;padding:.12rem .5rem;border:1px solid rgba(255,255,255,.25);border-radius:999px;font-size:.72rem;font-weight:600;letter-spacing:.02em;opacity:.9}
                        .ir-row{display:flex;align-items:center;justify-content:space-between;padding:.36rem 0;border-top:1px dashed rgba(255,255,255,.08);}
                        .ir-row:first-of-type{border-top:0;}
                        .ir-label{font-size:.9rem;color:rgba(255,255,255,.80);}
                        .ir-value{font-variant-numeric:tabular-nums;white-space:nowrap;font-weight:600;}
                        .ir-section{margin-top:.4rem;margin-bottom:.2rem;font-size:.80rem;letter-spacing:.02em;color:rgba(255,255,255,.7);font-weight:700;text-transform:uppercase;}
                        .ir-inline{display:flex;align-items:center;justify-content:space-between;}
                        .ir-badge{display:inline-block;margin-left:.5rem;padding:.08rem .45rem;border:1px solid rgba(255,255,255,.25);border-radius:999px;font-size:.70rem;font-weight:600;letter-spacing:.02em;}
                        .ir-expander-pad { padding: 8px 12px 18px 12px; }
                        </style>
                        """, unsafe_allow_html=True)
                        st.session_state["pag8_resumo_css_loaded"] = True
                    
                    # ==== RESUMO DO MÊS (valores para cards e detalhes) ====
                    import pandas as pd
                    # [IR-P60] Divergência por regime para rótulos das abas (Comum/DT/FII)
                    def _diverge_reg_local(_diag: dict, reg: str) -> bool:
                        try:
                            if not _diag:
                                return False
                            _snap_reg = (snap.get(reg) if isinstance(snap, dict) else None)
                            if not _snap_reg:
                                return False
                            _ir_mes = float(_diag.get("ir_devido_mes", 0.0) or 0.0)
                            _snap_ir = float(_snap_reg.get("ir_devido_tipo", 0.0) or 0.0)
                            return abs(_ir_mes - _snap_ir) >= 0.01
                        except Exception:
                            return False

                    # Diagnósticos locais para a aba Resumo
                    diag_comum = run_memo(("diag", ano, m, "comum"), lambda: _cached_diag(user_id, ano, m, "comum", _epoch())) or {}
                    diag_dt    = run_memo(("diag", ano, m, "daytrade"), lambda: _cached_diag(user_id, ano, m, "daytrade", _epoch())) or {}
                    diag_fii   = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", _epoch())) or {}

                    dvg_c   = _diverge_reg_local(diag_comum or {}, "comum")
                    dvg_dt  = _diverge_reg_local(diag_dt    or {}, "daytrade")
                    dvg_fii = _diverge_reg_local(diag_fii   or {}, "fii")

                    label_c  = "Comum ⚠️" if dvg_c else "Comum"
                    label_dt = "Day Trade ⚠️" if dvg_dt else "Day Trade"
                    label_f  = "FII ⚠️" if dvg_fii else "FII"

                    def _fmt_brl(v: float) -> str:
                        try:
                            return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")
                        except Exception:
                            return "R$ 0,00"
                    _m_ledger = (ledger_cache.get((ano, m)) or {})
                    _resumo_ledger = _m_ledger.get("resumo")
                    resumo = _resumo_ledger or obter_resumo_categorias_mes(supabase, user_id, ano, m)
                    # Agregados por coluna
                    total_comum = float(resumo["comum"]["acoes"]) + float(resumo["comum"]["bdrefffii"]) + float(resumo["comum"]["opcoes"])
                    total_dt    = float(resumo["dt"]["acoes"])    + float(resumo["dt"]["bdrefffii"])    + float(resumo["dt"]["opcoes"])

                    vendas_acoes_fmt = _fmt_brl(resumo["comum"]["vendas_acoes_total"])
                    c_acoes   = _fmt_brl(resumo["comum"]["acoes"])
                    c_bdreff  = _fmt_brl(resumo["comum"]["bdrefffii"])
                    c_opcoes  = _fmt_brl(resumo["comum"]["opcoes"])
                    c_total   = _fmt_brl(total_comum)
                    c_fiis    = _fmt_brl(resumo["comum"].get("fiis", 0.0))

                    dt_acoes  = _fmt_brl(resumo["dt"]["acoes"])
                    dt_bdreff = _fmt_brl(resumo["dt"]["bdrefffii"])
                    dt_opcoes = _fmt_brl(resumo["dt"]["opcoes"])
                    dt_total  = _fmt_brl(total_dt)
                    dt_fiis   = _fmt_brl(resumo["dt"].get("fiis", 0.0))

                    # === Regra de Isenção 20k (apenas Ações Comum/swing) ===
                    _isencao_ledger = _m_ledger.get("isencao")
                    isencao = _isencao_ledger or apurar_isencao_20k_mes(supabase, user_id, ano, m)
                    isencao_str = "Sim" if isencao.get("isencao_aplicada") else "Não"
                    c_acoes_trib = _fmt_brl(isencao.get("lucro_tributavel_acoes", 0.0))
                    c_acoes_isento = _fmt_brl(isencao.get("lucro_isento_acoes", 0.0))

                    # Recalcula total da coluna COMUM usando o lucro TRIBUTÁVEL de ações
                    total_comum_val = float(resumo["comum"]["bdrefffii"]) + float(resumo["comum"]["opcoes"]) + float(isencao.get("lucro_tributavel_acoes", 0.0))
                    c_total = _fmt_brl(total_comum_val)

                    # === IR devido por regime (base bruta) + compensação (C1) ===
                    _bases_ledger = _m_ledger.get("bases")
                    bases = _bases_ledger or _cached_apurar_base(user_id, ano, m, _epoch())

                    # Compensação do mês por regime (usa carry-in de compensacoes_ir)
                    _comp_ledger = _m_ledger.get("comp")
                    comp = _comp_ledger or _cached_apurar_comp(user_id, ano, m, _epoch())


                    # FORMATOS – COMUM
                    comp_comum_fmt = _fmt_brl((comp.get("NORMAL") or {}).get("compensado", 0.0))
                    basepos_comum_fmt = _fmt_brl((comp.get("NORMAL") or {}).get("base_pos", 0.0))
                    ir_comum_fmt = _fmt_brl((comp.get("NORMAL") or {}).get("ir_devido", 0.0))
                    prej_comum_fmt = _fmt_brl((comp.get("NORMAL") or {}).get("prejuizo_restante", 0.0))

                    # FORMATOS – DAY TRADE
                    comp_dt_fmt = _fmt_brl((comp.get("DAYTRADE") or {}).get("compensado", 0.0))
                    basepos_dt_fmt = _fmt_brl((comp.get("DAYTRADE") or {}).get("base_pos", 0.0))
                    ir_dt_fmt = _fmt_brl((comp.get("DAYTRADE") or {}).get("ir_devido", 0.0))
                    prej_dt_fmt = _fmt_brl((comp.get("DAYTRADE") or {}).get("prejuizo_restante", 0.0))

                    # [DARF-IRRF] Exibição do IRRF disponível (saldo anterior + mês) com tooltip (FIFO)

                    # === Snapshot consolidado (se existir) para IR a recolher e status ===
                    snap = run_memo(("snapshot", ano, m), lambda: _cached_snapshot(user_id, ano, m, st.session_state["pag8_cache_epoch"]))

                    def _ir_e_badge(reg):
                        """
                        Usa a PRÉVIA corrigida por regime (que já contempla IRRF acumulado + carry_sub10),
                        e aplica a mesma semântica de badges utilizada no mini-card SITUAÇÃO.
                        Retorna (valor_fmt, badge_txt).
                        """
                        try:
                            pc = run_memo(("previa_corrigida_regime", ano, m, reg, _epoch()), lambda: _previa_corrigida_regime(user_id, ano, m, reg, _epoch())) or {}
                        except Exception:
                            pc = {}

                        total_cons = float(pc.get("total_cons_corr", 0.0) or 0.0)   # já inclui carry_sub10
                        pagos      = float(pc.get("pagos_mes", 0.0) or 0.0)
                        devido_now = max(total_cons - pagos, 0.0)

                        # Semântica dos badges
                        if total_cons <= 0.0:
                            return ("Não devido", "Isento")

                        if 0.0 < total_cons < 10.0:
                            return ("Não devido", "Abaixo do mínimo")

                        # total_cons >= 10.0
                        if abs(devido_now) < 0.01:
                            # quitado por DARF ou IRRF (prévia já desconta IRRF no total_cons)
                            return (_fmt_brl(0.0), "Pago")

                        if pagos <= 0.0:
                            # há devido e nada pago no mês
                            return (_fmt_brl(devido_now), "Devido")

                        # houve pagamento, mas ainda resta saldo
                        return (_fmt_brl(devido_now), ("Pago –" if devido_now >= 10.0 else "Abaixo do mínimo"))

                    ir_a_rec_comum_fmt, badge_comum = _ir_e_badge("comum")
                    ir_a_rec_dt_fmt, badge_dt = _ir_e_badge("daytrade")

                    # [IRRF-RESUMO] Fonte única para exibição do IRRF disponível (saldo anterior + mês) com tooltip
                    try:
                        # 1) Preferir o que já veio no ledger da página (quando disponível)
                        _m_ledger_local = (ledger_cache.get((ano, m)) or {})
                        _irrf_from_ledger = _m_ledger_local.get("irrf_regs")
                        irrf_regs = _irrf_from_ledger if isinstance(_irrf_from_ledger, dict) else None

                        # 2) Fallback para o agregado oficial cacheado da abertura (abertura_total)
                        if not isinstance(irrf_regs, dict):
                            irrf_regs = run_memo(
                                ("irrf", ano, m, _epoch()),
                                lambda: _cached_irrf(user_id, ano, m, "abertura_total", _epoch())
                            ) or {}
                    except Exception:
                        irrf_regs = {}

                    def _irrf_disp_fmt_resumo(_reg_alias: str, _reg_key: str) -> str:
                        try:
                            irrf_mes = float((irrf_regs.get(_reg_key, 0.0) or 0.0))
                            saldo_prev = 0.0
                            if m > 1:
                                saldo_prev, _ = _irrf_acumulado_e_consumo(user_id, ano, m - 1, _reg_alias, _epoch()) or (0.0, 0.0)
                            val = max((saldo_prev or 0.0) + (irrf_mes or 0.0), 0.0)
                            out = _fmt_brl(val)
                            # Tooltip com composição quando houver mais de um mês contribuindo
                            bd = _irrf_breakdown_disponivel(user_id, ano, m, _reg_alias, _epoch()) or {}
                            _mes_abrev = {1:"Jan",2:"Fev",3:"Mar",4:"Abr",5:"Mai",6:"Jun",7:"Jul",8:"Ago",9:"Set",10:"Out",11:"Nov",12:"Dez"}
                            itens = [(k, v) for k, v in sorted(bd.items()) if v > 1e-9]
                            if len(itens) > 1:
                                tip = " | ".join([f"{_mes_abrev.get(int(k), k)}: {_fmt_brl(float(v))}" for k, v in itens])
                                out = f'<span title="{tip}">{out}</span>'
                            return out
                        except Exception:
                            return _fmt_brl(0.0)

                    # Formatos usados nos cards do Resumo
                    irrf_comum_fmt = _irrf_disp_fmt_resumo("comum", "NORMAL")
                    irrf_dt_fmt    = _irrf_disp_fmt_resumo("daytrade", "DAYTRADE")

                    # [IR-P32] Override em caso de divergência: usar PRÉVIA líquida de IRRF
                    #          comparada ao snapshot **após** descontar pagamentos efetivos do mês.
                    def __ir_prev_liq(d: dict, reg: str) -> float:
                        ir_mes_val = float((d or {}).get("ir_devido_mes", 0.0) or 0.0)
                        irrf_val = 0.0
                        if reg in ("comum", "daytrade"):
                            try:
                                irrf_val = float((d or {}).get("irrf_retido", 0.0) or 0.0)
                            except Exception:
                                irrf_val = 0.0
                            if irrf_val <= 0.0:
                                try:
                                    regs = irrf_regs or {}
                                    irrf_val = float((regs.get("NORMAL", 0.0) if reg == "comum" else regs.get("DAYTRADE", 0.0)) or 0.0)
                                except Exception:
                                    irrf_val = 0.0
                        return max(ir_mes_val - irrf_val, 0.0)
                    def __pagos_reg(d: dict, reg: str) -> float:
                        val = 0.0
                        try:
                            val = float(sum_pagamentos_darf(supabase_autenticado(), user_id, ano, m, reg) or 0.0)
                        except Exception:
                            val = 0.0
                        if val <= 0.0:
                            try:
                                val = float((d or {}).get("pagos_mes", 0.0) or 0.0)
                            except Exception:
                                pass
                        if val <= 0.0:
                            try:
                                lst = (_pags_both.get(reg, []) if isinstance(_pags_both, dict) else []) or []
                                val = _sum_val(lst, key="valor_pago")
                            except Exception:
                                pass
                        return max(val, 0.0)
                    def __diverge_ir_a_recolher(d: dict, reg: str) -> bool:
                        snap_reg = (snap.get(reg) if isinstance(snap, dict) else None)
                        if not snap_reg:
                            return False
                        try:
                            prev_liq = __ir_prev_liq(d or {}, reg)
                            pagos    = __pagos_reg(d or {}, reg)
                            prev_liq_pos = max(prev_liq - pagos, 0.0)
                            snap_ir_a_rec = float(snap_reg.get("ir_a_recolher_tipo", 0.0) or 0.0)
                            return abs(prev_liq_pos - snap_ir_a_rec) >= 0.01
                        except Exception:
                            return False
                    diag_c = (_diag_both.get("comum") if isinstance(_diag_both, dict) else {}) or {}
                    diag_dt = (_diag_both.get("daytrade") if isinstance(_diag_both, dict) else {}) or {}
                    if __diverge_ir_a_recolher(diag_c, "comum"):
                        _val = max(__ir_prev_liq(diag_c, "comum") - __pagos_reg(diag_c, "comum"), 0.0)
                        ir_a_rec_comum_fmt = _fmt_brl(_val)
                    if __diverge_ir_a_recolher(diag_dt, "daytrade"):
                        _val = max(__ir_prev_liq(diag_dt, "daytrade") - __pagos_reg(diag_dt, "daytrade"), 0.0)
                        ir_a_rec_dt_fmt = _fmt_brl(_val)


                    col_comum, col_dt, col_fii = st.columns(3, gap="small")

                    # ===== COLUNA COMUM =====
                    with col_comum:
                        st.markdown(
                            f"""
                            <div class="ir-card">
                              <div class="ir-head">
                                <div class="ir-title">COMUM</div>
                                <span class="ir-pill">TRIBUTÁVEL</span>
                              </div>
                              <div class="ir-inline" style="margin-bottom:.25rem;">
                                <div class="ir-label">IR a recolher</div>
                                <div class="ir-inline">
                                  <div class="ir-value">{ir_a_rec_comum_fmt}</div>
                                </div>
                              </div>
                              <div class="ir-section" style="color:#ffffff;">CÁLCULO DO MÊS</div>
                              <div class="ir-row"><div class="ir-label">Lucro tributável</div><div class="ir-value">{c_total}</div></div>
                              <div class="ir-row"><div class="ir-label">Compensado</div><div class="ir-value">{comp_comum_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">Base pós-compensação</div><div class="ir-value">{basepos_comum_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IR devido</div><div class="ir-value">{ir_comum_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IRRF retido</div><div class="ir-value">{irrf_comum_fmt}</div></div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        with st.expander("Detalhes"):
                            st.markdown(
                                f"""
                                <div class="ir-expander-pad">
                                  <div class="ir-card">
                                    <div class="ir-row"><div class="ir-label">Vendas em ações (à vista)</div><div class="ir-value">{vendas_acoes_fmt}</div></div>
                                    <div class="ir-row"><div class="ir-label">Isenção 20k aplicada?</div><div class="ir-value">{isencao_str}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (Ações)</div><div class="ir-value">{c_acoes_trib}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (BDR, ETF)</div><div class="ir-value">{c_bdreff}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (Opções)</div><div class="ir-value">{c_opcoes}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro em ações (isento)</div><div class="ir-value">{c_acoes_isento}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro líquido (total do tipo)</div><div class="ir-value">{c_total}</div></div>
                                    <div class="ir-row"><div class="ir-label">Prejuízo restante</div><div class="ir-value">{prej_comum_fmt}</div></div>
                                  </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )


                    # ===== COLUNA DAY TRADE =====

                    # ===== COLUNA DAY TRADE =====
                    with col_dt:
                        st.markdown(
                            f"""
                            <div class="ir-card">
                              <div class="ir-head">
                                <div class="ir-title">DAY TRADE</div>
                                <span class="ir-pill">TRIBUTÁVEL</span>
                              </div>
                              <div class="ir-inline" style="margin-bottom:.25rem;">
                                <div class="ir-label">IR a recolher</div>
                                <div class="ir-inline">
                                  <div class="ir-value">{ir_a_rec_dt_fmt}</div>
                                </div>
                              </div>
                              <div class="ir-section" style="color:#ffffff;">CÁLCULO DO MÊS</div>
                              <div class="ir-row"><div class="ir-label">Lucro tributável</div><div class="ir-value">{dt_total}</div></div>
                              <div class="ir-row"><div class="ir-label">Compensado</div><div class="ir-value">{comp_dt_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">Base pós-compensação</div><div class="ir-value">{basepos_dt_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IR devido</div><div class="ir-value">{ir_dt_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IRRF retido</div><div class="ir-value">{irrf_dt_fmt}</div></div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        with st.expander("Detalhes"):
                            st.markdown(
                                f"""
                                <div class="ir-expander-pad">
                                  <div class="ir-card">
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (Ações)</div><div class="ir-value">{dt_acoes}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (BDR, ETF)</div><div class="ir-value">{dt_bdreff}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro tributável (Opções)</div><div class="ir-value">{dt_opcoes}</div></div>
                                    <div class="ir-row"><div class="ir-label">Lucro líquido (total do tipo)</div><div class="ir-value">{dt_total}</div></div>
                                    <div class="ir-row"><div class="ir-label">Prejuízo restante</div><div class="ir-value">{prej_dt_fmt}</div></div>
                                  </div>
                                </div>
                                """,
                                unsafe_allow_html=True
                            )
                    # ===== CARD FII (linha inteira) =====
                    with col_fii:
                        def _ir_e_badge_fii():
                            rec = snap.get("fii") if isinstance(snap, dict) else None
                            if rec:
                                try:
                                    ir_rec = float(rec.get("ir_a_recolher_tipo", 0.0) or 0.0)
                                except Exception:
                                    ir_rec = 0.0
                                if ir_rec <= 0:
                                    return ("Não devido", "Consolidado")
                                if ir_rec < 10:
                                    return ("Não devido", "Consolidado")
                                return (_fmt_brl(ir_rec), "Devido")

                            # Diagnóstico FII do mês (fonte única); usa _epoch() para evitar sujeira
                            _diag_fii = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", _epoch())) or {}
                            total_cons = float(_diag_fii.get("total_considerado", 0.0) or 0.0)
                            sugerido   = float(_diag_fii.get("sugerido_pagar", 0.0) or 0.0)

                            if total_cons <= 0.0:
                                return ("Não devido", "Quitado/sem débito")
                            if total_cons < 10.0:
                                return ("Não devido", "Abaixo do mínimo")

                            # Pagamentos do mês (preferir ledger/_pags_both/override; fallback para cache oficial)
                            pags_f = []
                            try:
                                pags_f = (_pags_both.get("fii") if isinstance(_pags_both, dict) else []) or []
                            except Exception:
                                pags_f = []

                            # Override local (se existir)
                            _override_key_fii = f"pag8_pay_override_{ano}_{m}_fii"
                            if st.session_state.get(_override_key_fii) is not None:
                                pags_f = st.session_state[_override_key_fii]

                            if not pags_f:
                                try:
                                    pags_f = run_memo(("listar_pag", ano, m, "fii"), lambda: _cached_listar_pag(user_id, ano, m, "fii", _epoch())) or []
                                except Exception:
                                    pags_f = []

                            try:
                                pagos_f = sum(float(r.get("valor_pago", 0.0) or 0.0) for r in (pags_f or []))
                            except Exception:
                                pagos_f = 0.0

                            saldo_fii = max((sugerido or 0.0) - (pagos_f or 0.0), 0.0)
                            badge = "Quitado" if (total_cons >= 10.0 and abs(saldo_fii) < 0.01) else "Devido"
                            return (_fmt_brl(saldo_fii), badge)

                        ir_a_rec_fii_fmt, badge_fii = _ir_e_badge_fii()

                        # Lucro total de FII (COMUM + DT) no mês
                        f_total_bruto = float(resumo["comum"].get("fiis", 0.0) or 0.0) + float(resumo["dt"].get("fiis", 0.0) or 0.0)
                        f_total_bruto_fmt = _fmt_brl(f_total_bruto)

                        # Alinha o card FII com a lógica da aba DARF, usando o diagnóstico do mês
                        _diag_fii = run_memo(("diag", ano, m, "fii"), lambda: _cached_diag(user_id, ano, m, "fii", st.session_state["pag8_cache_epoch"])) or {}
                        ir_fii_val = float(_diag_fii.get("ir_devido_mes", 0.0) or 0.0)
                        try:
                            _aliq_fii = float(get_param(supabase, "ALIQUOTA_FII", ano, m, default=0.20)) or 0.20
                        except Exception:
                            _aliq_fii = 0.20
                        basepos_fii_val = (ir_fii_val / _aliq_fii) if _aliq_fii else 0.0
                        # Compensado estimado = lucro bruto - base pós (se positivo)
                        comp_fii_val = max(f_total_bruto - basepos_fii_val, 0.0)

                        # Prejuízo restante (fallback): se o mês deu negativo, mostra o módulo; se houver valor vindo do backend, preferir
                        prej_backend = (comp.get("FII") or {}).get("prejuizo_restante", None)
                        if prej_backend is None:
                            prej_fii_val = max(-f_total_bruto, 0.0) if ir_fii_val == 0 else 0.0
                        else:
                            try:
                                prej_fii_val = float(prej_backend or 0.0)
                            except Exception:
                                prej_fii_val = 0.0

                        # Formatações
                        comp_fii_fmt    = _fmt_brl(comp_fii_val)
                        basepos_fii_fmt = _fmt_brl(basepos_fii_val)
                        ir_fii_fmt      = _fmt_brl(ir_fii_val)
                        prej_fii_fmt    = _fmt_brl(prej_fii_val)

                        st.markdown(
                            f"""
                            <div class="ir-card">
                              <div class="ir-head">
                                <div class="ir-title">FII</div>
                                <span class="ir-pill">TRIBUTÁVEL</span>
                              </div>
                              <div class="ir-inline" style="margin-bottom:.25rem;">
                                <div class="ir-label">IR a recolher</div>
                                <div class="ir-inline">
                                  <div class="ir-value">{ir_a_rec_fii_fmt}</div>
                                </div>
                              </div>
                              <div class="ir-section" style="color:#ffffff;">CÁLCULO DO MÊS</div>
                              <div class="ir-row"><div class="ir-label">Lucro tributável</div><div class="ir-value">{f_total_bruto_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">Compensado</div><div class="ir-value">{comp_fii_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">Base pós-compensação</div><div class="ir-value">{basepos_fii_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IR devido (20%)</div><div class="ir-value">{ir_fii_fmt}</div></div>
                              <div class="ir-row"><div class="ir-label">IRRF retido</div><div class="ir-value">Não se aplica a FII</div></div>
                              <div class="ir-row"><div class="ir-label">Prejuízo restante</div><div class="ir-value">{prej_fii_fmt}</div></div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    

                # [IR-P06] Novo expander: "🧭 O que mudou?" baseado no diff real

                with sub_tabs[1]:
                    # ===== UI da aba Operações (lista/agrupamento do mês) =====
                    import pandas as pd

                    # Toggle para agrupar linhas por ticker (e tipo)
                    agrupar = st.toggle("Agrupar por ticker", value=False, key=f"pag8_group_{ano}_{m}")

                    # --- Classificação de mercado para exibição/agrupamento ---
                    def _is_option_row(row):
                        try:
                            return str(row.get("mercado","")).upper().startswith("OP")
                        except Exception:
                            return False

                    # Cria coluna de mercado classificado
                    def _classify_row(row):
                        if _is_option_row(row):
                            return "Opções"
                        tk = row.get("ticker")
                        cls = classificar_ticker(tk)
                        if cls in ("BDR","ETF"):
                            return "BDR/ETF"
                        if cls == "FII":
                            return "FII"
                        return "Ações"

                    # --- Helpers novos: percentual coerente e sentido (Compra/Venda) ---
                    def _safe_pct(row):
                        try:
                            lucro = float(row.get("lucro_rs", 0.0) or 0.0)
                            q  = float(row.get("quantidade", 0.0) or 0.0)
                            pi = float(row.get("preco_inicial", 0.0) or 0.0)
                            pf = float(row.get("preco_final", 0.0) or 0.0)
                            denom = max(abs(pi * q), abs(pf * q), 1e-9)  # simétrico e robusto para opções (inclui pf=0)
                            pct = (abs(lucro) / denom) * 100.0
                            return pct if lucro >= 0 else -pct
                        except Exception:
                            return 0.0

                    def _infer_sentido(row):
                        """Deduz o sentido de abertura: 'Compra' ou 'Venda'.
                        Intuição: se o lucro caminha no mesmo sentido da variação (pf - pi), a abertura foi Compra; caso contrário, Venda.
                        Funciona para à vista e opções (inclui expiração/exercício com preco_final=0)."""
                        try:
                            lucro = float(row.get("lucro_rs", 0.0) or 0.0)
                            q  = float(row.get("quantidade", 0.0) or 0.0)
                            pi = float(row.get("preco_inicial", 0.0) or 0.0)
                            pf = float(row.get("preco_final", 0.0) or 0.0)
                            diff = (pf - pi) * q
                            if abs(lucro) < 1e-6 and abs(diff) < 1e-6:
                                return "Compra"
                            return "Compra" if ((diff >= 0 and lucro >= 0) or (diff <= 0 and lucro <= 0)) else "Venda"
                        except Exception:
                            return "Compra"

                    # Mapeamento de exibição para a coluna "Ponta"
                    _PONTA_MAP = {"Compra": "Compradora", "Venda": "Vendedora", "Misto": "Mista"}

                    if not df.empty:
                        try:
                            df["mercado_cls"] = df.apply(_classify_row, axis=1)
                        except Exception:
                            df["mercado_cls"] = df.get("mercado", "Ações")

                    if df.empty:
                        if n_ops_hint > 0:
                            st.warning("Não consegui carregar as operações via cache, apesar do contador indicar movimentação. Tente clicar em **Recarregar mês** abaixo.", icon="⚠️")
                            if st.button("Recarregar mês", key=f"btn_reload_{ano}_{m}"):
                                # força invalidação local e rerun
                                st.session_state["pag8_cache_epoch"] += 1
                                st.session_state[f"pag8_calc_{ano}_{m}"] = True
                                st.rerun()
                        else:
                            st.info("Nenhuma operação neste mês.")
                    else:
                        # Coluna auxiliar para cálculo de base (pi * q) ao agrupar
                        df["_base_pi_q"] = df["preco_inicial"].fillna(0) * df["quantidade"].fillna(0)
                        df["_base_pf_q"] = df["preco_final"].fillna(0) * df["quantidade"].fillna(0)
                        # Precomputar sentido de abertura (Compra/Venda) para cada linha
                        df["_sentido"] = df.apply(_infer_sentido, axis=1)

                        # Exibição sem agrupamento
                        if not agrupar:
                            # No agrupamento desligado, apenas copia df (já contém "custo")
                            df_exibir = df.copy()
                            df_exibir["mercado"] = df_exibir.get("mercado_cls", df_exibir.get("mercado"))
                            # (Re)calcula percentual coerente e Sentido por linha
                            df_exibir["lucro_pct"] = df_exibir.apply(_safe_pct, axis=1)
                            df_exibir["Sentido"]   = df_exibir.apply(_infer_sentido, axis=1)
                            df_exibir["Ponta"] = df_exibir["Sentido"].map(_PONTA_MAP).fillna(df_exibir["Sentido"])

                        else:
                            # Agrupamento por ticker + tipo (+ mercado para não confundir à vista e opções)
                            grp = df.groupby(["ticker", "tipo", "mercado_cls"], as_index=False).agg(
                                quantidade=("quantidade", "sum"),
                                lucro_rs=("lucro_rs", "sum"),
                                _base_pi_total=("_base_pi_q", "sum"),
                                _base_pf_total=("_base_pf_q", "sum"),
                                custo=("custo", "sum"),
                                data=("data", "max"),
                                sentido=("_sentido", lambda s: s.iloc[0] if s.nunique() == 1 else "Misto"),
                            )

                            # Preços médios ponderados por quantidade
                            grp["preco_inicial"] = grp.apply(
                                lambda r: (r["_base_pi_total"] / r["quantidade"]) if r["quantidade"] else 0.0, axis=1
                            )
                            grp["preco_final"] = grp.apply(
                                lambda r: (r["_base_pf_total"] / r["quantidade"]) if r["quantidade"] else 0.0, axis=1
                            )

                            # Percentual coerente com sinal do lucro (robusto para opções)
                            grp["lucro_pct"] = grp.apply(_safe_pct, axis=1)

                            # Não remover a coluna "custo"
                            grp = grp.rename(columns={"mercado_cls":"mercado"})
                            grp = grp.rename(columns={"sentido": "Sentido"})
                            grp["Ponta"] = grp["Sentido"].map(_PONTA_MAP).fillna(grp["Sentido"])
                            df_exibir = grp.drop(columns=["_base_pi_total", "_base_pf_total"])

                        # Ordenação padrão: data asc, ticker
                        df_exibir = df_exibir.sort_values(by=["data", "ticker"]).reset_index(drop=True)

                        # Formatação leve
                        df_exibir["data"] = pd.to_datetime(df_exibir["data"]).dt.strftime("%d/%m/%y")
                        # Renomear colunas para capitalizar antes de exibir
                        df_exibir = df_exibir.rename(columns={
                            "data": "Data",
                            "mercado": "Mercado",
                            "ticker": "Ticker",
                            "tipo": "Tipo",
                            "Ponta": "Ponta",
                            "quantidade": "Quant.",
                            "preco_inicial": "Preço Inicial",
                            "preco_final": "Preço Final",
                            "lucro_rs": "Lucro (R$)*",
                            "lucro_pct": "Lucro (%)",
                            "custo": "Custo"
                        })
                        # Seleciona colunas na ordem desejada (mantendo tipos numéricos)
                        # "Custo" não exibido em df_vis
                        df_vis = df_exibir[["Data","Mercado","Ticker","Tipo","Ponta","Quant.","Preço Inicial","Preço Final","Lucro (R$)*","Lucro (%)"]].copy()

                        # Funções de formatação BR (sem converter tipo do DataFrame)
                        def _fmt_brl(x):
                            try:
                                return ("R$ {:,.2f}".format(x)).replace(",", "X").replace(".", ",").replace("X", ".")
                            except Exception:
                                return ""
                        def _fmt_pct(x):
                            try:
                                return ("{:,.2f}%".format(x)).replace(",", "X").replace(".", ",").replace("X", ".")
                            except Exception:
                                return ""
                        # Helper para tooltip BRL
                        def _fmt_brl_val(x):
                            try:
                                return ("R$ {:,.2f}".format(x)).replace(",", "X").replace(".", ",").replace("X", ".")
                            except Exception:
                                return ""

                        # Cores condicionais para lucro (positivo/negativo)
                        def _color_profit(v):
                            try:
                                if v > 0:
                                    return "color: #4CAF50;"
                                if v < 0:
                                    return "color: #e53935;"
                                return ""
                            except Exception:
                                return ""

                        # Create Styler object for dataframe
                        num_rows = df_vis.shape[0]
                        styler = (
                            df_vis.style
                            .format({
                                "Preço Inicial": _fmt_brl,
                                "Preço Final": _fmt_brl,
                                "Lucro (R$)*": _fmt_brl,
                                "Lucro (%)": _fmt_pct,
                            })
                        )
                        if num_rows <= 500:
                            styler = styler.map(_color_profit, subset=["Lucro (R$)*", "Lucro (%)"])

                        st.dataframe(
                            styler,
                            width='stretch',
                            hide_index=True,
                        )
                        # --- Total do mês para a coluna "Lucro (R$)*" (exibição abaixo da tabela) ---
                        try:
                            _total_lucro_mes = float(df_vis["Lucro (R$)*"].sum() or 0.0)
                        except Exception:
                            _total_lucro_mes = 0.0
                        _total_color = "#4CAF50" if _total_lucro_mes > 0 else ("#e53935" if _total_lucro_mes < 0 else "rgba(255,255,255,.85)")
                        st.markdown(
                            f"""
                            <div class="ir-inline" style="justify-content:flex-end; margin-top:.25rem;">
                              <div class="ir-label">Total do mês</div>
                              <div class="ir-value" style="margin-left:.5rem; color:{_total_color};">{_fmt_brl(_total_lucro_mes)}</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        st.caption("*Lucro ajustado depois de Custos Operacionais")
                with sub_tabs[2]:
                    # ===== UI da aba DARF: sub-abas para Comum e Day Trade =====
                    import datetime as _dt
                    # --- PRÉVIA TOTAL (Comum + Day Trade + FII) ---
                    _m_ledger = (ledger_cache.get((ano, m)) or {})
                    _pags_from_ledger = _m_ledger.get("pagamentos") or {}

                    # --- PRÉVIA TOTAL (Comum + Day Trade + FII) ---
                    # Cálculos por regime (usamos os caches já existentes + uma chamada para FII)
                    diag_comum  = _cached_diag(user_id, ano, m, "comum", st.session_state["pag8_cache_epoch"])
                    diag_dt     = _cached_diag(user_id, ano, m, "daytrade", st.session_state["pag8_cache_epoch"])
                    diag_fii    = _cached_diag(user_id, ano, m, "fii", st.session_state["pag8_cache_epoch"])

                    ir_c  = float((diag_comum or {}).get("ir_devido_mes", 0.0) or 0.0)
                    ir_dt = float((diag_dt    or {}).get("ir_devido_mes", 0.0) or 0.0)
                    ir_f  = float((diag_fii   or {}).get("ir_devido_mes", 0.0) or 0.0)

                    carry_c  = float((diag_comum or {}).get("carry_sub10", 0.0) or 0.0)
                    carry_dt = float((diag_dt    or {}).get("carry_sub10", 0.0) or 0.0)
                    carry_f  = float((diag_fii   or {}).get("carry_sub10", 0.0) or 0.0)

                    totc_c  = float((diag_comum or {}).get("total_considerado", 0.0) or 0.0)
                    totc_dt = float((diag_dt    or {}).get("total_considerado", 0.0) or 0.0)
                    totc_f  = float((diag_fii   or {}).get("total_considerado", 0.0) or 0.0)

                  # Pagos no mês por regime (fonte única, centralizada)
                    _pags_both = _pags_from_ledger if isinstance(_pags_from_ledger, dict) else {}
                    pags_c  = _pag8_pags_for(user_id, ano, m, "comum", _pags_both)
                    pags_dt = _pag8_pags_for(user_id, ano, m, "daytrade", _pags_both)
                    pags_f  = _pag8_pags_for(user_id, ano, m, "fii", _pags_both)

                    def _sum_val(lst):
                        try:
                            return sum(float(r.get("valor_pago", 0.0) or 0.0) for r in (lst or []))
                        except Exception:
                            return 0.0


                    try:
                        pagos_c = float(sum_pagamentos_darf(supabase_autenticado(), user_id, ano, m, "comum") or 0.0)
                    except Exception:
                        pagos_c = 0.0
                    if pagos_c <= 0.0:
                        pagos_c = _sum_val(pags_c)

                    # Badge da PRÉVIA (Comum) com base nos mesmos números exibidos no card do tipo
                    def _badge_from_tipo(total_cons: float, pagos: float) -> str:
                        tc = float(total_cons or 0.0)
                        pg = float(pagos or 0.0)
                        if tc <= 0.0:
                            return "Não devido"
                        if tc < 10.0:
                            return "Abaixo do mínimo"
                        return "Devido" if (tc - pg) > 0.01 else "Quitado"

                    badge_c_prev = _badge_from_tipo(totc_c, pagos_c)

                    try:
                        pagos_dt = float(sum_pagamentos_darf(supabase_autenticado(), user_id, ano, m, "daytrade") or 0.0)
                    except Exception:
                        pagos_dt = 0.0
                    if pagos_dt <= 0.0:
                        pagos_dt = _sum_val(pags_dt)

                    try:
                        pagos_f = float(sum_pagamentos_darf(supabase_autenticado(), user_id, ano, m, "fii") or 0.0)
                    except Exception:
                        pagos_f = 0.0
                    if pagos_f <= 0.0:
                        pagos_f = _sum_val(pags_f)

                    # Helper unificado para badge do card de PRÉVIA (segue a regra do mínimo com base nos mesmos números exibidos)
                    def _badge_from(total_considerado: float, pagos: float) -> str:
                        try:
                            tc = float(total_considerado or 0.0)
                            pg = float(pagos or 0.0)
                        except Exception:
                            tc, pg = 0.0, 0.0
                        if tc <= 0.0:
                            return "Não devido"
                        if tc < 10.0:
                            return "Abaixo do mínimo"
                        return "Devido" if (tc - pg) > 0.01 else "Quitado"

                    # Totais agregados (usados nas mesmas linhas do card)
                    ir_total     = ir_c + ir_dt + ir_f
                    carry_total  = carry_c + carry_dt + carry_f
                    tot_cons_all = float(totc_c or 0.0) + float(totc_dt or 0.0) + float(totc_f or 0.0)
                    pagos_total  = float(pagos_c or 0.0) + float(pagos_dt or 0.0) + float(pagos_f or 0.0)

                    # IRRF Total do mês (Comum + Day Trade). FII não tem IRRF
                    irrf_c  = float((diag_comum or {}).get("irrf_retido", 0.0) or 0.0)
                    irrf_dt = float((diag_dt    or {}).get("irrf_retido", 0.0) or 0.0)
                    if (irrf_c <= 0.0) and (irrf_dt <= 0.0):
                        # Fallback para agregado oficial se prévia não trouxe o campo (cache antigo)
                        try:
                            regs_total = _cached_irrf(user_id, ano, m, "abertura_total", st.session_state["pag8_cache_epoch"]) or {}
                            if irrf_c <= 0.0:
                                irrf_c = float(regs_total.get("NORMAL", 0.0) or 0.0)
                            if irrf_dt <= 0.0:
                                irrf_dt = float(regs_total.get("DAYTRADE", 0.0) or 0.0)
                        except Exception:
                            pass
                    irrf_total = irrf_c + irrf_dt

                    # Badge e sugerido calculados a partir dos mesmos valores exibidos no card
                    badge_total = _badge_from(tot_cons_all, pagos_total)
                    if tot_cons_all < 10.0:
                        sugerido_total = 0.0
                        sugerido_total_fmt = "Não devido (&lt; R$ 10)"
                    else:
                        sugerido_total = max(tot_cons_all - pagos_total, 0.0)
                        sugerido_total_fmt = _fmt_brl(sugerido_total)

                    # [BADGE-TOTAL-P1] Badge do card PRÉVIA DE IR (Total) baseado na prévia TOTAL corrigida (ledger IRRF)
                    try:
                        _pc_tot = _previa_corrigida_total(user_id, ano, m, st.session_state["pag8_cache_epoch"]) or {}
                        _tot_cons = float(_pc_tot.get("total_cons_corr_total", 0.0) or 0.0)
                        _pagos    = float(_pc_tot.get("pagos_total", 0.0) or 0.0)
                        _saldo    = max(_tot_cons - _pagos, 0.0)
                        sugerido_total = float(_pc_tot.get("sugerido_total", 0.0) or 0.0)

                        badge_total_text  = "Devido"
                        badge_total_color = "#e53935"  # vermelho
                        badge_total_tip   = ""

                        # depois
                        if _tot_cons <= 0.0:
                            badge_total_text, badge_total_color = "Isento", "#9e9e9e"
                            badge_total_tip = "Sem imposto devido"
                        elif 0.0 < _tot_cons < 10.0:
                            badge_total_text, badge_total_color = "Abaixo do mínimo", "#9e9e9e"
                            badge_total_tip = "Transportado para o próximo mês"
                        elif abs(_saldo) < 0.01:
                            badge_total_text, badge_total_color = "Quitado", "#43A047"
                            badge_total_tip = "Sem saldo a pagar"
                        elif _saldo >= 10.0 and _pagos > 0.0:
                            badge_total_text, badge_total_color = "Pago –", "#FB8C00"
                            badge_total_tip = "Pagamento parcial registrado"
                    except Exception:
                        badge_total_text, badge_total_color, badge_total_tip = "Devido", "#e53935", ""
                    # Card único de PRÉVIA TOTAL
                    st.markdown(
                        f"""
                        <div class="ir-card" style="margin-bottom:.5rem;">
                          <div class="ir-head">
                            <div class="ir-title">PRÉVIA DE IR (Total)</div>
                            <span class="ir-pill" title="{badge_total_tip}" style="border-color:{badge_total_color}; color:{badge_total_color};">{badge_total_text}</span>
                          </div>
                          <div class="ir-row"><div class="ir-label">Comum – IR devido</div><div class="ir-value">{_fmt_brl(ir_c)}</div></div>
                          <div class="ir-row"><div class="ir-label">Day Trade – IR devido</div><div class="ir-value">{_fmt_brl(ir_dt)}</div></div>
                          <div class="ir-row"><div class="ir-label">FII – IR devido</div><div class="ir-value">{_fmt_brl(ir_f)}</div></div>
                          <div class="ir-row"><div class="ir-label">Carry &lt; R$ 10 (soma)</div><div class="ir-value">{_fmt_brl(carry_total)}</div></div>
                          <div class="ir-row"><div class="ir-label">IRRF retido do mês (Comum + Day Trade)</div><div class="ir-value">{_irrf_disp_fmt_total_html(user_id, ano, m, st.session_state["pag8_cache_epoch"])}</div></div>
                          <div class="ir-row"><div class="ir-label">Pagamentos do mês (soma)</div><div class="ir-value">{_fmt_brl(pagos_total)}</div></div>
                          <div class="ir-row"><div class="ir-label">Sugerido a pagar agora (Total)</div><div class="ir-value">{_fmt_brl(sugerido_total)}</div></div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    def _fmt_brl(v: float) -> str:
                        try:
                            return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")
                        except Exception:
                            return "R$ 0,00"

                    tabs_darf = st.tabs([label_c, label_dt, label_f])
                    for _tab_darf, tipo_darf in zip(tabs_darf, ["comum", "daytrade", "fii"]):
                        with _tab_darf:
                            st.subheader(f"Pagamentos – {MESES[m-1]} / {ano}")
                            suggested_now = 0.0

                            # --- Prévia de IR do mês (sem gravar snapshot) ---
                            if tipo_darf in ("comum", "daytrade"):
                                diag = (_diag_both.get(tipo_darf) if isinstance(_diag_both, dict) else None)
                            else:
                                # FII não está em _diag_both; buscar diagnóstico diretamente
                                diag = _cached_diag(user_id, ano, m, "fii", st.session_state["pag8_cache_epoch"])

                            # Vamos definir o HTML do sugerido depois de carregar os pagamentos efetivos (UI) para evitar race de cache
                            sugerido_place_html = None
                            # badge, ir_mes, carry10, total_cons, pagos_mes, delta_snap, snap_ir, etc. são definidos aqui para uso posterior
                            badge = ""
                            ir_mes = 0.0
                            carry10 = 0.0
                            total_cons = 0.0
                            pagos_mes = 0.0
                            delta_snap = 0.0
                            snap_ir = None
                            if diag:
                                total_cons = float(diag.get("total_considerado", 0.0))
                                pagos_mes  = float(diag.get("pagos_mes", 0.0))
                                sugerido   = float(diag.get("sugerido_pagar", 0.0))
                                status_min = str(diag.get("status_minimo", ""))
                                ir_mes     = float(diag.get("ir_devido_mes", 0.0))
                                carry10    = float(diag.get("carry_sub10", 0.0))
                                # [DARF-P3a] Override: usar prévia corrigida pelo ledger do IRRF para total_cons/pagos/sugerido (Comum/DT)
                                try:
                                    if tipo_darf in ("comum", "daytrade"):
                                        _pc = _previa_corrigida_regime(user_id, ano, m, tipo_darf, st.session_state["pag8_cache_epoch"]) or {}
                                        total_cons = float(_pc.get("total_cons_corr", total_cons))
                                        pagos_mes  = float(_pc.get("pagos_mes", pagos_mes))
                                        sugerido   = float(_pc.get("sugerido_agora", sugerido))
                                except Exception:
                                    pass
                                # Delta local (on-the-fly): PRÉVIA líquida de IRRF vs snapshot atual
                                snap_rec = (snap.get(tipo_darf) if isinstance(snap, dict) else None)
                                try:
                                    snap_ir = float(snap_rec.get("ir_a_recolher_tipo", 0.0)) if snap_rec else None
                                except Exception:
                                    snap_ir = None
                                # Hotfix (reforçado): se `ir_a_recolher_tipo` diverge de (ir_devido_tipo − IRRF),
                                # usar IRRF do snapshot; se ausente/zero, cair no IRRF agregado oficial (NORMAL/DAYTRADE)
                                try:
                                    if snap_rec:
                                        snap_ir_dev = float(snap_rec.get("ir_devido_tipo", 0.0) or 0.0)
                                        snap_irrf   = float(snap_rec.get("irrf_retido_tipo", 0.0) or 0.0)
                                        # Fallback para IRRF agregado quando o snapshot não o traz corretamente
                                        if (tipo_darf in ("comum", "daytrade")) and (snap_irrf <= 0.0):
                                            try:
                                                regs_fallback = _cached_irrf(user_id, ano, m, "abertura_total", st.session_state["pag8_cache_epoch"]) or {}
                                                snap_irrf = float((regs_fallback.get("NORMAL", 0.0) if tipo_darf == "comum" else regs_fallback.get("DAYTRADE", 0.0)) or 0.0)
                                            except Exception:
                                                pass
                                        snap_ir_corr = max(snap_ir_dev - snap_irrf, 0.0)
                                        if (snap_ir is not None) and (abs(float(snap_ir) - snap_ir_corr) >= 0.01):
                                            snap_ir = snap_ir_corr
                                except Exception:
                                    pass

                                # IRRF atual do mês para o regime (fallback para agregado, como na UI)
                                irrf_atual = 0.0
                                if tipo_darf in ("comum", "daytrade"):
                                    try:
                                        irrf_atual = float(diag.get("irrf_retido", 0.0) or 0.0)
                                    except Exception:
                                        irrf_atual = 0.0
                                    if irrf_atual <= 0.0:
                                        try:
                                            regs_tmp = _cached_irrf(user_id, ano, m, "abertura_total", st.session_state["pag8_cache_epoch"]) or {}
                                            irrf_atual = float((regs_tmp.get("NORMAL", 0.0) if tipo_darf == "comum" else regs_tmp.get("DAYTRADE", 0.0)) or 0.0)
                                        except Exception:
                                            pass
                                # Prévia líquida (FII não tem IRRF)
                                prev_liq = max(ir_mes - irrf_atual, 0.0) if tipo_darf in ("comum", "daytrade") else max(ir_mes, 0.0)
                                delta_snap = (prev_liq - float(snap_ir or 0.0)) if (snap_ir is not None) else 0.0

                                # Badge dinâmico: prioriza snapshot (mês consolidado), senão usa a prévia
                                if snap_ir is not None:
                                    # Há snapshot ativo para este regime
                                    try:
                                        _snap_ir_val = float(snap_ir)
                                    except Exception:
                                        _snap_ir_val = 0.0
                                    if _snap_ir_val <= 0:
                                        badge = "Consolidado"
                                    elif _snap_ir_val < 10:
                                        # Consolidado e abaixo do mínimo — tratamos como quitado para o mês
                                        badge = "Consolidado"
                                    else:
                                        badge = "Devido"
                                else:
                                    # Sem snapshot: usa a prévia do mês
                                    if total_cons <= 0:
                                        badge = "Quitado/sem débito"
                                    elif total_cons < 10:
                                        badge = "Abaixo do mínimo"
                                    else:
                                        # Se já não há nada a pagar agora, tratamos como quitado
                                        badge = "Quitado" if sugerido <= 0 else "Devido"

                            # Override do badge com a fonte única (utils_ir.calcular_status_mes)
                            _status_all = calcular_status_mes(supabase, user_id, ano, m)
                            badge = _status_all.get(tipo_darf, {}).get("badge", badge or "–")

                            # Pill de divergência prévia vs snapshot (exibição no cabeçalho do card)
                            _delta_pill_html = ""
                            try:
                                _has_snapshot = (snap_ir is not None)
                                _has_delta = abs(delta_snap) >= 0.01 if isinstance(delta_snap, (int, float)) else False
                            except Exception:
                                _has_snapshot = False
                                _has_delta = False
                            if _has_snapshot and _has_delta and (total_cons >= 10):
                                _delta_pill_html = f'<span class="ir-pill" title="Prévia difere do snapshot atual em {_fmt_brl(delta_snap)}. Use Recalcular Mês para alinhar." style="border-color:#e53935;color:#e53935;">Cálculo Desatualizado</span>'

                            # Indicador de rollover de dezembro (regra do mínimo)
                            try:
                                _rollover_dez = _houve_rollover_dezembro(supabase, user_id, ano, m, tipo_darf)
                            except Exception:
                                _rollover_dez = False

                            _carry_label_html = 'Carry &lt; R$ 10 acumulado'
                            if _rollover_dez:
                                _carry_label_html += ' <span title="Inclui saldo carregado de dezembro do ano anterior (regra do mínimo)." style="opacity:.85; cursor:help;">ℹ️</span>'

                            # --- Listagem de pagamentos do mês/regime ---
                            pagamentos = _pag8_pags_for(user_id, ano, m, tipo_darf, _pags_both)

                            # --- Override local para refletir exclusões imediatamente (sem depender do cache/refresh)
                            override_key = f"pag8_pay_override_{ano}_{m}_{tipo_darf}"
                            if st.session_state.get(override_key) is not None:
                                pagamentos = st.session_state[override_key]

                            # Ordena por data desc (mais recente primeiro)
                            from datetime import datetime as _dt__
                            if pagamentos:
                                try:
                                    pagamentos = sorted(
                                        pagamentos,
                                        key=lambda r: _dt__.fromisoformat(str(r.get("data_pagamento"))),
                                        reverse=True,
                                    )
                                except Exception:
                                    # Fallback: ordena pela string da data caso não seja ISO
                                    pagamentos = sorted(
                                        pagamentos,
                                        key=lambda r: str(r.get("data_pagamento") or ""),
                                        reverse=True,
                                    )

                            # Se a lista de pagamentos estiver vazia, limpa o override para não manter estado obsoleto
                            if not pagamentos:
                                st.session_state.pop(override_key, None)

                            # --- Calcula o total pago visível na UI (pós-exclusões) e define o sugerido em cima disso
                            pagos_ui = 0.0
                            if pagamentos:
                                try:
                                    pagos_ui = sum(float(p.get("valor_pago", 0.0) or 0.0) for p in pagamentos)
                                except Exception:
                                    pagos_ui = 0.0

                            # Define sugerido a pagar agora baseado na prévia: IR devido do mês + carry(<10) acumulado – pagamentos visíveis
                            suggested_now = 0.0
                            if diag and total_cons >= 10:
                                try:
                                    # Basear no Total considerado (já líquido de IRRF) menos pagamentos visíveis
                                    suggested_now = max(float(total_cons) - float(pagos_ui), 0.0)
                                except Exception:
                                    suggested_now = 0.0

                            # Monta o HTML do sugerido agora usando o valor recalculado
                            if diag:
                                if total_cons < 10:
                                    sugerido_place_html = '<div class="ir-row"><div class="ir-label">Sugerido a pagar agora</div><div class="ir-value">Não devido (&lt; R$ 10)</div></div>'
                                else:
                                    sugerido_place_html = f'<div class="ir-row"><div class="ir-label">Sugerido a pagar agora</div><div class="ir-value">{_fmt_brl(suggested_now)}</div></div>'

                            # Linha informativa: IRRF retido do mês (apenas Comum/DT)
                            irrf_mes = 0.0
                            if diag and tipo_darf in ("comum", "daytrade"):
                                try:
                                    irrf_mes = float(diag.get("irrf_retido", 0.0) or 0.0)
                                except Exception:
                                    irrf_mes = 0.0
                                # Fallback: se vier 0.0 (cache antigo ou prévia sem campo), usa agregado oficial
                                if irrf_mes <= 0:
                                    try:
                                        regs_tmp = _cached_irrf(user_id, ano, m, "abertura_total", st.session_state["pag8_cache_epoch"]) or {}
                                        if tipo_darf == "comum":
                                            irrf_mes = float(regs_tmp.get("NORMAL", 0.0) or 0.0)
                                        else:
                                            irrf_mes = float(regs_tmp.get("DAYTRADE", 0.0) or 0.0)
                                    except Exception:
                                        pass
                            irrf_row_html = (
                                f'<div class="ir-row"><div class="ir-label">IRRF retido do mês</div><div class="ir-value">{_irrf_disp_fmt_html(user_id, ano, m, tipo_darf, st.session_state["pag8_cache_epoch"])}</div></div>'
                                if tipo_darf in ("comum", "daytrade") else ''
                            )

                            # [PTP-02] Badge do card PRÉVIA DE IR (por tipo) usando a prévia corrigida
                            badge_tipo_text  = "Devido"
                            badge_tipo_color = "#e53935"
                            badge_tipo_tip   = ""
                            try:
                                if tipo_darf in ("comum", "daytrade"):
                                    pc = _previa_corrigida_regime(user_id, ano, m, tipo_darf, st.session_state["pag8_cache_epoch"]) or {}
                                    tot  = float(pc.get("total_cons_corr", 0.0) or 0.0)
                                    pagos = float(pc.get("pagos_mes", 0.0) or 0.0)
                                    saldo = max(tot - pagos, 0.0)
                                    if tot <= 0.0:
                                        badge_tipo_text, badge_tipo_color = "Isento", "#9e9e9e"
                                        badge_tipo_tip = "Sem imposto devido"
                                    elif 0.0 < tot < 10.0:
                                        badge_tipo_text, badge_tipo_color = "Abaixo do mínimo", "#9e9e9e"
                                        badge_tipo_tip = "Transportado para o próximo mês"
                                    elif abs(saldo) < 0.01:
                                        badge_tipo_text, badge_tipo_color = "Quitado", "#43A047"
                                        badge_tipo_tip = "Sem saldo a pagar"
                                    elif saldo >= 10.0 and pagos > 0.0:
                                        badge_tipo_text, badge_tipo_color = "Pago –", "#FB8C00"
                                        badge_tipo_tip = "Pagamento parcial registrado"
                                    else:
                                        badge_tipo_text, badge_tipo_color = "Devido", "#e53935"
                                        badge_tipo_tip = "Nenhum pagamento"
                                else:  # FII (sem IRRF)
                                    _diag_fii_local = _cached_diag(user_id, ano, m, "fii", st.session_state["pag8_cache_epoch"]) or {}
                                    tot = float(_diag_fii_local.get("total_considerado", 0.0) or 0.0)
                                    # pagamentos FII
                                    try:
                                        pagos = float(sum_pagamentos_darf(supabase_autenticado(), user_id, ano, m, "fii") or 0.0)
                                    except Exception:
                                        pagamentos = _cached_listar_pag(user_id, ano, m, "fii", st.session_state["pag8_cache_epoch"]) or []
                                        pagos = _sum_val(pagamentos, key="valor_pago")
                                    saldo = max(tot - pagos, 0.0)
                                    if tot <= 0.0:
                                        badge_tipo_text, badge_tipo_color = "Isento", "#9e9e9e"
                                        badge_tipo_tip = "Sem imposto devido"
                                    elif 0.0 < tot < 10.0:
                                        badge_tipo_text, badge_tipo_color = "Abaixo do mínimo", "#9e9e9e"
                                        badge_tipo_tip = "Transportado para o próximo mês"
                                    elif abs(saldo) < 0.01:
                                        badge_tipo_text, badge_tipo_color = "Quitado", "#43A047"
                                        badge_tipo_tip = "Sem saldo a pagar"
                                    elif saldo >= 10.0 and pagos > 0.0:
                                        badge_tipo_text, badge_tipo_color = "Pago –", "#FB8C00"
                                        badge_tipo_tip = "Pagamento parcial registrado"
                                    else:
                                        badge_tipo_text, badge_tipo_color = "Devido", "#e53935"
                                        badge_tipo_tip = "Nenhum pagamento"
                            except Exception:
                                pass

                            # Escolhe o badge a exibir na pill do card por TIPO (usa o cálculo específico do Comum quando aplicável)
                            _badge_to_show = badge_c_prev if (tipo_darf == "comum") else badge
                            st.markdown(
                                f"""
                                <div class="ir-card" style="margin-bottom: .5rem;">
                                  <div class="ir-head">
                                    <div class="ir-title">PRÉVIA DE IR</div>
                                    <span class="ir-pill" title="{badge_tipo_tip}" style="border-color:{badge_tipo_color}; color:{badge_tipo_color};">{badge_tipo_text}</span>
                                    {_delta_pill_html}
                                  </div>
                                  <div class="ir-row"><div class="ir-label">IR devido (mês)</div><div class="ir-value">{_fmt_brl(ir_mes)}</div></div>
                                  <div class="ir-row"><div class="ir-label">{_carry_label_html}</div><div class="ir-value">{_fmt_brl(carry10)}</div></div>
                                  {irrf_row_html}
                                  <div class="ir-row"><div class="ir-label">Total considerado</div><div class="ir-value">{_fmt_brl(total_cons)}</div></div>
                                  <div class="ir-row"><div class="ir-label">Pagamentos do mês</div><div class="ir-value">{_fmt_brl(pagos_ui)}</div></div>
                                  {sugerido_place_html or ''}
                                </div>
                                """,
                                unsafe_allow_html=True
                            )

                            if diag and total_cons < 10:
                                st.caption("Abaixo do mínimo; será carregado para o próximo mês.")

                            # Informação de snapshot vs. prévia
                            if diag and (snap_ir is not None) and (total_cons >= 10) and (abs(delta_snap) >= 0.01):
                                st.info(
                                    f"Prévia difere do snapshot atual em {_fmt_brl(delta_snap)}. Use **Recalcular Mês** para alinhar.",
                                    icon="ℹ️",
                                )

                            # --- Card: registro e listagem de pagamentos ---
                            with st.container(border=True):
                                # Header for the card
                                st.markdown(
                                    "<div class='ir-head'><div class='ir-title'>Registrar pagamento</div></div>",
                                    unsafe_allow_html=True,
                                )

                                # --- Formulário de novo pagamento ---
                                with st.form(f"form_darf_{tipo_darf}_{ano}_{m}", clear_on_submit=True):
                                    colf = st.columns([1.0, 1.0, 2.0, 1.0])
                                    with colf[0]:
                                        valor_pago_str = st.text_input(
                                            "Valor pago (R$)",
                                            value=("R$ {:,.2f}".format(float(suggested_now))).replace(",", "X").replace(".", ",").replace("X", "."),
                                        )
                                        try:
                                            valor_pago = float(valor_pago_str.replace("R$", "").replace(".", "").replace(",", ".").strip())
                                        except Exception:
                                            valor_pago = 0.0
                                    with colf[1]:
                                        data_pagamento = st.date_input("Data de pagamento", value=_dt.date.today(), format="DD/MM/YYYY")
                                    with colf[2]:
                                        obs = st.text_input("Observações", placeholder="opcional")
                                    with colf[3]:
                                        # Empurra o botão para alinhar com os outros campos (altura do label ~32px)
                                        st.markdown("<div style='height:32px'></div>", unsafe_allow_html=True)
                                        sub = st.form_submit_button("Adicionar", use_container_width=True)

                                    if sub:
                                        try:
                                            data_str = data_pagamento.strftime("%Y-%m-%d")
                                            inserir_pagamento_darf(
                                                supabase=supabase,
                                                user_id=user_id,
                                                ano=ano,
                                                mes=m,
                                                tipo=tipo_darf,
                                                valor_pago=valor_pago,
                                                data_pagamento=data_str,
                                                obs=obs or "",
                                            )
                                            st.success("Pagamento registrado.")
                                            st.session_state["pag8_cache_epoch"] += 1
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Erro ao salvar pagamento: {e}")

                                # Separador entre o formulário e a lista
                                st.markdown("<hr style='border-color: rgba(255,255,255,.08); margin: 10px 0;'>", unsafe_allow_html=True)

                                # --- Listagem de pagamentos do mês/regime ---
                                st.markdown(
                                    "<div class='ir-head'><div class='ir-title'>Pagamentos registrados</div></div>",
                                    unsafe_allow_html=True,
                                )

                                def _fmt_brl(v: float) -> str:
                                    try:
                                        return ("R$ {:,.2f}".format(float(v))).replace(",", "X").replace(".", ",").replace("X", ".")
                                    except Exception:
                                        return "R$ 0,00"

                                if not pagamentos:
                                    st.info("Nenhum pagamento registrado para esta competência.")
                                else:
                                    total_pago = 0.0
                                    for row in pagamentos:
                                        pid = row.get("id")
                                        data_str = row.get("data_pagamento") or ""
                                        try:
                                            # Normaliza para DD/MM/AAAA caso venha em ISO
                                            data_fmt = _dt__.fromisoformat(str(data_str)).strftime("%d/%m/%Y")
                                        except Exception:
                                            data_fmt = str(data_str)
                                        valor = float(row.get("valor_pago", 0.0) or 0.0)
                                        total_pago += valor
                                        obs_txt = (row.get("obs") or "").strip()

                                        c1, c2, c3, c4 = st.columns([1.6, 1.2, 5.6, 0.6])
                                        c1.markdown(
                                            f"<div class='ir-label'>Data</div><div class='ir-value'>{data_fmt}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        c2.markdown(
                                            f"<div class='ir-label'>Valor</div><div class='ir-value'>{_fmt_brl(valor)}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        c3.markdown(
                                            f"<div class='ir-label'>Obs.</div><div class='ir-value' style='font-weight:400;'>{obs_txt or '-'}</div>",
                                            unsafe_allow_html=True,
                                        )
                                        with c4:
                                            if st.button("🗑️", key=f"del_{tipo_darf}_{pid}", use_container_width=True):
                                                try:
                                                    # Exclui no banco
                                                    excluir_pagamento_darf(supabase, pid)

                                                    # Atualiza imediatamente a lista local e grava override na sessão
                                                    pagamentos = [r for r in pagamentos if r.get("id") != pid]
                                                    st.session_state[override_key] = pagamentos

                                                    # Limpa caches (para próximas leituras) e atualiza epoch
                                                    try: _cached_listar_pag.clear()
                                                    except Exception: pass
                                                    try: _cached_diag.clear()
                                                    except Exception: pass
                                                    try: _cached_snapshot.clear()
                                                    except Exception: pass

                                                    st.session_state["pag8_cache_epoch"] = st.session_state.get("pag8_cache_epoch", 0) + 1

                                                    # Força reexecução já com a lista override aplicada
                                                    st.rerun()
                                                except Exception as e:
                                                    st.error(f"Erro ao excluir: {e}")

                                    # Linha de separação e total dentro do mesmo card
                                    st.markdown(
                                        "<hr style='border-color: rgba(255,255,255,.08); margin: 8px 0;'>",
                                        unsafe_allow_html=True,
                                    )
                                    t1, t2 = st.columns([1.6, 1.2])
                                    t1.markdown("<div class='ir-label'>Total pago</div>", unsafe_allow_html=True)
                                    t2.markdown(f"<div class='ir-value'>{_fmt_brl(total_pago)}</div>", unsafe_allow_html=True)

                    # --- Mini manual DARF (código 6015) --- (movido para o final da aba "DARF")
                    with st.expander("ℹ️ Como pagar a DARF (código 6015)", expanded=False):
                        # CSS customizado para o manual DARF (acima do primeiro uso)
                        st.markdown("""
<style>
.ir-manual .ir-row {
  align-items: flex-start;
  justify-content: flex-start;
  gap: .5rem;
}
.ir-manual .ir-label {
  flex: 0 0 220px;
}
.ir-manual .ir-value {
  white-space: normal;
}
</style>
""", unsafe_allow_html=True)
                        st.markdown(
                            """
                            <div class="ir-card ir-manual" style="margin-bottom:.5rem;">
                              <div class="ir-head">
                                <div class="ir-title">Como preencher</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Regra do mínimo (&lt; R$ 10):</div>
                                <div class="ir-value">Se o total considerado do mês for inferior a R$ 10, não há pagamento naquele mês; o valor é acumulado. Em dezembro, o saldo é carregado para janeiro (não se perde).</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Quando pagar:</div>
                                <div class="ir-value">Até o último dia útil do mês seguinte ao das operações.</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Código:</div>
                                <div class="ir-value">6015 – Ganhos Líquidos em Renda Variável</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Período de apuração (PA):</div>
                                <div class="ir-value">MM/AAAA do mês em que ocorreram as operações (ex.: 03/2025)</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Valor:</div>
                                <div class="ir-value">Use o “Sugerido a pagar agora” do app (já considera compensações e a regra de &lt; R$ 10)</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Onde pagar:</div>
                                <div class="ir-value"><a href="https://sicalc.receita.economia.gov.br/sicalc/rapido/contribuinte" target="_blank" rel="noopener noreferrer">SicalcWeb</a> (Receita Federal) ou Internet Banking em “Pagamento de DARF”.</div>
                              </div>

                              <div class="ir-row">
                                <div class="ir-label">Identificação:</div>
                                <div class="ir-value">Informe seu CPF e confira os dados antes de confirmar.</div>
                              </div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
