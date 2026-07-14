import json
import streamlit as st
import time
from datetime import datetime, date
from typing import List, Dict, Any
from utils import (
    formatar_valor,
    get_logo_img_tag,
    supabase_autenticado,
    redirecionar_para_login,
    tratar_erro_autenticacao,
    obter_total_dividendos_para_lote_intervalado,
    obter_credito_opcoes_para_lote_intervalado,
    editar_venda,
    deletar_venda,
)


st.set_page_config(page_title="Histórico de Vendas", page_icon="🧾", layout="wide")

# Barra de usuário + logout (padrão simplificado)
usuario_logado = st.session_state.get("usuario", "desconhecido")
st.markdown(
    f"""
    <div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 0.5rem;'>
        <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
        <form action='/?logout=true' method='get' style='margin:0;'>
            <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
        </form>
    </div>
    """,
    unsafe_allow_html=True,
)

# Logout
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()


def _handle_auth_error(exc):
    if tratar_erro_autenticacao(exc):
        st.stop()


if "uid" not in st.session_state or not st.session_state.uid:
    redirecionar_para_login()

# caches simples para reduzir chamadas repetidas de abatimentos
_div_cache: Dict = {}
_opt_cache: Dict = {}

st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0rem;
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
    }
    .fin-card {
        background-color: transparent;
        color: #E5E7EB;
        border-radius: 0;
        padding: 0;
        margin-top: 0;
        box-shadow: none;
    }
    .fin-card-inner {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 0;
        margin-top: 10px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
    }
    .fin-card:hover,
    .fin-card-inner:hover {
        transform: none !important;
        box-shadow: none !important;
    }
    .fin-header-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
    }
    .fin-header-table,
    .fin-header-table thead,
    .fin-header-table tr,
    .fin-header-table th {
        border: none !important;
    }
    .fin-header-table th {
        font-size: 0.9rem;
        color: #CDD2E7;
        font-weight: 700;
        padding: 4px 6px;
        text-align: left;
        border: none;
    }
    .fin-card2-table th {
        color: #F7F8FF;
    }
    .fin-card2-table th,
    .fin-card2-table td {
        border: none;
    }
    /* header em bloco próprio dentro do card principal */
    .fin-header-card {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 0;
        margin-top: 10px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .fin-header-card:hover {
        transform: none !important;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32) !important;
    }
    .fin-action-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 6px 8px;
        background-color: #1F2230;
        color: #E5E7EB;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 8px;
        text-decoration: none;
        font-size: 0.95rem;
        cursor: pointer;
    }
    .fin-action-btn:hover {
        background-color: #262a3b;
    }
    /* centraliza o botão de ações na última coluna */
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"]:last-child {
        display: flex;
        justify-content: center;
        align-items: center;
        padding: 0 !important;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"]:last-child > div {
        width: 100%;
        display: flex;
        justify-content: center;
        align-items: center;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"]:last-child button {
        margin: 0;
    }
    /* alinha verticalmente o conteúdo das colunas das linhas */
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"] {
        display: flex;
        align-items: center;
    }
    /* zera bordas das tabelas de dados (linhas) */
    .fin-card2-table,
    .fin-card2-table tr,
    .fin-card2-table td,
    .fin-card2-table th {
        border: none !important;
        border-collapse: collapse;
    }
    /* card das linhas (usado como marker para containers streamlit) */
    .fin-row-marker {
        display: none;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 4px 8px;
        margin-top: 0;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)):hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 18px rgba(0, 0, 0, 0.45);
    }
    /* grade visível para debug dentro das linhas */
    .fin-header-table th {
        border: none !important;
    }
    /* popover inline de ações */
    .fin-row-pop {
        display: none;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-pop) {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 12px 14px;
        margin-top: 6px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-pop):not(:has(div[data-testid="stVerticalBlock"] .fin-row-pop)):hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 18px rgba(0, 0, 0, 0.45);
    }
    .fin-tooltip {
        position: relative;
        display: inline-block;
        cursor: help;
    }

    .fin-tooltip .fin-tooltiptext {
        visibility: hidden;
        width: max-content;
        max-width: 260px;
        background-color: #1F2230;
        color: #E5E7EB;
        text-align: left;
        padding: 6px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
        box-shadow: 0 6px 16px rgba(0, 0, 0, 0.35);

        position: absolute;
        z-index: 1000;
        bottom: 130%;
        left: 50%;
        transform: translateX(-50%);

        white-space: nowrap;
    }

    .fin-tooltip:hover .fin-tooltiptext {
        visibility: visible;
    }
    .fin-tip {
        position: relative;
        cursor: default;
    }
    .fin-tip[data-tip]:hover::after {
        content: attr(data-tip);
        position: absolute;
        left: 0;
        top: -2.4rem;
        background: #1f2230;
        color: #eee;
        border: 1px solid #444;
        padding: 6px 8px;
        border-radius: 6px;
        white-space: nowrap;
        font-size: 12px;
        box-shadow: 0 6px 12px rgba(0,0,0,0.35);
        z-index: 9999;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

headers = [
    ("Logo", 0.6),
    ("Ticker", 1.0),
    ("Quant.", 0.8),
    ("Preço Compra", 1.2),
    ("Preço Venda", 1.2),
    ("Valor Compra", 1.3),
    ("Valor Venda", 1.3),
    ("Custos", 1.1),
    ("Resultado", 1.3),
    ("Data Venda", 1.0),
    ("Ações", 0.8),
]
peso_total = sum(peso for _, peso in headers)
colgroup_html = "".join(
    f"<col style='width:{(peso/peso_total)*100:.2f}%;'>"
    for _, peso in headers
)
headers_html = "".join(f"<th>{col}</th>" for col, _ in headers)


def formatar_data_ddmmyy(valor):
    if not valor:
        return "—"
    try:
        if isinstance(valor, (datetime, date)):
            dt = valor if isinstance(valor, datetime) else datetime.combine(valor, datetime.min.time())
        else:
            s = str(valor)
            for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(s[:19], fmt)
                    break
                except Exception:
                    dt = None
            if dt is None:
                return s
        return dt.strftime("%d/%m/%y")
    except Exception:
        return str(valor)


def _to_date(valor):
    if not valor:
        return None
    try:
        if isinstance(valor, datetime):
            return valor.date()
        if isinstance(valor, date):
            return valor
        s = str(valor)
        try:
            return datetime.fromisoformat(s[:10]).date()
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(s[:19], fmt).date()
            except Exception:
                continue
        return None
    except Exception:
        return None


def _parse_date_any(x) -> date | None:
    """
    Converte entradas flexíveis em date para cálculo de abatimentos.
    Aceita: None, datetime/date, string dd/mm/yy, dd/mm/yyyy, yyyy-mm-dd.
    """
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    if not s:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except Exception:
            continue
    try:
        return datetime.fromisoformat(s.replace("T", " ").split("+")[0].split(".")[0]).date()
    except Exception:
        return None


def _fmt_money_br(x) -> str:
    try:
        v = float(x)
    except Exception:
        v = 0.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _preco_compra_cell(preco_exibido, preco_original, dividendos, opcoes, tem_ajuste: bool) -> str:
    """
    Retorna HTML seguro p/ exibir o preço compra na célula:
    - Se tem ajuste: valor + * e tooltip (title) em uma linha
    - Se não: apenas valor (sem tooltip e sem *)
    """
    valor_fmt = _fmt_money_br(preco_exibido)
    if not tem_ajuste:
        return valor_fmt

    po = _fmt_money_br(preco_original)
    dv = _fmt_money_br(dividendos)
    op = _fmt_money_br(opcoes)
    tooltip = f"Original: {po} | Div: -{dv} | Opções: -{op}"
    tooltip = tooltip.replace(",", "X").replace(".", ",").replace("X", ".")
    return (
        f"<span class='fin-tip' data-tip=\"{tooltip}\">{valor_fmt} <span style=\"opacity:0.85;\">*</span></span>"
    )


def carregar_ultima_venda():
    uid = st.session_state.get("uid")
    if not uid:
        return None
    try:
        sb = supabase_autenticado()
        resp = (
            sb.table("ativos_vendidos")
            .select("*")
            .eq("user_id", uid)
            .order("data_venda", desc=True)
            .limit(1)
            .execute()
        )
        data = getattr(resp, "data", []) or []
        return data[0] if data else None
    except Exception as exc:
        _handle_auth_error(exc)
        return None

# Todas as vendas do usuário (ordenadas por data desc)
def carregar_vendas_usuario():
    uid = st.session_state.get("uid")
    if not uid:
        return []
    return _carregar_vendas_cache(uid)


@st.cache_data(show_spinner=False)
def _carregar_vendas_cache(uid: str):
    try:
        sb = supabase_autenticado()
        resp = (
            sb.table("ativos_vendidos")
            .select("*")
            .eq("user_id", uid)
            .order("data_venda", desc=True)
            .execute()
        )
        return getattr(resp, "data", []) or []
    except Exception as exc:
        _handle_auth_error(exc)
        return []


def _calcular_custos_ajustados(venda: Dict[str, Any], uid: str) -> Dict[str, float]:
    preco_compra_unit = float(venda.get("preco_compra") or 0.0)
    qtd = float(venda.get("quantidade") or 0.0)
    ticker = (venda.get("ticker") or "").upper()
    dt_compra = _parse_date_any(venda.get("data_compra"))
    dt_venda = _parse_date_any(venda.get("data_venda"))

    if not ticker or not dt_compra or not dt_venda or qtd <= 0:
        return {
            "preco_compra_original": preco_compra_unit,
            "dividendos_lote": 0.0,
            "creditos_opcoes_lote": 0.0,
            "preco_compra_ajustado": preco_compra_unit,
        }

    div_key = (uid, ticker, dt_compra, dt_venda)
    opt_key = (uid, ticker, dt_compra, dt_venda, qtd)

    if div_key in _div_cache:
        dividendos = _div_cache[div_key]
    else:
        try:
            dividendos = float(
                obter_total_dividendos_para_lote_intervalado(uid, ticker, dt_compra.isoformat(), dt_venda.isoformat())
                or 0.0
            )
        except Exception:
            dividendos = 0.0
        _div_cache[div_key] = dividendos

    if opt_key in _opt_cache:
        creditos = _opt_cache[opt_key]
    else:
        try:
            creditos = float(
                obter_credito_opcoes_para_lote_intervalado(
                    uid, ticker, dt_compra.isoformat(), dt_venda.isoformat(), qtd
                )
                or 0.0
            )
        except Exception:
            creditos = 0.0
        _opt_cache[opt_key] = creditos

    custo_ajustado = max(preco_compra_unit - dividendos - creditos, 0.0)
    return {
        "preco_compra_original": preco_compra_unit,
        "dividendos_lote": dividendos,
        "creditos_opcoes_lote": creditos,
        "preco_compra_ajustado": custo_ajustado,
    }


def preparar_vendas_com_custo_ajustado(vendas: List[Dict[str, Any]], uid: str):
    inicio = time.perf_counter()
    ajustadas = []
    for venda in vendas:
        calculos = _calcular_custos_ajustados(venda, uid)
        nova = {**venda}
        nova.update(calculos)
        ajustadas.append(nova)
    duracao = time.perf_counter() - inicio
    return ajustadas, duracao


def _serialize_vendas(vendas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Converte datas e tipos não serializáveis para estruturas simples (para cache)."""
    serial = []
    for v in vendas:
        novo = {}
        for k, val in v.items():
            if isinstance(val, (datetime, date)):
                novo[k] = val.isoformat()
            else:
                try:
                    json.dumps(val)
                    novo[k] = val
                except Exception:
                    novo[k] = str(val)
        serial.append(novo)
    return serial


def preparar_vendas_com_custo_ajustado_cached(vendas: List[Dict[str, Any]], uid: str):
    serial = _serialize_vendas(vendas)
    return _preparar_vendas_com_custo_ajustado_cached(uid, serial)


@st.cache_data(show_spinner=False)
def _preparar_vendas_com_custo_ajustado_cached(uid: str, vendas_serial: List[Dict[str, Any]]):
    return preparar_vendas_com_custo_ajustado(vendas_serial, uid)


def agrupar_vendas_por_ticker(vendas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grupos: Dict[str, Dict[str, Any]] = {}
    for venda in vendas:
        ticker = (venda.get("ticker") or "").upper()
        if not ticker:
            continue

        grupo = grupos.setdefault(
            ticker,
            {
                "id": f"agg::{ticker}",
                "ticker": ticker,
                "quantidade_total": 0,
                "soma_q_preco_compra": 0.0,
                "soma_q_preco_compra_ajustado": 0.0,
                "soma_q_preco_venda": 0.0,
                "custo_operacional_total": 0.0,
                "irrf_total": 0.0,
                "dividendos_total": 0.0,
                "creditos_opcoes_total": 0.0,
                "data_venda_mais_recente": None,
            },
        )

        q = int(venda.get("quantidade") or 0)
        pc = float(venda.get("preco_compra") or 0)
        pc_ajust = float(venda.get("preco_compra_ajustado") or pc)
        pv = float(venda.get("preco_venda") or 0)
        custo_op = float(venda.get("custo_operacional") or 0)
        irrf = float(venda.get("irrf") or 0)
        data_venda = venda.get("data_venda")
        dividendos_lote = float(venda.get("dividendos_lote") or 0.0)
        creditos_lote = float(venda.get("creditos_opcoes_lote") or 0.0)

        grupo["quantidade_total"] += q
        grupo["soma_q_preco_compra"] += q * pc
        grupo["soma_q_preco_compra_ajustado"] += q * pc_ajust
        grupo["soma_q_preco_venda"] += q * pv
        grupo["custo_operacional_total"] += custo_op
        grupo["irrf_total"] += irrf
        grupo["dividendos_total"] += dividendos_lote * q
        grupo["creditos_opcoes_total"] += creditos_lote * q

        if data_venda is not None:
            atual = grupo["data_venda_mais_recente"]
            grupo["data_venda_mais_recente"] = max(atual, data_venda) if atual is not None else data_venda

    agregados: List[Dict[str, Any]] = []
    for ticker, g in grupos.items():
        qt = g["quantidade_total"] or 0
        preco_compra_medio = g["soma_q_preco_compra_ajustado"] / qt if qt else 0.0
        preco_venda_medio = g["soma_q_preco_venda"] / qt if qt else 0.0
        agregados.append(
            {
                "id": g["id"],
                "ticker": g["ticker"],
                "quantidade": qt,
                "preco_compra": preco_compra_medio,
                "preco_compra_original": (g["soma_q_preco_compra"] / qt) if qt else 0.0,
                "preco_compra_ajustado": preco_compra_medio,
                "preco_venda": preco_venda_medio,
                "custo_operacional": g["custo_operacional_total"],
                "irrf": g["irrf_total"],
                "dividendos_lote": (g["dividendos_total"] / qt) if qt else 0.0,
                "creditos_opcoes_lote": (g["creditos_opcoes_total"] / qt) if qt else 0.0,
                "data_venda": g["data_venda_mais_recente"],
            }
        )

    agregados.sort(key=lambda x: x.get("data_venda") or "", reverse=True)
    return agregados


uid_atual = st.session_state.get("uid")
vendas_raw = carregar_vendas_usuario()
if uid_atual:
    vendas, tempo_ajuste = preparar_vendas_com_custo_ajustado_cached(vendas_raw, uid_atual)
else:
    vendas, tempo_ajuste = vendas_raw, 0.0
agrupar_por_ticker = st.toggle(
    "Agrupar vendas por ticker",
    value=False,
    help="Mostra os totais consolidados por ticker (leitura). Para editar, use o modo detalhado.",
)
if agrupar_por_ticker:
    vendas_exibidas = agrupar_vendas_por_ticker(vendas)
    st.session_state["linha_acao"] = None
else:
    vendas_exibidas = vendas

# Total consolidado do resultado (independente do modo)
total_resultado = 0.0
for v in vendas_exibidas:
    q = float(v.get("quantidade") or 0)
    pc = float(v.get("preco_compra_ajustado") or v.get("preco_compra") or 0)
    pv = float(v.get("preco_venda") or 0)
    custos_v = float(v.get("custo_operacional") or 0) + float(v.get("irrf") or 0)
    total_resultado += (q * pv) - (q * pc) - custos_v

pill_color = "#00FF00" if total_resultado >= 0 else "#FF4C4C"
pill_text = formatar_valor(total_resultado)

st.markdown(
    f"""
    <div class="fin-card" style="min-height: 120px;">
        <div style="display:flex; justify-content: space-between; align-items: center;">
            <div style="display:flex; align-items:center; gap:12px;">
                <h1 style="margin: 0; color: #E5E7EB;">Histórico de Vendas</h1>
                <span style="
                    background-color: #303445;
                    color: {pill_color};
                    font-weight: 700;
                    padding: 6px 10px;
                    border-radius: 999px;
                    border: 1px solid {pill_color};
                    font-size: 0.9rem;
                    line-height: 1;
                    white-space: nowrap;">
                    {pill_text}
                </span>
            </div>
            <div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px;'>
                <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
                <form action='/?logout=true' method='get' style='margin:0;'>
                    <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
                </form>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# Header em bloco próprio (mesmo nível das linhas)
st.markdown(
    f"""
    <div class="fin-header-card">
        <table class="fin-header-table">
            <colgroup>
                {colgroup_html}
            </colgroup>
            <thead>
                <tr>
                    {headers_html}
                </tr>
                </thead>
            </table>
        </div>
    """,
    unsafe_allow_html=True,
)

# controle de linha aberta
if "linha_acao" not in st.session_state:
    st.session_state["linha_acao"] = None

# Render das linhas como cards usando containers com marker para manter visual
if not vendas_exibidas:
    st.markdown(
        """
        <div class="fin-card-inner" style="text-align:center; color:#ccc; margin-top:10px;">
            Nenhuma venda encontrada.
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    weights = [peso for _, peso in headers]
    for venda in vendas_exibidas:
        venda_id = venda.get("id") or venda.get("ticker", "row")
        ticker_raw = (venda.get("ticker") or "").upper()
        ticker_disp = ticker_raw[:-3] if ticker_raw.endswith(".SA") else ticker_raw or "—"
        logo = get_logo_img_tag(ticker_raw, size=30) if ticker_raw else get_logo_img_tag("LOGO", size=28)
        ticker_form_val = venda.get("ticker") or ""
        quantidade = float(venda.get("quantidade") or 0)
        preco_c_original = float(
            venda.get("preco_compra_original")
            if venda.get("preco_compra_original") is not None
            else venda.get("preco_compra")
            or 0
        )
        preco_c = float(venda.get("preco_compra_ajustado") or preco_c_original)
        preco_v = float(venda.get("preco_venda") or 0)
        dividendos_lote = float(venda.get("dividendos_lote") or 0.0)
        creditos_lote = float(venda.get("creditos_opcoes_lote") or 0.0)
        valor_c = quantidade * preco_c
        valor_v = quantidade * preco_v
        custos = float(venda.get("custo_operacional") or 0) + float(venda.get("irrf") or 0)
        resultado = valor_v - valor_c - custos
        resultado_html = f"<span style='color:{'#00FF00' if resultado >= 0 else '#FF4C4C'};'>{formatar_valor(resultado)}</span>"
        data_html = formatar_data_ddmmyy(venda.get("data_venda"))
        data_compra_fmt = formatar_data_ddmmyy(venda.get("data_compra"))
        data_venda_fmt = formatar_data_ddmmyy(venda.get("data_venda"))
        dt_compra = _to_date(venda.get("data_compra"))
        dt_venda = _to_date(venda.get("data_venda"))
        dias_txt = "—"
        meses_txt = "—"
        if dt_compra and dt_venda:
            dias = (dt_venda - dt_compra).days
            dias_txt = f"{dias} dias"
            meses = dias / 30.4375
            meses_arred = round(meses * 2) / 2
            meses_txt = f"{meses_arred:.1f} meses"
        custo_operacional = float(venda.get("custo_operacional") or 0)
        irrf = float(venda.get("irrf") or 0)
        data_form_val = venda.get("data_venda")
        if isinstance(data_form_val, datetime):
            data_form_val = data_form_val.date()
        elif not isinstance(data_form_val, date):
            try:
                data_form_val = datetime.fromisoformat(str(data_form_val)[:10]).date()
            except Exception:
                data_form_val = date.today()

        with st.container():
            st.markdown('<div class="fin-row-marker"></div>', unsafe_allow_html=True)
            cols = st.columns(weights)
            cols[0].markdown(logo, unsafe_allow_html=True)
            cols[1].markdown(f"**{ticker_disp}**")
            cols[2].markdown(f"**{int(quantidade)}**")
            tem_ajuste = (
                (abs(dividendos_lote) > 0 or abs(creditos_lote) > 0)
                and abs(preco_c - preco_c_original) > 1e-9
            )
            cols[3].markdown(
                _preco_compra_cell(preco_c, preco_c_original, dividendos_lote, creditos_lote, tem_ajuste),
                unsafe_allow_html=True,
            )
            cols[4].markdown(f"**{formatar_valor(preco_v)}**")
            cols[5].markdown(f"**{formatar_valor(valor_c)}**")
            cols[6].markdown(f"**{formatar_valor(valor_v)}**")
            cols[7].markdown(f"**{formatar_valor(custos)}**")
            cols[8].markdown(resultado_html, unsafe_allow_html=True)
            cols[9].markdown(
                f"""
                <span class="fin-tooltip">
                    <strong>{data_venda_fmt}</strong>
                    <span class="fin-tooltiptext">
                        {data_compra_fmt} → {data_venda_fmt} : {dias_txt} ({meses_txt})
                    </span>
                </span>
                """,
                unsafe_allow_html=True,
            )
            with cols[10]:
                if not agrupar_por_ticker:
                    if st.button("⚙️", key=f"gear_{venda_id}"):
                        st.session_state["linha_acao"] = venda_id if st.session_state.get("linha_acao") != venda_id else None
                else:
                    st.markdown("—")

        if (not agrupar_por_ticker) and (st.session_state.get("linha_acao") == venda_id):
            with st.container():
                st.markdown('<div class="fin-row-pop"></div>', unsafe_allow_html=True)
                with st.form(f"form_{venda_id}", border=False):
                    c_ticker, c_q, c_pc, c_pv, c_co, c_irrf, c_data = st.columns([1.0, 0.8, 1.0, 1.0, 1.0, 1.0, 1.0])
                    novo_ticker = c_ticker.text_input("Ticker", value=ticker_form_val, key=f"tk_{venda_id}")
                    nova_quantidade = c_q.number_input(
                        "Quantidade", min_value=0, value=int(venda.get("quantidade") or 0), step=1, key=f"q_{venda_id}"
                    )
                    novo_preco_compra = c_pc.number_input(
                        "Preço Compra", min_value=0.0, value=float(venda.get("preco_compra") or 0), step=0.01, format="%.2f", key=f"pc_{venda_id}"
                    )
                    novo_preco_venda = c_pv.number_input(
                        "Preço Venda", min_value=0.0, value=float(venda.get("preco_venda") or 0), step=0.01, format="%.2f", key=f"pv_{venda_id}"
                    )
                    novo_custo_operacional = c_co.number_input(
                        "Custo Oper.", min_value=0.0, value=float(venda.get("custo_operacional") or 0), step=0.01, format="%.2f", key=f"co_{venda_id}"
                    )
                    novo_irrf = c_irrf.number_input(
                        "IRRF", min_value=0.0, value=float(venda.get("irrf") or 0), step=0.01, format="%.2f", key=f"irrf_{venda_id}"
                    )
                    nova_data = c_data.date_input(
                        "Data Venda", value=data_form_val, format="DD/MM/YYYY", key=f"dv_{venda_id}"
                    )

                    b1, b2, b3 = st.columns(3)
                    salvar = b1.form_submit_button("Salvar")
                    excluir = b2.form_submit_button("Excluir")
                    cancelar = b3.form_submit_button("Cancelar")

                    if cancelar:
                        st.session_state["linha_acao"] = None
                        st.rerun()
                    if salvar:
                        try:
                            uid = st.session_state.get("uid")
                            if not uid:
                                st.error("Usuário não autenticado.")
                            else:
                                payload = {
                                    "ticker": novo_ticker.strip(),
                                    "quantidade": nova_quantidade,
                                    "preco_compra": novo_preco_compra,
                                    "preco_venda": novo_preco_venda,
                                    "custo_operacional": novo_custo_operacional,
                                    "irrf": novo_irrf,
                                    "data_venda": nova_data.isoformat(),
                                }
                                editar_venda(venda_id, payload)
                                st.session_state["linha_acao"] = None
                                st.success("Venda atualizada.")
                                st.rerun()
                        except Exception as exc:
                            _handle_auth_error(exc)
                            st.error("Erro ao salvar a venda.")
                    if excluir:
                        try:
                            uid = st.session_state.get("uid")
                            if not uid:
                                st.error("Usuário não autenticado.")
                            else:
                                deletar_venda(venda_id)
                                st.session_state["linha_acao"] = None
                                st.success("Venda excluída.")
                                st.rerun()
                        except Exception as exc:
                            _handle_auth_error(exc)
                            st.error("Erro ao excluir a venda.")
