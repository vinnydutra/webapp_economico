import streamlit as st
import pandas as pd
import yfinance as yf
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Optional, List

from utils import (
    restaurar_usuario_sessao,
    supabase_autenticado,
    formatar_valor,
)


restaurar_usuario_sessao()

st.set_page_config(page_title="Painel Econômico", page_icon="📊", layout="wide")

# Ajuste de margens consistente com o template e as demais páginas.
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# CSS copiado do template para manter os cards "flutuando".
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
    .fin-placeholder {
        color: rgba(255, 255, 255, 0.5);
        font-style: italic;
        text-align: center;
        padding: 12px 0;
    }
    .fin-divider {
        border-top: 1px solid rgba(255, 255, 255, 0.08);
        margin: 14px 0;
    }
    .fin-help-pill {
        position: relative;
        width: 26px;
        height: 26px;
        border-radius: 999px;
        background-color: rgba(255, 255, 255, 0.12);
        color: #fff;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        font-weight: 600;
        cursor: default;
    }
    .fin-help-tooltip {
        position: absolute;
        left: calc(100% + 12px);
        top: 50%;
        transform: translateY(-50%);
        background-color: rgba(22, 22, 30, 0.95);
        color: #fff;
        padding: 12px 16px;
        border-radius: 8px;
        width: 300px;
        font-size: 0.85rem;
        line-height: 1.4;
        opacity: 0;
        visibility: hidden;
        transition: opacity 0.2s ease;
        z-index: 10;
    }
    .fin-help-pill:hover .fin-help-tooltip {
        opacity: 1;
        visibility: visible;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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

# Lógica de logout baseada no template.
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

if "uid" not in st.session_state or not st.session_state.uid:
    st.warning("Usuário não autenticado. Faça login para visualizar o painel.")
    st.stop()

supabase_client = supabase_autenticado()
user_id = st.session_state.uid


def format_percent(value: Optional[float]) -> str:
    if value is None:
        return "N/D"
    return f"{value:+.2f}%".replace(".", ",")


def formatar_variacao_html(valor: Optional[float]) -> str:
    if valor is None:
        return "N/D"
    cor = "#00FF00" if valor >= 0 else "#FF4C4C"
    return f"<span style='color:{cor};'>{format_percent(valor)}</span>"


def gerar_datas_alvo():
    hoje = datetime.now().date()
    ano_atual = hoje.year
    datas = {
        "Dia": "DIA_ESPECIAL",
        "Semana": hoje - pd.Timedelta(days=7),
        "Mês": hoje - pd.Timedelta(days=30),
        "YTD": datetime(ano_atual, 1, 1).date(),
        "12M": hoje - pd.Timedelta(days=365),
    }
    for i in range(1, 6):
        ano_label = ano_atual - i
        datas[str(ano_label)] = datetime(ano_label, 12, 31).date()
    return datas


def estilizar_tabela(df: pd.DataFrame, chaves: List[str], font_size: str = "1.2em"):
    if df.empty:
        return None
    df_estilo = df.copy()
    for col in df_estilo.columns:
        if col not in chaves:
            df_estilo[col] = df_estilo[col].astype(str).str.replace(r"<.*?>", "", regex=True)

    def aplicar_estilo(val):
        if isinstance(val, str) and val.startswith("+"):
            return "color: #00FF00"
        if isinstance(val, str) and val.startswith("-"):
            return "color: #FF4C4C"
        return "color: white"

    subset = [col for col in df_estilo.columns if col not in chaves]
    return (
        df_estilo.style
        .applymap(aplicar_estilo, subset=subset)
        .set_table_styles([{"selector": "table", "props": [("font-size", font_size)]}])
    )


def obter_preco_minerio():
    url = "https://www.indexmundi.com/commodities/?commodity=iron-ore&months=12"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")
        tabela = soup.find("table", {"class": "tblData"})
        if tabela:
            linhas = tabela.find_all("tr")
            if len(linhas) >= 3:
                linha1 = linhas[1].find_all("td")
                linha2 = linhas[2].find_all("td")
                preco1 = float(linha1[1].text.strip().replace(",", ""))
                preco2 = float(linha2[1].text.strip().replace(",", ""))
                return preco1, preco2
        return None, None
    except Exception as e:
        st.error(f"Erro ao obter preço do minério: {e}")
        return None, None


def carregar_variacao_indices():
    indices = {
        "Ibovespa": "^BVSP",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
        "DAX": "^GDAXI",
        "Nikkei": "^N225",
    }
    datas_alvo = gerar_datas_alvo()
    resultado = []
    resumo = {}

    for nome, ticker in indices.items():
        try:
            ativo = yf.Ticker(ticker)
            serie = ativo.history(period="5y")["Close"].dropna()
            if serie.empty:
                continue
            preco_hoje = serie.iloc[-1]
            linha = {"Índice": nome, "Valor": formatar_valor(preco_hoje, moeda=False)}
            variacao_dia = None

            for rotulo, data_ref in datas_alvo.items():
                if rotulo == "Dia":
                    if len(serie) >= 2:
                        preco_passado = serie.iloc[-2]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        variacao_dia = variacao
                        linha[rotulo] = formatar_variacao_html(variacao)
                    else:
                        linha[rotulo] = "N/D"
                    continue
                serie_filtrada = serie[serie.index.date <= data_ref]
                if not serie_filtrada.empty:
                    preco_passado = serie_filtrada.iloc[-1]
                    variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                    linha[rotulo] = formatar_variacao_html(variacao)
                else:
                    linha[rotulo] = "N/D"

            resultado.append(linha)
            resumo[nome] = {"valor": preco_hoje, "variacao_dia": variacao_dia}
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_final = pd.DataFrame(resultado)
    if not df_final.empty:
        colunas = ["Índice", "Valor"] + [col for col in df_final.columns if col not in ["Índice", "Valor"]]
        df_final = df_final[colunas]
    styled = estilizar_tabela(df_final, ["Índice", "Valor"], font_size="1.5em") if not df_final.empty else None
    return {"df": df_final, "styled": styled, "resumo": resumo}


def carregar_moedas():
    pares = {
        "USD/BRL": "USDBRL=X",
        "CAD/BRL": "CADBRL=X",
        "EUR/BRL": "EURBRL=X",
        "GBP/BRL": "GBPBRL=X",
        "BTC/USD": "BTC-USD",
        "ARS/BRL": ("USDBRL=X", "ARS=X"),
        "UYU/BRL": ("USDBRL=X", "UYU=X"),
    }
    datas_alvo = gerar_datas_alvo()
    resultado = []
    resumo = {}

    for nome, ticker in pares.items():
        try:
            linha = {"Par": nome}
            preco_hoje = None
            variacao_dia_resumo = None

            if isinstance(ticker, tuple):
                ativo_div = yf.Ticker(ticker[0])
                ativo_divisor = yf.Ticker(ticker[1])
                div = ativo_div.history(period="5y")["Close"].dropna()
                divisor = ativo_divisor.history(period="5y")["Close"].dropna()
                if div.empty or divisor.empty:
                    linha["Valor"] = "N/D"
                    for rotulo in datas_alvo:
                        linha[rotulo] = "N/D"
                    resultado.append(linha)
                    resumo[nome] = {"valor": None, "variacao_dia": None}
                    continue
                preco_hoje = div.iloc[-1] / divisor.iloc[-1]
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(div) >= 2 and len(divisor) >= 2:
                            preco_passado = div.iloc[-2] / divisor.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            variacao_dia_resumo = variacao
                            linha[rotulo] = formatar_variacao_html(variacao)
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    serie_div = div[div.index.date <= data_ref]
                    serie_divisor = divisor[divisor.index.date <= data_ref]
                    if not serie_div.empty and not serie_divisor.empty:
                        preco_passado = serie_div.iloc[-1] / serie_divisor.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        linha[rotulo] = formatar_variacao_html(variacao)
                    else:
                        linha[rotulo] = "N/D"
            else:
                ativo = yf.Ticker(ticker)
                serie = ativo.history(period="5y")["Close"].dropna()
                if serie.empty:
                    continue
                preco_hoje = serie.iloc[-1]
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(serie) >= 2:
                            preco_passado = serie.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            variacao_dia_resumo = variacao
                            linha[rotulo] = formatar_variacao_html(variacao)
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    serie_filtrada = serie[serie.index.date <= data_ref]
                    if not serie_filtrada.empty:
                        preco_passado = serie_filtrada.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        linha[rotulo] = formatar_variacao_html(variacao)
                    else:
                        linha[rotulo] = "N/D"

            resultado.append(linha)
            resumo[nome] = {"valor": preco_hoje, "variacao_dia": variacao_dia_resumo}
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_final = pd.DataFrame(resultado)
    if not df_final.empty:
        colunas = ["Par", "Valor"] + [col for col in df_final.columns if col not in ["Par", "Valor"]]
        df_final = df_final[colunas]
    styled = estilizar_tabela(df_final, ["Par", "Valor"], font_size="1.15em") if not df_final.empty else None
    return {"df": df_final, "styled": styled, "resumo": resumo}


def carregar_commodities(minerio_precos: Optional[tuple[Optional[float], Optional[float]]] = None):
    commodities = {
        "Brent": "BZ=F",
        "WTI": "CL=F",
        "Ouro": "GC=F",
        "Minério": None,
    }
    datas_alvo = gerar_datas_alvo()
    resultado = []
    resumo = {}

    for nome, ticker in commodities.items():
        try:
            linha = {"Commoditie": nome}
            preco_hoje = None

            if ticker is None:
                preco_atual = minerio_precos[0] if minerio_precos else None
                preco_anterior = minerio_precos[1] if minerio_precos else None
                if preco_atual is not None:
                    linha["Valor"] = f"{preco_atual:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")
                    for rotulo in datas_alvo:
                        if rotulo == "Dia" and preco_anterior is not None and preco_anterior != 0:
                            variacao = ((preco_atual - preco_anterior) / preco_anterior) * 100
                            linha[rotulo] = formatar_variacao_html(variacao)
                        else:
                            linha[rotulo] = "N/D"
                else:
                    linha["Valor"] = "N/D"
                    for rotulo in datas_alvo:
                        linha[rotulo] = "N/D"
            else:
                serie = yf.Ticker(ticker).history(period="5y")["Close"].dropna()
                if serie.empty:
                    continue
                preco_hoje = serie.iloc[-1]
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(serie) >= 2:
                            preco_passado = serie.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            linha[rotulo] = formatar_variacao_html(variacao)
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    serie_filtrada = serie[serie.index.date <= data_ref]
                    if not serie_filtrada.empty:
                        preco_passado = serie_filtrada.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        linha[rotulo] = formatar_variacao_html(variacao)
                    else:
                        linha[rotulo] = "N/D"

            resultado.append(linha)
            resumo[nome] = {"valor": preco_hoje}
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_final = pd.DataFrame(resultado)
    if not df_final.empty:
        colunas = ["Commoditie", "Valor"] + [col for col in df_final.columns if col not in ["Commoditie", "Valor"]]
        df_final = df_final[colunas]
    styled = estilizar_tabela(df_final, ["Commoditie", "Valor"], font_size="1.15em") if not df_final.empty else None
    return {"df": df_final, "styled": styled, "resumo": resumo}


