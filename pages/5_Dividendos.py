import streamlit as st
from utils import (
    carregar_dividendos_usuario,
    inserir_dividendo,
    excluir_dividendo,
    redirecionar_para_login,
    tratar_erro_autenticacao,
    get_logo_img_tag,
    executar_query_supabase,
    supabase_autenticado,
)
from datetime import datetime
# Modificação de teste para forçar salvamento
from utils_style import apply_global_dark_theme
from textwrap import dedent

import pandas as pd


st.set_page_config(page_title="Dividendos", page_icon="💰", layout="wide")
apply_global_dark_theme()

# Mantém o mesmo ajuste de margens utilizado nas páginas no padrão final.
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Copia o estilo oficial de cards e tabelas do template (fin-card-marker + tema escuro).
st.markdown(
    """
    <style>
	    .fin-card-marker {
	        display: none;
	    }
	    div[data-testid="stVerticalBlock"]:has(.fin-card-marker) {
	        background-color: #303445;
	        color: #E5E7EB;
	        border-radius: 10px;
	        padding: 12px 14px;
	        margin-top: -2px;
	        margin-bottom: -2px;
	        box-shadow: none !important;
	        transition: transform 0.18s ease, box-shadow 0.18s ease;
	    }
	    div[data-testid="stVerticalBlock"]:has(.fin-card-marker) > div:has(> .fin-card-marker) {
	        display: none;
	    }
	    /* Garantir que o card do header não "suba" */
	    div[data-testid="stVerticalBlock"]:has(.fin-card-marker):hover {
	        transform: none !important;
	        box-shadow: none !important;
	    }

	    /* Header em HTML (padrão Pag4: bordas praticamente coladas no texto) */
	    .fin-header-card {
	        background-color: #303445;
	        color: #E5E7EB;
	        border-radius: 10px;
	        padding: 0;
	        margin-top: 10px;
	        margin-bottom: 0;
	        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32);
	        transition: transform 0.18s ease, box-shadow 0.18s ease;
	    }
	    .fin-header-card:hover {
	        transform: none !important;
	        box-shadow: 0 8px 14px rgba(0, 0, 0, 0.32) !important;
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

	    /* card das linhas (marker para containers streamlit) - padrão Pag4 */
	    .fin-row-marker {
	        display: none;
	    }
	    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)) {
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
	    /* centraliza o botão de ações na última coluna */
	    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)) div[data-testid="column"]:last-child {
	        display: flex;
	        justify-content: center;
	        align-items: center;
	        padding: 0 !important;
	    }
	    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)) div[data-testid="column"]:last-child > div {
	        width: 100%;
	        display: flex;
	        justify-content: center;
	        align-items: center;
	    }
	    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)) div[data-testid="column"]:last-child button {
	        margin: 0;
	    }
	    /* alinha verticalmente o conteúdo das colunas das linhas */
	    div[data-testid="stVerticalBlock"]:has(.fin-row-marker):not(:has(div[data-testid="stVerticalBlock"] .fin-row-marker)) div[data-testid="column"] {
	        display: flex;
	        align-items: center;
	    }

    .fin-title {
        font-size: 0.85rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #AEB5CC;
        margin-bottom: 12px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .fin-badge {
        background-color: rgba(255, 255, 255, 0.12);
        padding: 2px 10px;
        border-radius: 999px;
        font-size: 0.7rem;
        color: #E4E8FF;
    }
    .fin-label {
        color: #9FA5BD;
        font-size: 0.9rem;
    }
    .fin-divider {
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        margin: 14px 0;
    }

	    /* Tabela manual (colunas + HTML) com densidade/cores da Pag4 */
    .tabela-dividendos .celula {
        background-color: transparent;
        border: none;
        padding: 4px 6px;
        border-radius: 0;
	        color: #E5E7EB;
        font-size: 0.9rem;
        line-height: 1.2rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        text-align: left;
    }
    .tabela-dividendos .celula.header {
        background-color: transparent;
        color: #CDD2E7;
        font-weight: 700;
        padding: 4px 6px;
    }
    .tabela-dividendos .celula *, .tabela-dividendos .celula.header * {
        color: inherit !important;
    }
    .fin-kpi-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 12px;
        margin-top: 6px;
    }
    .fin-kpi-card {
        background: #303445;
        color: #E5E7EB;
        padding: 12px;
        border-radius: 10px;
        box-shadow: 0 8px 14px rgba(0,0,0,0.32);
        border: 1px solid rgba(255,255,255,0.06);
    }
    .fin-kpi-label {
        font-size: 0.8rem;
        color: #AEB5CC;
        margin-bottom: 6px;
    }
    .fin-kpi-value {
        font-size: 1.2rem;
        font-weight: 700;
    }
    .stButton button {
        white-space: nowrap;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Verificar sessão e exibir usuário com botão de logout no topo da tela
if "usuario" not in st.session_state or not st.session_state.usuario:
    redirecionar_para_login()
usuario_logado = st.session_state.get("usuario", "desconhecido")

# Lógica de logout
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

# Captura do usuário logado (padrão do app)
if (
    "usuario" not in st.session_state
    or not st.session_state.usuario
    or "uid" not in st.session_state
    or not st.session_state.uid
):
    redirecionar_para_login()

usuario = st.session_state.usuario.strip().lower()

st.markdown(
    f"""
    <div style='display:flex; align-items:center; justify-content:space-between; margin:0 0 8px 0; gap:16px;'>
        <h1 style='margin: 0;'>Controle de Dividendos</h1>
        <div style='display:flex; align-items:center; gap:10px;'>
            <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
            <form action='/?logout=true' method='get' style='margin:0;'>
                <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer; padding:0;'>⏻</button>
            </form>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

edit_id = st.session_state.get("edit_id")
editando = "edit_id" in st.session_state


def _handle_auth_error(exc):
    if tratar_erro_autenticacao(exc):
        st.stop()


def _format_currency(valor: float) -> str:
    try:
        return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"


def normalize_ticker_key(t):
    val = str(t or "").upper().strip()
    if val.endswith(".SA"):
        val = val[:-3]
    return val


def normalize_ticker_yahoo(t):
    original = str(t or "").upper().strip()
    if original.endswith(".SA"):
        return original
    base = normalize_ticker_key(original)
    if base and base[-1].isdigit():
        return base + ".SA"
    return base

# Alias de ticker SOMENTE para lookup de preço atual (Yahoo)
TICKER_PRICE_ALIASES = {
    "CPLE6": "CPLE3",
    "CPLE6.SA": "CPLE3.SA",
}


def ticker_para_preco_atual(t: str) -> str:
    """
    Retorna o ticker correto para lookup de preço atual.
    Mantém ticker histórico (ex: CPLE6) intacto para cálculos e exibição.
    """
    raw = str(t or "").upper().strip()
    aliased = TICKER_PRICE_ALIASES.get(raw, raw)
    return normalize_ticker_yahoo(aliased)


def display_ticker(t):
    val = str(t or "").upper().strip()
    return val[:-3] if val.endswith(".SA") else val


try:
    dividendos = carregar_dividendos_usuario(st.session_state.usuario)
except Exception as exc:
    _handle_auth_error(exc)
    dividendos = []
if dividendos:
    df = pd.DataFrame(dividendos)
    colunas_esperadas = ["id", "ticker", "tipo", "valor", "quantidade", "data"]
    df = df[[c for c in colunas_esperadas if c in df.columns]]
    df.columns = ["ID", "Ticker", "Tipo", "Valor (R$)", "Quantidade", "Data de Pagamento"]
    df = df[["ID", "Ticker", "Valor (R$)", "Quantidade", "Data de Pagamento", "Tipo"]]
    df["Total (R$)"] = df["Valor (R$)"] * df["Quantidade"]
    df["_data_dt"] = pd.to_datetime(df["Data de Pagamento"], dayfirst=True, errors="coerce")
    df["_mes"] = df["_data_dt"].dt.to_period("M").astype(str)
    df = df[["ID", "Ticker", "Valor (R$)", "Quantidade", "Total (R$)", "Data de Pagamento", "Tipo", "_data_dt", "_mes"]]
    df["Data de Pagamento"] = df["_data_dt"].dt.strftime("%d/%m/%Y").fillna("")
else:
    df = pd.DataFrame(
        columns=["ID", "Ticker", "Valor (R$)", "Quantidade", "Total (R$)", "Data de Pagamento", "Tipo", "_data_dt", "_mes"]
    )

df["_data_dt"] = pd.to_datetime(df["_data_dt"], errors="coerce")
if "_mes" in df.columns:
    df["_mes"] = df["_data_dt"].dt.to_period("M").astype(str)
df_original = df.copy()


# Se estiver editando, busca os dados da linha correspondente
if editando:
    try:
        registro = df_original[df_original["ID"] == st.session_state["edit_id"]].iloc[0]
        valor_inicial = float(registro["Valor (R$)"])
        quantidade_inicial = int(registro["Quantidade"])
        ticker_inicial = registro["Ticker"]
        tipo_inicial = registro["Tipo"]
        data_inicial = datetime.strptime(registro["Data de Pagamento"], "%d/%m/%Y")
    except Exception:
        valor_inicial = 0.0
        quantidade_inicial = 0
        ticker_inicial = ""
        tipo_inicial = "DIVIDENDO"
        data_inicial = datetime.today()
else:
    valor_inicial = 0.0
    quantidade_inicial = 0
    ticker_inicial = ""
    tipo_inicial = "DIVIDENDO"
    data_inicial = datetime.today()

# --------------------------
# Filtros + métricas
# --------------------------
today = pd.Timestamp.today().normalize()
ttm_cutoff = today - pd.Timedelta(days=365)

with st.container():
    st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
    st.markdown("#### Filtros")
    c1, c2, c3, c4 = st.columns([1.3, 1.2, 1.0, 1.2], gap="small")
    with c1:
        periodo_opcoes = ["Últimos 12 meses (TTM)", "Ano atual", "Tudo", "Personalizado"]
        periodo_escolhido = st.selectbox("Período", periodo_opcoes, index=0)
    with c2:
        tipo_escolhido = st.selectbox("Tipo", ["Ambos", "DIVIDENDO", "JCP"], index=0)
    with c3:
        ticker_filtro = st.text_input("Ticker (opcional)", value="").strip().upper()
    with c4:
        if periodo_escolhido == "Personalizado":
            inicio_default = (today - pd.Timedelta(days=90)).to_pydatetime()
            fim_default = today.to_pydatetime()
            intervalo_personalizado = st.date_input(
                "Selecione o intervalo",
                value=(inicio_default, fim_default),
                format="DD/MM/YYYY",
            )
        else:
            intervalo_personalizado = None

df_filtrado = df_original.copy()

if tipo_escolhido != "Ambos":
    df_filtrado = df_filtrado[df_filtrado["Tipo"] == tipo_escolhido]

if ticker_filtro:
    df_filtrado = df_filtrado[df_filtrado["Ticker"].str.contains(ticker_filtro, case=False, na=False)]

data_inicio = None
data_fim = today
if periodo_escolhido == "Últimos 12 meses (TTM)":
    data_inicio = ttm_cutoff
elif periodo_escolhido == "Ano atual":
    data_inicio = pd.Timestamp(today.year, 1, 1)
elif periodo_escolhido == "Personalizado" and intervalo_personalizado and len(intervalo_personalizado) == 2:
    try:
        data_inicio = pd.Timestamp(intervalo_personalizado[0])
        data_fim = pd.Timestamp(intervalo_personalizado[1])
        if data_inicio > data_fim:
            data_inicio, data_fim = data_fim, data_inicio
    except Exception:
        data_inicio = None
        data_fim = today

if data_inicio is not None:
    df_filtrado = df_filtrado[df_filtrado["_data_dt"].between(data_inicio, data_fim, inclusive="both")]

total_recebido = float(df_filtrado["Total (R$)"].sum()) if not df_filtrado.empty else 0.0
meses_unicos = int(df_filtrado["_data_dt"].dt.to_period("M").nunique()) if not df_filtrado.empty else 0
if periodo_escolhido == "Tudo" and meses_unicos == 0:
    meses_unicos = int(df_original["_data_dt"].dt.to_period("M").nunique())
media_mensal = total_recebido / meses_unicos if meses_unicos else 0.0
numero_pagamentos = int(len(df_filtrado))
tickers_pagadores = int(df_filtrado["Ticker"].nunique()) if not df_filtrado.empty else 0

with st.container():
    st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
    st.markdown("#### Visão do período")
    st.markdown(
        f"""
        <div class="fin-kpi-grid">
            <div class="fin-kpi-card">
                <div class="fin-kpi-label">Total recebido (R$)</div>
                <div class="fin-kpi-value">{_format_currency(total_recebido)}</div>
            </div>
            <div class="fin-kpi-card">
                <div class="fin-kpi-label">Média mensal (R$)</div>
                <div class="fin-kpi-value">{_format_currency(media_mensal)}</div>
            </div>
            <div class="fin-kpi-card">
                <div class="fin-kpi-label">Nº de pagamentos</div>
                <div class="fin-kpi-value">{numero_pagamentos}</div>
            </div>
            <div class="fin-kpi-card">
                <div class="fin-kpi-label">Nº de tickers pagadores</div>
                <div class="fin-kpi-value">{tickers_pagadores}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

aba_ranking, aba_dy, aba_timeline = st.tabs(["Ranking", "Dividend Yield", "Timeline"])

with aba_ranking:
    top_ranking_title, top_ranking_ordem = st.columns([1, 4], gap="small")
    with top_ranking_title:
        st.markdown("##### Ranking por ticker")
    with top_ranking_ordem:
        st.radio(
            "Ordenar por",
            ["Total", "Frequência", "Recência"],
            index=0,
            horizontal=True,
            key="ordenar_ranking_radio",
            label_visibility="collapsed",
        )
        ordem_escolhida = st.session_state.get("ordenar_ranking_radio", "Total")
    if df_filtrado.empty:
        st.info("Nenhum dividendo encontrado para os filtros selecionados.")
    else:
        agrupado = (
            df_filtrado.groupby("Ticker")
            .agg(
                total_recebido=("Total (R$)", "sum"),
                pagamentos=("ID", "count"),
                ultimo_pagamento=("_data_dt", "max"),
            )
            .reset_index()
        )
        agrupado["media_pagamento"] = agrupado["total_recebido"] / agrupado["pagamentos"]
        total_geral_ranking = agrupado["total_recebido"].sum()
        agrupado["participacao"] = agrupado["total_recebido"] / total_geral_ranking if total_geral_ranking else 0

        ordenacoes = {
            "Total": ("total_recebido", False),
            "Frequência": ("pagamentos", False),
            "Recência": ("ultimo_pagamento", False),
        }
        campo_ordem, asc = ordenacoes.get(ordem_escolhida, ("total_recebido", False))
        agrupado = agrupado.sort_values(campo_ordem, ascending=asc)

        linhas = []
        for _, row in agrupado.iterrows():
            logo = get_logo_img_tag(str(row["Ticker"]), size=28)
            ultimo_fmt = row["ultimo_pagamento"].strftime("%d/%m/%Y") if pd.notnull(row["ultimo_pagamento"]) else "-"
            participacao_pct = row["participacao"] * 100 if total_geral_ranking else 0
            linhas.append(
                dedent(
                    f"""
                    <tr>
                      <td class='celula'>{logo} <b>{display_ticker(row['Ticker'])}</b></td>
                      <td class='celula'>{_format_currency(row['total_recebido'])}</td>
                      <td class='celula'>{int(row['pagamentos'])}</td>
                      <td class='celula'>{ultimo_fmt}</td>
                      <td class='celula'>{_format_currency(row['media_pagamento'])}</td>
                      <td class='celula'>{participacao_pct:.2f}%</td>
                    </tr>
                    """
                ).strip()
            )

        tabela_html = dedent(
            f"""
            <table class="tabela-dividendos" style="width:100%;">
              <thead>
                <tr>
                  <th class='celula header'>Ticker</th>
                  <th class='celula header'>Total recebido (R$)</th>
                  <th class='celula header'>Pagamentos</th>
                  <th class='celula header'>Último pagamento</th>
                  <th class='celula header'>Média por pagamento (R$)</th>
                  <th class='celula header'>Participação (%)</th>
                </tr>
              </thead>
              <tbody>
                {''.join(linhas)}
              </tbody>
            </table>
            """
        ).strip()
        st.markdown(tabela_html, unsafe_allow_html=True)

with aba_dy:
    st.markdown("##### Dividend Yield por ticker")
    st.caption("Dividendos por ação calculados com base no período filtrado.")

    df_dy = df_filtrado.copy()
    if df_dy.empty:
        st.info("Nenhum dividendo no período selecionado para calcular DY.")
    else:
        df_dy = df_dy[df_dy["Quantidade"] > 0].copy()
        df_dy["TickerNorm"] = df_dy["Ticker"].apply(normalize_ticker_key)
        df_dy["dpa_evento"] = df_dy["Total (R$)"] / df_dy["Quantidade"]
        dpa_por_ticker = (
            df_dy.groupby("TickerNorm")
            .agg(dpa_periodo=("dpa_evento", "sum"), ticker_raw=("Ticker", "first"))
            .reset_index()
        )

        _precos_cache = {}

        def _preco_atual_float(ticker_str: str):
            ticker_key = normalize_ticker_key(ticker_str)
            if ticker_key in _precos_cache:
                return _precos_cache[ticker_key]
            preco_float = None
            try:
                from utils import obter_preco_ativo

                ticker_preco = ticker_para_preco_atual(ticker_str)

                candidatos = [
                    ticker_preco,
                    ticker_preco.replace(".SA", ""),
                    normalize_ticker_yahoo(ticker_str),
                    ticker_str.upper().strip(),
                ]
                for cand in candidatos:
                    if not cand:
                        continue
                    preco_str = obter_preco_ativo(cand)
                    if isinstance(preco_str, str) and "R$" in preco_str:
                        preco_float = float(preco_str.replace("R$ ", "").replace(".", "").replace(",", "."))
                        break
            except Exception:
                preco_float = None
            _precos_cache[ticker_key] = preco_float
            return preco_float

        def _query_lotes_tabela(nome_tabela: str, campos: str):
            sb = supabase_autenticado()
            def _extract_rows(resp):
                if resp is None:
                    return []
                if isinstance(resp, list):
                    return resp
                data = getattr(resp, "data", None)
                if isinstance(data, list):
                    return data
                return []
            filtros = [
                ("user_id", st.session_state.get("uid")),
                ("usuario", st.session_state.get("usuario")),
            ]
            for coluna, valor in filtros:
                if not valor:
                    continue
                try:
                    resp = executar_query_supabase(
                        sb.table(nome_tabela).select(campos).eq(coluna, valor)
                    )
                    dados = _extract_rows(resp)
                    return dados, True
                except Exception:
                    continue
            try:
                resp = executar_query_supabase(sb.table(nome_tabela).select(campos))
                dados = _extract_rows(resp)
                return dados, True
            except Exception:
                return [], False

        def _carregar_lotes():
            lotes = []
            if not st.session_state.get("uid") and not st.session_state.get("usuario"):
                return lotes, False
            compras_ok = True
            def _to_float(val):
                try:
                    if isinstance(val, (int, float)):
                        return float(val)
                    return float(str(val).replace(".", "").replace(",", "."))
                except Exception:
                    return None

            def _to_int(val):
                try:
                    return int(float(str(val).replace(",", ".").replace(" ", "")))
                except Exception:
                    return None

            resp_carteira, ok_car = _query_lotes_tabela("carteira", "ticker, quantidade, custo, data_compra")
            if not ok_car:
                compras_ok = False
            for item in resp_carteira:
                qt_parsed = _to_int(item.get("quantidade"))
                preco_parsed = _to_float(item.get("custo"))
                if qt_parsed is None or qt_parsed <= 0 or preco_parsed is None or preco_parsed <= 0:
                    continue
                lotes.append(
                    {
                        "Ticker": normalize_ticker_key(item.get("ticker")),
                        "Qtd": float(qt_parsed),
                        "PrecoCompraUnit": float(preco_parsed),
                        "DataCompra": item.get("data_compra"),
                    }
                )
            resp_vendidos, ok_vend = _query_lotes_tabela(
                "ativos_vendidos", "ticker, quantidade, preco_compra, data_compra"
            )
            if not ok_vend:
                compras_ok = False
            for item in resp_vendidos:
                qt_parsed = _to_int(item.get("quantidade"))
                preco_parsed = _to_float(item.get("preco_compra"))
                if qt_parsed is None or qt_parsed <= 0 or preco_parsed is None or preco_parsed <= 0:
                    continue
                lotes.append(
                    {
                        "Ticker": normalize_ticker_key(item.get("ticker")),
                        "Qtd": float(qt_parsed),
                        "PrecoCompraUnit": float(preco_parsed),
                        "DataCompra": item.get("data_compra"),
                    }
                )
            if st.session_state.get("debug") and len(resp_carteira) == 0 and len(resp_vendidos) == 0:
                st.caption("DEBUG DY: 0 lotes encontrados em carteira e ativos_vendidos para este usuário.")
            return lotes, compras_ok

        lotes, compras_ok = _carregar_lotes()

        def _preco_periodo_por_ticker():
            if not lotes:
                return {}, {}
            df_lotes_full = pd.DataFrame(lotes)
            df_lotes_full["TickerNorm"] = df_lotes_full["Ticker"].apply(normalize_ticker_key)
            df_lotes_full["Qtd"] = pd.to_numeric(df_lotes_full["Qtd"], errors="coerce")
            df_lotes_full["PrecoCompraUnit"] = pd.to_numeric(df_lotes_full["PrecoCompraUnit"], errors="coerce")
            df_lotes_full["DataCompra"] = pd.to_datetime(df_lotes_full["DataCompra"], errors="coerce", dayfirst=True)
            df_lotes_full = df_lotes_full[(df_lotes_full["Qtd"] > 0) & (df_lotes_full["PrecoCompraUnit"] > 0)]

            def _ponderado(df_ref):
                if df_ref.empty:
                    return {}
                def _calc(grp):
                    soma_qt = grp["Qtd"].sum()
                    if soma_qt <= 0:
                        return None
                    return (grp["PrecoCompraUnit"] * grp["Qtd"]).sum() / soma_qt
                series = df_ref.groupby("TickerNorm").apply(_calc)
                return series.to_dict() if not series.empty else {}

            preco_total = _ponderado(df_lotes_full)

            if periodo_escolhido != "Tudo" and data_inicio is not None:
                df_filtrado_lotes = df_lotes_full.dropna(subset=["DataCompra"])
                df_filtrado_lotes = df_filtrado_lotes[df_filtrado_lotes["DataCompra"].between(data_inicio, data_fim, inclusive="both")]
            else:
                df_filtrado_lotes = df_lotes_full

            preco_filtrado = _ponderado(df_filtrado_lotes)
            return preco_filtrado, preco_total

        preco_periodo_por_ticker, preco_periodo_por_ticker_total = _preco_periodo_por_ticker()

        if compras_ok is False:
            st.info("Preço do período indisponível (histórico de compras não acessível na Pag5).")

        linhas = []
        for _, row in dpa_por_ticker.iterrows():
            ticker_raw = row["ticker_raw"]
            ticker_norm = row["TickerNorm"]
            dpa_periodo = float(row["dpa_periodo"])

            preco_atual = _preco_atual_float(ticker_norm)
            dy_preco_atual = dpa_periodo / preco_atual if preco_atual and preco_atual > 0 else None

            preco_periodo = preco_periodo_por_ticker.get(ticker_norm) or preco_periodo_por_ticker_total.get(ticker_norm)
            dy_preco_periodo = (
                dpa_periodo / preco_periodo if preco_periodo and preco_periodo > 0 else None
            )

            dy_preco_atual_str = f"{dy_preco_atual*100:.2f}%" if dy_preco_atual is not None else "N/A"
            dy_preco_periodo_str = f"{dy_preco_periodo*100:.2f}%" if dy_preco_periodo is not None else "N/A"

            preco_atual_str = _format_currency(preco_atual) if preco_atual else "Indisponível"
            preco_periodo_str = _format_currency(preco_periodo) if preco_periodo else "Indisponível"

            linhas.append(
                dedent(
                    f"""
                    <tr>
                      <td class='celula'><b>{display_ticker(ticker_raw)}</b></td>
                      <td class='celula'>{_format_currency(dpa_periodo)}</td>
                      <td class='celula'>{preco_atual_str}</td>
                      <td class='celula'>{dy_preco_atual_str}</td>
                      <td class='celula'>{preco_periodo_str}</td>
                      <td class='celula'>{dy_preco_periodo_str}</td>
                    </tr>
                    """
                ).strip()
            )

        tabela_dy_html = dedent(
            f"""
            <table class="tabela-dividendos" style="width:100%;">
              <thead>
                <tr>
                  <th class='celula header'>Ticker</th>
                  <th class='celula header'>Dividendos por ação (R$)</th>
                  <th class='celula header'>Preço Atual (R$)</th>
                  <th class='celula header'>DY (Preço Atual)</th>
                  <th class='celula header'>Preço do Período (R$)</th>
                  <th class='celula header'>DY (Preço do Período)</th>
                </tr>
              </thead>
              <tbody>
                {''.join(linhas)}
              </tbody>
            </table>
            """
        ).strip()
        st.markdown(tabela_dy_html, unsafe_allow_html=True)

with aba_timeline:
    st.markdown("##### Timeline mensal")
    if df_filtrado.empty:
        st.info("Nenhum dado para montar a timeline com os filtros escolhidos.")
    else:
        timeline = (
            df_filtrado.groupby("_mes")
            .agg(total=("Total (R$)", "sum"))
            .reset_index()
            .sort_values("_mes")
        )

        top_tickers = (
            df_filtrado.groupby(["_mes", "Ticker"])["Total (R$)"].sum().reset_index()
        )
        top_por_mes = (
            top_tickers.sort_values(["_mes", "Total (R$)"], ascending=[True, False])
            .groupby("_mes")
            .first()
        )

        linhas = []
        for _, row in timeline.iterrows():
            mes = row["_mes"]
            total_mes = row["total"]
            top_ticker = "-"
            if mes in top_por_mes.index:
                top_ticker = display_ticker(top_por_mes.loc[mes, "Ticker"])
            linhas.append(
                dedent(
                    f"""
                    <tr>
                      <td class='celula'>{mes}</td>
                      <td class='celula'>{_format_currency(total_mes)}</td>
                      <td class='celula'>{top_ticker}</td>
                    </tr>
                    """
                ).strip()
            )

        tabela_timeline_html = dedent(
            f"""
            <table class="tabela-dividendos" style="width:100%;">
              <thead>
                <tr>
                  <th class='celula header'>Mês</th>
                  <th class='celula header'>Total (R$)</th>
                  <th class='celula header'>Top ticker do mês</th>
                </tr>
              </thead>
              <tbody>
                {''.join(linhas)}
              </tbody>
            </table>
            """
        ).strip()
        st.markdown(tabela_timeline_html, unsafe_allow_html=True)

if not editando:
    st.markdown("### Registro Manual de Dividendos")
    with st.container():
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        with st.form("form_dividendo"):
            col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
            with col1:
                ticker = st.text_input("Ticker", value=ticker_inicial, label_visibility="visible").strip().upper()
            with col2:
                valor = st.number_input("Valor (R$)", min_value=0.0, step=0.01, value=valor_inicial)
            with col3:
                quantidade = st.number_input("Qtd", min_value=0, value=quantidade_inicial)
            with col4:
                data_pagamento = st.date_input("Data", value=data_inicial, format="DD/MM/YYYY")
            with col5:
                tipo = st.radio("Tipo", ["DIVIDENDO", "JCP"], horizontal=True, index=0 if tipo_inicial == "DIVIDENDO" else 1)
            with col6:
                st.markdown("<div style='height: 2.2em;'></div>", unsafe_allow_html=True)
                submitted = st.form_submit_button("Ok" if editando else "➕")

            if submitted:
                if not ticker or not st.session_state.uid:
                    st.session_state["erro_dividendo"] = "Ticker ou usuário inválido."
                    st.rerun()
                try:
                    if editando:
                        from utils import atualizar_dividendo
                        atualizar_dividendo(
                            st.session_state["edit_id"],
                            {
                                "ticker": ticker,
                                "valor": valor,
                                "quantidade": quantidade,
                                "data": data_pagamento.strftime("%Y-%m-%d"),
                                "tipo": tipo
                            }
                        )
                        st.success(f"Alterações salvas para {ticker}.")
                        if "edit_id" in st.session_state:
                            del st.session_state["edit_id"]
                        st.rerun()
                    else:
                        inserir_dividendo(st.session_state.uid, ticker, data_pagamento.strftime("%Y-%m-%d"), valor, quantidade, tipo)
                        st.success("Dividendo registrado com sucesso!")
                        st.rerun()
                except Exception as e:
                    _handle_auth_error(e)
                    st.session_state["erro_dividendo"] = str(e)
                    st.rerun()

df_lancamentos = df_filtrado if not df_filtrado.empty else df_original

with st.expander("Ver lançamentos individuais", expanded=False):
    if df_filtrado.empty and not df_original.empty and not df_lancamentos.empty:
        st.caption("Filtros não retornaram lançamentos; exibindo todos os registros.")
    elif df_filtrado.empty and df_original.empty:
        st.info("Nenhum lançamento cadastrado.")

    if not df_lancamentos.empty:
        weights = [0.6, 1.0, 1.0, 0.8, 1.0, 1.0, 0.9, 0.8]
        header_cols = ["", "Ticker", "Valor (R$)", "Quantidade", "Total (R$)", "Data", "Tipo", "Ação"]
        peso_total = sum(weights)
        colgroup_html = "".join(f"<col style='width:{(peso/peso_total)*100:.2f}%;'>" for peso in weights)
        headers_html = "".join(f"<th>{col}</th>" for col in header_cols)
        header_html = (
            "<div class=\"fin-header-card\">"
            "<table class=\"fin-header-table\">"
            f"<colgroup>{colgroup_html}</colgroup>"
            "<thead><tr>"
            f"{headers_html}"
            "</tr></thead>"
            "</table>"
            "</div>"
        )
        st.markdown(header_html, unsafe_allow_html=True)

        for i, row in df_lancamentos.iterrows():
            with st.container():
                st.markdown("<div class='fin-row-marker'></div>", unsafe_allow_html=True)
                col0, col1, col2, col3, col4, col5, col6, col7 = st.columns(weights, gap="small")
                ticker_raw = str(row["Ticker"] or "").upper()
                if ticker_raw in ("NAN", "NONE"):
                    ticker_raw = ""
                col0.markdown(get_logo_img_tag(ticker_raw or "LOGO", size=30), unsafe_allow_html=True)
                col1.markdown(f"**{display_ticker(row['Ticker'])}**")
                col2.markdown(f"**R$ {row['Valor (R$)']:.2f}**".replace(".", ","))
                col3.markdown(f"**{int(row['Quantidade']):,}**".replace(",", "."))
                col4.markdown(f"**R$ {row['Total (R$)']:.2f}**".replace(".", ","))
                col5.markdown(f"**{row['Data de Pagamento']}**")
                col6.markdown(f"**{row['Tipo']}**")
                if col7.button("⚙️", key=f"engrenagem_{row['ID']}"):
                    st.session_state["editar_dividendo_id"] = row["ID"]
                    st.rerun()

                if st.session_state.get("edit_id") == row["ID"]:
                    with st.form(f"form_edicao_{row['ID']}"):
                        col1, col2, col3, col4, col5, col6 = st.columns([2, 2, 2, 2, 2, 1])
                        with col1:
                            novo_ticker = st.text_input("Ticker", value=row["Ticker"])
                        with col2:
                            novo_valor = st.number_input("Valor (R$)", min_value=0.0, step=0.01, value=row["Valor (R$)"])
                        with col3:
                            nova_quantidade = st.number_input("Quantidade", min_value=0, step=1, value=int(row["Quantidade"]))
                        with col4:
                            nova_data = st.date_input(
                                "Data",
                                value=datetime.strptime(row["Data de Pagamento"], "%d/%m/%Y"),
                                format="DD/MM/YYYY",
                            )
                        with col5:
                            novo_tipo = st.radio(
                                "Tipo",
                                ["DIVIDENDO", "JCP"],
                                horizontal=True,
                                index=0 if row["Tipo"] == "DIVIDENDO" else 1,
                            )
                        botoes = st.columns([3, 2, 5])
                        with botoes[0]:
                            salvar = st.form_submit_button("💾 Salvar Alterações")
                        with botoes[1]:
                            cancelar = st.form_submit_button("↩️ Cancelar", use_container_width=True)

                        if salvar:
                            try:
                                from utils import atualizar_dividendo

                                atualizar_dividendo(
                                    row["ID"],
                                    {
                                        "ticker": novo_ticker,
                                        "valor": novo_valor,
                                        "quantidade": nova_quantidade,
                                        "data": nova_data.strftime("%Y-%m-%d"),
                                        "tipo": novo_tipo,
                                    },
                                )
                                st.success(f"Alterações salvas para {novo_ticker}.")
                                del st.session_state["edit_id"]
                                st.rerun()
                            except Exception as exc:
                                _handle_auth_error(exc)
                                st.error("Não foi possível salvar as alterações.")

                        if cancelar:
                            del st.session_state["edit_id"]
                            st.rerun()

                if st.session_state.get("editar_dividendo_id") == row["ID"]:
                    weights_acoes = [0.6, 1.0, 1.0, 1.0, 1.0, 1.0, 0.9, 0.8]
                    col_acao = st.columns(weights_acoes)
                    with col_acao[1]:
                        if st.button("✏️ Editar", key=f"editar_{row['ID']}"):
                            st.session_state["edit_id"] = row["ID"]
                            if "editar_dividendo_id" in st.session_state:
                                del st.session_state["editar_dividendo_id"]
                            st.rerun()
                    with col_acao[2]:
                        if st.button("ⓧ Excluir", key=f"excluir_{row['ID']}"):
                            try:
                                excluir_dividendo(row["ID"])
                                st.success(f"Dividendo de {row['Ticker']} excluído com sucesso.")
                                del st.session_state["editar_dividendo_id"]
                                st.rerun()
                            except Exception as exc:
                                _handle_auth_error(exc)
                                st.error("Não foi possível excluir o dividendo.")
                    with col_acao[3]:
                        if st.button("↩️ Cancelar", key=f"cancelar_{row['ID']}", use_container_width=True):
                            if "editar_dividendo_id" in st.session_state:
                                del st.session_state["editar_dividendo_id"]
                            st.rerun()
