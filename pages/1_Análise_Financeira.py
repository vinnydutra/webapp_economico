import streamlit as st
import yfinance as yf
from datetime import datetime
import wikipedia
import re
import pandas as pd

import base64
from pathlib import Path

# Helper to convert image to base64 for HTML embedding
def _img_to_base64(path: str) -> str:
    p = Path(path)
    with p.open("rb") as f:
        return base64.b64encode(f.read()).decode()

from finance_calcs import (
    calcular_oscilacao_mes,
    calcular_oscilacao_30d,
    calcular_oscilacao_12m,
    calcular_oscilacao_ano,
    calcular_fcf_yield,
    calcular_componentes_fcf_yield,
    calcular_roic,
    calcular_roic_real,
    calcular_crescimento_receita,
    calcular_crescimento_lucro,
    calcular_div_patrimonio_finance,
    calcular_div_patrimonio,
    calcular_divida_liquida,
    calcular_divida_liquida_conservadora,
    calcular_liquidez_corrente,
)
from st_copy import copy_button

# Restaura o token da sessão para garantir autenticação Supabase antes de qualquer acesso
from utils import restaurar_usuario_sessao
restaurar_usuario_sessao()


st.set_page_config(page_title="Dashboard Financeiro", page_icon="💰", layout="wide")

# Reduz o padding default do container principal para evitar espaço vazio no topo
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Cabeçalho do usuário logado com atalho de logout em layout flexível
usuario_logado = st.session_state.get("usuario", "desconhecido")

st.markdown(f"""
<div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 6px;'>
    <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
    <form action='/?logout=true' method='get'>
        <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
    </form>
</div>
""", unsafe_allow_html=True)

# Limpa a sessão quando o usuário aciona o logout via query param
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "carteira", "ticker", "favoritos_analise", "uid"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

# Utilitários compartilhados (favoritos, formatação e integração Supabase)
from utils import (
    carregar_favoritos,
    adicionar_favorito,
    remover_favorito,
    formatar_valor,
    supabase_autenticado,
    traduzir_recomendacao,
)


def format_number_short(value):
    if value is None:
        return "N/D"
    negativo = value < 0
    valor_abs = abs(value)

    if valor_abs >= 1_000_000_000_000:
        resultado = f"{valor_abs / 1_000_000_000_000:.2f} Tri"
    elif valor_abs >= 1_000_000_000:
        resultado = f"{valor_abs / 1_000_000_000:.2f} Bi"
    elif valor_abs >= 1_000_000:
        resultado = f"{valor_abs / 1_000_000:.2f} Mi"
    else:
        resultado = f"{valor_abs:,.0f}"

    if negativo:
        resultado = f"-{resultado}"
    return resultado.replace(".", ",")


def format_number(value):
    if value is None:
        return "N/D"
    return str(round(value, 2)).replace(".", ",")


def format_number_money(value):
    if value is None:
        return "N/D"
    return f"US$ {format_number_short(value)}"


def format_percent(value):
    if value is None:
        return "N/D"
    return f"{round(value, 2):.2f}".replace(".", ",") + "%"


def safe_calc(func, *args, **kwargs):
    try:
        return func(*args, **kwargs)
    except Exception:
        return None


def safe_financial_value(ticker_obj, label):
    try:
        return ticker_obj.financials.loc[label].iloc[0]
    except Exception:
        return None


def safe_balance_value(ticker_obj, label):
    try:
        return ticker_obj.balance_sheet.loc[label].iloc[0]
    except Exception:
        return None


def safe_financial_value_at(ticker_obj, label, timestamp):
    try:
        return ticker_obj.financials.loc[label, pd.Timestamp(timestamp)]
    except Exception:
        return None


def safe_quarterly_value(ticker_obj, label, date_str):
    try:
        return ticker_obj.quarterly_financials.loc[label, pd.Timestamp(date_str)]
    except Exception:
        return None

def buscar_fundacao(nome_empresa):
    try:
        # Tenta recuperar a página primeiro em português
        wikipedia.set_lang("pt")
        try:
            pagina = wikipedia.page(nome_empresa)
        except wikipedia.exceptions.PageError:
            # Sem resultado em PT, faz fallback para a versão em inglês
            wikipedia.set_lang("en")
            pagina = wikipedia.page(nome_empresa)
        
        conteudo = pagina.content.lower()

        # Busca marcadores textuais que indiquem o trecho com a data
        marcadores = [
            "fundada em", "fundada no", "fundada a", "criada em", "criada no", "criada a",
            "founded in", "founded on", "founded at", "incorporated in", "incorporated on"
        ]

        for marcador in marcadores:
            if marcador in conteudo:
                parte = conteudo.split(marcador)[1]
                trecho = parte.split(".")[0].split("\n")[0].strip()

                # Extrai o primeiro ano de quatro dígitos encontrado no trecho
                ano = re.search(r'\b(17|18|19|20)\d{2}\b', trecho)
                if ano:
                    return ano.group()

                return trecho.capitalize()

        return "Não encontrado"
    except Exception:
        return "Não disponível"




if "uid" in st.session_state and st.session_state.uid:
    if "favoritos_analise" not in st.session_state or not isinstance(st.session_state["favoritos_analise"], list):
        st.session_state["favoritos_analise"] = carregar_favoritos(st.session_state.uid)
else:
    st.warning("Usuário não autenticado. Faça login para acessar a carteira.")
    st.stop()

carteira = st.session_state.get("favoritos_analise", [])

if 'ticker' not in st.session_state:
    st.session_state.ticker = "PETR4.SA"

# Define o ticker atual a partir da sessão e gera lista ordenada de favoritos
ticker = st.session_state.ticker
tickers_ordenados = sorted(carteira)


def render_favoritos_card():
    with st.container():
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        st.markdown(
            "<div class='fin-title'>Favoritos <span class='fin-badge'>Seleção rápida</span></div>",
            unsafe_allow_html=True,
        )

        if tickers_ordenados:
            st.markdown("<div class='fin-pill-group'>", unsafe_allow_html=True)
            botoes_por_linha = 7
            for i in range(0, len(tickers_ordenados), botoes_por_linha):
                linha = tickers_ordenados[i:i + botoes_por_linha]
                cols = st.columns(len(linha))
                for col, ticker_item in zip(cols, linha):
                    with col:
                        if st.button(ticker_item, key=f"botao_topo_{ticker_item}", use_container_width=True):
                            st.session_state.ticker = ticker_item
                            st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='fin-label'>Nenhum favorito cadastrado até o momento.</div>", unsafe_allow_html=True)



