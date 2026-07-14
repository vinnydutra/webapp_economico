import os
import tempfile
import time
from collections import defaultdict
from datetime import date, datetime
from typing import Dict, List, Tuple

import streamlit as st
import yfinance as yf

from utils import (
    carregar_carteira_supabase,
    deletar_ativo_carteira,
    editar_ativo_carteira,
    formatar_numero_para_float,
    get_logo_img_tag,
    importar_nota_xp_pdf,
    inserir_ativo_carteira,
    inserir_venda,
    restaurar_usuario_sessao,
    supabase_autenticado,
    alocar_coberturas_por_lote,
    redirecionar_para_login,
    tratar_erro_autenticacao,
)
from utils_style import apply_global_dark_theme


restaurar_usuario_sessao()
supabase = supabase_autenticado()

st.set_page_config(page_title="Posição Atual", page_icon="📊", layout="wide")
apply_global_dark_theme()

# -------------------------------------------------------------------------------------
# Estilos (layout inspirado na Página 4)
# -------------------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .block-container {
        padding-top: 0.5rem;
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
        max-width: 100% !important;
    }
    .fin-page-bg {
        background: linear-gradient(180deg, #1c1f2b 0%, #1b1d27 100%);
        border-radius: 14px;
        padding: 14px;
        box-shadow: 0 12px 24px rgba(0,0,0,0.35);
    }
    .fin-header-card {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 0 12px;
        margin-top: 8px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .fin-header-card:hover {
        transform: none !important;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32) !important;
    }
    .fin-title-card {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 10px 12px;
        margin-top: 8px;
        box-shadow: none;
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
    .fin-row-marker {
        display: none;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 6px 10px;
        margin-top: 6px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)):hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 18px rgba(0, 0, 0, 0.45);
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"] {
        display: flex;
        align-items: center;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-row-marker) div[data-testid="column"]:last-child {
        justify-content: center;
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
    }
    .fin-panel-marker {
        display: none;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-panel-marker):not(:has(.fin-row-marker)):not(:has(div[data-testid="stVerticalBlock"] .fin-panel-marker)) {
        background-color: #303445;
        color: #E5E7EB;
        border-radius: 10px;
        padding: 0 14px 12px 14px;
        margin-top: 8px;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-panel-marker):not(:has(.fin-row-marker)):not(:has(div[data-testid="stVerticalBlock"] .fin-panel-marker)):hover {
        transform: none !important;
        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32) !important;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-panel-marker) h3 {
        margin-top: 0;
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

# -------------------------------------------------------------------------------------
# Sessão e logout
# -------------------------------------------------------------------------------------
if "usuario" not in st.session_state or not st.session_state.usuario:
    redirecionar_para_login()

usuario_logado = st.session_state.get("usuario", "desconhecido")
uid = st.session_state.uid


if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

# -------------------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------------------
DEBUG_PRECOS = False


def parse_data_compra(data_str: str) -> datetime:
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    st.error(f"Data inválida: {data_str}")
    return datetime.min


def formatar_valor(numero: float) -> str:
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def formatar_data_ddmmyy(valor) -> str:
    try:
        if isinstance(valor, datetime):
            return valor.strftime("%d/%m/%y")
        if isinstance(valor, date):
            return datetime.combine(valor, datetime.min.time()).strftime("%d/%m/%y")
        return str(valor)
    except Exception:
        return str(valor)


def _ticker_cache_key(ticker: str) -> str:
    t = (ticker or "").upper().strip()
    return t[:-3] if t.endswith(".SA") else t


def obter_preco_ativo(ticker: str) -> str:
    try:
        ticker_yf = yf.Ticker(ticker)
        hist = ticker_yf.history(period="5d")
        preco_atual = hist["Close"].dropna().iloc[-1]
        return formatar_valor(float(preco_atual))
    except Exception:
        return "Erro"


def obter_preco_ativo_float(ticker: str) -> float:
    try:
        ticker_yf = yf.Ticker(ticker)
        hist = ticker_yf.history(period="5d")
        preco_atual = hist["Close"].dropna().iloc[-1]
        return round(float(preco_atual), 2)
    except Exception:
        return 0.0


@st.cache_data(ttl=120, show_spinner=False)
def _preco_float_cache(ticker: str) -> float:
    return obter_preco_ativo_float(ticker)


@st.cache_data(ttl=120, show_spinner=False)
def _preco_str_cache(ticker: str) -> str:
    return obter_preco_ativo(ticker)


def _custo_final_unit_para_item(item: Dict, alloc_por_ticker: Dict, supabase_client) -> Tuple[float, Dict]:
    """
    Calcula o custo final unitário econômico do lote:
    (custo_original + custo_operacional/qtde) - dividendos_unitarios_acumulados - (credito_liquido_opcoes_alocado/qtde)
    Retorna: (custo_final_unit, detalhes_dict)
    """
    ticker = item["Ticker"].upper()
    data_compra = parse_data_compra(item["Data de Compra"])
    quantidade = int(item.get("Quantidade") or 0)
    if quantidade <= 0:
        return 0.0, {"custo_base_unit": 0.0, "div_por_acao": 0.0, "opc_por_acao": 0.0}

    custo_original = formatar_numero_para_float(item["Custo"])
    custo_oper_total = formatar_numero_para_float(item.get("Custo Operacional"))
    custo_base_unit = custo_original + (custo_oper_total / quantidade if quantidade > 0 else 0.0)

    res = (
        None
    )
    try:
        res = (
            supabase_client.table("dividendos_recebidos")
            .select("*")
            .eq("ticker", ticker)
            .gte("data", str(data_compra))
            .lte("data", str(date.today()))
            .execute()
        )
        dividendos_brutos = res.data or []
    except Exception as exc:
        if tratar_erro_autenticacao(exc):
            st.stop()
        dividendos_brutos = []
    dividendos_unit_total = sum(float(d.get("valor") or 0.0) for d in dividendos_brutos)

    alloc = (alloc_por_ticker.get(ticker) or {}).get("por_lote", {})
    lote_alloc = alloc.get(item.get("UUID"), {}) if item.get("UUID") else {}
    credito_total_opcoes = float(lote_alloc.get("credito_total", 0.0))

    custo_bruto_total = custo_base_unit * quantidade
    desconto_div_total = dividendos_unit_total * quantidade
    desconto_opc_total = credito_total_opcoes

    custo_final_unit = max(0.0, (custo_bruto_total - desconto_div_total - desconto_opc_total) / quantidade)

    detalhes = {
        "custo_base_unit": custo_base_unit,
        "div_por_acao": dividendos_unit_total,
        "opc_por_acao": (desconto_opc_total / quantidade) if quantidade > 0 else 0.0,
    }
    return custo_final_unit, detalhes


# -------------------------------------------------------------------------------------
# Estado inicial
# -------------------------------------------------------------------------------------
if "linha_acao" not in st.session_state:
    st.session_state["linha_acao"] = None
if "modo_acao" not in st.session_state:
    st.session_state["modo_acao"] = None
if st.session_state.get("pdf_upload_done"):
    st.session_state["pdf_upload_done"] = False
    st.rerun()
if "file_uploader_key" not in st.session_state:
    st.session_state["file_uploader_key"] = str(time.time())


def _recarregar_carteira():
    dados_carteira = carregar_carteira_supabase(uid) or []
    return [
        {
            "UUID": item["id"],
            "Ticker": item["ticker"],
            "Quantidade": item["quantidade"],
            "Custo": f'{item["custo"]:.2f}'.replace(".", ","),
            "Data de Compra": item["data_compra"],
            "Custo Operacional": f'{float(item.get("custo_operacional") or 0):.2f}'.replace(".", ","),
        }
        for item in dados_carteira
    ]


# Carregar carteira na sessão
if "posicao_atual" not in st.session_state or not st.session_state.posicao_atual:
    st.session_state.posicao_atual = _recarregar_carteira()

# Ordenação e retrocompat
st.session_state.posicao_atual.sort(key=lambda x: parse_data_compra(x.get("Data de Compra", "01/01/1900")))
for item in st.session_state.posicao_atual:
    if "Preço Pago (R$)" in item:
        item["Custo"] = item.pop("Preço Pago (R$)")

# -------------------------------------------------------------------------------------
# Alocação de coberturas (uma chamada por ticker)
# -------------------------------------------------------------------------------------
_allocacoes_por_ticker: Dict[str, Dict] = {}
_lotes_por_ticker: Dict[str, List[Dict]] = defaultdict(list)
for _it in st.session_state.posicao_atual:
    _lotes_por_ticker[_it["Ticker"].upper()].append(
        {"uuid": _it["UUID"], "data_compra": parse_data_compra(_it["Data de Compra"]), "quantidade": int(_it["Quantidade"])}
    )
for _tk, _lots in _lotes_por_ticker.items():
    try:
        _alloc = alocar_coberturas_por_lote(uid, _tk, _lots)
        _allocacoes_por_ticker[_tk] = _alloc
    except Exception:
        _allocacoes_por_ticker[_tk] = {"por_lote": {}, "ops": {}}

# -------------------------------------------------------------------------------------
# Totais (para pills e rodapé)
# -------------------------------------------------------------------------------------
precos_cache: Dict[str, Dict[str, float | str]] = {}


def _preco_cached(ticker_raw: str) -> Dict[str, float | str]:
    key = _ticker_cache_key(ticker_raw)
    if key not in precos_cache:
        preco_float = float(_preco_float_cache(ticker_raw))
        precos_cache[key] = {
            "preco_float": preco_float,
            "preco_str": _preco_str_cache(ticker_raw) if preco_float > 0 else "Erro",
        }
    return precos_cache[key]


total_geral = 0.0
for _item in st.session_state.posicao_atual:
    try:
        qt = int(_item.get("Quantidade") or 0)
        if qt <= 0:
            continue
        custo_unit, _ = _custo_final_unit_para_item(_item, _allocacoes_por_ticker, supabase)
        total_geral += qt * custo_unit
    except Exception:
        continue

total_variacao_reais = 0.0
for _item in st.session_state.posicao_atual:
    try:
        preco_atual = float(_preco_cached(_item["Ticker"])["preco_float"])
        custo_unit, _ = _custo_final_unit_para_item(_item, _allocacoes_por_ticker, supabase)
        qt = int(_item.get("Quantidade") or 0)
        if qt <= 0:
            continue
        variacao_reais = (preco_atual - custo_unit) * qt
        total_variacao_reais += variacao_reais
    except Exception:
        continue

# Valor de mercado (para participação) — usa último preço do yfinance
total_valor_mercado = 0.0
for _item in st.session_state.posicao_atual:
    try:
        qt = int(_item.get("Quantidade") or 0)
        if qt <= 0:
            continue
        preco_atual = float(_preco_cached(_item["Ticker"])["preco_float"])
        total_valor_mercado += qt * preco_atual
    except Exception:
        continue

# -------------------------------------------------------------------------------------
# Layout principal
# -------------------------------------------------------------------------------------
headers = [
    ("Logo", 0.8),
    ("Ticker", 1.3),
    ("Quant", 0.9),
    ("Preço (R$)", 1.3),
    ("Total", 1.4),
    ("Últ. Preço (R$)", 1.2),
    ("Result. (R$)", 1.2),
    ("Result. %", 1.0),
    ("Data", 1.3),
    ("Ação", 0.8),
]
weights = [w for _, w in headers]



# Header card com título e pills
pill_cor = "#00FF00" if total_variacao_reais >= 0 else "#FF4C4C"
st.markdown(
    f"""
    <div class="fin-title-card">
        <div style="display:flex; justify-content: space-between; align-items: center; gap: 12px;">
            <div style="display:flex; align-items:center; gap:12px; flex-wrap: wrap;">
                <h1 style="margin: 0; color: #E5E7EB;">Posição Atual</h1>
                <span style="
                    background-color: rgba(255,255,255,0.05);
                    color: #E5E7EB;
                    font-weight: 700;
                    padding: 6px 10px;
                    border-radius: 999px;
                    border: 1px solid rgba(255,255,255,0.12);
                    font-size: 0.9rem;
                    line-height: 1;
                    white-space: nowrap;">
                    Total Carteira: {formatar_valor(total_geral)}
                </span>
                <span style="
                    background-color: rgba(255,255,255,0.05);
                    color: {pill_cor};
                    font-weight: 700;
                    padding: 6px 10px;
                    border-radius: 999px;
                    border: 1px solid {pill_cor};
                    font-size: 0.9rem;
                    line-height: 1;
                    white-space: nowrap;">
                    Variação: {formatar_valor(total_variacao_reais)}
                </span>
            </div>
            <div style="display:flex; justify-content:flex-end; align-items:center; gap:10px;">
                <span style="color:#cfd3e6; font-size:14px; white-space:nowrap;">👤 {usuario_logado}</span>
                <form action='/?logout=true' method='get' style='margin:0;'>
                    <button type='submit' title='Logout' style='background: none; border: none; color: #cfd3e6; font-size: 18px; cursor: pointer; padding: 0; line-height: 1;'>⏻</button>
                </form>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# Painéis lado a lado (manual à esquerda, upload à direita)
col_left, col_right = st.columns([1, 1], gap="small")

# Adicionar ativo manualmente
with col_left:
    # Adicionar ativo manualmente
    with st.container():
        st.markdown('<div class="fin-panel-marker"></div>', unsafe_allow_html=True)
        st.markdown("### Adicionar Ativo")
        with st.form("form_adicionar_ativo", clear_on_submit=False):
            # Linha 1: ticker / quantidade / custo
            r1c1, r1c2, r1c3 = st.columns(3)
            with r1c1:
                ticker = st.text_input("Ticker").upper()
            with r1c2:
                quantidade = st.number_input("Quantidade", min_value=0, step=1, format="%d")
            with r1c3:
                preco = st.number_input("Preço (R$)", min_value=0.0, step=0.01)

            # Linha 2: data / custo operacional / ação
            r2c1, r2c2, r2c3 = st.columns(3)
            with r2c1:
                data_compra_obj = st.date_input("Data de Compra", value=datetime.now(), format="DD/MM/YYYY")
            with r2c2:
                custo_operacional = st.number_input("Custo Oper. (R$)", min_value=0.0, step=0.01, format="%.2f")
            with r2c3:
                st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
                clicked_add = st.form_submit_button("Adicionar", use_container_width=True)

            if clicked_add:
                try:
                    data_formatada = data_compra_obj.strftime("%d/%m/%y")
                except Exception:
                    st.error("Data inválida! Use o formato DD/MM/YY.")
                    st.stop()
                if ticker and quantidade > 0 and preco > 0:
                    inserir_ativo_carteira(uid, ticker, quantidade, float(preco), data_formatada, custo_operacional)
                    st.session_state.posicao_atual = _recarregar_carteira()
                    st.success("Ativo adicionado com sucesso!")
                else:
                    st.warning("Preencha todos os campos corretamente.")

# Importação de nota XP
with col_right:
    # Importação de nota XP
    with st.container():
        st.markdown('<div class="fin-panel-marker"></div>', unsafe_allow_html=True)
        st.markdown("### Importar Nota de Negociação")
        arquivos_pdf = st.file_uploader(
            "Importar Nota XP (PDF)",
            type=["pdf"],
            accept_multiple_files=True,
            key=st.session_state["file_uploader_key"],
            label_visibility="collapsed",
        )
        ativos_importados_total = []
        if arquivos_pdf:
            for arquivo_pdf in arquivos_pdf:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                    temp_file.write(arquivo_pdf.read())
                    caminho_temp = temp_file.name
                try:
                    ativos_importados = importar_nota_xp_pdf(caminho_temp, uid)
                    import fitz

                    with fitz.open(caminho_temp) as doc:
                        _ = "\n".join([page.get_text() for page in doc])
                    os.remove(caminho_temp)

                    if ativos_importados:
                        ativos_importados_total.extend(ativos_importados)
                        st.markdown(f"#### ✅ Ativos identificados na nota: `{arquivo_pdf.name}`")
                        for ativo in ativos_importados:
                            custo_unitario = str(ativo.get("Custo", "")).strip()
                            custo_op = float(ativo.get("Custo Operacional", 0.0))
                            data_compra = ativo.get("Data de Compra", "").strip()
                            st.markdown(
                                f"""
                                <span style='font-weight:bold'>Ticker:</span> <span style='font-family: monospace;'>{ativo['Ticker']}</span> |
                                <span style='font-weight:bold'>Quantidade:</span> {ativo['Quantidade']} |
                                <span style='font-weight:bold'>Custo unitário:</span> R&#36; {custo_unitario} |
                                <span style='font-weight:bold'>Custo operacional:</span> R&#36; {custo_op:.2f} |
                                <span style='font-weight:bold'>Data:</span> {data_compra}
                                """,
                                unsafe_allow_html=True,
                            )
                    else:
                        st.warning(f"Nenhum ativo encontrado na nota: `{arquivo_pdf.name}`")
                except Exception as e:
                    st.error(f"Erro ao importar `{arquivo_pdf.name}`: {str(e)}")

            if ativos_importados_total and st.button("Importar ativos para a carteira"):
                for ativo in ativos_importados_total:
                    preco_float = float(ativo["Custo"].replace(",", "."))
                    custo_op = ativo.get("Custo Operacional", 0.0)
                    inserir_ativo_carteira(uid, ativo["Ticker"], ativo["Quantidade"], preco_float, ativo["Data de Compra"], custo_op)
                st.session_state.posicao_atual = _recarregar_carteira()
                st.success(f"{len(ativos_importados_total)} ativo(s) importado(s) com sucesso!")
            st.session_state["file_uploader_key"] = str(time.time())
            st.rerun()

# Toggle de agrupamento (logo abaixo do card de importação, alinhado à direita dentro da coluna direita)
toggle_col_left, toggle_col_right = col_right.columns([1, 1], gap="small")
with toggle_col_left:
    st.markdown("<div style='height: 28px;'></div>", unsafe_allow_html=True)
    agrupar_por_ticker = st.toggle(
        "Agrupar por ticker",
        value=False,
        help="Consolida todos os lotes do mesmo ticker em uma linha (edição desabilitada enquanto agrupado).",
    )

# Header da tabela
colgroup_html = "".join(f"<col style='width:{(peso/sum(weights))*100:.2f}%;'>" for peso in weights)
headers_html = "".join(f"<th>{col}</th>" for col, _ in headers)
st.markdown(
    f"""
    <div class="fin-header-card">
        <table class="fin-header-table">
            <colgroup>{colgroup_html}</colgroup>
            <thead><tr>{headers_html}</tr></thead>
        </table>
    </div>
    """,
    unsafe_allow_html=True,
)

# Linhas
if not st.session_state.posicao_atual:
    st.markdown(
        """
        <div class="fin-panel" style="text-align:center; color:#ccc;">
            Nenhum ativo na carteira.
        </div>
        """,
        unsafe_allow_html=True,
    )
else:
    if agrupar_por_ticker:
        st.session_state["linha_acao"] = None
        st.session_state["modo_acao"] = None

    # Se agrupar, consolida lotes por ticker (mantém custos econômicos)
    if agrupar_por_ticker:
        agg = {}
        for item in st.session_state.posicao_atual:
            ticker_raw = (item["Ticker"] or "").upper()
            ticker_key = _ticker_cache_key(ticker_raw)
            qt = int(item.get("Quantidade") or 0)
            if qt <= 0:
                continue
            custo_unit, det = _custo_final_unit_para_item(item, _allocacoes_por_ticker, supabase)
            total_custo = qt * custo_unit
            data_obj = parse_data_compra(item.get("Data de Compra", "01/01/1900"))
            reg = agg.setdefault(
                ticker_key,
                {
                    "ticker_raw": ticker_raw,
                    "ticker_disp": ticker_key,
                    "quantidade": 0,
                    "custo_total": 0.0,
                    "custo_base_total": 0.0,
                    "div_total": 0.0,
                    "opc_total": 0.0,
                    "min_data": data_obj,
                },
            )
            reg["quantidade"] += qt
            reg["custo_total"] += total_custo
            reg["custo_base_total"] += det.get("custo_base_unit", 0.0) * qt
            reg["div_total"] += det.get("div_por_acao", 0.0) * qt
            reg["opc_total"] += det.get("opc_por_acao", 0.0) * qt
            if data_obj < reg["min_data"]:
                reg["min_data"] = data_obj

        linhas_exibidas = []
        for reg in agg.values():
            qt = reg["quantidade"]
            custo_unit_med = reg["custo_total"] / qt if qt > 0 else 0.0
            custo_base_med = reg["custo_base_total"] / qt if qt > 0 else 0.0
            div_med = reg["div_total"] / qt if qt > 0 else 0.0
            opc_med = reg["opc_total"] / qt if qt > 0 else 0.0
            preco_info = _preco_cached(reg["ticker_raw"])
            preco_float = float(preco_info["preco_float"])
            total_linha = qt * custo_unit_med
            valor_mercado_linha = qt * preco_float
            variacao_reais = (preco_float - custo_unit_med) * qt
            variacao_percentual = (
                ((preco_float - custo_unit_med) / custo_unit_med) * 100 if custo_unit_med > 0 else 0.0
            )
            linhas_exibidas.append(
                {
                    "UUID": f"agg::{reg['ticker_raw']}",
                    "TickerRaw": reg["ticker_raw"],
                    "TickerDisp": reg["ticker_disp"],
                    "Quantidade": qt,
                    "CustoUnit": custo_unit_med,
                    "CustoBaseMed": custo_base_med,
                    "DivMed": div_med,
                    "OpcMed": opc_med,
                    "TotalLinha": total_linha,
                    "ValorMercado": valor_mercado_linha,
                    "PrecoInfo": preco_info,
                    "VariacaoReais": variacao_reais,
                    "VariacaoPercentual": variacao_percentual,
                    "DataCompra": reg["min_data"].strftime("%d/%m/%y"),
                }
            )
    else:
        linhas_exibidas = st.session_state.posicao_atual

    for item in linhas_exibidas:
        uuid = item["UUID"]
        if agrupar_por_ticker:
            ticker_raw = item["TickerRaw"]
            ticker_disp = item["TickerDisp"]
            quantidade = item["Quantidade"]
            custo_final_unit = item["CustoUnit"]
            total_linha = item["TotalLinha"]
            valor_mercado_linha = item.get("ValorMercado", 0.0)
            participacao = (valor_mercado_linha / total_valor_mercado * 100) if total_valor_mercado > 0 else 0
            total_fmt = formatar_valor(total_linha)
            preco_info = item["PrecoInfo"]
            preco_ultimo = preco_info["preco_str"]
            div_med = float(item["DivMed"])
            opc_med = float(item["OpcMed"])
            custo_base = float(item["CustoBaseMed"])
            tem_ajuste = (abs(div_med) > 0 or abs(opc_med) > 0) and abs(custo_final_unit - custo_base) > 1e-9
            custo_fmt = formatar_valor(custo_final_unit)
            if tem_ajuste:
                tooltip = (
                    f"Original: R$ {custo_base:,.2f} | "
                    f"Div: -R$ {div_med:,.2f} | "
                    f"Opções: -R$ {opc_med:,.2f}"
                )
                tooltip = tooltip.replace(",", "X").replace(".", ",").replace("X", ".")
                custo_fmt = f"<span class='fin-tip' data-tip=\"{tooltip}\">{custo_fmt} <span style='opacity:0.85;'>*</span></span>"
            variacao_reais = item["VariacaoReais"]
            variacao_percentual = item["VariacaoPercentual"]
            variacao_reais_fmt = formatar_valor(variacao_reais)
            cor_reais = "#00FF00" if variacao_reais >= 0 else "#FF4C4C"
            cor_pct = "#00FF00" if variacao_percentual >= 0 else "#FF4C4C"
            variacao_percentual_fmt = f"{variacao_percentual:+.2f}%".replace(".", ",")
            data_compra_exibe = item["DataCompra"]
        else:
            ticker_raw = (item["Ticker"] or "").upper()
            ticker_disp = ticker_raw[:-3] if ticker_raw.endswith(".SA") else ticker_raw or "—"
            custo_final_unit, det = _custo_final_unit_para_item(item, _allocacoes_por_ticker, supabase)
            quantidade = int(item.get("Quantidade") or 0)
            total_linha = quantidade * custo_final_unit
            total_fmt = formatar_valor(total_linha)
            preco_info = _preco_cached(ticker_raw)
            valor_mercado_linha = quantidade * float(preco_info["preco_float"])
            participacao = (valor_mercado_linha / total_valor_mercado * 100) if total_valor_mercado > 0 else 0
            preco_ultimo = preco_info["preco_str"]
            div_unit = float(det["div_por_acao"])
            opc_unit = float(det["opc_por_acao"])
            custo_base = float(det["custo_base_unit"])
            tem_ajuste = (abs(div_unit) > 0 or abs(opc_unit) > 0) and abs(custo_final_unit - custo_base) > 1e-9
            custo_fmt = formatar_valor(custo_final_unit)
            if tem_ajuste:
                tooltip = (
                    f"Original: R$ {custo_base:,.2f} | "
                    f"Div: -R$ {div_unit:,.2f} | "
                    f"Opções: -R$ {opc_unit:,.2f}"
                )
                tooltip = tooltip.replace(",", "X").replace(".", ",").replace("X", ".")
                custo_fmt = f"<span class='fin-tip' data-tip=\"{tooltip}\">{custo_fmt} <span style='opacity:0.85;'>*</span></span>"
            variacao_percentual = ((float(preco_info["preco_float"]) - custo_final_unit) / custo_final_unit * 100) if custo_final_unit > 0 else 0
            variacao_reais = (float(preco_info["preco_float"]) - custo_final_unit) * quantidade
            variacao_reais_fmt = formatar_valor(variacao_reais)
            cor_reais = "#00FF00" if variacao_reais >= 0 else "#FF4C4C"
            cor_pct = "#00FF00" if variacao_percentual >= 0 else "#FF4C4C"
            variacao_percentual_fmt = f"{variacao_percentual:+.2f}%".replace(".", ",")
            data_compra_exibe = item["Data de Compra"]

        with st.container():
            st.markdown('<div class="fin-row-marker"></div>', unsafe_allow_html=True)
            cols = st.columns(weights)
            cols[0].markdown(get_logo_img_tag(ticker_raw or "LOGO", size=30), unsafe_allow_html=True)
            cols[1].markdown(f"**{ticker_disp}**")
            cols[2].markdown(f"**{quantidade}**")
            cols[3].markdown(custo_fmt, unsafe_allow_html=True)
            cols[4].markdown(
                f"<span title='Participação: {participacao:.2f}%'>{total_fmt}</span>", unsafe_allow_html=True
            )
            cols[5].markdown(f"**{preco_ultimo}**", unsafe_allow_html=True)
            cols[6].markdown(f"<span style='color:{cor_reais};'>{variacao_reais_fmt}</span>", unsafe_allow_html=True)
            cols[7].markdown(f"<span style='color:{cor_pct};'>{variacao_percentual_fmt}</span>", unsafe_allow_html=True)
            cols[8].markdown(f"**{data_compra_exibe}**")
            with cols[9]:
                if agrupar_por_ticker:
                    st.markdown("—")
                else:
                    if st.button("⚙️", key=f"gear_{uuid}"):
                        if st.session_state.get("linha_acao") == uuid:
                            st.session_state["linha_acao"] = None
                            st.session_state["modo_acao"] = None
                        else:
                            st.session_state["linha_acao"] = uuid
                            st.session_state["modo_acao"] = None

        if (not agrupar_por_ticker) and st.session_state.get("linha_acao") == uuid:
            with st.container():
                st.markdown('<div class="fin-row-pop"></div>', unsafe_allow_html=True)
                b1, b2, b3, b4 = st.columns([1.1, 0.9, 0.9, 1.1])
                if b1.button("✅ Registrar Venda", key=f"sell_{uuid}"):
                    st.session_state["modo_acao"] = "vender"
                if b2.button("✏️ Editar", key=f"edit_{uuid}"):
                    st.session_state["modo_acao"] = "editar"
                if b3.button("❌ Excluir", key=f"del_{uuid}"):
                    resposta = deletar_ativo_carteira(uuid)
                    if hasattr(resposta, "data") and resposta.data:
                        st.session_state.posicao_atual = [at for at in st.session_state.posicao_atual if at["UUID"] != uuid]
                        st.success("Ativo excluído com sucesso.")
                        st.session_state["linha_acao"] = None
                        st.session_state["modo_acao"] = None
                    else:
                        st.error("Erro ao tentar excluir o ativo.")
                if b4.button("↩️ Cancelar", key=f"cancel_{uuid}"):
                    st.session_state["linha_acao"] = None
                    st.session_state["modo_acao"] = None
                    st.rerun()

            # Form de edição
            if st.session_state.get("modo_acao") == "editar":
                with st.container():
                    st.markdown('<div class="fin-row-pop"></div>', unsafe_allow_html=True)
                    with st.form(f"form_edit_{uuid}", border=False):
                        c_tk, c_qtd, c_custo, c_data, c_cop = st.columns([1, 1, 1, 1, 1])
                        with c_tk:
                            novo_ticker_input = st.text_input(
                                "Ticker (cru do banco)", value=item["Ticker"], key=f"tk_{uuid}"
                            )
                        with c_qtd:
                            nova_quantidade = st.number_input(
                                "Nova Quantidade", min_value=1, value=quantidade, step=1, key=f"q_{uuid}"
                            )
                        with c_custo:
                            novo_custo = st.number_input(
                                "Novo Preço (R$)",
                                min_value=0.0,
                                value=float(item["Custo"].replace(",", ".")),
                                step=0.01,
                                format="%.2f",
                                key=f"c_{uuid}",
                            )
                        with c_data:
                            nova_data_obj = parse_data_compra(item["Data de Compra"]).date()
                            nova_data = st.date_input("Nova Data de Compra", value=nova_data_obj, format="DD/MM/YYYY")
                        with c_cop:
                            novo_custo_operacional = st.number_input(
                                "Novo Custo Operacional (R$)",
                                min_value=0.0,
                                format="%.2f",
                                value=formatar_numero_para_float(item.get("Custo Operacional", 0.0)),
                                key=f"cop_{uuid}",
                            )
                        c_s, c_c = st.columns([1, 1])
                        salvar = c_s.form_submit_button("💾 Salvar Alterações")
                        cancelar = c_c.form_submit_button("↩️ Cancelar")
                        if cancelar:
                            st.session_state["modo_acao"] = None
                            st.session_state["linha_acao"] = None
                            st.rerun()
                        if salvar:
                            novo_ticker_raw = " ".join(str(novo_ticker_input or "").strip().upper().split())
                            if not novo_ticker_raw:
                                st.error("Ticker não pode ficar vazio.")
                            elif " " in novo_ticker_raw:
                                st.error("Ticker não deve conter espaços.")
                            else:
                                novos_dados = {
                                    "ticker": novo_ticker_raw,
                                    "quantidade": int(nova_quantidade),
                                    "custo": float(novo_custo),
                                    "data_compra": nova_data.strftime("%d/%m/%y"),
                                    "custo_operacional": novo_custo_operacional,
                                }
                                try:
                                    resposta = editar_ativo_carteira(uuid, novos_dados)
                                    if resposta:
                                        st.session_state.posicao_atual = _recarregar_carteira()
                                        st.success("Ativo atualizado com sucesso!")
                                        st.session_state["linha_acao"] = None
                                        st.session_state["modo_acao"] = None
                                        st.rerun()
                                    else:
                                        st.error("Erro ao atualizar ativo.")
                                except Exception as e:
                                    st.error(f"Não foi possível salvar as alterações. Erro: {e}")

            # Form de venda
            if st.session_state.get("modo_acao") == "vender":
                with st.container():
                    st.markdown('<div class="fin-row-pop"></div>', unsafe_allow_html=True)
                    with st.form(f"form_sell_{uuid}", border=False):
                        c_q, c_pv, c_dv, c_cov, c_irrf = st.columns([1, 1, 1, 1, 1])
                        qtd_venda = c_q.number_input(
                            "Quantidade Vendida",
                            min_value=1,
                            max_value=quantidade,
                            value=quantidade,
                            step=1,
                            key=f"qv_{uuid}",
                        )
                        preco_venda = c_pv.number_input(
                            "Preço de Venda (R$)", min_value=0.0, step=0.01, format="%.2f", key=f"pv_{uuid}"
                        )
                        data_venda = c_dv.date_input("Data da Venda", value=datetime.now(), format="DD/MM/YYYY", key=f"dv_{uuid}")
                        custo_operacional_venda = c_cov.number_input(
                            "Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f", key=f"cov_{uuid}"
                        )
                        irrf_venda = c_irrf.number_input(
                            "IRRF (R$)", min_value=0.0, step=0.01, format="%.2f", key=f"irrf_{uuid}"
                        )
                        c_s, c_c = st.columns([1, 1])
                        confirmar = c_s.form_submit_button("💾 Confirmar Venda")
                        cancelar = c_c.form_submit_button("↩️ Cancelar")

                        if cancelar:
                            st.session_state["modo_acao"] = None
                            st.session_state["linha_acao"] = None
                            st.rerun()

                        if confirmar:
                            try:
                                custo_operacional_compra_total = float(item["Custo Operacional"].replace(",", "."))
                                if qtd_venda == quantidade:
                                    custo_operacional_compra_proporcional = custo_operacional_compra_total
                                    custo_operacional_restante = 0.0
                                else:
                                    custo_operacional_compra_proporcional = round(
                                        custo_operacional_compra_total * qtd_venda / quantidade, 2
                                    )
                                    custo_operacional_restante = round(
                                        custo_operacional_compra_total - custo_operacional_compra_proporcional, 2
                                    )
                                custo_operacional_total = custo_operacional_compra_proporcional + custo_operacional_venda

                                venda_ok = inserir_venda(
                                    uid,
                                    item["Ticker"],
                                    qtd_venda,
                                    float(item["Custo"].replace(",", ".")),
                                    item["Data de Compra"],
                                    float(preco_venda),
                                    data_venda,
                                    custo_operacional_total,
                                    irrf=irrf_venda,
                                )
                                if venda_ok:
                                    nova_qtd = int(quantidade - qtd_venda)
                                    if nova_qtd > 0:
                                        resp_edit = editar_ativo_carteira(
                                            uuid,
                                            {"quantidade": nova_qtd, "custo_operacional": custo_operacional_restante},
                                        )
                                        if not resp_edit:
                                            st.error("Erro ao atualizar a carteira com a nova quantidade e custo operacional.")
                                    else:
                                        deletar_ativo_carteira(uuid)
                                    st.session_state.posicao_atual = _recarregar_carteira()
                                    st.success("Venda registrada com sucesso!")
                                    st.session_state["linha_acao"] = None
                                    st.session_state["modo_acao"] = None
                                    st.rerun()
                                else:
                                    st.error("Erro ao registrar venda.")
                            except Exception as e:
                                st.error(f"Erro ao processar a venda: {e}")

# Rodapé totais
st.markdown(
    f"""
    <div class="fin-panel" style="display:flex; gap:12px; align-items:center; justify-content:flex-start;">
        <span style="font-weight:700;">Total Carteira:</span> <span>{formatar_valor(total_geral)}</span>
        <span style="font-weight:700; margin-left:20px;">Variação Total:</span>
        <span style="color:{'#00FF00' if total_variacao_reais >= 0 else '#FF4C4C'};">{formatar_valor(total_variacao_reais)}</span>
    </div>
    """,
    unsafe_allow_html=True,
)



if DEBUG_PRECOS:
    print(f"[DEBUG_PRECOS] tickers consultados no Yahoo: {len(precos_cache)}")
