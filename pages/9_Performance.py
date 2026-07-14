import streamlit as st
from collections import defaultdict
from datetime import datetime, date

import pandas as pd
import numpy as np
import time
from utils_style import apply_global_dark_theme

try:
    import numpy_financial as npf
except ImportError:
    npf = None


def _irr_newton(values: list[float] | np.ndarray, tol: float = 1e-6, maxiter: int = 100) -> float | None:
    """Fallback IRR solver (Newton-Raphson) caso numpy_financial não esteja disponível."""
    if values is None:
        return None
    cashflows = np.asarray(values, dtype=float)
    if cashflows.size == 0:
        return None
    if not (np.any(cashflows > 0) and np.any(cashflows < 0)):
        return None
    guess = 0.1
    for _ in range(maxiter):
        denom = (1.0 + guess) ** np.arange(cashflows.size)
        npv = np.sum(cashflows / denom)
        d_npv = np.sum(-np.arange(cashflows.size) * cashflows / ((1.0 + guess) ** (np.arange(cashflows.size) + 1)))
        if abs(d_npv) < 1e-12:
            break
        new_guess = guess - npv / d_npv
        if abs(new_guess - guess) <= tol:
            guess = new_guess
            break
        guess = new_guess
        if guess <= -0.999999:
            guess = -0.999999
    if not np.isfinite(guess):
        return None
    return guess

try:
    import plotly.graph_objects as go
except ImportError:
    go = None

from utils import (
    restaurar_usuario_sessao,
    carregar_carteira_supabase,
    calcular_desempenho_consolidado,
    carregar_vendas,
    obter_total_dividendos_para_lote_intervalado,
    obter_credito_opcoes_para_lote_intervalado,
    supabase_autenticado,
    alocar_coberturas_por_lote,
    formatar_numero_para_float,
    formatar_valor,
    obter_preco_ativo,
    parse_data_flexivel,
    carregar_dividendos_usuario,
    carregar_operacoes_finalizadas,
    redirecionar_para_login,
    tratar_erro_autenticacao,
)


st.set_page_config(page_title="Performance da Carteira", page_icon="📈", layout="wide")
apply_global_dark_theme()

# Mantém padronização de margens com as demais páginas
st.markdown(
    """
    <style>
    main > div.block-container, section.main > div.block-container, .block-container {
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 100% !important;
        padding-top: 1rem !important;
    }
    h1 { margin-top: 0rem !important; }
    </style>

    """,
    unsafe_allow_html=True,
)

def format_brl(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(percentual: float) -> str:
    return f"{percentual:+.2f}%".replace(".", ",")


PLOTLY_CONFIG_DEFAULT = {"displaylogo": False}
KNOWN_DELISTED_TICKERS = {"RRRP3.SA", "BPOT39.SA"}


def render_plotly(fig, *, key: str | None = None) -> None:
    """Wrapper padronizado para gráficos Plotly."""
    st.plotly_chart(
        fig,
        config=dict(PLOTLY_CONFIG_DEFAULT),
        key=key,
    )


def _handle_auth_error(exc):
    if tratar_erro_autenticacao(exc):
        st.stop()


if "_pag9_missing_quotes" not in st.session_state:
    st.session_state["_pag9_missing_quotes"] = {}
if "_pag9_quote_blacklist" not in st.session_state:
    st.session_state["_pag9_quote_blacklist"] = set()


def register_missing_quote(ticker: str, detail: str) -> None:
    """Guarda tickers com dados ausentes para exibir aviso consolidado."""
    missing = st.session_state.get("_pag9_missing_quotes", {})
    missing[ticker] = detail
    st.session_state["_pag9_missing_quotes"] = missing
    blacklist = st.session_state.get("_pag9_quote_blacklist", set())
    blacklist.add(ticker)
    st.session_state["_pag9_quote_blacklist"] = blacklist


@st.cache_data(show_spinner=False)
def get_yahoo_monthly_data(ticker: str, start: str, end: str):
    import yfinance as yf

    blacklist = st.session_state.get("_pag9_quote_blacklist", set())
    if ticker in KNOWN_DELISTED_TICKERS or ticker in blacklist:
        return pd.DataFrame()

    last_error = None
    # First try the native monthly endpoint (faster, less data to transfer).
    for attempt in range(3):
        try:
            data = yf.download(
                ticker,
                start=start,
                end=end,
                interval="1mo",
                progress=False,
                threads=False,
                timeout=10,
            )
            if data.empty:
                last_error = "dados vazios"
                time.sleep(min(3, 1.5 * (attempt + 1)))
                continue
            if getattr(data.index, "tz", None) is not None:
                data.index = data.index.tz_localize(None)
            return data
        except Exception as exc:
            last_error = exc
            time.sleep(min(3, 1.5 * (attempt + 1)))

    # Fallback: download daily data and resample to monthly close.
    try:
        daily = yf.download(
            ticker,
            start=start,
            end=end,
            interval="1d",
            progress=False,
            threads=False,
            timeout=10,
        )
        if getattr(daily.index, "tz", None) is not None:
            daily.index = daily.index.tz_localize(None)
        if not daily.empty:
            monthly = daily.resample("M").last().dropna(how="all")
            if not monthly.empty:
                monthly.index = monthly.index.to_period("M").to_timestamp()
                return monthly
    except Exception as exc:  # noqa: PERF203 - falha do yfinance precisa ser capturada
        last_error = exc

    register_missing_quote(ticker, str(last_error))
    return pd.DataFrame()


def render_cards(dados) -> None:
    if not dados:
        st.markdown("<div class='cards-wrapper'></div>", unsafe_allow_html=True)
        return

    valores_rs = [float(item.get("variacao_rs") or 0.0) for item in dados]
    valores_pct = [float(item.get("variacao_pct") or 0.0) for item in dados]
    max_gain_rs = max((v for v in valores_rs if v > 0), default=0.0)
    max_loss_rs = min((v for v in valores_rs if v < 0), default=0.0)
    max_gain_pct = max((v for v in valores_pct if v > 0), default=0.0)
    max_loss_pct = min((v for v in valores_pct if v < 0), default=0.0)

    def _mix_hex(color_start: str, color_end: str, factor: float) -> str:
        factor = max(0.0, min(1.0, factor))
        start = tuple(int(color_start[i : i + 2], 16) for i in (0, 2, 4))
        end = tuple(int(color_end[i : i + 2], 16) for i in (0, 2, 4))
        mixed = tuple(int(s + (e - s) * factor) for s, e in zip(start, end))
        return "#{:02X}{:02X}{:02X}".format(*mixed)

    def _color_for_value(valor_rs: float, valor_pct: float) -> str:
        if valor_pct > 0 and max_gain_pct > 0:
            intensity = valor_pct / max_gain_pct
            return _mix_hex("8FF0C1", "1EBF63", intensity)
        if valor_pct < 0 and max_loss_pct < 0:
            intensity = valor_pct / max_loss_pct
            return _mix_hex("F7A8A8", "D92626", intensity)
        if valor_rs > 0 and max_gain_rs > 0:
            intensity = valor_rs / max_gain_rs
            return _mix_hex("8FF0C1", "1EBF63", intensity)
        if valor_rs < 0 and max_loss_rs < 0:
            intensity = valor_rs / max_loss_rs
            return _mix_hex("F7A8A8", "D92626", intensity)
        return "#CCCCCC"

    cards_html = []
    for item in dados:
        ticker = str(item.get("ticker", "")).upper()
        display_ticker = ticker.split(".")[0]
        variacao_pct = float(item.get("variacao_pct") or 0.0)
        variacao_rs = float(item.get("variacao_rs") or 0.0)
        tooltip = item.get("tooltip")
        detalhes = item.get("detalhes") or []

        cor = _color_for_value(variacao_rs, variacao_pct)
        card_html = "<div class='card-performance'"
        if tooltip:
            card_html += f" title='{tooltip}'"
        card_html += ">"
        card_html += f"<div class='ticker'>{display_ticker}</div>"
        card_html += f"<div class='percentual' style='color:{cor};'>{format_pct(variacao_pct)}</div>"
        card_html += f"<div class='reais' style='color:{cor};'>{format_brl(variacao_rs)}</div>"
        if detalhes:
            card_html += "<small>" + "<br>".join(detalhes) + "</small>"
        card_html += "</div>"
        cards_html.append(card_html)

    container_html = "<div class='cards-wrapper'>" + "".join(cards_html) + "</div>"
    st.markdown(container_html, unsafe_allow_html=True)


def parse_data_compra(data_str):
    if not data_str:
        return datetime.today()
    if isinstance(data_str, datetime):
        return data_str
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(data_str), fmt)
        except ValueError:
            continue
    return datetime.today()


def custo_final_unit_para_item(item, alloc_por_ticker, supabase_client):
    ticker = item["Ticker"].upper()
    data_compra = parse_data_compra(item["Data de Compra"])
    quantidade = int(item.get("Quantidade") or 0)
    if quantidade <= 0:
        return 0.0, {"custo_base_unit": 0.0, "div_por_acao": 0.0, "opc_por_acao": 0.0}

    custo_original = formatar_numero_para_float(item.get("Custo"))
    custo_oper_total = formatar_numero_para_float(item.get("Custo Operacional"))
    custo_base_unit = custo_original + (custo_oper_total / quantidade if quantidade else 0.0)

    try:
        res = (
            supabase_client.table("dividendos_recebidos")
            .select("*")
            .eq("ticker", ticker)
            .gte("data", str(data_compra.date()))
            .lte("data", str(date.today()))
            .execute()
        )
        dividendos_brutos = res.data or []
    except Exception as exc:
        _handle_auth_error(exc)
        dividendos_brutos = []

    dividendos_unit_total = sum(float(d.get("valor") or 0.0) for d in dividendos_brutos)

    alloc = (alloc_por_ticker.get(ticker) or {}).get("por_lote", {})
    lote_alloc = alloc.get(item.get("UUID"), {}) if item.get("UUID") else {}
    credito_total_opcoes = float(lote_alloc.get("credito_total", 0.0))

    custo_bruto_total = custo_base_unit * quantidade
    desconto_div_total = dividendos_unit_total * quantidade
    desconto_opc_total = credito_total_opcoes

    custo_final_unit = max(
        0.0, (custo_bruto_total - desconto_div_total - desconto_opc_total) / quantidade
    )

    detalhes = {
        "custo_base_unit": custo_base_unit,
        "div_por_acao": dividendos_unit_total,
        "opc_por_acao": (desconto_opc_total / quantidade) if quantidade else 0.0,
    }
    return custo_final_unit, detalhes