def carregar_setores_sp500():
    setores = {
        "XLY": "XLY", "XLE": "XLE", "XLK": "XLK", "XLI": "XLI", "XLB": "XLB",
        "XLF": "XLF", "XLC": "XLC", "XLRE": "XLRE", "XLP": "XLP", "XLU": "XLU", "XLV": "XLV",
    }
    datas_alvo = gerar_datas_alvo()
    resultado = []

    for nome, ticker in setores.items():
        try:
            ativo = yf.Ticker(ticker)
            serie = ativo.history(period="5y")["Close"].dropna()
            if serie.empty:
                continue
            preco_hoje = serie.iloc[-1]
            linha = {"Setor": nome, "Valor": f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")}

            for rotulo, data_ref in datas_alvo.items():
                if rotulo == "Dia":
                    if len(serie) >= 2:
                        preco_passado = serie.iloc[-2]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        linha[rotulo] = formatar_variacao_html(variacao)
                    else:
                        linha[rotulo] = "N/D"
                    continue
                serie_filtrada = serie[serie.index.date <= data_ref]
                if not serie_filtrada.empty:
                    preco_passado = serie_filtrada.iloc[-1]
                    variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                    linha[rotulo] = formatar_variacao_html(variacao)
                else:
                    linha[rotulo] = "N/D"

            resultado.append(linha)
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_final = pd.DataFrame(resultado)
    if not df_final.empty:
        colunas = ["Setor", "Valor"] + [col for col in df_final.columns if col not in ["Setor", "Valor"]]
        df_final = df_final[colunas]
    styled = estilizar_tabela(df_final, ["Setor", "Valor"], font_size="1.15em") if not df_final.empty else None
    return {"df": df_final, "styled": styled}


def carregar_contexto_painel():
    indices = carregar_variacao_indices()
    moedas = carregar_moedas()
    minerio_atual, minerio_anterior = obter_preco_minerio()
    commodities = carregar_commodities((minerio_atual, minerio_anterior))
    setores = carregar_setores_sp500()

    return {
        "left_card": {
            "title": "Mercados globais",
            "badge": "Índices & Setores",
            "sections": [
                {
                    "title": "Variação dos Índices",
                    "dataframe": indices["styled"],
                },
                {
                    "title": "Setores do S&P 500",
                    "dataframe": setores["styled"],
                    "helper_html": """
                    <div class='fin-help-pill'>?
                        <div class='fin-help-tooltip'>
                            <strong>Legenda:</strong><br>
                            XLY – Consumo Discricionário<br>
                            XLE – Energia<br>
                            XLK – Tecnologia da Informação<br>
                            XLI – Industriais<br>
                            XLB – Materiais<br>
                            XLF – Financeiro<br>
                            XLC – Serviços de Comunicação<br>
                            XLRE – Imobiliário<br>
                            XLP – Consumo Básico<br>
                            XLU – Utilidade Pública<br>
                            XLV – Saúde
                        </div>
                    </div>
                    """,
                },
            ],
        },
        "right_card": {
            "title": "Câmbio e Commodities",
            "badge": "Moedas & Energia",
            "sections": [
                {
                    "title": "Pares de Moeda",
                    "dataframe": moedas["styled"],
                },
                {
                    "title": "Commodities",
                    "dataframe": commodities["styled"],
                },
            ],
        },
    }


def render_header_section():
 
    st.title("Painel Econômico")
    

def render_card_section(section: dict, titulo_card: str):
    with st.container():
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        helper_html = section.get("helper_html")
        helper_markup = helper_html if helper_html else ""
        st.markdown(
            f"<div class='fin-title'><span class='fin-badge'>{titulo_card}</span>{helper_markup}</div>",
            unsafe_allow_html=True,
        )

        descricao = section.get("description")
        if descricao:
            st.markdown(f"<div class='fin-label'>{descricao}</div>", unsafe_allow_html=True)

        dataframe = section.get("dataframe")
        if dataframe is not None:
            st.dataframe(dataframe, width="stretch", hide_index=True)
        else:
            st.markdown("<div class='fin-placeholder'>Não foi possível carregar dados.</div>", unsafe_allow_html=True)

def render_secondary_cards(context: dict):
    ordem_renderizacao = [
        ("left_card", 0, "Variação dos Índices"),
        ("left_card", 1, "Setores do S&P 500"),
        ("right_card", 0, "Câmbio"),
        ("right_card", 1, "Commodities"),
    ]

    for chave_card, indice, titulo in ordem_renderizacao:
        card = context.get(chave_card, {})
        sections = card.get("sections", [])
        if indice >= len(sections):
            continue

        section = sections[indice]
        render_card_section(section, titulo)


def render_painel_layout():
    render_header_section()
    contexto = carregar_contexto_painel()
    render_secondary_cards(contexto)


render_painel_layout()

# Evita lint no import até que dados reais do Supabase sejam usados aqui.
_ = (supabase_client, user_id)