def render_card_contexto_vazio(*, ticker_atual: str | None = None, nome_empresa: str | None = None):
    with st.container():
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns([0.5, 1, 1.5, 1])
        with col1:
            st.markdown("<div class='fin-label'>Favoritar</div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-star' style='margin-top:6px;'>", unsafe_allow_html=True)
            estrela_ativa = ticker in carteira
            estrela = "⭐" if estrela_ativa else "☆"
            if st.button(estrela, key="star-button-card2", help="Adicionar ou remover dos Favoritos"):
                if estrela_ativa:
                    carteira.remove(ticker)
                else:
                    carteira.append(ticker)
                st.session_state.favoritos_analise = carteira
                if estrela_ativa:
                    remover_favorito(ticker)
                else:
                    if not supabase_autenticado():
                        st.error("Você não está autenticado. Faça login para favoritar ativos.")
                    else:
                        adicionar_favorito(ticker)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        with col2:
            ticker_display = ticker_atual or st.session_state.get("ticker", "TICKER")
            nome_display = nome_empresa or "Carregando..."
            st.markdown(f"<div class='fin-label'>{nome_display}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='fin-price'>{ticker_display}</div>", unsafe_allow_html=True)
        with col3:
            st.markdown("<div class='fin-label'>Pesquisar ticker</div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-search'>", unsafe_allow_html=True)
            novo_ticker_card2 = st.text_input(
                "Pesquisar ticker card 2",
                ticker_display,
                label_visibility="collapsed",
                key=f"ticker-search-card2-{ticker_display}",
            ).upper()
            st.markdown("</div>", unsafe_allow_html=True)
            if novo_ticker_card2 != ticker_display:
                st.session_state.ticker = novo_ticker_card2
                st.rerun()
        with col4:
            st.markdown("<div class='fin-label' style='text-align:right;'>Dados coletados</div>", unsafe_allow_html=True)
            st.markdown(
                f"<div class='fin-value' style='text-align:right;margin-top:4px;'>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</div>",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"<div style='text-align:right; margin-top:8px;'><a class='fin-link' href='https://finance.yahoo.com/quote/{ticker_display}' target='_blank'>Yahoo! Finance</a></div>",
                unsafe_allow_html=True,
            )


st.markdown("""
<style>
section[data-testid="stSidebar"] h2 {
    margin-bottom: 2px !important;
}
section[data-testid="stSidebar"] .block-container > div {
    margin-top: 0px !important;
    padding-top: 0px !important;
}
section[data-testid="stSidebar"] {
    padding-top: 0px !important;
    margin-top: 0px !important;
}
</style>
""", unsafe_allow_html=True)

# Harmoniza o estilo dos alerts (ex.: st.success) com o tema escuro da sidebar
st.markdown("""
    <style>
    div.stAlert {
        background-color: #31333F !important;  /* Mesma cor da sidebar */
        color: white !important;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        box-shadow: 0px 0px 8px rgba(0,0,0,0.6);
    }
    </style>
    """, unsafe_allow_html=True)


# Paleta e componentes reutilizáveis para cards financeiros
st.markdown(
    """
    <style>
    .fin-card-marker {
        display: none;
    }
    div[data-testid="stVerticalBlock"]:has(.fin-card-marker) {
        background-color: #2B2E3F;
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 18px 22px;
        margin-top: 6px;
        margin-bottom: 12px;
        box-shadow: 0 12px 24px rgba(0, 0, 0, 0.35);
    }
    div[data-testid="stVerticalBlock"]:has(.fin-card-marker) > div:has(> .fin-card-marker) {
        display: none;
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
    .fin-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 8px;
    }
    .fin-label {
        color: #9FA5BD;
        font-size: 0.9rem;
    }
    .fin-value {
        color: #F7F8FF;
        font-weight: 600;
        font-size: 1rem;
        text-align: right;
    }
    .fin-price {
        font-size: 2.4rem;
        font-weight: 600;
        color: #FFFFFF;
    }
    .fin-variation {
        font-size: 1.1rem;
        font-weight: 600;
    }
    .fin-variation--up {
        color: #2EE68C;
    }
    .fin-variation--down {
        color: #FF6B6B;
    }
    .fin-link {
        color: #8FD5FF !important;
        text-decoration: none;
        font-size: 0.85rem;
    }
    .fin-placeholder {
        color: rgba(255, 255, 255, 0.5);
        font-style: italic;
        text-align: center;
        padding: 12px 0;
    }
    .fin-search div[data-testid="stTextInput"] {
        width: 100% !important;
        min-width: 0 !important;
    }
    .fin-divider {
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        margin: 14px 0;
    }
    .pag9-part-wrapper {
        margin-top: 8px;
    }
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
    .fin-pill-group div[data-testid="stButton"] > button {
        background-color: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(255, 255, 255, 0.18);
        border-radius: 999px;
        color: #FFFFFF;
        font-size: 0.75rem;
        min-width: 100%;
    }
    .fin-pill-group div[data-testid="stButton"] > button:hover {
        background-color: rgba(255, 255, 255, 0.18);
        border-color: rgba(255, 255, 255, 0.35);
    }
    .fin-star div[data-testid="stButton"] > button {
        font-size: 24px !important;
        width: 48px;
        height: 48px;
        border-radius: 50% !important;
        padding: 0 !important;
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.12);
    }
    </style>
    """,
    unsafe_allow_html=True
)


render_favoritos_card()