def inject_audit_styles() -> None:
    """Inject CSS helpers used by the rentability audit tables."""
    st.markdown(
        """
        <style>
        .audit-summary-table {
            width: 100%;
            border-collapse: collapse;
            margin: 8px 0 16px;
            font-size: 0.95rem;
        }
        .audit-summary-table th {
            text-align: left;
            padding: 6px 12px;
            color: #e5e7eb;
            font-weight: 600;
            background: rgba(148, 163, 184, 0.15);
        }
        .audit-summary-table td {
            padding: 10px 12px;
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        }
        .formula-box {
            border: 1px solid rgba(148, 163, 184, 0.2);
            border-radius: 8px;
            padding: 12px 16px;
            background: rgba(15,23,42,0.4);
            margin-bottom: 16px;
        }
        .formula-box .row {
            display: flex;
            justify-content: space-between;
            margin: 4px 0;
            font-size: 0.93rem;
        }
        .formula-box .row span:first-child {
            color: #cbd5f5;
        }
        .formula-box .result {
            margin-top: 12px;
            font-weight: 600;
        }
        </style>

        """,
        unsafe_allow_html=True,
    )


def parse_preco_float(preco_str):
    try:
        if isinstance(preco_str, (int, float)):
            return float(preco_str)
        preco_str = str(preco_str)
        if "R$" in preco_str:
            preco_str = preco_str.replace("R$", "").strip()
        preco_str = preco_str.replace(".", "").replace(",", ".")
        return float(preco_str)
    except Exception:
        return None


def adicionar_cotas(df: pd.DataFrame) -> pd.DataFrame:
    """Emite/resgata cotas mensais com base nas colunas `total` e `aportes`."""
    if df.empty:
        df["valor_cota"] = []
        df["num_cotas"] = []
        return df

    df = df.sort_index().copy()
    valor_cota_series = []
    num_cotas_series = []

    patrimonio_inicial = float(df["total"].iloc[0] or 0.0)
    if patrimonio_inicial <= 0:
        valor_cota_atual = 1.0
        num_cotas_atual = 1.0
    else:
        valor_cota_atual = patrimonio_inicial
        num_cotas_atual = 1.0

    valor_cota_series.append(valor_cota_atual)
    num_cotas_series.append(num_cotas_atual)

    for i in range(1, len(df)):
        patrimonio = float(df["total"].iloc[i] or 0.0)
        aporte = float(df["aportes"].iloc[i] or 0.0) if "aportes" in df.columns else 0.0

        if num_cotas_atual <= 0:
            valor_cota_atual = patrimonio if patrimonio > 0 else 1.0
            num_cotas_atual = 1.0
        else:
            valor_cota_atual = patrimonio / num_cotas_atual

        if aporte > 0 and valor_cota_atual > 0:
            novas_cotas = aporte / valor_cota_atual
            num_cotas_atual += novas_cotas
        elif aporte < 0 and valor_cota_atual > 0:
            cotas_resgatadas = abs(aporte) / valor_cota_atual
            num_cotas_atual = max(0.0, num_cotas_atual - cotas_resgatadas)

        valor_cota_series.append(valor_cota_atual)
        num_cotas_series.append(num_cotas_atual)

    df["valor_cota"] = valor_cota_series
    df["num_cotas"] = num_cotas_series
    return df


def rent_cota_window(df: pd.DataFrame, meses: int):
    """Retorna a rentabilidade acumulada da cota em `meses` meses (decimal)."""
    if df.empty or "valor_cota" not in df.columns:
        return None
    df = df.sort_index()
    if len(df) <= meses:
        return None
    cota_final = df["valor_cota"].iloc[-1]
    cota_inicial = df["valor_cota"].iloc[-(meses + 1)]
    if cota_inicial in (0, None):
        return None
    return (cota_final / cota_inicial) - 1


def rent_cota_ytd(df: pd.DataFrame):
    """Retorna a rentabilidade acumulada no ano vigente (decimal)."""
    if df is None or df.empty or "valor_cota" not in df.columns:
        return None
    df = df.sort_index()
    inicio_ano = datetime(datetime.today().year, 1, 1)
    df_periodo = df[df.index >= inicio_ano]
    if df_periodo.empty or len(df_periodo) < 2:
        return None
    valor_inicial = df_periodo["valor_cota"].iloc[0]
    valor_final = df_periodo["valor_cota"].iloc[-1]
    if not valor_inicial:
        return None
    return (valor_final / valor_inicial) - 1


def calcular_tir_anualizada(df: pd.DataFrame, patrimonio_atual: float | None) -> float | None:
    """Calcula a TIR anualizada com base nos fluxos mensais registrados no dataframe."""
    if df is None or df.empty:
        return None
    required_cols = [
        "aportes",
        "dividendos_mes",
        "realizado_acoes_mes",
        "resultado_opcoes_mes",
    ]
    if any(col not in df.columns for col in required_cols):
        return None

    fluxos = []
    for _, row in df.sort_index().iterrows():
        aporte = float(row.get("aportes") or 0.0)
        dividendos = float(row.get("dividendos_mes") or 0.0)
        realizado_acoes = float(row.get("realizado_acoes_mes") or 0.0)
        realizado_opcoes = float(row.get("resultado_opcoes_mes") or 0.0)
        fluxo = -aporte + dividendos + realizado_acoes + realizado_opcoes
        fluxos.append(fluxo)

    fluxos.append(float(patrimonio_atual or 0.0))

    if len(fluxos) < 2:
        return None
    if not (any(f > 0 for f in fluxos) and any(f < 0 for f in fluxos)):
        return None
    try:
        if npf is not None:
            tir_mensal = npf.irr(fluxos)
        else:
            tir_mensal = _irr_newton(fluxos)
    except Exception:
        return None
    if tir_mensal is None or isinstance(tir_mensal, complex) or np.isnan(tir_mensal):
        return None
    if tir_mensal <= -1:
        return None
    return (1 + tir_mensal) ** 12 - 1


