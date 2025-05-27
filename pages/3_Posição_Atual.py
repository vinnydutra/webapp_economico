import streamlit as st
import pandas as pd
from datetime import datetime
import yfinance as yf

def validar_posicao(posicao):
    if not isinstance(posicao, list):
        return False
    for item in posicao:
        if not isinstance(item, dict):
            return False
        if not all(key in item for key in ["Ticker", "Quantidade", "Custo", "Data de Compra"]):
            return False
    return True

def obter_preco_ativo(ticker):
    try:
        ticker_yf = yf.Ticker(ticker)
        hist = ticker_yf.history(period="5d")
        preco_atual = hist['Close'].dropna().iloc[-1]
        return f"R$ {preco_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "Erro"

query_params = st.query_params

if "usuario" in query_params:
    st.session_state.usuario = query_params["usuario"]

usuario = st.session_state.get("usuario", None)

if not usuario:
    st.warning("Usuário não definido na URL. Redirecione via Análise Financeira ou adicione ?usuario=SeuNome na URL.")
else:
    st.query_params["usuario"] = usuario

# Importa funções utilitárias para carregar e salvar a carteira
from utils import (
    carregar_carteira_supabase,
    inserir_ativo_carteira,
    deletar_ativo_carteira,
    atualizar_ativo_carteira
)