if ticker:
    try:
        acao = yf.Ticker(ticker)
        historico = acao.history(period="1mo")
        info = acao.info
        nome_empresa_topo = info.get("shortName", "Empresa não identificada")
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        dados_ultimos = acao.history(period="5d").dropna()

        # Calcula a data do próximo resultado antes de renderizar o container principal
        proximo_resultado = info.get('nextEarningsDate') or info.get('earningsTimestamp')
        if proximo_resultado:
            try:
                proximo_resultado = datetime.fromtimestamp(proximo_resultado).strftime('%d/%m/%Y')
            except:
                proximo_resultado = str(proximo_resultado)
        else:
            proximo_resultado = "Não disponível"

        moeda = info.get('currency', 'Moeda não disponível')
        preco_atual = None
        fechamento_anterior = "Não disponível"
        variacao_percentual = None
        variacao_classe = ""

        if not dados_ultimos.empty:
            preco_atual = dados_ultimos['Close'].iloc[-1]
            if len(dados_ultimos) >= 2:
                fechamento_anterior = dados_ultimos['Close'].iloc[-2]
            if isinstance(fechamento_anterior, (int, float)) and fechamento_anterior != 0:
                variacao_percentual = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100
                variacao_classe = "fin-variation--up" if variacao_percentual >= 0 else "fin-variation--down"

        abertura = dados_ultimos['Open'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
        if not dados_ultimos.empty:
            volume_acoes = dados_ultimos['Volume'].iloc[-1]
            preco_medio = (dados_ultimos['High'].iloc[-1] + dados_ultimos['Low'].iloc[-1]) / 2
            volume_financeiro = volume_acoes * preco_medio
            volume_formatado = formatar_valor(volume_financeiro)
        else:
            volume_formatado = "Não disponível"
        maxima = dados_ultimos['High'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
        minima = dados_ultimos['Low'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
        media_dia = (maxima + minima) / 2 if maxima != "Não disponível" and minima != "Não disponível" else "Não disponível"

        fechamento_anterior_str = f"{fechamento_anterior:.2f}" if isinstance(fechamento_anterior, (int, float)) else fechamento_anterior
        maxima_str = f"{maxima:.2f}" if isinstance(maxima, (int, float)) else maxima
        abertura_str = f"{abertura:.2f}" if isinstance(abertura, (int, float)) else abertura
        media_dia_str = f"{media_dia:.2f}" if isinstance(media_dia, (int, float)) else media_dia
        minima_str = f"{minima:.2f}" if isinstance(minima, (int, float)) else minima

        render_card_contexto_vazio(ticker_atual=ticker, nome_empresa=nome_empresa_topo)

        painel_cols = st.columns(2)

        # Card de preço atual
        with painel_cols[0]:
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='fin-title'>Preço Atual <span class='fin-badge'>Últimos pregões</span></div>",
                unsafe_allow_html=True,
            )
            if preco_atual is not None:
                st.markdown(f"<div class='fin-price'>{moeda} {preco_atual:.2f}</div>", unsafe_allow_html=True)
                if variacao_percentual is not None:
                    sinal = "+" if variacao_percentual >= 0 else ""
                    st.markdown(
                        f"<div class='fin-variation {variacao_classe}'>{sinal}{variacao_percentual:.2f}%</div>",
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown("<div class='fin-label'>Preço indisponível para o período selecionado.</div>", unsafe_allow_html=True)

            st.markdown("<div class='fin-divider'></div>", unsafe_allow_html=True)

            price_rows = [
                ("Fech. Ant.", f"{moeda} {fechamento_anterior_str}"),
                ("Abertura", f"{moeda} {abertura_str}"),
                ("Volume financeiro", f"{moeda} {volume_formatado}"),
                ("Preço Máx.", f"{moeda} {maxima_str}"),
                ("Preço Méd.", f"{moeda} {media_dia_str}"),
                ("Preço Mín.", f"{moeda} {minima_str}"),
                ("Próx. Resultados", proximo_resultado),
            ]

            for label, value in price_rows:
                st.markdown(
                    f"<div class='fin-row'><span class='fin-label'>{label}</span><span class='fin-value'>{value}</span></div>",
                    unsafe_allow_html=True,
                )

        # Card de consenso
        with painel_cols[1]:
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown(
                "<div class='fin-title'>Consenso das Casas de Análise <span class='fin-badge'>Últimos 12 meses</span></div>",
                unsafe_allow_html=True,
            )
            rec_chart_data = {}
            try:
                preco_base = historico['Close'].iloc[-1]
                preco_alvo = info.get("targetMeanPrice")
                preco_alvo_max = info.get("targetHighPrice")
                preco_alvo_min = info.get("targetLowPrice")
                numero_analistas = info.get("numberOfAnalystOpinions")
                consenso = traduzir_recomendacao(info.get("recommendationKey", ""))

                if preco_alvo and numero_analistas:
                    variacao = ((preco_alvo - preco_base) / preco_base) * 100
                    sinal = "+" if variacao >= 0 else ""
                    cor = "#2EE68C" if variacao >= 0 else "#FF6B6B"
                    consenso_rows = [
                        ("Recomendação geral", consenso),
                        ("Número de analistas", numero_analistas),
                        ("Preço atual", f"{preco_base:.2f}"),
                        ("Preço-alvo médio", f"{preco_alvo:.2f}"),
                        ("Preço-alvo máx.", f"{(preco_alvo_max or 0):.2f}" if preco_alvo_max else "Não informado"),
                        ("Preço-alvo mín.", f"{(preco_alvo_min or 0):.2f}" if preco_alvo_min else "Não informado"),
                    ]
                    for label, value in consenso_rows:
                        st.markdown(
                            f"<div class='fin-row'><span class='fin-label'>{label}</span><span class='fin-value'>{value}</span></div>",
                            unsafe_allow_html=True,
                        )
                    st.markdown(
                        f"<div class='fin-row'><span class='fin-label'>Potencial</span><span class='fin-value' style='color:{cor};'>{sinal}{variacao:.2f}%</span></div>",
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("<div class='fin-label'>❌ Dados de consenso não disponíveis para este ativo.</div>", unsafe_allow_html=True)
            except Exception as e:
                st.markdown(f"<div class='fin-label'>❌ Erro ao obter dados de consenso: {e}</div>", unsafe_allow_html=True)

            # Gráfico de recomendações detalhadas
            resumo_recs = getattr(acao, "recommendations_summary", None)
            if isinstance(resumo_recs, pd.DataFrame) and not resumo_recs.empty:
                ultimo_registro = resumo_recs.iloc[-1]
                mapping = [
                    ("strongBuy", "Strong Buy"),
                    ("buy", "Buy"),
                    ("hold", "Hold"),
                    ("sell", "Sell"),
                    ("strongSell", "Strong Sell"),
                ]
                for key, label in mapping:
                    valor = ultimo_registro.get(key)
                    if valor is not None and valor > 0:
                        rec_chart_data[label] = float(valor)
            else:
                recomendacoes_df = getattr(acao, "recommendations", None)
                if isinstance(recomendacoes_df, pd.DataFrame) and not recomendacoes_df.empty:
                    series = recomendacoes_df["To Grade"].dropna().str.title().tail(50)
                    rec_chart_data = series.value_counts().to_dict()

            if rec_chart_data:
                st.markdown("<div class='fin-divider'></div>", unsafe_allow_html=True)
                color_map = {
                    "Strong Buy": "#2EE68C",
                    "Buy": "#8FD17A",
                    "Hold": "#F4D44D",
                    "Underperform": "#F39C5E",
                    "Sell": "#FF6B6B",
                    "Strong Sell": "#B94B6A",
                }
                order = ["Strong Buy", "Buy", "Hold", "Underperform", "Sell", "Strong Sell"]
                valores = [
                    (label, rec_chart_data[label])
                    for label in order
                    if rec_chart_data.get(label)
                ]
                total = sum(v for _, v in valores)
                if valores and total > 0:
                    segments_html = ""
                    for idx, (label, valor) in enumerate(valores):
                        pct = (valor / total) * 100
                        radius_style = ""
                        if idx == 0:
                            radius_style += "border-top-left-radius:999px;border-bottom-left-radius:999px;"
                        if idx == len(valores) - 1:
                            radius_style += "border-top-right-radius:999px;border-bottom-right-radius:999px;"
                        segments_html += (
                            f"<div class='pag9-part-seg' style='width:{pct:.4f}%;background:{color_map.get(label, '#888')};{radius_style}' "
                            f"title='{label}: {int(valor)} analistas'></div>"
                        )
                    legend_html = "".join(
                        f"<span><span class='pag9-part-dot' style='background:{color_map.get(label, '#888')}'></span>{label} ({int(valor)})</span>"
                        for label, valor in valores
                    )
                    st.markdown(
                        "<div class='pag9-part-wrapper'><div class='pag9-part-bar'>"
                        + segments_html
                        + "</div><div class='pag9-part-legend'>"
                        + legend_html
                        + "</div></div>",
                        unsafe_allow_html=True,
                    )
                    # Gauge images
                    gauge_base_b64 = _img_to_base64("artifacts/gauge_base.png")
                    needle_b64 = _img_to_base64("artifacts/gauge_needle.png")

                    # Determine pointer angle
                    mapa_angulo = {
                        "Compra Forte": -80,
                        "Compra": -45,
                        "Manter": 0,
                        "Venda": 45,
                        "Venda Forte": 80,
                    }
                    angulo_ponteiro = mapa_angulo.get(consenso, 0)

                    gauge_html = f"""
<div style="
    position: relative;
    width: 100%;
    max-width: 420px;
    margin: 16px auto 0 auto;
">
  <img
    src="data:image/png;base64,{gauge_base_b64}"
    style="width: 100%; display: block;"
  />
  <img
    src="data:image/png;base64,{needle_b64}"
    style="
      position: absolute;
      left: 50%;
      bottom: 8%;
      transform: translateX(-50%) rotate({angulo_ponteiro}deg);
      transform-origin: 50% 90%;
      width: 32%;
    "
  />
</div>
"""
                    st.markdown(gauge_html, unsafe_allow_html=True)
            else:
                st.markdown("<div class='fin-label'>⚠️ Sem detalhamento de recomendações disponível.</div>", unsafe_allow_html=True)

        st.markdown("<div style='margin-top: 6px;'></div>", unsafe_allow_html=True)

        # Expander corporativo
        with st.expander("📝 Sobre a Empresa"):
            data_fundacao = buscar_fundacao(info.get('shortName', ticker))

            ceo = "Não disponível"
            officers = info.get('companyOfficers')
            if officers and isinstance(officers, list):
                for officer in officers:
                    if officer.get('title') and 'CEO' in officer.get('title'):
                        ceo = officer.get('name', 'Não disponível')
                        break

            descricao = info.get('longBusinessSummary', 'Descrição não disponível')
            valor_mercado = info.get('marketCap')
            funcionarios = info.get('fullTimeEmployees')
            if funcionarios:
                funcionarios = f"{funcionarios:,}".replace(',', '.')
            else:
                funcionarios = "Não disponível"

            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            detalhamento_cols = st.columns(2)
            with detalhamento_cols[0]:
                detalhes_esq = [
                    ("Empresa", info.get('shortName', 'Não disponível')),
                    ("Setor", info.get('sector', 'Não disponível')),
                    ("País", info.get('country', 'Não disponível')),
                    ("Moeda", info.get('currency', 'Não disponível')),
                    ("Fundação", data_fundacao),
                ]
                for label, value in detalhes_esq:
                    st.markdown(
                        f"<div class='fin-row'><span class='fin-label'>{label}</span><span class='fin-value'>{value}</span></div>",
                        unsafe_allow_html=True,
                    )

            with detalhamento_cols[1]:
                detalhes_dir = [
                    ("Valor de mercado", formatar_valor(valor_mercado)),
                    ("Funcionários", funcionarios),
                    ("CEO", ceo),
                ]
                for label, value in detalhes_dir:
                    st.markdown(
                        f"<div class='fin-row'><span class='fin-label'>{label}</span><span class='fin-value'>{value}</span></div>",
                        unsafe_allow_html=True,
                    )

            st.markdown("<div class='fin-divider'></div>", unsafe_allow_html=True)
            st.markdown(descricao)

        # === Indicadores complementares oriundos da página 6 ===
        ticker_obj = acao
        empresa = info.get("longName", info.get("shortName", "N/D"))
        setor = info.get("sector", "N/D")
        subsetor = info.get("industry", "N/D")
        market_cap = info.get("marketCap")
        valor_firma_info = info.get("enterpriseValue")
        volume_medio = info.get("averageVolume")
        num_acoes = info.get("sharesOutstanding")
        variacao_dia = info.get("regularMarketChangePercent")
        preco_atual_info = info.get("regularMarketPrice")
        volume_financeiro_medio = volume_medio * preco_atual_info if volume_medio and preco_atual_info else None
        data_cotacao_ts = info.get("regularMarketTime")
        data_cotacao = datetime.fromtimestamp(data_cotacao_ts).strftime("%d/%m/%Y %H:%M:%S") if data_cotacao_ts else "N/D"

        ano_atual = datetime.now().year
        variacao_mes = safe_calc(calcular_oscilacao_mes, ticker_obj)
        variacao_30d = safe_calc(calcular_oscilacao_30d, ticker_obj)
        variacao_12m = safe_calc(calcular_oscilacao_12m, ticker_obj)
        variacao_ytd = safe_calc(calcular_oscilacao_ano, ano_atual, ticker_obj)
        variacao_ano_1 = safe_calc(calcular_oscilacao_ano, ano_atual - 1, ticker_obj)
        variacao_ano_2 = safe_calc(calcular_oscilacao_ano, ano_atual - 2, ticker_obj)
        variacao_ano_3 = safe_calc(calcular_oscilacao_ano, ano_atual - 3, ticker_obj)
        variacao_ano_4 = safe_calc(calcular_oscilacao_ano, ano_atual - 4, ticker_obj)

        trailing_pe = info.get("trailingPE")
        price_to_book = info.get("priceToBook")
        price_to_sales = info.get("priceToSalesTrailing12Months")
        ebit_val = safe_financial_value(ticker_obj, "EBIT")
        total_assets = safe_balance_value(ticker_obj, "Total Assets")
        p_ebit = market_cap / ebit_val if market_cap and ebit_val else None
        p_ativos = market_cap / total_assets if market_cap and total_assets else None
        valor_ebitda = info.get("ebitda")
        ev_ebit = valor_firma_info / ebit_val if valor_firma_info and ebit_val else None
        ev_ebitda = valor_firma_info / valor_ebitda if valor_firma_info and valor_ebitda else None

        ativo_circulante_bs = safe_balance_value(ticker_obj, "Current Assets")
        passivo_circulante_bs = safe_balance_value(ticker_obj, "Current Liabilities")
        capital_giro = (ativo_circulante_bs - passivo_circulante_bs) if (ativo_circulante_bs is not None and passivo_circulante_bs is not None) else None
        p_cap_giro = market_cap / capital_giro if market_cap and capital_giro else None

        contas_a_receber = safe_balance_value(ticker_obj, "Accounts Receivable")
        estoques = safe_balance_value(ticker_obj, "Inventory")
        fornecedores = safe_balance_value(ticker_obj, "Accounts Payable")
        cap_giro_operacional = None
        if contas_a_receber is not None and estoques is not None and fornecedores is not None:
            cap_giro_operacional = contas_a_receber + estoques - fornecedores
        p_cap_giro_op = market_cap / cap_giro_operacional if market_cap and cap_giro_operacional else None

        roe = info.get("returnOnEquity")
        roic = safe_calc(calcular_roic, ticker_obj)
        roic_real = safe_calc(calcular_roic_real, ticker_obj)
        ebit_ativo = (ebit_val / total_assets * 100) if ebit_val and total_assets else None
        roa = info.get("returnOnAssets")
        gross_margin = info.get("grossMargins")
        operating_margin = info.get("operatingMargins")
        profit_margin = info.get("profitMargins")
        ebitda_margin = info.get("ebitdaMargins")

        crescimento_receita = safe_calc(calcular_crescimento_receita, ticker_obj)
        crescimento_lucro = safe_calc(calcular_crescimento_lucro, ticker_obj)
        receitas_anuais = {}
        lucros_anuais = {}
        for offset in [1, 2, 3]:
            ano = ano_atual - offset
            receitas_anuais[ano] = safe_financial_value_at(ticker_obj, "Total Revenue", f"{ano}-12-31")
            lucros_anuais[ano] = safe_financial_value_at(ticker_obj, "Net Income", f"{ano}-12-31")

        receitas_trimestrais = {}
        lucros_trimestrais = {}
        for trimestre, data in enumerate(["03-31", "06-30", "09-30"], start=1):
            chave = f"{ano_atual}Q{trimestre}"
            receitas_trimestrais[chave] = safe_quarterly_value(ticker_obj, "Total Revenue", f"{ano_atual}-{data}")
            lucros_trimestrais[chave] = safe_quarterly_value(ticker_obj, "Net Income", f"{ano_atual}-{data}")

        div_patrimonio = safe_calc(calcular_div_patrimonio_finance, ticker_obj)
        div_patrimonio_total = safe_calc(calcular_div_patrimonio, ticker_obj)
        divida_bruta = info.get("totalDebt")
        divida_liquida = safe_calc(calcular_divida_liquida, ticker_obj)
        div_liquida_cons = safe_calc(calcular_divida_liquida_conservadora, ticker_obj)
        liquidez_corrente = safe_calc(calcular_liquidez_corrente, ticker_obj)
        disponibilidades = info.get("totalCash")
        patrimonio_liquido = None
        for key in ["Common Stock Equity", "Stockholders Equity", "Total Equity"]:
            valor_tmp = safe_balance_value(ticker_obj, key)
            if valor_tmp:
                patrimonio_liquido = valor_tmp
                break

        ativo_total = safe_balance_value(ticker_obj, "Total Assets")
        ativo_circulante = safe_balance_value(ticker_obj, "Current Assets")
        book_value = info.get("bookValue")
        trailing_eps = info.get("trailingEps")

        receita_total = safe_financial_value(ticker_obj, "Total Revenue")
        giro_ativos = (receita_total / total_assets) if receita_total and total_assets else None
        fcf_yield = safe_calc(calcular_fcf_yield, ticker_obj)
        calcular_componentes_fcf_yield(ticker_obj)  # executa por consistência com pag6
        volume_medio_2m = None
        try:
            historico_60d = ticker_obj.history(period="60d")
            volume_medio_2m = historico_60d["Volume"].mean()
        except Exception:
            volume_medio_2m = None

        # --- Card: Oscilações de Preço ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>📊 Oscilações de Preço</div>", unsafe_allow_html=True)
            osc_col1, osc_col2, osc_col3 = st.columns(3)
            def render_variacao(col, label, valor):
                if valor is not None:
                    col.markdown(f"🟢 **{label}:** {valor:.2f}%".replace(".", ","))
                else:
                    col.markdown(f"🔴 **{label}:** N/D")
            render_variacao(osc_col1, "Dia", variacao_dia)
            render_variacao(osc_col1, "Mês", variacao_mes)
            render_variacao(osc_col1, "30 dias", variacao_30d)
            render_variacao(osc_col2, "12 meses", variacao_12m)
            render_variacao(osc_col2, f"YTD ({ano_atual})", variacao_ytd)
            render_variacao(osc_col2, f"{ano_atual - 1}", variacao_ano_1)
            render_variacao(osc_col3, f"{ano_atual - 2}", variacao_ano_2)
            render_variacao(osc_col3, f"{ano_atual - 3}", variacao_ano_3)
            render_variacao(osc_col3, f"{ano_atual - 4}", variacao_ano_4)

        # --- Card: Dados da Empresa ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>🧾 Dados da Empresa</div>", unsafe_allow_html=True)
            dados_cols = st.columns(3)
            with dados_cols[0]:
                st.markdown(f"🟢 **Empresa:** {empresa}")
                st.markdown(f"🟢 **Setor:** {setor}")
                st.markdown(f"🟢 **Subsetor:** {subsetor}")
            with dados_cols[1]:
                st.markdown(f"🟢 **Ticker:** {ticker}")
                st.markdown(f"🟢 **Valor de Mercado:** {format_number_money(market_cap)}" if market_cap else "🔴 **Valor de Mercado:** N/D")
                st.markdown(f"🟢 **Valor da Firma:** {format_number_money(valor_firma_info)}" if valor_firma_info else "🔴 **Valor da Firma:** N/D")
            with dados_cols[2]:
                st.markdown(f"🟢 **Volume Médio:** {format_number_short(volume_medio)}/dia" if volume_medio else "🔴 **Volume Médio:** N/D")
                st.markdown(f"🟢 **Ações Emitidas:** {format_number_short(num_acoes)}" if num_acoes else "🔴 **Ações Emitidas:** N/D")
                st.markdown(f"🟢 **Vol. Fin. Médio:** {format_number_money(volume_financeiro_medio)}" if volume_financeiro_medio else "🔴 **Vol. Fin. Médio:** N/D")

        # --- Card: Valuation ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>📊 Valuation</div>", unsafe_allow_html=True)
            val_cols = st.columns(3)
            with val_cols[0]:
                st.markdown(f"🟢 **P/L:** {format_number(trailing_pe)}" if trailing_pe is not None else "🔴 **P/L:** N/D")
                st.markdown(f"🟢 **P/VP:** {format_number(price_to_book)}" if price_to_book is not None else "🔴 **P/VP:** N/D")
                st.markdown(f"🟢 **P/EBIT:** {format_number(p_ebit)}" if p_ebit is not None else "🔴 **P/EBIT:** N/D")
            with val_cols[1]:
                st.markdown(f"🟢 **P/Ativos:** {format_number(p_ativos)}" if p_ativos is not None else "🔴 **P/Ativos:** N/D")
                st.markdown(f"🟢 **PSR:** {format_number(price_to_sales)}" if price_to_sales is not None else "🔴 **PSR:** N/D")
                st.markdown(f"🟢 **EV/EBIT:** {format_number(ev_ebit)}" if ev_ebit is not None else "🔴 **EV/EBIT:** N/D")
            with val_cols[2]:
                st.markdown(f"🟢 **EV/EBITDA:** {format_number(ev_ebitda)}" if ev_ebitda is not None else "🔴 **EV/EBITDA:** N/D")
                st.markdown(f"🟢 **P/Cap. Giro:** {format_number(p_cap_giro)}" if p_cap_giro is not None else "🔴 **P/Cap. Giro:** N/D")
                st.markdown(f"🟢 **P/Cap. Giro Operacional:** {format_number(p_cap_giro_op)}" if p_cap_giro_op is not None else "🔴 **P/Cap. Giro Operacional:** N/D")

        # --- Card: Rentabilidade ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>💸 Rentabilidade</div>", unsafe_allow_html=True)
            rent_cols = st.columns(3)
        with rent_cols[0]:
            st.markdown(f"🟢 **ROE:** {format_percent(roe * 100)}" if roe is not None else "🔴 **ROE:** N/D")
            st.markdown(f"🟢 **ROIC:** {format_percent(roic)}" if roic is not None else "🔴 **ROIC:** N/D")
            st.markdown(f"🟢 **ROIC Real:** {format_percent(roic_real)}" if roic_real is not None else "🔴 **ROIC Real:** N/D")
        with rent_cols[1]:
            st.markdown(f"🟢 **EBIT/Ativo:** {format_percent(ebit_ativo)}" if ebit_ativo is not None else "🔴 **EBIT/Ativo:** N/D")
            st.markdown(f"🟢 **ROA:** {format_percent(roa * 100)}" if roa is not None else "🔴 **ROA:** N/D")
            st.markdown(f"🟢 **Margem Bruta:** {format_percent(gross_margin * 100)}" if gross_margin is not None else "🔴 **Margem Bruta:** N/D")
        with rent_cols[2]:
            st.markdown(f"🟢 **Margem EBIT:** {format_percent(operating_margin * 100)}" if operating_margin is not None else "🔴 **Margem EBIT:** N/D")
            st.markdown(f"🟢 **Marg. Líquida:** {format_percent(profit_margin * 100)}" if profit_margin is not None else "🔴 **Marg. Líquida:** N/D")
            st.markdown(f"🟢 **Margem EBITDA:** {format_percent(ebitda_margin * 100)}" if ebitda_margin is not None else "🔴 **Margem EBITDA:** N/D")

        # --- Card: Crescimento ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>📈 Crescimento</div>", unsafe_allow_html=True)
            cresc_cols = st.columns(3)
        with cresc_cols[0]:
            st.markdown(f"🟢 **Cresc. Receita (5 anos):** {format_percent(crescimento_receita) if crescimento_receita is not None else '🔴 **Cresc. Receita (5 anos):** N/D'}")
            st.markdown(f"🟢 **Cresc. Lucro (5 anos):** {format_percent(crescimento_lucro) if crescimento_lucro is not None else '🔴 **Cresc. Lucro (5 anos):** N/D'}")
            for ano, valor in receitas_anuais.items():
                st.markdown(f"{'🟢' if valor else '🔴'} **Receita {ano}:** {format_number_money(valor) if valor else 'N/D'}")
        with cresc_cols[1]:
            for ano, valor in lucros_anuais.items():
                st.markdown(f"{'🟢' if valor else '🔴'} **Lucro {ano}:** {format_number_money(valor) if valor else 'N/D'}")
            for chave in ["Q1", "Q2"]:
                key = f"{ano_atual}{chave}"
                valor = receitas_trimestrais.get(key)
                st.markdown(f"{'🟢' if valor else '🔴'} **Receita {chave} {ano_atual}:** {format_number_money(valor) if valor else 'N/D'}")
        with cresc_cols[2]:
            for chave in ["Q1", "Q2"]:
                key = f"{ano_atual}{chave}"
                valor = lucros_trimestrais.get(key)
                st.markdown(f"{'🟢' if valor else '🔴'} **Lucro {chave} {ano_atual}:** {format_number_money(valor) if valor else 'N/D'}")
            receita_q3 = receitas_trimestrais.get(f"{ano_atual}Q3")
            lucro_q3 = lucros_trimestrais.get(f"{ano_atual}Q3")
            st.markdown(f"{'🟢' if receita_q3 else '🔴'} **Receita Q3 {ano_atual}:** {format_number_money(receita_q3) if receita_q3 else 'N/D'}")
            st.markdown(f"{'🟢' if lucro_q3 else '🔴'} **Lucro Q3 {ano_atual}:** {format_number_money(lucro_q3) if lucro_q3 else 'N/D'}")

        # --- Card: Endividamento & Estrutura ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>📉 Endividamento & Estrutura</div>", unsafe_allow_html=True)
            end_cols = st.columns(3)
        with end_cols[0]:
            st.markdown(f"{'🟢' if div_patrimonio_total is not None else '🔴'} **Dív/Patrimônio (Total):** {format_number(div_patrimonio_total) if div_patrimonio_total is not None else 'N/D'}")
            st.markdown(f"{'🟢' if div_patrimonio is not None else '🔴'} **Dív/Patrimônio (Financeiro):** {format_number(div_patrimonio) if div_patrimonio is not None else 'N/D'}")
            st.markdown(f"{'🟢' if divida_bruta else '🔴'} **Dívida Bruta:** {format_number_money(divida_bruta) if divida_bruta else 'N/D'}")
        with end_cols[1]:
            st.markdown(f"{'🟢' if divida_liquida is not None else '🔴'} **Dívida Líq. (Ampla):** {format_number_money(divida_liquida) if divida_liquida is not None else 'N/D'}")
            st.markdown(f"{'🟢' if div_liquida_cons is not None else '🔴'} **Dívida Líq. (Finan.):** {format_number_money(div_liquida_cons) if div_liquida_cons is not None else 'N/D'}")
            st.markdown(f"{'🟢' if patrimonio_liquido else '🔴'} **Patrimônio Líquido:** {format_number_money(patrimonio_liquido) if patrimonio_liquido else 'N/D'}")
        with end_cols[2]:
            st.markdown(f"{'🟢' if liquidez_corrente is not None else '🔴'} **Liquidez Corrente:** {format_number(liquidez_corrente) if liquidez_corrente is not None else 'N/D'}")
            st.markdown(f"{'🟢' if disponibilidades else '🔴'} **Disponibilidades:** {format_number_money(disponibilidades) if disponibilidades else 'N/D'}")

        # --- Card: Balanço Patrimonial ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>🏦 Balanço Patrimonial</div>", unsafe_allow_html=True)
            bal_cols = st.columns(3)
        with bal_cols[0]:
            st.markdown(f"{'🟢' if ativo_total else '🔴'} **Ativo Total:** {format_number_money(ativo_total) if ativo_total else 'N/D'}")
            st.markdown(f"{'🟢' if ativo_circulante else '🔴'} **Ativo Circulante:** {format_number_money(ativo_circulante) if ativo_circulante else 'N/D'}")
            st.markdown(f"{'🟢' if valor_firma_info else '🔴'} **Enterprise Value:** {format_number_money(valor_firma_info) if valor_firma_info else 'N/D'}")
        with bal_cols[1]:
            st.markdown(f"{'🟢' if book_value else '🔴'} **VPA:** {format_number(book_value) if book_value else 'N/D'}")
            st.markdown(f"{'🟢' if market_cap else '🔴'} **Market Cap:** {format_number_money(market_cap) if market_cap else 'N/D'}")
            st.markdown(f"{'🟢' if trailing_eps else '🔴'} **LPA:** {format_number(trailing_eps) if trailing_eps else 'N/D'}")
        with bal_cols[2]:
            st.markdown(f"{'🟢' if trailing_eps else '🔴'} **Trailing EPS:** {format_number(trailing_eps) if trailing_eps else 'N/D'}")
            st.markdown(f"{'🟢' if valor_ebitda else '🔴'} **EBITDA (últ. 12m):** {format_number_money(valor_ebitda) if valor_ebitda else 'N/D'}")

        # --- Card: Eficiência Operacional ---
        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>⚙️ Eficiência Operacional</div>", unsafe_allow_html=True)
            efic_cols = st.columns(3)
        with efic_cols[0]:
            st.markdown(f"{'🟢' if giro_ativos else '🔴'} **Giro dos Ativos:** {format_number(giro_ativos) if giro_ativos else 'N/D'}")
            st.markdown(f"{'🟢' if fcf_yield is not None else '🔴'} **FCF Yield:** {format_percent(fcf_yield) if fcf_yield is not None else 'N/D'}")
        with efic_cols[1]:
            st.markdown(f"{'🟢' if volume_medio else '🔴'} **Volume Médio (3m):** {format_number_short(volume_medio) if volume_medio else 'N/D'}")
        with efic_cols[2]:
            st.markdown(f"{'🟢' if volume_medio_2m else '🔴'} **Volume Médio (2m):** {format_number_short(volume_medio_2m) if volume_medio_2m else 'N/D'}")

        # --- Painel consolidado com botão de cópia ---
        mensagem_inicial = """📋 Instruções para Interpretação:

Os dados a seguir foram extraídos automaticamente do **WebApp Econômico**, desenvolvido em Streamlit com integração à API do Yahoo Finance. Eles representam um **painel completo de indicadores fundamentalistas e técnicos** de uma ação negociada na bolsa (ticker especificado logo no início do painel).

As informações incluem: oscilações de preço em múltiplos períodos, dados cadastrais da empresa, múltiplos de valuation, rentabilidade, crescimento histórico de receita e lucro, estrutura de endividamento, composição do balanço patrimonial e indicadores de eficiência operacional.  
Cada valor é atualizado dinamicamente com base em dados públicos e reflete o momento da coleta no WebApp.

Use os dados abaixo como **insumo para análises fundamentalistas, geração de relatórios financeiros, sugestões de investimento, ou respostas explicativas**. Considere o contexto do ativo e os padrões do setor ao interpretá-los.
"""

        mensagem_final = """
Com base nesses dados, sua tarefa é analisar e interpretar o painel como se você fosse o maior economista do mundo, dotado de doutorado em Economia, Finanças, Contabilidade e Gestão de Investimentos. Sua conduta deve ser didática, precisa e objetiva — como a de um professor altamente experiente explicando para um investidor de nível intermediário.  
Use uma linguagem acessível, mas nunca simplista. Sua análise deve combinar fundamentos quantitativos com interpretações qualitativas, contextualizando cada indicador dentro do setor, do histórico da empresa e das tendências macroeconômicas.  
Dê atenção especial a anomalias, divergências entre indicadores, sinais de força ou fraqueza financeira e perspectivas de valorização.  
Não repita os dados — eles já estão no prompt. Foque em transformá-los em conclusões práticas, recomendações de ação, ou insights estratégicos.  
Você pode usar listas, subtítulos ou blocos estruturados para facilitar a leitura. Nunca fale como um chatbot. Fale como o melhor analista econômico do planeta, capaz de unir técnica, clareza e visão de futuro.
"""

        painel_texto = f"""{mensagem_inicial}🎯 Empresa analisada: **{ticker}** ({empresa})
📊 Oscilações de Preço
Dia: {format_percent(variacao_dia) if variacao_dia is not None else 'N/D'}
Mês: {format_percent(variacao_mes) if variacao_mes is not None else 'N/D'}
30 dias: {format_percent(variacao_30d) if variacao_30d is not None else 'N/D'}
12 meses: {format_percent(variacao_12m) if variacao_12m is not None else 'N/D'}
YTD ({ano_atual}): {format_percent(variacao_ytd) if variacao_ytd is not None else 'N/D'}
{ano_atual - 1}: {format_percent(variacao_ano_1) if variacao_ano_1 is not None else 'N/D'}
{ano_atual - 2}: {format_percent(variacao_ano_2) if variacao_ano_2 is not None else 'N/D'}
{ano_atual - 3}: {format_percent(variacao_ano_3) if variacao_ano_3 is not None else 'N/D'}
{ano_atual - 4}: {format_percent(variacao_ano_4) if variacao_ano_4 is not None else 'N/D'}
🧾 Dados da Empresa
Empresa: {empresa}
Setor: {setor}
Subsetor: {subsetor}
Ticker: {ticker}
Valor de Mercado: {format_number_money(market_cap)}
Valor da Firma: {format_number_money(valor_firma_info)}
Volume Médio: {format_number_short(volume_medio) if volume_medio else 'N/D'}/dia
Ações Emitidas: {format_number_short(num_acoes) if num_acoes else 'N/D'}
Vol. Fin. Médio: {format_number_money(volume_financeiro_medio)}
📊 Valuation
P/L: {format_number(trailing_pe)}
P/VP: {format_number(price_to_book)}
P/EBIT: {format_number(p_ebit)}
P/Ativos: {format_number(p_ativos)}
PSR: {format_number(price_to_sales)}
EV/EBIT: {format_number(ev_ebit)}
EV/EBITDA: {format_number(ev_ebitda)}
P/Cap. Giro: {format_number(p_cap_giro)}
P/Cap. Giro Operacional: {format_number(p_cap_giro_op)}
💸 Rentabilidade
ROE: {format_percent(roe * 100) if roe is not None else 'N/D'}
ROIC: {format_percent(roic)}
ROIC Real: {format_percent(roic_real)}
EBIT / Ativo: {format_percent(ebit_ativo)}
ROA: {format_percent(roa * 100) if roa is not None else 'N/D'}
Margem Bruta: {format_percent(gross_margin * 100) if gross_margin is not None else 'N/D'}
Margem EBIT: {format_percent(operating_margin * 100) if operating_margin is not None else 'N/D'}
Marg. Líquida: {format_percent(profit_margin * 100) if profit_margin is not None else 'N/D'}
Margem EBITDA: {format_percent(ebitda_margin * 100) if ebitda_margin is not None else 'N/D'}
📈 Crescimento
Cresc. Receita (5 anos): {format_percent(crescimento_receita)}
Cresc. Lucro (5 anos): {format_percent(crescimento_lucro)}
Receita {ano_atual - 1}: {format_number_money(receitas_anuais.get(ano_atual - 1))}
Lucro {ano_atual - 1}: {format_number_money(lucros_anuais.get(ano_atual - 1))}
Receita {ano_atual - 2}: {format_number_money(receitas_anuais.get(ano_atual - 2))}
Lucro {ano_atual - 2}: {format_number_money(lucros_anuais.get(ano_atual - 2))}
Receita {ano_atual - 3}: {format_number_money(receitas_anuais.get(ano_atual - 3))}
Lucro {ano_atual - 3}: {format_number_money(lucros_anuais.get(ano_atual - 3))}
Receita Q1 {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q1'))}
Lucro Q1 {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q1'))}
Receita Q2 {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q2'))}
Lucro Q2 {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q2'))}
Receita Q3 {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q3'))}
Lucro Q3 {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q3'))}
📉 Endividamento & Estrutura
Dív/Patrimônio (Total): {format_number(div_patrimonio_total)}
Dív/Patrimônio (Financeiro): {format_number(div_patrimonio)}
Dívida Bruta: {format_number_money(divida_bruta)}
Dívida Líq. (Ampla): {format_number_money(divida_liquida)}
Dívida Líq. (Finan.): {format_number_money(div_liquida_cons)}
Patrimônio Líquido: {format_number_money(patrimonio_liquido)}
Liquidez Corrente: {format_number(liquidez_corrente)}
Disponibilidades: {format_number_money(disponibilidades)}
🏦 Balanço Patrimonial
Ativo Total: {format_number_money(ativo_total)}
Ativo Circulante: {format_number_money(ativo_circulante)}
Enterprise Value: {format_number_money(valor_firma_info)}
VPA: {format_number(book_value)}
Market Cap: {format_number_money(market_cap)}
LPA: {format_number(trailing_eps)}
EBITDA (últ. 12m): {format_number_money(valor_ebitda)}
⚙️ Eficiência Operacional
Giro dos Ativos: {format_number(giro_ativos)}
FCF Yield: {format_percent(fcf_yield)}
Volume Médio (3m): {format_number_short(volume_medio) if volume_medio else 'N/D'}
Volume Médio (2m): {format_number_short(volume_medio_2m) if volume_medio_2m else 'N/D'}"""

        painel_texto = f"{painel_texto}\n\n---\n📌 A seguir, sua tarefa:\n{mensagem_final}"
        painel_texto += """
Se algum campo apresentar "N/D" (não disponível), realize uma busca ativa na internet para preenchê-lo. Utilize apenas fontes públicas, confiáveis e atualizadas (como Yahoo Finance, B3, SEC.gov, ou relatórios financeiros oficiais). Isso permitirá análises mais completas e relevantes.
"""

        painel_texto += """

ℹ️ Glossário Rápido:
ROIC = Retorno sobre o Capital Investido  
ROE = Retorno sobre o Patrimônio  
ROA = Retorno sobre Ativos  
FCF = Fluxo de Caixa Livre  
EBIT = Lucro Antes de Juros e Tributos  
EBITDA = Lucros antes de Juros, Impostos, Depreciação e Amortização  
PSR = Preço sobre Receita  
EV/EBIT = Valor da Firma sobre Lucro Operacional  
VPA = Valor Patrimonial por Ação  
LPA = Lucro por Ação
"""

        with st.container():
            st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
            st.markdown("<div class='fin-title'>📋 Copiar Painel Consolidado</div>", unsafe_allow_html=True)
            copy_button(
                painel_texto,
                tooltip="Copiar painel completo",
            )

    except Exception as e:
        st.error(f"❌ Não foi possível obter dados para {ticker}. Verifique se o ticker está correto.")
        from difflib import get_close_matches
        tickers_disponiveis = st.session_state.favoritos_analise
        sugestoes = get_close_matches(ticker, tickers_disponiveis, n=3, cutoff=0.4)

        if sugestoes:
            st.markdown("#### 🔍 Você quis dizer:")
            for sugestao in sugestoes:
                if st.button(sugestao, key=f"sugestao_{sugestao}"):
                    st.session_state.ticker = sugestao
                    st.rerun()


# Verificação de segurança complementar: garante que os botões só renderizem quando favoritos estiverem prontos
if "favoritos_analise" not in st.session_state or not isinstance(st.session_state.favoritos_analise, list):
    st.warning("⏳ Carregando carteira...")
    st.stop()