def plotar_evolucao_mensal(
    posicao_atual,
    ajuste_por_ticker,
    vendas_registros,
    compras_registros,
    dividendos_registros,
    opcoes_operacoes_registros,
    opcoes_carteira_registros,
):
    """Prepara dados de rentabilidade mensal (%) com cotas considerando ações, dividendos e opções."""

    empty_details = {"valores_ticker": pd.DataFrame(), "realizado_ticker": pd.DataFrame()}

    if not posicao_atual:
        return {}, None, None, pd.DataFrame(), empty_details

    try:
        import yfinance  # noqa: F401
    except ImportError:
        st.warning("Biblioteca yfinance ausente; instale-a para calcular a rentabilidade mensal.")
        return {}, None, None, pd.DataFrame(), empty_details

    def _parse_data_generica(valor):
        if not valor:
            return None
        if isinstance(valor, datetime):
            return valor
        for parser in (parse_data_flexivel, parse_data_compra):
            try:
                return parser(valor)
            except Exception:
                continue
        return None

    datas_referencia = []
    for item in posicao_atual:
        datas_referencia.append(_parse_data_generica(item.get("Data de Compra")))
    for registro in compras_registros:
        datas_referencia.append(_parse_data_generica(registro.get("data_compra")))
    for venda in vendas_registros:
        datas_referencia.append(_parse_data_generica(venda.get("data_compra")))
        datas_referencia.append(_parse_data_generica(venda.get("data_venda")))
    for dividendo in dividendos_registros or []:
        datas_referencia.append(_parse_data_generica(dividendo.get("data")))
    for operacao in opcoes_operacoes_registros or []:
        datas_referencia.append(_parse_data_generica(operacao.get("data_operacao")))
        datas_referencia.append(_parse_data_generica(operacao.get("data_encerramento")))
    for opcao in opcoes_carteira_registros or []:
        datas_referencia.append(_parse_data_generica(opcao.get("data_operacao")))

    datas_referencia = [d for d in datas_referencia if isinstance(d, datetime)]
    if not datas_referencia:
        return {}, None, None, pd.DataFrame(), empty_details

    inicio = min(datas_referencia).replace(day=1)
    fim = datetime.today().replace(day=1)
    idx = pd.date_range(start=inicio, end=fim, freq="MS")
    if idx.empty:
        return {}, None, None, pd.DataFrame(), empty_details

    eventos_lotes = []

    def _registrar_lote(ticker: str, quantidade_bruta, data_compra_raw, data_venda_raw=None):
        ticker = (ticker or "").upper()
        quantidade = formatar_numero_para_float(quantidade_bruta)
        if not ticker or quantidade <= 0:
            return
        data_compra = _parse_data_generica(data_compra_raw)
        if data_compra is None:
            return
        data_venda = _parse_data_generica(data_venda_raw)
        eventos_lotes.append(
            {
                "ticker": ticker,
                "quantidade": quantidade,
                "data_compra": data_compra,
                "data_venda": data_venda,
            }
        )

    for registro in compras_registros or []:
        _registrar_lote(
            registro.get("ticker") or registro.get("Ticker"),
            registro.get("quantidade"),
            registro.get("data_compra") or registro.get("Data de Compra"),
            None,
        )

    for venda in vendas_registros or []:
        _registrar_lote(
            venda.get("ticker") or venda.get("Ticker"),
            venda.get("quantidade"),
            venda.get("data_compra"),
            venda.get("data_venda"),
        )

    if not eventos_lotes:
        return {}, None, None, pd.DataFrame(), empty_details

    eventos_lotes.sort(key=lambda lote: lote["data_compra"])
    idx_array = idx.to_numpy(dtype="datetime64[ns]")
    quant_arrays: dict[str, np.ndarray] = {}

    valor_por_ticker = {}
    realizado_acoes_por_ticker = {}

    for lote in eventos_lotes:
        ticker = lote["ticker"]
        if ticker not in quant_arrays:
            quant_arrays[ticker] = np.zeros(len(idx_array), dtype=float)
        arr = quant_arrays[ticker]
        data_compra_mes = lote["data_compra"].replace(day=1)
        data_compra_np = np.datetime64(data_compra_mes)
        compra_mask = idx_array >= data_compra_np
        arr[compra_mask] += lote["quantidade"]
        data_venda = lote.get("data_venda")
        if data_venda:
            data_venda_mes = data_venda.replace(day=1)
            data_venda_np = np.datetime64(data_venda_mes)
            venda_mask = idx_array >= data_venda_np
            arr[venda_mask] -= lote["quantidade"]

    # Série que carregará o valor agregado dos ativos ao longo do tempo.
    valor_em_carteira = pd.Series(0.0, index=idx, dtype=float)
    for ticker, quantidade_array in quant_arrays.items():
        if quantidade_array.sum() == 0:
            continue
        quantidade_series = pd.Series(quantidade_array, index=idx)
        ticker_yf = ticker if ticker.endswith(".SA") else f"{ticker}.SA"
        start_str = pd.Timestamp(idx[0]).strftime("%Y-%m-%d")
        end_str = pd.Timestamp(idx[-1] + pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")
        try:
            hist = get_yahoo_monthly_data(ticker_yf, start_str, end_str)
        except Exception:
            continue
        if hist.empty:
            continue
        close_series = hist["Close"] if "Close" in hist else hist.squeeze()
        if isinstance(close_series, pd.DataFrame):
            close_series = close_series.iloc[:, 0]
        if getattr(close_series.index, "tz", None) is not None:
            close_series.index = close_series.index.tz_localize(None)
        close_series = close_series.to_period("M").to_timestamp()
        close_series = close_series.reindex(idx).ffill().bfill()
        valor_ticker = close_series * quantidade_series
        valor_por_ticker[ticker] = valor_ticker
        valor_em_carteira = valor_em_carteira.add(valor_ticker, fill_value=0.0)

    valor_opcoes = pd.Series(0.0, index=idx, dtype=float)

    def _valor_premio(opcao: dict) -> float:
        quantidade = formatar_numero_para_float(opcao.get("quantidade"))
        premio = formatar_numero_para_float(opcao.get("preco"))
        custo = formatar_numero_para_float(opcao.get("custo"))
        if quantidade <= 0 or premio is None:
            return 0.0
        operacao = (opcao.get("tipo_operacao") or "").strip().lower()
        premio_total = quantidade * premio
        if operacao == "compra":
            return -(premio_total + custo)
        return premio_total - custo

    for opcao in opcoes_carteira_registros or []:
        data_operacao = _parse_data_generica(opcao.get("data_operacao"))
        data_vencimento = _parse_data_generica(opcao.get("data_vencimento")) or datetime.today()
        if not data_operacao:
            continue
        inicio_op = pd.Timestamp(data_operacao.replace(day=1))
        fim_op = pd.Timestamp(data_vencimento.replace(day=1))
        valor_premio = _valor_premio(opcao)
        if valor_premio == 0.0:
            continue
        mask = (idx >= inicio_op) & (idx <= fim_op)
        if mask.any():
            valor_opcoes.loc[mask] += valor_premio

    # Fluxos mensais realizados provenientes de vendas de ações.
    realizado_acoes = pd.Series(0.0, index=idx)
    for venda in vendas_registros or []:
        try:
            data_venda = parse_data_flexivel(venda.get("data_venda"))
        except Exception:
            continue
        mes = data_venda.replace(day=1)
        if mes not in realizado_acoes.index:
            continue
        receita = float(venda.get("preco_venda") or 0.0) * float(venda.get("quantidade") or 0.0)
        realizado_acoes.loc[mes] += receita
        ticker_venda = str(venda.get("ticker") or venda.get("Ticker") or "").upper()
        if ticker_venda:
            serie = realizado_acoes_por_ticker.get(ticker_venda)
            if serie is None:
                serie = pd.Series(0.0, index=idx)
            serie.loc[mes] += receita
            realizado_acoes_por_ticker[ticker_venda] = serie

    # Fluxos mensais de dividendos.
    dividendos_series = pd.Series(0.0, index=idx)
    for dividendo in dividendos_registros or []:
        try:
            data_pagamento = parse_data_flexivel(dividendo.get("data"))
        except Exception:
            continue
        mes = data_pagamento.replace(day=1)
        if mes not in dividendos_series.index:
            continue
        valor_unit = formatar_numero_para_float(dividendo.get("valor"))
        quantidade = formatar_numero_para_float(dividendo.get("quantidade"))
        dividendos_series.loc[mes] += valor_unit * quantidade

    # Fluxos mensais provenientes de operações com opções (lançamentos, recompras, encerramentos).
    opcoes_fluxo = pd.Series(0.0, index=idx)
    for operacao in opcoes_operacoes_registros or []:
        quantidade = formatar_numero_para_float(operacao.get("quantidade"))
        if quantidade <= 0:
            continue
        preco_inicial = formatar_numero_para_float(operacao.get("preco_inicial"))
        preco_final = formatar_numero_para_float(operacao.get("preco_final"))
        custo_operacional = formatar_numero_para_float(operacao.get("custo"))
        tipo_inicial = (operacao.get("tipo_operacao_inicial") or "").strip().lower()

        data_operacao = _parse_data_generica(operacao.get("data_operacao"))
        mes_op = None
        if data_operacao:
            mes_op = data_operacao.replace(day=1)
            if mes_op in opcoes_fluxo.index:
                if tipo_inicial == "venda":
                    opcoes_fluxo.loc[mes_op] += preco_inicial * quantidade
                else:
                    opcoes_fluxo.loc[mes_op] -= preco_inicial * quantidade

        data_encerramento = _parse_data_generica(operacao.get("data_encerramento"))
        if data_encerramento:
            mes_fech = data_encerramento.replace(day=1)
            if mes_fech in opcoes_fluxo.index:
                if tipo_inicial == "venda":
                    opcoes_fluxo.loc[mes_fech] -= preco_final * quantidade + custo_operacional
                else:
                    opcoes_fluxo.loc[mes_fech] += preco_final * quantidade - custo_operacional
        else:
            # Se a operação ainda não foi encerrada, aloca custo no mês da operação para não perder o desembolso.
            if data_operacao and mes_op in opcoes_fluxo.index and custo_operacional:
                opcoes_fluxo.loc[mes_op] -= custo_operacional

    realizado_acoes_acum = realizado_acoes.cumsum()
    dividendos_acum = dividendos_series.cumsum()
    opcoes_acum = opcoes_fluxo.cumsum()
    realizado_total = realizado_acoes_acum + dividendos_acum + opcoes_acum
    total = valor_em_carteira + valor_opcoes + realizado_total

    aportes = pd.Series(0.0, index=idx)
    for registro in compras_registros:
        try:
            data_compra = parse_data_flexivel(registro.get("data_compra"))
        except Exception:
            continue
        mes = data_compra.replace(day=1)
        if mes not in aportes.index:
            continue
        quantidade = formatar_numero_para_float(registro.get("quantidade"))
        custo_unit = formatar_numero_para_float(registro.get("custo"))
        custo_oper = formatar_numero_para_float(registro.get("custo_operacional"))
        aportes.loc[mes] += quantidade * custo_unit + custo_oper

    for venda in vendas_registros:
        try:
            data_compra = parse_data_flexivel(venda.get("data_compra"))
        except Exception:
            continue
        mes = data_compra.replace(day=1)
        if mes not in aportes.index:
            continue
        quantidade = formatar_numero_para_float(venda.get("quantidade"))
        preco_compra = formatar_numero_para_float(venda.get("preco_compra"))
        aportes.loc[mes] += quantidade * preco_compra

    cotas_df = pd.DataFrame(
        {
            "total": total.values,
            "aportes": aportes.values,
            "valor_carteira": valor_em_carteira.values,
            "valor_opcoes": valor_opcoes.values,
            "realizado_acoes_acum": realizado_acoes_acum.values,
            "dividendos_acum": dividendos_acum.values,
            "resultado_opcoes_acum": opcoes_acum.values,
            "realizado_total_acum": realizado_total.values,
            "realizado_acoes_mes": realizado_acoes.values,
            "dividendos_mes": dividendos_series.values,
            "resultado_opcoes_mes": opcoes_fluxo.values,
        },
        index=idx,
    )
    cotas_df = adicionar_cotas(cotas_df)

    rent_cota_pct = cotas_df["valor_cota"].pct_change() * 100.0
    cotas_df["rentabilidade_pct"] = rent_cota_pct
    cotas_df["valor_cota_anterior"] = cotas_df["valor_cota"].shift(1)
    cotas_df["total_anterior"] = cotas_df["total"].shift(1)
    rent_full = pd.DataFrame({"Data": idx, "Rentabilidade (%)": rent_cota_pct}).dropna()
    valores_ticker_df = (
        pd.DataFrame(valor_por_ticker, index=idx) if valor_por_ticker else pd.DataFrame(index=idx)
    )
    realizado_ticker_df = (
        pd.DataFrame(realizado_acoes_por_ticker, index=idx)
        if realizado_acoes_por_ticker
        else pd.DataFrame(index=idx)
    )
    # debug (opcional):
    # debug_df = pd.DataFrame(
    #     {
    #         "Data": idx,
    #         "total": total.values,
    #         "aportes": aportes.values,
    #         "valor_cota": cotas_df["valor_cota"].values,
    #         "rent_mensal_cota": rent_cota_pct.values,
    #     }
    # )
    # print(debug_df.tail(60)[["total", "aportes", "valor_cota", "rent_mensal_cota"]])
    if rent_full.empty:
        return {}, None, None, pd.DataFrame(), empty_details

    def _cum_return(last_n: int | None):
        series = rent_full.tail(last_n) if last_n else rent_full
        if series.empty or (last_n and len(series) < last_n):
            return None
        monthly = series["Rentabilidade (%)"].astype(float) / 100.0
        cumulative = (1 + monthly).prod() - 1
        return cumulative * 100

    def _cum_cota(last_n: int):
        resultado = rent_cota_window(cotas_df, last_n)
        return resultado * 100 if resultado is not None else None

    agregados = {12: _cum_cota(12), 24: _cum_cota(24), 36: _cum_cota(36), 48: _cum_cota(48)}

    period_options = {
        "12 meses": 12,
        "24 meses": 24,
        "36 meses": 36,
        "48 meses": 48,
        "Todo o período": None,
    }
    period_key = "rent_period_option"
    if period_key not in st.session_state:
        st.session_state[period_key] = "12 meses"

    def _render_rentabilidade_chart():
        selected_period = st.session_state.get(period_key, "12 meses")
        limit = period_options.get(selected_period)

        rent_df = rent_full.copy()
        if limit:
            rent_df = rent_df.tail(limit)

        if rent_df.empty:
            st.info("Sem dados no intervalo selecionado.")
            return

        rent_df["Mes"] = rent_df["Data"].dt.strftime("%b/%y")

        if go is None:
            st.warning("Instale plotly para visualizar a rentabilidade mensal da carteira.")
            st.line_chart(rent_df.set_index("Mes")["Rentabilidade (%)"])
        else:
            max_abs = max(abs(rent_df["Rentabilidade (%)"].max()), abs(rent_df["Rentabilidade (%)"].min()))
            if max_abs == 0:
                max_abs = 1
            color_neutral = "#ffd54f"
            rent_df["Hover"] = rent_df["Rentabilidade (%)"].round(2)
            fig = go.Figure()
            fig.add_trace(
                go.Bar(
                    x=rent_df["Mes"],
                    y=rent_df["Rentabilidade (%)"],
                    marker=dict(color=color_neutral, line=dict(width=0), opacity=0.9),
                    customdata=rent_df["Hover"],
                    hovertemplate="%{x}: %{customdata:+.2f}%<extra></extra>",
                    name="Rentabilidade Mensal",
                )
            )
            fig.update_layout(
                title="Rentabilidade Mensal da Carteira (%)",
                xaxis=dict(showgrid=False, zeroline=False, title="Meses", tickangle=-45),
                yaxis=dict(
                    showgrid=False,
                    showticklabels=False,
                    zeroline=True,
                    zerolinecolor="#777",
                    range=[-max_abs * 1.15, max_abs * 1.15],
                ),
                showlegend=False,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
            )
            render_plotly(fig, key="rentabilidade_mensal_chart")

        with st.container():
            st.markdown(
                """
                <style>
                .periodo-inline-wrapper label {margin-right: 18px;}
                </style>

                """,
                unsafe_allow_html=True,
            )
        st.markdown('<div class="periodo-inline-wrapper">', unsafe_allow_html=True)
        st.radio(
            "Período",
            options=list(period_options.keys()),
            horizontal=True,
            key=period_key,
            help="Selecione o intervalo de visualização da rentabilidade mensal.",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    cota_period_options = ["YTD", "12m", "24m", "36m", "48m", "Todos"]
    cota_period_titles = {
        "YTD": "Ano Corrente",
        "12m": "Últimos 12 Meses",
        "24m": "Últimos 24 Meses",
        "36m": "Últimos 36 Meses",
        "48m": "Últimos 48 Meses",
        "Todos": "Período Completo",
    }
    cota_period_key = "cota_period_option"
    if cota_period_key not in st.session_state:
        st.session_state[cota_period_key] = "12m"

    def _filtrar_cotas(periodo: str) -> pd.DataFrame:
        df_filtrado = cotas_df.copy()
        if periodo == "Todos":
            return df_filtrado
        if periodo == "YTD":
            inicio_ano = datetime(datetime.today().year, 1, 1)
            return df_filtrado[df_filtrado.index >= inicio_ano]
        try:
            meses = int(periodo.replace("m", ""))
        except ValueError:
            return df_filtrado
        if len(df_filtrado) <= meses:
            return df_filtrado
        return df_filtrado.tail(meses)

    def _render_cota_chart():
        periodo_selecionado = st.session_state.get(cota_period_key, "12m")
        df_plot = _filtrar_cotas(periodo_selecionado)
        if df_plot.empty:
            st.info("Sem dados disponíveis para evolução de cota.")
        else:
            periodo_titulo = cota_period_titles.get(periodo_selecionado, periodo_selecionado)
            st.subheader(f"Evolução da Cota — {periodo_titulo}")
            eixo_x = df_plot.index
            eixo_y = df_plot["valor_cota"]
            if go is None:
                st.line_chart(eixo_y)
            else:
                ultimo_x = eixo_x[-1]
                ultimo_y = eixo_y.iloc[-1]
                fig_cota = go.Figure()
                fig_cota.add_trace(
                    go.Scatter(
                        x=eixo_x,
                        y=eixo_y,
                        mode="lines",
                        line=dict(color="#4ade80", width=3),
                        name="Valor da Cota",
                        hovertemplate="%{x|%b/%Y}: %{y:.2f}<extra></extra>",
                    )
                )
                fig_cota.add_trace(
                    go.Scatter(
                        x=[ultimo_x],
                        y=[ultimo_y],
                        mode="markers+text",
                        marker=dict(color="#facc15", size=10),
                        text=[f"{ultimo_y:.2f}"],
                        textposition="top center",
                        name="Última Cota",
                        hovertemplate="%{x|%b/%Y}: %{y:.2f}<extra></extra>",
                    )
                )
                fig_cota.update_layout(
                    xaxis=dict(
                        showgrid=False,
                        tickformat="%b/%y",
                        title="Meses",
                    ),
                    yaxis=dict(
                        showgrid=True,
                        tickformat=".2f",
                        title="Valor da Cota",
                        zeroline=False,
                    ),
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
                    margin=dict(t=50, b=40),
                )
                render_plotly(fig_cota, key="evolucao_cota_chart")
        with st.container():
            st.markdown(
                """
                <style>
                .cota-period-inline label {margin-right: 18px;}
                </style>

                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="cota-period-inline">', unsafe_allow_html=True)
            st.radio(
                "Intervalo de cota",
                options=cota_period_options,
                horizontal=True,
                key=cota_period_key,
                help="Selecione o intervalo exibido para a evolução do valor da cota.",
            )
            st.markdown("</div>", unsafe_allow_html=True)

    detalhes_ticker = {
        "valores_ticker": valores_ticker_df,
        "realizado_ticker": realizado_ticker_df,
    }

    return agregados, _render_rentabilidade_chart, _render_cota_chart, cotas_df, detalhes_ticker


# --- Sessão / autenticação ---
restaurar_usuario_sessao()
if "usuario" not in st.session_state or not st.session_state.usuario:
    redirecionar_para_login()

usuario_logado = st.session_state.get("usuario", "desconhecido")

st.markdown(
    f"""
<br>
<div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 0px;'>
    <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
    <form action='/?logout=true' method='get'>
        <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
    </form>
</div>
""",
    unsafe_allow_html=True,
)

if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

uid = st.session_state.get("uid")
if not uid:
    redirecionar_para_login()

# Carrega as vendas uma única vez para reaproveitar nos blocos da página.
try:
    vendas_registros = carregar_vendas(uid) or []
except Exception as exc:
    _handle_auth_error(exc)
    st.error("Não foi possível carregar as vendas do usuário.")
    st.stop()

st.subheader("Performance da Carteira")


# --- Dados da carteira ---
try:
    carteira_registros = carregar_carteira_supabase(uid) or []
except Exception as exc:
    _handle_auth_error(exc)
    st.error("Não foi possível carregar a carteira do usuário.")
    st.stop()
if not carteira_registros:
    st.info("Nenhum ativo encontrado na carteira.")
    st.stop()

supabase_client = supabase_autenticado()

try:
    dividendos_registros = carregar_dividendos_usuario(st.session_state.usuario) or []
except Exception as exc:
    _handle_auth_error(exc)
    dividendos_registros = []

try:
    opcoes_operacoes_registros = carregar_operacoes_finalizadas(uid) or []
except Exception as exc:
    _handle_auth_error(exc)
    opcoes_operacoes_registros = []

try:
    resp_opcoes_carteira = (
        supabase_client.table("opcoes_carteira")
        .select("*")
        .eq("user_id", uid)
        .execute()
    )
    opcoes_carteira_registros = getattr(resp_opcoes_carteira, "data", None) or []
except Exception as exc:
    _handle_auth_error(exc)
    opcoes_carteira_registros = []

posicao_atual = []
lotes_por_ticker = defaultdict(list)
ajuste_por_ticker = defaultdict(lambda: {"aporte": 0.0, "div": 0.0, "opcao": 0.0, "quantidade": 0})

for registro in carteira_registros:
    ticker = str(registro.get("ticker", "")).upper()
    quantidade = int(registro.get("quantidade") or 0)
    custo_unitario = float(registro.get("custo") or 0.0)
    custo_operacional = float(registro.get("custo_operacional") or 0.0)
    data_compra = registro.get("data_compra", "")
    uuid_registro = registro.get("id")

    if not ticker or quantidade <= 0:
        continue

    item = {
        "UUID": uuid_registro,
        "Ticker": ticker,
        "Quantidade": quantidade,
        "Custo": f"{custo_unitario:.2f}".replace(".", ","),
        "Data de Compra": data_compra,
        "Custo Operacional": f"{custo_operacional:.2f}".replace(".", ","),
    }
    posicao_atual.append(item)
    lotes_por_ticker[ticker].append(
        {
            "uuid": uuid_registro,
            "data_compra": parse_data_compra(data_compra),
            "quantidade": quantidade,
        }
    )

if not posicao_atual:
    st.info("Nenhum ativo válido encontrado na carteira.")
    st.stop()

alloc_por_ticker = {}
for ticker, lots in lotes_por_ticker.items():
    try:
        alloc_por_ticker[ticker] = alocar_coberturas_por_lote(uid, ticker, lots)
    except Exception:
        alloc_por_ticker[ticker] = {"por_lote": {}, "ops": {}}

for item in posicao_atual:
    custo_final_unit, detalhes = custo_final_unit_para_item(item, alloc_por_ticker, supabase_client)
    item["Custo"] = f"{custo_final_unit:.2f}".replace(".", ",")
    item["_custo_ajustado_unit"] = custo_final_unit
    item["_detalhes"] = detalhes
    ticker = item["Ticker"]
    quantidade = item["Quantidade"]
    ajuste = ajuste_por_ticker[ticker]
    ajuste["aporte"] += custo_final_unit * quantidade
    ajuste["div"] += detalhes.get("div_por_acao", 0.0) * quantidade
    ajuste["opcao"] += detalhes.get("opc_por_acao", 0.0) * quantidade
    ajuste["quantidade"] += quantidade

preco_cache = {}
for ticker in list(ajuste_por_ticker.keys()):
    try:
        preco_cache[ticker] = parse_preco_float(obter_preco_ativo(ticker))
    except Exception:
        preco_cache[ticker] = None
    ajuste_por_ticker[ticker]["preco_atual"] = preco_cache[ticker]

# --- Desempenho por ticker (usa yfinance via utils) ---
desempenho = calcular_desempenho_consolidado(posicao_atual)
if not desempenho:
    st.warning("Não foi possível calcular o desempenho da carteira.")
    st.stop()

desempenho = sorted(desempenho, key=lambda x: x.get("variacao_percentual", 0.0), reverse=True)
total_aportado = sum(info["aporte"] for info in ajuste_por_ticker.values())

valor_investido = total_aportado
valor_atual = 0.0
for ativo in desempenho:
    ticker = str(ativo.get("ticker", "")).upper()
    variacao_rs = float(ativo.get("variacao_reais") or 0.0)
    info = ajuste_por_ticker.get(ticker, {})
    aporte = info.get("aporte", 0.0)
    quantidade = info.get("quantidade", 0)
    preco_atual = info.get("preco_atual")
    if preco_atual is not None and quantidade:
        valor_atual_ticker = preco_atual * quantidade
    else:
        valor_atual_ticker = aporte + variacao_rs
    info["valor_atual"] = valor_atual_ticker
    info["variacao_reais"] = variacao_rs
    info["variacao_percentual"] = float(ativo.get("variacao_percentual") or 0.0)
    valor_atual += valor_atual_ticker


variacao_percentual_total = ((valor_atual / valor_investido) - 1) * 100 if valor_investido else 0.0
resultado_total = valor_atual - valor_investido

# Rentabilidade mensal (%), separando carteira vs. realizados.
rent_aggs, rent_chart_renderer, cota_chart_renderer, cotas_auditoria_df, detalhes_ticker_df = plotar_evolucao_mensal(
    posicao_atual,
    ajuste_por_ticker,
    vendas_registros,
    carteira_registros,
    dividendos_registros,
    opcoes_operacoes_registros,
    opcoes_carteira_registros,
)
tir_anual = calcular_tir_anualizada(cotas_auditoria_df, valor_atual)
tir_percentual = tir_anual * 100 if tir_anual is not None else None
tir_display = format_pct(tir_percentual) if tir_percentual is not None else "—"

# === Layouts de métricas principais ===


def _metric_block(title: str, value: str) -> str:
    return f"""
    <div class='metric-block'>
        <span class='metric-title'>{title}</span>
        <span class='metric-value'>{value}</span>
    </div>
    """


rent_12m = rent_aggs.get(12) if isinstance(rent_aggs, dict) else None
rent_24m = rent_aggs.get(24) if isinstance(rent_aggs, dict) else None
rent_36m = rent_aggs.get(36) if isinstance(rent_aggs, dict) else None
rent_48m = rent_aggs.get(48) if isinstance(rent_aggs, dict) else None
rent_6m = rent_cota_window(cotas_auditoria_df, 6)
rent_ytd = rent_cota_ytd(cotas_auditoria_df)
rent_6m_pct = rent_6m * 100 if rent_6m is not None else None
rent_ytd_pct = rent_ytd * 100 if rent_ytd is not None else None

_layout3_html = """
<style>
.metric-card {
    border:1px solid rgba(255,255,255,0.08);
    border-radius:16px;
    padding:22px 26px;
    margin-bottom:32px;
    background:rgba(11,16,28,0.9);
}
.metric-row {
    display:grid;
    gap:20px;
}
.metric-row--top {
    grid-template-columns: repeat(5, minmax(0, 1fr));
    margin-bottom:18px;
}
.metric-row--bottom {
    grid-template-columns: repeat(6, minmax(0, 1fr));
    border-top:1px solid rgba(255,255,255,0.08);
    padding-top:14px;
}
.metric-item {
    display:flex;
    flex-direction:column;
    min-width:0;
    width:100%;
}
.metric-item .label {
    color:#8EA0C4;
    font-size:0.78rem;
    letter-spacing:0.05em;
    text-transform:uppercase;
}
.metric-item .value {
    font-size:1.3rem;
    font-weight:600;
    color:#F4F7FF;
    white-space:nowrap;
}
.metric-item.large .value {font-size:1.55rem;}
@media (max-width: 1100px) {
    .metric-row--top {
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }
    .metric-row--bottom {
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    }
}
</style>
<div class='metric-card'>
    <div class='metric-row metric-row--top'>
        <div class='metric-item large'><span class='label'>Patrimônio</span><span class='value'>{{patrimonio}}</span></div>
        <div class='metric-item large'><span class='label'>Valor Investido</span><span class='value'>{{valor_inv}}</span></div>
        <div class='metric-item large'><span class='label'>Resultado</span><span class='value'>{{resultado}}</span></div>
        <div class='metric-item large'><span class='label'>Variação %</span><span class='value'>{{variacao}}</span></div>
        <div class='metric-item large'><span class='label'>TIR ao ano</span><span class='value'>{{tir}}</span></div>
    </div>
    <div class='metric-row metric-row--bottom'>
        <div class='metric-item'><span class='label'>Rent. YTD</span><span class='value'>{{rentYTD}}</span></div>
        <div class='metric-item'><span class='label'>Rent. 6m</span><span class='value'>{{rent6}}</span></div>
        <div class='metric-item'><span class='label'>Rent. 12m</span><span class='value'>{{rent12}}</span></div>
        <div class='metric-item'><span class='label'>Rent. 24m</span><span class='value'>{{rent24}}</span></div>
        <div class='metric-item'><span class='label'>Rent. 36m</span><span class='value'>{{rent36}}</span></div>
        <div class='metric-item'><span class='label'>Rent. 48m</span><span class='value'>{{rent48}}</span></div>
    </div>
</div>
"""
st.markdown(
    _layout3_html
    .replace("{{patrimonio}}", formatar_valor(valor_atual))
    .replace("{{tir}}", tir_display)
    .replace("{{valor_inv}}", formatar_valor(valor_investido))
    .replace("{{resultado}}", formatar_valor(resultado_total))
    .replace("{{variacao}}", format_pct(variacao_percentual_total))
    .replace("{{rentYTD}}", format_pct(rent_ytd_pct) if rent_ytd_pct is not None else "--")
    .replace("{{rent6}}", format_pct(rent_6m_pct) if rent_6m_pct is not None else "--")
    .replace("{{rent12}}", format_pct(rent_12m) if rent_12m is not None else "--")
    .replace("{{rent24}}", format_pct(rent_24m) if rent_24m is not None else "--")
    .replace("{{rent36}}", format_pct(rent_36m) if rent_36m is not None else "--")
    .replace("{{rent48}}", format_pct(rent_48m) if rent_48m is not None else "--"),
    unsafe_allow_html=True,
)


def _fmt_optional(value):
    return format_pct(value) if (value is not None) else "--"


def preparar_df_auditoria(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    audit = df.sort_index().copy()
    audit = audit.reset_index().rename(columns={"index": "Data"})
    audit["Mes"] = audit["Data"].dt.strftime("%Y-%m")
    audit["cota_anterior"] = audit["valor_cota"].shift(1)
    audit["retorno_pct"] = audit.get("rentabilidade_pct", audit["valor_cota"].pct_change() * 100.0)
    audit["total_anterior"] = audit["total"].shift(1)
    audit["carteira_acoes"] = audit.get("valor_carteira", 0.0)
    audit["valor_opcoes"] = audit.get("valor_opcoes", 0.0)
    audit["realizado_acoes_mes"] = audit.get("realizado_acoes_mes", 0.0)
    audit["realizado_opcoes_mes"] = audit.get("resultado_opcoes_mes", 0.0)
    audit["dividendos_mes"] = audit.get("dividendos_mes", 0.0)
    audit["aportes_mes"] = audit.get("aportes", 0.0)
    audit["total_economico"] = audit.get("total", 0.0)
    audit["realizado_acoes_acum"] = audit.get("realizado_acoes_acum", 0.0)
    audit["resultado_opcoes_acum"] = audit.get("resultado_opcoes_acum", 0.0)
    audit["dividendos_acum"] = audit.get("dividendos_acum", 0.0)
    audit["fonte_carteira"] = audit["carteira_acoes"].diff().fillna(audit["carteira_acoes"])
    audit["fonte_dividendos"] = audit["dividendos_mes"]
    audit["fonte_opcoes"] = audit["realizado_opcoes_mes"]
    audit["fonte_realizado_acoes"] = audit["realizado_acoes_mes"]
    return audit


def filtrar_auditoria_por_periodo(df: pd.DataFrame, periodo: str) -> pd.DataFrame:
    if df.empty:
        return df
    if periodo == "Todos":
        return df
    if periodo == "YTD":
        inicio_ano = datetime(datetime.today().year, 1, 1)
        return df[df["Data"] >= inicio_ano]
    try:
        meses = int(periodo.split()[0])
    except ValueError:
        return df
    if len(df) <= meses:
        return df
    return df.tail(meses)


def formatar_opcional_valor(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "--"
    return formatar_valor(valor)

def formatar_pct_opcional(valor: float | None) -> str:
    if valor is None or pd.isna(valor):
        return "--"
    return format_pct(valor)

df_auditoria = preparar_df_auditoria(cotas_auditoria_df)

inject_audit_styles()

if callable(cota_chart_renderer):
    try:
        cota_chart_renderer()
    except Exception as exc:
        st.error(f"Não foi possível renderizar a evolução da cota ({exc}).")

if callable(rent_chart_renderer):
    try:
        rent_chart_renderer()
    except Exception as exc:
        st.error(f"Não foi possível renderizar a rentabilidade mensal ({exc}).")

if not df_auditoria.empty:
    with st.expander("Auditoria da rentabilidade (detalhe mensal)", expanded=False):
        st.markdown(
            "_Atenção: os valores abaixo consideram o patrimônio econômico (carteira + vendas + "
            "opções + dividendos). O card de patrimônio no topo exibe apenas a carteira viva._"
        )

        aba_mes, aba_periodo = st.tabs(["Por mês", "Por período"])

        with aba_mes:
            anos_disponiveis = sorted(df_auditoria["Data"].dt.year.unique(), reverse=True)
            if not anos_disponiveis:
                aba_mes.info("Sem dados disponíveis para exibição mensal.")
            else:
                abas_anos = aba_mes.tabs([str(ano) for ano in anos_disponiveis])
                for tab_ano, ano in zip(abas_anos, anos_disponiveis):
                    with tab_ano:
                        df_ano = df_auditoria[df_auditoria["Data"].dt.year == ano]
                        if df_ano.empty:
                            st.info(f"Sem dados disponíveis para o ano {ano}.")
                            continue
                        meses_numeros = sorted(df_ano["Data"].dt.month.unique())
                        if not meses_numeros:
                            st.info(f"Sem dados mensais disponíveis para {ano}.")
                            continue
                        meses_nomes = {
                            1: "Janeiro",
                            2: "Fevereiro",
                            3: "Março",
                            4: "Abril",
                            5: "Maio",
                            6: "Junho",
                            7: "Julho",
                            8: "Agosto",
                            9: "Setembro",
                            10: "Outubro",
                            11: "Novembro",
                            12: "Dezembro",
                        }
                        meses_labels = [meses_nomes.get(int(m), str(m)) for m in meses_numeros]
                        label_para_mes = dict(zip(meses_labels, meses_numeros))
                        meses_labels_desc = list(reversed(meses_labels))
                        abas_meses = st.tabs(meses_labels_desc)
                        for idx_tab, (tab_mes, mes_label) in enumerate(zip(abas_meses, meses_labels_desc)):
                            mes_numero = label_para_mes.get(mes_label, meses_numeros[-1])
                            with tab_mes:
                                df_mes = df_ano[df_ano["Data"].dt.month == mes_numero]
                                if df_mes.empty:
                                    st.info("Sem dados para este mês.")
                                    continue
                                linha_mes = df_mes.iloc[0]
                                data_mes = linha_mes["Data"]
                                mes_label_completo = f"{meses_nomes.get(data_mes.month, data_mes.strftime('%b'))}/{data_mes.year}"
                                prev_data = data_mes - pd.offsets.MonthBegin(1)
                                mes_anterior_ref = (
                                    f"{meses_nomes.get(prev_data.month, prev_data.strftime('%b'))}/{prev_data.year}"
                                    if not pd.isna(prev_data)
                                    else "N/A"
                                )
                                rentabilidade_valor = linha_mes["retorno_pct"]
                                rentabilidade_mes = formatar_pct_opcional(rentabilidade_valor)
                                cor_rent = (
                                    "green"
                                    if rentabilidade_valor and rentabilidade_valor > 0
                                    else "red"
                                    if rentabilidade_valor and rentabilidade_valor < 0
                                    else "inherit"
                                )
                                cota_anterior_txt = formatar_opcional_valor(
                                    linha_mes["cota_anterior"]
                                )
                                cota_atual_txt = formatar_opcional_valor(linha_mes["valor_cota"])

                                resumo_html = f"""
                                <table class="audit-summary-table">
                                  <tr>
                                    <th>Cota anterior</th>
                                    <th>Cota atual</th>
                                    <th>Rentabilidade</th>
                                  </tr>
                                  <tr>
                                    <td>{cota_anterior_txt}</td>
                                    <td>{cota_atual_txt}</td>
                                    <td style="color:{cor_rent};font-weight:600;">{rentabilidade_mes}</td>
                                  </tr>
                                </table>
                                """
                                col_resumo, col_formula = st.columns([1, 1], gap="medium")
                                with col_resumo:
                                    st.markdown(f"### Mês auditado: {mes_label_completo}")
                                    st.markdown(resumo_html, unsafe_allow_html=True)

                                total_atual = linha_mes["total_economico"]
                                total_anterior = linha_mes.get("total_anterior")
                                if pd.isna(total_anterior):
                                    total_anterior_val = 0.0
                                    mes_anterior_ref_mostrar = "N/A"
                                else:
                                    total_anterior_val = total_anterior
                                    mes_anterior_ref_mostrar = mes_anterior_ref
                                aporte_mes = linha_mes["aportes_mes"]

                                formula_html = f"""
                                <div class="formula-box">
                                  <div class="row"><span>Total (mês atual)</span><span>{formatar_valor(total_atual)}</span></div>
                                  <div class="row"><span>Total (mês anterior)</span><span>{formatar_valor(total_anterior_val)} ({mes_anterior_ref_mostrar})</span></div>
                                  <div class="row"><span>Aportes do mês</span><span>{formatar_valor(aporte_mes)}</span></div>
                                  <div class="result">
                                    Rentabilidade = ( {formatar_valor(total_atual)} / ( {formatar_valor(total_anterior_val)} + {formatar_valor(aporte_mes)} ) ) − 1<br>
                                    Resultado: <span style="color:{cor_rent};">{rentabilidade_mes}</span>
                                  </div>
                                </div>
                                """
                                with col_formula:
                                    st.markdown("### Fórmula da rentabilidade mensal")
                                    st.markdown(formula_html, unsafe_allow_html=True)

                                componentes = [
                                    ("Carteira (ações)", linha_mes["carteira_acoes"]),
                                    ("Valor em opções", linha_mes["valor_opcoes"]),
                                    ("Realizado ações (mês)", linha_mes["realizado_acoes_mes"]),
                                    ("Realizado opções (mês)", linha_mes["realizado_opcoes_mes"]),
                                    ("Dividendos (mês)", linha_mes["dividendos_mes"]),
                                    ("Aportes (mês)", aporte_mes),
                                    ("Total econômico (mês)", total_atual),
                                ]
                                for i in range(0, len(componentes), 3):
                                    cols = st.columns(min(3, len(componentes) - i))
                                    for col, (label, valor) in zip(cols, componentes[i : i + 3]):
                                        col.metric(label, formatar_valor(valor))

                                valores_ticker_df = detalhes_ticker_df.get(
                                    "valores_ticker", pd.DataFrame()
                                )
                                realizado_ticker_df = detalhes_ticker_df.get(
                                    "realizado_ticker", pd.DataFrame()
                                )
                                st.markdown(f"#### Ativos que mais impactaram {mes_label_completo}")
                                if (
                                    valores_ticker_df.empty
                                    or data_mes not in valores_ticker_df.index
                                    or len(valores_ticker_df.columns) == 0
                                ):
                                    st.info("Sem dados de variação de ativos para este mês.")
                                else:
                                    prev_data_valores = data_mes - pd.offsets.MonthBegin(1)
                                    valor_mes = valores_ticker_df.loc[data_mes]
                                    if prev_data_valores in valores_ticker_df.index:
                                        valor_prev = valores_ticker_df.loc[prev_data_valores]
                                    else:
                                        valor_prev = pd.Series(
                                            0.0, index=valores_ticker_df.columns
                                        )
                                    delta_valor = (valor_mes - valor_prev).fillna(0.0)
                                    if (
                                        not realizado_ticker_df.empty
                                        and data_mes in realizado_ticker_df.index
                                    ):
                                        realizado_mes = (
                                            realizado_ticker_df.loc[data_mes]
                                            .reindex(delta_valor.index)
                                            .fillna(0.0)
                                        )
                                    else:
                                        realizado_mes = pd.Series(
                                            0.0, index=delta_valor.index
                                        )
                                    contribuicoes = (delta_valor + realizado_mes).dropna()
                                    contribuicoes = contribuicoes[contribuicoes != 0]
                                    if contribuicoes.empty:
                                        st.info(
                                            "Sem variações relevantes para destacar neste mês."
                                        )
                                    else:
                                        ordem = (
                                            contribuicoes.abs()
                                            .sort_values(ascending=False)
                                            .index[:10]
                                        )
                                        top_series = contribuicoes.loc[ordem]
                                        if go is None:
                                            st.bar_chart(
                                                pd.DataFrame({"Contribuição": top_series}),
                                                width="stretch",
                                                key=f"top_movers_{ano}_{mes_numero}_{idx_tab}",
                                            )
                                        else:
                                            y_labels = list(reversed(top_series.index.tolist()))
                                            valores_plot = list(
                                                reversed(top_series.values.tolist())
                                            )
                                            cores = [
                                                "#22c55e" if v >= 0 else "#ef4444"
                                                for v in valores_plot
                                            ]
                                            fig_top = go.Figure(
                                                go.Bar(
                                                    x=valores_plot,
                                                    y=y_labels,
                                                    orientation="h",
                                                    marker_color=cores,
                                                    hovertemplate="%{y}: %{x:.2f}<extra></extra>",
                                                )
                                            )
                                            fig_top.update_layout(
                                                xaxis_title="Contribuição (R$)",
                                                yaxis_title="Ticker",
                                                plot_bgcolor="rgba(0,0,0,0)",
                                                paper_bgcolor="rgba(0,0,0,0)",
                                                margin=dict(t=30, b=30),
                                            )
                                            render_plotly(
                                                fig_top,
                                                key=f"top_movers_{ano}_{mes_numero}_{idx_tab}",
                                            )

                                df_fontes_ano = df_auditoria[
                                    df_auditoria["Data"].dt.year == ano
                                ]
                                if df_fontes_ano.empty:
                                    st.info(
                                        "Sem dados de fontes de rentabilidade para o ano selecionado."
                                    )
                                else:
                                    df_fontes = df_fontes_ano[
                                        [
                                            "Mes",
                                            "fonte_carteira",
                                            "fonte_dividendos",
                                            "fonte_opcoes",
                                            "fonte_realizado_acoes",
                                        ]
                                    ].copy()
                                    df_fontes = df_fontes.rename(
                                        columns={
                                            "fonte_carteira": "Ações (MTM)",
                                            "fonte_dividendos": "Dividendos",
                                            "fonte_opcoes": "Opções",
                                            "fonte_realizado_acoes": "Vendas de ações",
                                        }
                                    )
                                    df_fontes_chart = df_fontes.set_index("Mes").fillna(0.0)
                                    if go is None:
                                        st.bar_chart(
                                            df_fontes_chart,
                                            width="stretch",
                                            key=f"fontes_{ano}_{mes_numero}_{idx_tab}",
                                        )
                                    else:
                                        fig_fontes = go.Figure()
                                        cores_fontes = {
                                            "Ações (MTM)": "#60a5fa",
                                            "Dividendos": "#facc15",
                                            "Opções": "#34d399",
                                            "Vendas de ações": "#fb7185",
                                        }
                                        for coluna, cor in cores_fontes.items():
                                            fig_fontes.add_trace(
                                                go.Bar(
                                                    name=coluna,
                                                    x=df_fontes_chart.index,
                                                    y=df_fontes_chart[coluna],
                                                    marker_color=cor,
                                                )
                                            )
                                        fig_fontes.update_layout(
                                            title=f"Fontes de rentabilidade no ano {ano}",
                                            barmode="relative",
                                            xaxis=dict(title="Mês"),
                                            yaxis=dict(title="Contribuição (R$)"),
                                            plot_bgcolor="rgba(0,0,0,0)",
                                            paper_bgcolor="rgba(0,0,0,0)",
                                            legend=dict(
                                                orientation="h",
                                                yanchor="bottom",
                                                y=1.02,
                                                xanchor="right",
                                                x=1,
                                            ),
                                            margin=dict(t=60, b=40),
                                        )
                                        render_plotly(
                                            fig_fontes,
                                            key=f"fontes_{ano}_{mes_numero}_{idx_tab}",
                                        )
        with aba_periodo:
            periodos_def = [
                ("12 meses", 12),
                ("24 meses", 24),
                ("36 meses", 36),
                ("48 meses", 48),
                ("Todos", None),
            ]
            resumos = []
            df_ordenado = df_auditoria.sort_values("Data")
            for label, meses in periodos_def:
                if meses is None:
                    df_period = df_ordenado.copy()
                else:
                    if len(df_ordenado) < meses:
                        continue
                    df_period = df_ordenado.tail(meses)
                if df_period.empty:
                    continue
                cota_inicio = df_period.iloc[0]["valor_cota_anterior"]
                if pd.isna(cota_inicio) or cota_inicio == 0:
                    cota_inicio = df_period.iloc[0]["valor_cota"]
                cota_fim = df_period.iloc[-1]["valor_cota"]
                rent_periodo = (
                    (cota_fim / cota_inicio - 1) if cota_inicio and not pd.isna(cota_inicio) else None
                )
                resumo = {
                    "Período": label,
                    "Cota início": cota_inicio,
                    "Cota fim": cota_fim,
                    "Rent. %": rent_periodo * 100 if rent_periodo is not None else None,
                    "Dividendos Σ": df_period["dividendos_mes"].sum(),
                    "Realizado ações Σ": df_period["realizado_acoes_mes"].sum(),
                    "Realizado opções Σ": df_period["realizado_opcoes_mes"].sum(),
                    "Aportes Σ": df_period["aportes_mes"].sum(),
                }
                resumos.append(resumo)

            if not resumos:
                aba_periodo.info("Sem dados suficientes para os períodos solicitados.")
            else:
                df_resumo = pd.DataFrame(resumos)
                df_resumo_display = df_resumo.copy()
                df_resumo_display["Cota início"] = df_resumo_display["Cota início"].apply(
                    formatar_opcional_valor
                )
                df_resumo_display["Cota fim"] = df_resumo_display["Cota fim"].apply(
                    formatar_opcional_valor
                )
                df_resumo_display["Rent. %"] = df_resumo_display["Rent. %"].apply(
                    formatar_pct_opcional
                )
                for coluna in ["Dividendos Σ", "Realizado ações Σ", "Realizado opções Σ", "Aportes Σ"]:
                    df_resumo_display[coluna] = df_resumo_display[coluna].apply(formatar_valor)
                aba_periodo.dataframe(df_resumo_display, hide_index=True)

                resumo_48 = next(
                    (item for item in resumos if item["Período"] == "48 meses"), None
                )
                if resumo_48:
                    rent_texto = formatar_pct_opcional(resumo_48["Rent. %"])
                    texto_resumo = (
                        f"Nos últimos 48 meses a rentabilidade ficou em {rent_texto}. "
                        f"Nesse período, dividendos somaram {formatar_valor(resumo_48['Dividendos Σ'])}, "
                        f"realizado de ações totalizou {formatar_valor(resumo_48['Realizado ações Σ'])} "
                        f"e realizado de opções {formatar_valor(resumo_48['Realizado opções Σ'])}, "
                        f"com aportes acumulados de {formatar_valor(resumo_48['Aportes Σ'])}."
                    )
                    aba_periodo.markdown(texto_resumo)



# Controle de ordenação (switch nativo se disponível)
toggle_label = "Ordenar por participação"
toggle_help = "Ative para ordenar os cards pela participação (aporte) em vez de rentabilidade."

toggle_fn = getattr(st, "toggle", None)
ordenar_por_participacao = False

if callable(toggle_fn):
    col_toggle, _ = st.columns([1, 1])
    with col_toggle:
        ordenar_por_participacao = toggle_fn(
            toggle_label,
            value=False,
            help=toggle_help,
            key="toggle_participacao_performance",
        )
else:
    ordenar_por_participacao = st.checkbox(
        toggle_label,
        value=False,
        help=toggle_help,
        key="toggle_participacao_performance",
    )

if ordenar_por_participacao:
    desempenho = sorted(
        desempenho,
        key=lambda x: ajuste_por_ticker.get(str(x.get("ticker", "")).upper(), {}).get("valor_atual", 0.0),
        reverse=True,
    )


# --- Estilo dos cards (replicando Pag.3) ---
st.markdown(
    """
    <style>
.cards-wrapper {
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        margin-top: 16px;
        margin-bottom: 24px;
        align-items: stretch;
    }
    .card-performance {
        display: flex;
        flex-direction: column;
        justify-content: center;
        flex: 0 1 180px;
        background: #262730;
        border-radius: 12px;
        padding: 12px 18px;
        min-width: 160px;
        min-height: 150px;
        text-align: center;
        box-shadow: 0 4px 14px rgba(0,0,0,0.28);
        transition: transform 0.18s ease, box-shadow 0.18s ease;
    }
    .card-performance:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 18px rgba(0,0,0,0.45);
    }
    .card-performance .ticker {
        font-size: 18px;
        font-weight: 700;
        color: #f5f5f5;
        margin-bottom: 4px;
    }
    .card-performance .percentual,
    .card-performance .reais {
        font-size: 16px;
        font-weight: 600;
        margin: 2px 0;
    }
    .card-performance small {
        display: block;
        margin-top: 6px;
        font-size: 11px;
        color: #9ca3af;
    }
    </style>

    """,
    unsafe_allow_html=True,
)


# --- Renderização ---

cards_carteira = []
total_valor_atual = valor_atual
for ativo in desempenho:
    ticker = str(ativo.get("ticker", "")).upper()
    variacao_pct = float(ativo.get("variacao_percentual") or 0.0)
    variacao_rs = float(ativo.get("variacao_reais") or 0.0)

    info = ajuste_por_ticker.get(ticker, {})
    aporte = info.get("aporte", 0.0)
    quantidade = info.get("quantidade", 0)
    valor_atual_ticker = info.get("valor_atual", aporte + variacao_rs)
    participacao = (valor_atual_ticker / total_valor_atual * 100) if total_valor_atual > 0 else 0.0
    detalhes = [
        f"Aporte: {format_brl(aporte)}",
        f"Valor atual: {format_brl(valor_atual_ticker)}",
        f"Participação: {participacao:.2f}%".replace(".", ","),
    ]
    div_total = info.get("div", 0.0)
    opcao_total = info.get("opcao", 0.0)
    if div_total:
        detalhes.append(f"Dividendos: {format_brl(div_total)}")
    if opcao_total:
        detalhes.append(f"Opções: {format_brl(opcao_total)}")

    preco_medio = (aporte / quantidade) if quantidade else None
    preco_atual = info.get("preco_atual")
    preco_medio_txt = format_brl(preco_medio) if preco_medio is not None else "N/D"
    preco_atual_txt = format_brl(preco_atual) if preco_atual is not None else "N/D"
    tooltip = f"Preço médio: {preco_medio_txt} • Cotação: {preco_atual_txt}"
    cards_carteira.append(
        {
            "ticker": ticker,
            "variacao_pct": variacao_pct,
            "variacao_rs": variacao_rs,
            "tooltip": tooltip,
            "detalhes": detalhes,
        }
    )

render_cards(cards_carteira)

# --- Gráficos de participação ---

st.markdown("### Participação por Ativo")

participacao_series = []
for ticker, info in ajuste_por_ticker.items():
    valor_atual_ticker = info.get("valor_atual", 0.0)
    if valor_atual_ticker > 0:
        participacao_series.append(
            {
                "ticker": ticker.split(".")[0],
                "valor": valor_atual_ticker,
                "categoria": "Carteira",
            }
        )

if participacao_series:
    total = sum(item["valor"] for item in participacao_series)
    for item in participacao_series:
        item["percent"] = (item["valor"] / total) * 100 if total else 0
    participacao_series.sort(key=lambda x: x["percent"], reverse=True)

    st.markdown(
        """
        <style>
        .pag9-part-bar {
            display: flex;
            width: 100%;
            border-radius: 14px;
            overflow: hidden;
            background: linear-gradient(90deg, rgba(30,30,30,0.85), rgba(15,15,15,0.95));
            border: 1px solid rgba(255,255,255,0.06);
            margin: 6px 0 12px;
        }
        .pag9-part-seg {
            height: 18px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-size: 0.68rem;
            font-weight: 600;
            padding: 0 6px;
            color: #fdfdfd;
            position: relative;
        }
        .pag9-part-seg::after {
            content: "";
            position: absolute;
            right: 0;
            top: 0;
            bottom: 0;
            width: 1px;
            background: rgba(0,0,0,0.35);
        }
        .pag9-part-seg:last-child::after {display: none;}
        .pag9-part-legend {
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
            font-size: 0.78rem;
            color: #cfcfcf;
        }
        .pag9-part-legend span {
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }
        .pag9-part-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            display: inline-block;
        }
        </style>

        """,
        unsafe_allow_html=True,
    )

    palette = [
        "#ff6b6b",
        "#feca57",
        "#1dd1a1",
        "#54a0ff",
        "#5f27cd",
        "#48dbfb",
        "#ff9ff3",
        "#10ac84",
        "#576574",
        "#ffa502",
    ]

    for idx, item in enumerate(participacao_series):
        item["color"] = palette[idx % len(palette)]

    segs = []
    for item in participacao_series:
        width = item["percent"]
        segs.append(
            f"<div class='pag9-part-seg' style='width:{width:.4f}%;background:{item['color']};' title='{item['ticker']} — {item['percent']:.2f}%'></div>"
        )
    st.markdown("<div class='pag9-part-bar'>" + "".join(segs) + "</div>", unsafe_allow_html=True)

    legend_html = "<div class='pag9-part-legend'>" + "".join(
        f"<span><span class='pag9-part-dot' style='background:{item['color']}'></span>{item['ticker']} ({item['percent']:.2f}%)</span>"
        for item in participacao_series
    ) + "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)
    st.markdown("<div style='height:18px;'></div>", unsafe_allow_html=True)


st.subheader("Performance Histórica")

toggle_fn_hist = getattr(st, "toggle", None)
ordenar_historico_por_valor = False
if callable(toggle_fn_hist):
    col_hist_toggle, _ = st.columns([1, 2])
    with col_hist_toggle:
        ordenar_historico_por_valor = toggle_fn_hist(
            "Ordenar histórico por valor absoluto",
            value=False,
            help="Alterne entre ordenação por resultado em R$ (valor absoluto) ou por percentual.",
            key="toggle_ordenacao_historico",
        )
else:
    ordenar_historico_por_valor = st.checkbox(
        "Ordenar histórico por valor absoluto",
        value=False,
        help="Alterne entre ordenação por resultado em R$ (valor absoluto) ou por percentual.",
        key="toggle_ordenacao_historico",
    )

if not vendas_registros:
    st.info("Nenhuma operação finalizada registrada até o momento.")
else:
    historico_agrupado: dict[str, dict] = defaultdict(
        lambda: {
            "custo_total": 0.0,
            "receita_total": 0.0,
            "resultado_total": 0.0,
            "quantidade_total": 0,
            "operacoes": 0,
        }
    )

    for venda in vendas_registros:
        try:
            ticker = str(venda.get("ticker", "")).upper()
            quantidade = int(venda.get("quantidade") or 0)
            preco_compra = float(venda.get("preco_compra") or 0.0)
            preco_venda = float(venda.get("preco_venda") or 0.0)
            data_compra = venda.get("data_compra")
            data_venda = venda.get("data_venda")

            if not ticker or quantidade <= 0:
                continue

            dividendos_unit = obter_total_dividendos_para_lote_intervalado(
                uid,
                ticker,
                data_compra,
                data_venda,
            )
            creditos_opcoes_unit = obter_credito_opcoes_para_lote_intervalado(
                uid,
                ticker,
                data_compra,
                data_venda,
                quantidade,
            )

            custo_ajustado_unit = max(preco_compra - dividendos_unit - creditos_opcoes_unit, 0.0)
            custo_total = custo_ajustado_unit * quantidade
            receita_total = preco_venda * quantidade
            resultado = receita_total - custo_total

            agrupado = historico_agrupado[ticker]
            agrupado["custo_total"] += custo_total
            agrupado["receita_total"] += receita_total
            agrupado["resultado_total"] += resultado
            agrupado["quantidade_total"] += quantidade
            agrupado["operacoes"] += 1
        except Exception:
            continue

    total_investido_hist = sum(dados["custo_total"] for dados in historico_agrupado.values())
    total_resgatado_hist = sum(dados["receita_total"] for dados in historico_agrupado.values())
    variacao_hist_pct = (
        ((total_resgatado_hist / total_investido_hist) - 1) * 100
        if total_investido_hist
        else 0.0
    )
    resultado_hist = total_resgatado_hist - total_investido_hist

    col_h1, col_h2, col_h3, col_h4 = st.columns(4)
    col_h1.metric("Valor Investido", formatar_valor(total_investido_hist))
    col_h2.metric("Valor Resgatado", formatar_valor(total_resgatado_hist))
    col_h3.metric("Resultado", formatar_valor(resultado_hist))
    col_h4.metric("Variação %", format_pct(variacao_hist_pct))

    cards_historico = []
    for ticker, dados in historico_agrupado.items():
        custo_total = dados["custo_total"]
        resultado_total = dados["resultado_total"]
        receita_total = dados["receita_total"]
        quantidade_total = dados["quantidade_total"]
        operacoes = dados["operacoes"]

        if custo_total <= 0 and resultado_total == 0:
            continue

        variacao_pct = (resultado_total / custo_total * 100) if custo_total else 0.0
        detalhes = [
            f"Receita: {format_brl(receita_total)}",
            f"Investimento: {format_brl(custo_total)}",
            f"Quantidade: {quantidade_total}",
            f"Operações: {operacoes}",
        ]
        tooltip = " • ".join(detalhes)

        cards_historico.append(
            {
                "ticker": ticker,
                "variacao_pct": variacao_pct,
                "variacao_rs": resultado_total,
                "tooltip": tooltip,
                "detalhes": detalhes,
            }
        )

    if ordenar_historico_por_valor:
        cards_historico.sort(key=lambda x: x["variacao_rs"], reverse=True)
    else:
        cards_historico.sort(key=lambda x: x["variacao_pct"], reverse=True)
    if cards_historico:
        render_cards(cards_historico)
    else:
        st.info("Não foi possível consolidar os resultados históricos das operações.")
