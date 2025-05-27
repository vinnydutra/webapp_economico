import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import streamlit as st
import yfinance as yf
from datetime import datetime
from utils import obter_usuario

def obter_preco_minerio():
    url = "https://www.indexmundi.com/commodities/?commodity=iron-ore&months=12"
    headers = {
        "User-Agent": "Mozilla/5.0"
    }

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
        print(f"Erro ao obter preço do minério: {e}")
        return None, None

def formatar_valor(valor, moeda=True, casas=2):
    if valor is None:
        return "Não disponível"
    formato = f"{{:,.{casas}f}}"
    if moeda:
        return "R$ " + formato.format(valor).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        return formato.format(valor).replace(",", "X").replace(".", ",").replace("X", ".")

# ✅ Configuração da página
st.set_page_config(page_title="Painel Econômico", page_icon="📈", layout="wide")

# ✅ Persistência do usuário via URL
query_params = st.query_params
if "usuario" in query_params:
    st.session_state.usuario = query_params["usuario"]

usuario = obter_usuario()
st.query_params["usuario"] = usuario

# ✅ Botão Logout no topo da sidebar
with st.sidebar:
    if st.button("🚪 Logout"):
        for chave in ["usuario", "carteira", "ticker"]:
            if chave in st.session_state:
                del st.session_state[chave]
        st.query_params.clear()
        st.rerun()

with st.expander("🌍 Índices e Bolsas", expanded=True):
    st.markdown("")
    ibov = yf.Ticker("^BVSP")
    data = ibov.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                1. Ibovespa – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("1. Ibovespa – Dados não disponíveis")

    sp500 = yf.Ticker("^GSPC")
    data = sp500.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                2. S&P 500 – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("2. S&P 500 – Dados não disponíveis")

    nasdaq = yf.Ticker("^IXIC")
    data = nasdaq.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                3. Nasdaq – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("3. Nasdaq – Dados não disponíveis")

    dowjones = yf.Ticker("^DJI")
    data = dowjones.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                4. Dow Jones – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("4. Dow Jones – Dados não disponíveis")

    dax = yf.Ticker("^GDAXI")
    data = dax.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                5. DAX – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("5. DAX – Dados não disponíveis")

    nikkei = yf.Ticker("^N225")
    data = nikkei.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                6. Nikkei – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("6. Nikkei – Dados não disponíveis")

with st.expander("💱 Câmbio e Moedas", expanded=True):
    st.markdown("")
    dolar = yf.Ticker("USDBRL=X")
    data = dolar.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                1. Dólar (USD/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("1. Dólar (USD/BRL) – Dados não disponíveis")

    # Dólar Canadense (CAD/BRL)
    cad = yf.Ticker("CADBRL=X")
    data = cad.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                2. Dólar Canadense (CAD/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("2. Dólar Canadense (CAD/BRL) – Dados não disponíveis")

    euro = yf.Ticker("EURBRL=X")
    data = euro.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                3. Euro (EUR/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("3. Euro (EUR/BRL) – Dados não disponíveis")

    # Libra Esterlina (GBP/BRL)
    libra = yf.Ticker("GBPBRL=X")
    data = libra.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                4. Libra Esterlina (GBP/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("4. Libra Esterlina (GBP/BRL) – Dados não disponíveis")

    bitcoin = yf.Ticker("BTC-USD")
    data = bitcoin.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                5. Bitcoin (USD) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("5. Bitcoin (USD) – Dados não disponíveis")

    # Peso Argentino (ARS/BRL) - cálculo indireto via USD
    usd_brl = yf.Ticker("USDBRL=X")
    ars_usd = yf.Ticker("ARS=X")

    data_usd_brl = usd_brl.history(period="5d")["Close"].dropna().tail(2)
    data_ars_usd = ars_usd.history(period="5d")["Close"].dropna().tail(2)

    if len(data_usd_brl) == 2 and len(data_ars_usd) == 2:
        fechamento_anterior = data_usd_brl.iloc[0] / data_ars_usd.iloc[0]
        preco_atual = data_usd_brl.iloc[1] / data_ars_usd.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, casas=5)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                6. Peso Argentino (ARS/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("6. Peso Argentino (ARS/BRL) – Dados não disponíveis")

    # Peso Uruguaio (UYU/BRL) - cálculo indireto via USD
    usd_brl = yf.Ticker("USDBRL=X")
    uyu_usd = yf.Ticker("UYU=X")

    data_usd_brl = usd_brl.history(period="5d")["Close"].dropna().tail(2)
    data_uyu_usd = uyu_usd.history(period="5d")["Close"].dropna().tail(2)

    if len(data_usd_brl) == 2 and len(data_uyu_usd) == 2:
        fechamento_anterior = data_usd_brl.iloc[0] / data_uyu_usd.iloc[0]
        preco_atual = data_usd_brl.iloc[1] / data_uyu_usd.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, casas=5)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                7. Peso Uruguaio (UYU/BRL) – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("7. Peso Uruguaio (UYU/BRL) – Dados não disponíveis")

with st.expander("🛢️ Commodities", expanded=True):
    st.markdown("")
    brent = yf.Ticker("BZ=F")
    data = brent.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                1. Petróleo Brent – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("1. Petróleo Brent – Dados não disponíveis")

    wti = yf.Ticker("CL=F")
    data = wti.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                2. Petróleo WTI – {preco_formatado} 
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("2. Petróleo WTI – Dados não disponíveis")

    preco_atual, fechamento_anterior = obter_preco_minerio()

    if preco_atual and fechamento_anterior:
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual, moeda=False)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                3. Minério de Ferro – {preco_formatado} USD/ton
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("3. Minério de Ferro – Dados não disponíveis no momento.")

    # Ouro
    ouro = yf.Ticker("GC=F")
    data = ouro.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

        st.markdown(
            f"""
            <div style='font-size: 20px;'>
                4. Ouro – {preco_formatado} USD/oz
                <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    else:
        st.markdown("4. Ouro – Dados não disponíveis")

# Novo bloco: Setores do S&P 500
with st.expander("🏛️ Setores do S&P 500", expanded=True):
    st.markdown("")

    setores = {
        "1. XLY – Consumer Discretionary (Consumo Discricionário)": "XLY",
        "2. XLE – Energy (Energia)": "XLE",
        "3. XLK – Technology (Tecnologia da Informação)": "XLK",
        "4. XLI – Industrials (Industriais)": "XLI",
        "5. XLB – Materials (Materiais)": "XLB",
        "6. XLF – Financials (Financeiro)": "XLF",
        "7. XLC – Communication Services (Serviços de Comunicação)": "XLC",
        "8. XLRE – Real Estate (Imobiliário)": "XLRE",
        "9. XLP – Consumer Staples (Consumo Básico)": "XLP",
        "10. XLU – Utilities (Serviços Públicos / Utilidade Pública)": "XLU",
        "11. XLV – Health Care (Saúde)": "XLV"
    }

    for nome, ticker in setores.items():
        ativo = yf.Ticker(ticker)
        data = ativo.history(period="5d")["Close"].dropna().tail(2)

        if len(data) == 2:
            fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
            variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

            preco_formatado = formatar_valor(preco_atual, moeda=False)
            sinal = "+" if variacao >= 0 else ""
            cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

            st.markdown(
                f"""
                <div style='font-size: 20px;'>
                    {nome} – {preco_formatado} 
                    <span style='color:{cor};'>({sinal}{variacao:.2f}%)</span>
                </div>
                """,
                unsafe_allow_html=True
            )
        else:
            st.markdown(f"{nome} – Dados não disponíveis")