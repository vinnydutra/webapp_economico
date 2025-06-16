import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder

st.set_page_config(page_title="Painel Econômico", page_icon="📈", layout="wide")

# Título principal da página
st.markdown("# Painel Econômico")

# Reduz as margens laterais da página
st.markdown("""
    <style>
        .main .block-container {
            padding-left: 1rem;
            padding-right: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

import requests
from bs4 import BeautifulSoup
import time
import yfinance as yf
from datetime import datetime
from utils import obter_usuario, formatar_valor

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




# Persistência e autenticação do usuário via session_state.uid
with st.sidebar:
    if "uid" not in st.session_state:
        usuario_input = st.text_input("Informe seu nome de usuário:", key="usuario_input")
        if usuario_input:
            st.session_state.usuario = usuario_input.strip()
            st.session_state.uid = usuario_input.strip().lower()
            st.experimental_rerun()
        st.stop()
    else:
        st.markdown("""
            <style>
                .user-block {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding: 12px 10px;
                    /* border-bottom: 1px solid #444; */
                }}
                .user-email {{
                    color: #ccc;
                    font-size: 14px;
                    margin-right: 6px;
                }}
                .logout-btn {{
                    background: none;
                    border: none;
                    color: #ccc;
                    font-size: 18px;
                    cursor: pointer;
                    padding: 0;
                }}
                .logout-btn:hover {{
                    color: #fff;
                }}
            </style>
            <div class="user-block">
                <span class="user-email">👤 {}</span>
                <form action='/?logout=true' method='get'>
                    <button type='submit' class="logout-btn" title="Logout">⏻</button>
                </form>
            </div>
        """.format(st.session_state.get("usuario", "desconhecido")), unsafe_allow_html=True)

        if st.query_params.get("logout") == "true":
            for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise"]:
                if chave in st.session_state:
                    del st.session_state[chave]
            st.query_params.clear()
            st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
            st.stop()

with st.expander("💹 Variação dos Índices", expanded=False):
    st.markdown("")

    import pandas as pd

    indices = {
        "Ibovespa": "^BVSP",
        "S&P 500": "^GSPC",
        "Nasdaq": "^IXIC",
        "Dow Jones": "^DJI",
        "DAX": "^GDAXI",
        "Nikkei": "^N225"
    }

    hoje = datetime.now().date()
    ano_atual = hoje.year
    # Localização do dicionário datas_alvo
    datas_alvo = {
        "Dia": "DIA_ESPECIAL",
        "Semana": hoje - pd.Timedelta(days=7),
        "Mês": hoje - pd.Timedelta(days=30),
        "YTD": datetime(ano_atual, 1, 1).date(),
        "12M": hoje - pd.Timedelta(days=365),
    }
    # Adiciona anos anteriores com rótulo automático
    for i in range(1, 6):
        ano_label = ano_atual - i
        datas_alvo[str(ano_label)] = datetime(ano_label, 12, 31).date()

    resultado = []

    for nome, ticker in indices.items():
        try:
            ativo = yf.Ticker(ticker)
            df = ativo.history(period="5y")["Close"].dropna()

            linha = {"Índice": nome}

            preco_hoje = df.iloc[-1]
            # Adiciona coluna Valor com preço formatado
            linha["Valor"] = formatar_valor(preco_hoje, moeda=False)

            for rotulo, data_ref in datas_alvo.items():
                # Lógica especial para variação diária
                if rotulo == "Dia":
                    if len(df) >= 2:
                        preco_passado = df.iloc[-2]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        valor = f"{variacao:+.2f}%"
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                        linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                    else:
                        linha[rotulo] = "N/D"
                    continue
                df_filtrado = df[df.index.date <= data_ref]
                if not df_filtrado.empty:
                    preco_passado = df_filtrado.iloc[-1]
                    variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                    valor = f"{variacao:+.2f}%"
                    cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                    linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                else:
                    linha[rotulo] = "N/D"

            resultado.append(linha)
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_final = pd.DataFrame(resultado)
    # Reordena colunas para inserir "Valor" logo após "Índice"
    colunas_ordenadas = ["Índice", "Valor"] + [col for col in df_final.columns if col not in ["Índice", "Valor"]]
    df_final = df_final[colunas_ordenadas]
    # TABELA COM ESTILO 1: PANDAS STYLER
    try:
        # Remove as tags HTML antes de aplicar estilo
        df_estilo = df_final.copy()
        for col in df_estilo.columns:
            if col not in ["Índice", "Valor"]:
                df_estilo[col] = df_estilo[col].str.replace(r"<.*?>", "", regex=True)

        def aplicar_estilo(val):
            if isinstance(val, str) and val.startswith("+"):
                return "color: #00FF00"
            elif isinstance(val, str) and val.startswith("-"):
                return "color: #FF4C4C"
            return "color: white"

        styled_df = (
            df_estilo.style
            .applymap(aplicar_estilo, subset=[col for col in df_estilo.columns if col not in ["Índice", "Valor"]])
            .set_table_styles(
                [{"selector": "table", "props": [("font-size", "1.5em")]}]
            )
        )
        st.dataframe(styled_df, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Erro ao exibir tabela com pandas Styler: {e}")


with st.expander("🪙 Câmbio e Moedas", expanded=False):
    st.markdown("")
    dolar = yf.Ticker("USDBRL=X")
    data = dolar.history(period="5d")["Close"].dropna().tail(2)

    if len(data) == 2:
        fechamento_anterior, preco_atual = data.iloc[0], data.iloc[1]
        variacao = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100

        preco_formatado = formatar_valor(preco_atual)
        sinal = "+" if variacao >= 0 else ""
        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"


    import pandas as pd
    from datetime import datetime
    import yfinance as yf

    pares = {
        "USD/BRL": "USDBRL=X",
        "CAD/BRL": "CADBRL=X",
        "EUR/BRL": "EURBRL=X",
        "GBP/BRL": "GBPBRL=X",
        "BTC/USD": "BTC-USD",
        "ARS/BRL": ("USDBRL=X", "ARS=X"),  # indireto
        "UYU/BRL": ("USDBRL=X", "UYU=X"),  # indireto
    }

    hoje = datetime.now().date()
    ano_atual = hoje.year
    datas_alvo = {
        "Dia": "DIA_ESPECIAL",
        "Semana": hoje - pd.Timedelta(days=7),
        "Mês": hoje - pd.Timedelta(days=30),
        "YTD": datetime(ano_atual, 1, 1).date(),
        "12M": hoje - pd.Timedelta(days=365),
    }
    for i in range(1, 6):
        ano_label = ano_atual - i
        datas_alvo[str(ano_label)] = datetime(ano_label, 12, 31).date()

    resultado = []

    for nome, ticker in pares.items():
        try:
            linha = {"Par": nome}

            if isinstance(ticker, tuple):
                div, divisor = yf.Ticker(ticker[0]), yf.Ticker(ticker[1])
                serie_div = div.history(period="5y")["Close"].dropna()
                serie_divisor = divisor.history(period="5y")["Close"].dropna()

                preco_hoje = (serie_div.iloc[-1] / serie_divisor.iloc[-1]) if not serie_div.empty and not serie_divisor.empty else None
                # Adiciona coluna Valor com preço formatado (sem prefixo, até 3 casas decimais)
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(serie_div) >= 2 and len(serie_divisor) >= 2:
                            preco_passado = serie_div.iloc[-2] / serie_divisor.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            valor = f"{variacao:+.2f}%"
                            cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                            linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    f1 = serie_div[serie_div.index.date <= data_ref]
                    f2 = serie_divisor[serie_divisor.index.date <= data_ref]
                    if not f1.empty and not f2.empty:
                        preco_passado = f1.iloc[-1] / f2.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        valor = f"{variacao:+.2f}%"
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                        linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                    else:
                        linha[rotulo] = "N/D"
            else:
                ativo = yf.Ticker(ticker)
                serie = ativo.history(period="5y")["Close"].dropna()
                preco_hoje = serie.iloc[-1] if not serie.empty else None
                # Adiciona coluna Valor com preço formatado (sem prefixo, até 3 casas decimais)
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(serie) >= 2:
                            preco_passado = serie.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            valor = f"{variacao:+.2f}%"
                            cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                            linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    f = serie[serie.index.date <= data_ref]
                    if not f.empty:
                        preco_passado = f.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        valor = f"{variacao:+.2f}%"
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                        linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                    else:
                        linha[rotulo] = "N/D"

            resultado.append(linha)
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_moedas_multi = pd.DataFrame(resultado)
    # Reordena colunas para inserir "Valor" logo após "Par"
    colunas_ordenadas = ["Par", "Valor"] + [col for col in df_moedas_multi.columns if col not in ["Par", "Valor"]]
    df_moedas_multi = df_moedas_multi[colunas_ordenadas]

    # Estilização
    df_estilo = df_moedas_multi.copy()
    for col in df_estilo.columns:
        if col not in ["Par", "Valor"]:
            df_estilo[col] = df_estilo[col].str.replace(r"<.*?>", "", regex=True)

    def aplicar_estilo(val):
        if isinstance(val, str) and val.startswith("+"):
            return "color: #00FF00"
        elif isinstance(val, str) and val.startswith("-"):
            return "color: #FF4C4C"
        return "color: white"

    styled_df = (
        df_estilo.style
        .applymap(aplicar_estilo, subset=[col for col in df_estilo.columns if col not in ["Par", "Valor"]])
        .set_table_styles(
            [{"selector": "table", "props": [("font-size", "1.15em")]}]
        )
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# Novo bloco: Commodities – Multiperíodo
with st.expander("🛢️ Commodities", expanded=False):

    commodities = {
        "Brent": "BZ=F",
        "WTI": "CL=F",
        "Ouro": "GC=F",
        "Minério": None  # Sem dados históricos disponíveis via yfinance
    }

    hoje = datetime.now().date()
    ano_atual = hoje.year
    datas_alvo = {
        "Dia": "DIA_ESPECIAL",
        "Semana": hoje - pd.Timedelta(days=7),
        "Mês": hoje - pd.Timedelta(days=30),
        "YTD": datetime(ano_atual, 1, 1).date(),
        "12M": hoje - pd.Timedelta(days=365),
    }
    for i in range(1, 6):
        ano_label = ano_atual - i
        datas_alvo[str(ano_label)] = datetime(ano_label, 12, 31).date()

    resultado = []

    for nome, ticker in commodities.items():
        try:
            linha = {"Commoditie": nome}

            if ticker is None:
                linha["Valor"] = "N/D"
                for rotulo in datas_alvo:
                    linha[rotulo] = "N/D"
            else:
                ativo = yf.Ticker(ticker)
                serie = ativo.history(period="5y")["Close"].dropna()
                preco_hoje = serie.iloc[-1] if not serie.empty else None
                linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

                for rotulo, data_ref in datas_alvo.items():
                    if rotulo == "Dia":
                        if len(serie) >= 2:
                            preco_passado = serie.iloc[-2]
                            variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                            valor = f"{variacao:+.2f}%"
                            cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                            linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                        else:
                            linha[rotulo] = "N/D"
                        continue
                    f = serie[serie.index.date <= data_ref]
                    if not f.empty:
                        preco_passado = f.iloc[-1]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        valor = f"{variacao:+.2f}%"
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                        linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                    else:
                        linha[rotulo] = "N/D"

            resultado.append(linha)
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_commodities = pd.DataFrame(resultado)
    colunas_ordenadas = ["Commoditie", "Valor"] + [col for col in df_commodities.columns if col not in ["Commoditie", "Valor"]]
    df_commodities = df_commodities[colunas_ordenadas]

    df_estilo = df_commodities.copy()
    for col in df_estilo.columns:
        if col not in ["Commoditie", "Valor"]:
            df_estilo[col] = df_estilo[col].str.replace(r"<.*?>", "", regex=True)

    def aplicar_estilo(val):
        if isinstance(val, str) and val.startswith("+"):
            return "color: #00FF00"
        elif isinstance(val, str) and val.startswith("-"):
            return "color: #FF4C4C"
        return "color: white"

    styled_df = (
        df_estilo.style
        .applymap(aplicar_estilo, subset=[col for col in df_estilo.columns if col not in ["Commoditie", "Valor"]])
        .set_table_styles(
            [{"selector": "table", "props": [("font-size", "1.15em")]}]
        )
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)


# Novo bloco: Setores do S&P 500 – Multiperíodo (placeholder)
with st.expander("🏛️ Setores do S&P 500", expanded=False):
    setores = {
        "XLY": "XLY", "XLE": "XLE", "XLK": "XLK", "XLI": "XLI", "XLB": "XLB",
        "XLF": "XLF", "XLC": "XLC", "XLRE": "XLRE", "XLP": "XLP", "XLU": "XLU", "XLV": "XLV"
    }

    hoje = datetime.now().date()
    ano_atual = hoje.year
    datas_alvo = {
        "Dia": "DIA_ESPECIAL",
        "Semana": hoje - pd.Timedelta(days=7),
        "Mês": hoje - pd.Timedelta(days=30),
        "YTD": datetime(ano_atual, 1, 1).date(),
        "12M": hoje - pd.Timedelta(days=365),
    }
    for i in range(1, 6):
        ano_label = ano_atual - i
        datas_alvo[str(ano_label)] = datetime(ano_label, 12, 31).date()

    resultado = []

    for nome, ticker in setores.items():
        try:
            linha = {"Setor": nome}
            ativo = yf.Ticker(ticker)
            serie = ativo.history(period="5y")["Close"].dropna()
            preco_hoje = serie.iloc[-1] if not serie.empty else None
            linha["Valor"] = f"{preco_hoje:,.3f}".replace(",", "X").replace(".", ",").replace("X", ".")

            for rotulo, data_ref in datas_alvo.items():
                if rotulo == "Dia":
                    if len(serie) >= 2:
                        preco_passado = serie.iloc[-2]
                        variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                        valor = f"{variacao:+.2f}%"
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                        linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                    else:
                        linha[rotulo] = "N/D"
                    continue
                f = serie[serie.index.date <= data_ref]
                if not f.empty:
                    preco_passado = f.iloc[-1]
                    variacao = ((preco_hoje - preco_passado) / preco_passado) * 100
                    valor = f"{variacao:+.2f}%"
                    cor = "#00FF00" if variacao >= 0 else "#FF4C4C"
                    linha[rotulo] = f"<span style='color:{cor};'>{valor}</span>"
                else:
                    linha[rotulo] = "N/D"

            resultado.append(linha)
        except Exception as e:
            st.error(f"Erro ao processar {nome}: {e}")

    df_setores = pd.DataFrame(resultado)
    colunas_ordenadas = ["Setor", "Valor"] + [col for col in df_setores.columns if col not in ["Setor", "Valor"]]
    df_setores = df_setores[colunas_ordenadas]

    df_estilo = df_setores.copy()
    for col in df_estilo.columns:
        if col not in ["Setor", "Valor"]:
            df_estilo[col] = df_estilo[col].str.replace(r"<.*?>", "", regex=True)

    def aplicar_estilo(val):
        if isinstance(val, str) and val.startswith("+"):
            return "color: #00FF00"
        elif isinstance(val, str) and val.startswith("-"):
            return "color: #FF4C4C"
        return "color: white"

    styled_df = (
        df_estilo.style
        .applymap(aplicar_estilo, subset=[col for col in df_estilo.columns if col not in ["Setor", "Valor"]])
        .set_table_styles(
            [{"selector": "table", "props": [("font-size", "1.15em")]}]
        )
    )

    st.dataframe(styled_df, use_container_width=True, hide_index=True)

    st.markdown("""
    <div style='font-size: 0.9rem; line-height: 1.6; color: #aaa; display: flex; gap: 3rem; margin-top: 1rem;'>
        <div>
            <strong>Legenda:</strong><br>
            XLY – Consumo Discricionário<br>
            XLE – Energia
        </div>
        <div>
            XLK – Tecnologia da Informação<br>
            XLI – Industriais<br>
            XLB – Materiais
        </div>
        <div>
            XLF – Financeiro<br>
            XLC – Serviços de Comunicação<br>
            XLRE – Imobiliário
        </div>
        <div>
            XLP – Consumo Básico<br>
            XLU – Utilidade Pública<br>
            XLV – Saúde
        </div>
    </div>
    """, unsafe_allow_html=True)



# Remover qualquer uso de experimental_set_query_params ou experimental_get_query_params