st.set_page_config(page_title="Posição Atual", page_icon="📊", layout="wide")
st.markdown("""
    <style>
    .main .block-container {
        padding-left: 0.2rem;
        padding-right: 0.2rem;
        max-width: 100%;
    }
    .block-container {
        max-width: 100%;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

st.title("📊 Posição Atual da Carteira")

st.markdown("""
Esta página permite que você insira seus ativos reais, informando:
- **Ticker** (ex.: VALE3, PETR4, AMZO34)
- **Quantidade**
- **Preço Médio de Compra**

A partir dessas informações, você acompanhará a valorização da sua carteira com dados ao vivo.
""")

 # Carrega dados da carteira do usuário e inicializa o estado da sessão
st.session_state.posicao_atual = [
    {
        "Ticker": item["ticker"],
        "Quantidade": item["quantidade"],
        "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
        "Data de Compra": item["data_compra"]
    }
    for item in carregar_carteira_supabase(usuario)
]

# Corrige dados antigos que usam "Preço Pago (R$)"
for item in st.session_state.posicao_atual:
    if "Preço Pago (R$)" in item:
        item["Custo"] = item.pop("Preço Pago (R$)")

remover = query_params.get("remover", None)
if remover is not None and str(remover).isdigit():
    indice = int(remover)
    if 0 <= indice < len(st.session_state.posicao_atual):
        ativo = st.session_state.posicao_atual.pop(indice)
        deletar_ativo_carteira(usuario, ativo["Ticker"])
    st.query_params["remover"] = None

editar = query_params.get("editar", None)
if editar is not None and str(editar).isdigit():
    indice = int(editar)
    if 0 <= indice < len(st.session_state.posicao_atual):
        ativo = st.session_state.posicao_atual[indice]
        st.subheader(f"✏️ Editar Ativo — {ativo['Ticker']}")

        with st.form("form_editar", clear_on_submit=False):
            data = st.text_input("Data de Compra", value=ativo["Data de Compra"])
            quantidade = st.number_input("Quantidade", min_value=0, step=1, value=ativo["Quantidade"], format="%d")
            custo = st.number_input("Custo (R$)", min_value=0.0, step=0.01, 
                                    value=float(ativo["Custo"].replace(",", ".")))

            salvar = st.form_submit_button("Salvar Alterações")

            if salvar:
                ativo["Data de Compra"] = data
                ativo["Quantidade"] = quantidade
                ativo["Custo"] = f"{custo:.2f}".replace(".", ",")
                atualizar_ativo_carteira(
                    usuario,
                    ativo["Ticker"],
                    quantidade,
                    float(custo),
                    data
                )
                st.success("Alterações salvas!")
                st.query_params["editar"] = None

st.subheader("➕ Adicionar Ativo à Carteira")

with st.form("formulario_ativo", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        ticker = st.text_input("Ticker").upper()
    with col2:
        quantidade = st.number_input("Quantidade", min_value=0, step=1, format="%d")
    with col3:
        preco = st.number_input("Custo (R$)", min_value=0.0, step=0.01)

    submitted = st.form_submit_button("Adicionar")

    if submitted:
        if ticker and quantidade > 0 and preco > 0:
            preco_str = f"{preco:.2f}".replace(".", ",")
            novo_ativo = {
                "Ticker": ticker,
                "Quantidade": quantidade,
                "Custo": preco_str,
                "Data de Compra": datetime.now().strftime("%d/%m/%y")
            }
            st.session_state.posicao_atual.append(novo_ativo)
            inserir_ativo_carteira(
                usuario,
                ticker,
                quantidade,
                float(preco),
                novo_ativo["Data de Compra"]
            )
        else:
            st.warning("Preencha todos os campos corretamente.")

st.subheader("🗂️ Carteira Atual")

st.markdown("""
    <style>
    .main .block-container {
        overflow-x: auto;
    }
    </style>
""", unsafe_allow_html=True)

if st.session_state.posicao_atual:
    # Cabeçalho manual centralizado, ajustando largura para botões menores e espaço para "Remover"
    header_cols = st.columns([2, 2.5, 3, 2.5, 2.5, 2.8, 2.5, 2.5, 3.2])
    header_cols[0].markdown(
        "<p style='text-align: center; margin: 0; white-space: nowrap;'><b>Remover</b></p>",
        unsafe_allow_html=True
    )
    header_cols[1].markdown("<p style='text-align: left; margin: 0;'><b>Compra</b></p>", unsafe_allow_html=True)
    header_cols[2].markdown("<p style='text-align: left; margin: 0;'><b>Ticker</b></p>", unsafe_allow_html=True)
    header_cols[3].markdown("<p style='text-align: left; margin: 0;'><b>Quant.</b></p>", unsafe_allow_html=True)
    header_cols[4].markdown("<p style='text-align: left; margin: 0;'><b>Custo</b></p>", unsafe_allow_html=True)
    header_cols[5].markdown("<p style='text-align: left; margin: 0;'><b>Total</b></p>", unsafe_allow_html=True)
    header_cols[6].markdown("<p style='text-align: left; margin: 0;'><b>Preço</b></p>", unsafe_allow_html=True)
    header_cols[7].markdown("<p style='text-align: left; margin: 0;'><b>Var. %</b></p>", unsafe_allow_html=True)
    header_cols[8].markdown("<p style='text-align: left; margin: 0;'><b>Var. R$</b></p>", unsafe_allow_html=True)

    for i, ativo in enumerate(st.session_state.posicao_atual):
        row_cols = st.columns([2, 2.5, 3, 2.5, 2.5, 2.8, 2.5, 2.5, 3.2])
        row_cols[0].markdown(
            f"""
            <div style='display:flex; gap:10px; justify-content:center; align-items:center;'>
                <a href='?usuario={usuario}&remover={i}' 
                style='color:red; text-decoration:none; font-size:18px;'>ⓧ</a>
                <a href='?usuario={usuario}&editar={i}' 
                style='color:#FFA500; text-decoration:none; font-size:18px;'>✏️</a>
            </div>
            """,
            unsafe_allow_html=True
        )
        row_cols[1].markdown(
            f"<p style='text-align: left; margin: 0;'>{ativo.get('Data de Compra', '--')}</p>",
            unsafe_allow_html=True
        )
        row_cols[2].markdown(
            f"<p style='text-align: left; margin: 0;'>{ativo['Ticker']}</p>", unsafe_allow_html=True
        )
        row_cols[3].markdown(
            f"<p style='text-align: left; margin: 0;'>{ativo['Quantidade']}</p>", unsafe_allow_html=True
        )
        row_cols[4].markdown(
            f"<p style='text-align: left; margin: 0;'>R$ {ativo['Custo']}</p>", unsafe_allow_html=True
        )
        try:
            custo_float = float(ativo['Custo'].replace(',', '.'))
            total = custo_float * ativo['Quantidade']
            total_str = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except Exception:
            total_str = "Erro"

        row_cols[5].markdown(
            f"<p style='text-align: left; margin: 0;'>{total_str}</p>",
            unsafe_allow_html=True
        )
        preco_atual = obter_preco_ativo(ativo['Ticker'])
        row_cols[6].markdown(
            f"<p style='text-align: left; margin: 0;'>{preco_atual}</p>",
            unsafe_allow_html=True
        )
        try:
            preco_atual_float = float(preco_atual.replace("R$ ", "").replace(".", "").replace(",", "."))
            variacao = ((preco_atual_float - custo_float) / custo_float) * 100
            variacao_str = f"{variacao:+.2f}%".replace(".", ",")
            cor = "#00FF00" if variacao > 0 else "#FF4B4B"

            variacao_reais = (preco_atual_float - custo_float) * ativo['Quantidade']
            variacao_reais_str = f"R$ {variacao_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            cor_r = "#00FF00" if variacao_reais > 0 else "#FF4B4B"
        except Exception:
            variacao_str = "N/A"
            cor = "#FFFFFF"
            variacao_reais_str = "N/A"
            cor_r = "#FFFFFF"

        row_cols[7].markdown(
            f"<p style='text-align: left; margin: 0; color: {cor};'>{variacao_str}</p>",
            unsafe_allow_html=True
        )
        row_cols[8].markdown(
            f"""
            <p style='text-align: left; margin: 0; color: {cor_r}; white-space: nowrap;'>
                {variacao_reais_str}
            </p>
            """,
            unsafe_allow_html=True
        )
else:
    st.info("Nenhum ativo na carteira. Adicione usando o formulário acima.")

# Placeholder para dados de preço ao vivo e cálculo de desempenho
st.subheader("🚀 Desempenho da Carteira (em desenvolvimento)")
st.info("Aqui serão exibidos os cálculos de valorização, dividendos e distribuição da carteira.")