import streamlit as st

query_params = st.query_params
usuario_inicial = query_params.get("usuario", st.session_state.get("usuario", ""))

if usuario_inicial and ("usuario" not in st.session_state or not st.session_state.usuario):
    st.session_state.usuario = usuario_inicial.strip().lower()

# Trecho para garantir consistência na persistência do usuário via URL e sessão
if not st.session_state.get("usuario"):
    usuario_input = st.session_state.get("usuario_input", "")
    if usuario_input and usuario_input != usuario_inicial:
        st.query_params.update({"usuario": usuario_input})
        st.stop()
    st.session_state.usuario = usuario_input
    usuario = usuario_input
else:
    usuario = st.session_state.usuario

if "usuario" in st.session_state:
    st.query_params.update({"usuario": st.session_state.usuario})

st.set_page_config(page_title="Posição Atual", page_icon="📊", layout="wide")
import pandas as pd
from datetime import datetime
import yfinance as yf

# Função auxiliar para tratar datas em diferentes formatos
def parse_data_compra(data_str):
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(data_str, fmt)
        except ValueError:
            continue
    st.error(f"Data inválida: {data_str}")
    return datetime.min

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


with st.sidebar:
    if "usuario" not in st.session_state or not st.session_state.usuario:
        usuario_input = st.text_input("Informe seu nome de usuário:", value=usuario_inicial, key="usuario_input")
        if usuario_input and usuario_input != usuario_inicial:
            st.query_params.update({"usuario": usuario_input.strip().lower()})
            st.session_state.usuario = usuario_input.strip().lower()
            st.rerun()
        usuario = usuario_input
    else:
        st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")
        # Adiciona botão de logout com redirecionamento usando HTML meta refresh
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.markdown("<meta http-equiv='refresh' content='0;url=/?usuario=' />", unsafe_allow_html=True)
            st.stop()
        usuario = st.session_state.usuario

query_params = st.query_params or {}

# Importa funções utilitárias para carregar e salvar a carteira
from utils import (
    carregar_carteira_supabase,
    inserir_ativo_carteira,
    deletar_ativo_carteira,
    atualizar_ativo_carteira,
    inserir_venda
)

 # Remover tooltip "Press Enter to apply" dos campos de entrada
st.markdown(
    """
    <style>
    /* Remove tooltip "Press Enter to apply" dos campos */
    .stNumberInput input:focus, .stTextInput input:focus {
        outline: none;
        box-shadow: none;
    }
    .stNumberInput div[data-baseweb="tooltip"] {
        display: none !important;
    }
    .stTextInput div[data-baseweb="tooltip"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)
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


# Carrega dados da carteira do usuário e inicializa o estado da sessão
if "posicao_atual" not in st.session_state or not st.session_state.posicao_atual:
    st.session_state.posicao_atual = [
        {
            "UUID": item["id"],
            "Ticker": item["ticker"],
            "Quantidade": item["quantidade"],
            "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
            "Data de Compra": item["data_compra"]
        }
        for item in carregar_carteira_supabase(usuario)
    ]

# Ordena os ativos pela data de compra do mais antigo para o mais recente
st.session_state.posicao_atual.sort(
    key=lambda x: parse_data_compra(x["Data de Compra"])
)

# Corrige dados antigos que usam "Preço Pago (R$)"
for item in st.session_state.posicao_atual:
    if "Preço Pago (R$)" in item:
        item["Custo"] = item.pop("Preço Pago (R$)")

remover = query_params.get("remover", None)
if remover is not None:
    deletar_ativo_carteira(remover)
    if "posicao_atual" in st.session_state:
        del st.session_state.posicao_atual
    st.query_params.pop("remover")
    st.rerun()

editar = query_params.get("editar", None)

if editar:
    ativo = next((a for a in st.session_state.posicao_atual if a["UUID"] == editar), None)
    if ativo:
        st.query_params.update({"editar": editar, "usuario": usuario})  # força persistência imediata
        st.subheader(f"✏️ Editar Ativo — {ativo['Ticker']}")
        with st.form("form_editar", clear_on_submit=False):
            data = st.text_input("Data de Compra (formato: DD/MM/YY)", value=ativo["Data de Compra"])
            quantidade = st.number_input("Quantidade", min_value=0, step=1, value=ativo["Quantidade"], format="%d")
            custo = st.number_input("Custo (R$)", min_value=0.0, step=0.01,
                                    value=float(ativo["Custo"].replace(",", ".")))

            salvar = st.form_submit_button("Salvar Alterações")

            if salvar:
                try:
                    data_formatada = datetime.strptime(data, "%d/%m/%y").strftime("%d/%m/%y")
                except ValueError:
                    st.error("Data inválida! Use o formato DD/MM/YY.")
                    st.stop()
                ativo["Data de Compra"] = data_formatada
                ativo["Quantidade"] = quantidade
                ativo["Custo"] = f"{custo:.2f}".replace(".", ",")
                atualizar_ativo_carteira(
                    ativo["UUID"],
                    quantidade,
                    float(custo),
                    data_formatada
                )
                st.success("Alterações salvas!")
                st.query_params["editar"] = None
                st.rerun()

vender = query_params.get("vender", None)
if vender is not None:
    ativo = next((a for a in st.session_state.posicao_atual if a["UUID"] == vender), None)
    if ativo:
        st.subheader(f"💰 Registrar Venda — {ativo['Ticker']}")

        with st.form("form_vender", clear_on_submit=False):
            data_venda = st.text_input(
                "Data da Venda (formato: DD/MM/YY)",
                value=datetime.now().strftime("%d/%m/%y")
            )
            quantidade_venda = st.number_input(
                "Quantidade Vendida",
                min_value=1,
                max_value=ativo["Quantidade"],
                value=ativo["Quantidade"],
                step=1,
                format="%d"
            )
            preco_venda = st.number_input(
                "Preço de Venda (R$)", min_value=0.0, step=0.01
            )

            confirmar_venda = st.form_submit_button("Confirmar Venda")

            if confirmar_venda:
                try:
                    data_formatada = datetime.strptime(data_venda, "%d/%m/%y").strftime("%d/%m/%y")
                except ValueError:
                    st.error("Data inválida! Use o formato DD/MM/YY.")
                    st.stop()

                # Registrar na tabela de vendas
                inserir_venda(
                    usuario,
                    ativo["Ticker"],
                    quantidade_venda,
                    float(ativo["Custo"].replace(",", ".")),
                    ativo["Data de Compra"],
                    preco_venda,
                    data_formatada
                )

                # Atualizar quantidade na carteira
                if quantidade_venda == ativo["Quantidade"]:
                    st.session_state.posicao_atual.remove(ativo)
                    deletar_ativo_carteira(ativo["UUID"])
                else:
                    ativo["Quantidade"] -= quantidade_venda
                    atualizar_ativo_carteira(
                        ativo["UUID"],
                        ativo["Quantidade"],
                        float(ativo["Custo"].replace(",", ".")),
                        ativo["Data de Compra"]
                    )

                st.success("Venda registrada com sucesso!")
                st.query_params["vender"] = None
                st.rerun()

st.subheader("➕ Adicionar Ativo à Carteira")

col1, col2, col3, col4 = st.columns(4)

with col1:
    ticker = st.text_input("Ticker").upper()
with col2:
    quantidade = st.number_input("Quantidade", min_value=0, step=1, format="%d")
with col3:
    preco = st.number_input("Custo (R$)", min_value=0.0, step=0.01)
with col4:
    data_compra = st.text_input(
        "Data de Compra (DD/MM/YY)",
        value=datetime.now().strftime("%d/%m/%y")
    )

adicionar = st.button("Adicionar")

if adicionar:
    try:
        data_formatada = datetime.strptime(data_compra, "%d/%m/%y").strftime("%d/%m/%y")
    except ValueError:
        st.error("Data inválida! Use o formato DD/MM/YY.")
        st.stop()
    if ticker and quantidade > 0 and preco > 0:
        preco_str = f"{preco:.2f}".replace(".", ",")
        uuid_ativo = inserir_ativo_carteira(
            usuario,
            ticker,
            quantidade,
            float(preco),
            data_formatada
        )
        novo_ativo = {
            "UUID": uuid_ativo,
            "Ticker": ticker,
            "Quantidade": quantidade,
            "Custo": preco_str,
            "Data de Compra": data_formatada
        }
        st.session_state.posicao_atual.append(novo_ativo)
        st.success("Ativo adicionado com sucesso!")
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
    header_cols = st.columns([2.4, 2.1, 3, 2.5, 2.5, 2.8, 2.5, 2.5, 3.2])
    header_cols[0].markdown(
        "<p style='text-align: center; margin: 0; white-space: nowrap;'></p>",
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
        row_cols = st.columns([2.4, 2.1, 3, 2.5, 2.5, 2.8, 2.5, 2.5, 3.2])
        row_cols[0].markdown(
            f"""
            <div style='display:flex; gap:10px; justify-content:center; align-items:center;'>
                <a href='?usuario={usuario}&remover={ativo["UUID"]}'
                target='_self' style='color:red; text-decoration:none; font-size:18px;'>ⓧ</a>
                <a href='?usuario={usuario}&editar={ativo["UUID"]}'
                target='_self' style='color:#FFA500; text-decoration:none; font-size:18px;'>✏️</a>
                <a href='?usuario={usuario}&vender={ativo["UUID"]}'
                target='_self' style='color:#00BFFF; text-decoration:none; font-size:18px;'>✅</a>
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

    # Calcular Totais da Carteira
    total_investido = 0
    total_variacao_reais = 0

    for ativo in st.session_state.posicao_atual:
        try:
            custo_float = float(ativo['Custo'].replace(',', '.'))
            total = custo_float * ativo['Quantidade']
            preco_atual_float = float(obter_preco_ativo(ativo['Ticker']).replace("R$ ", "").replace(".", "").replace(",", "."))

            variacao_reais = (preco_atual_float - custo_float) * ativo['Quantidade']

            total_investido += total
            total_variacao_reais += variacao_reais
        except Exception:
            continue

    # Calcular variação percentual ponderada
    if total_investido != 0:
        total_variacao_percentual = (total_variacao_reais / total_investido) * 100
    else:
        total_variacao_percentual = 0

    # Formatar valores
    total_investido_str = f"R$ {total_investido:,.2f}".replace(',', "X").replace('.', ",").replace("X", ".")
    total_variacao_reais_str = f"R$ {total_variacao_reais:,.2f}".replace(',', "X").replace('.', ",").replace("X", ".")
    total_variacao_percentual_str = f"{total_variacao_percentual:+.2f}%".replace(".", ",")

    cor_percentual = "#00FF00" if total_variacao_percentual > 0 else "#FF4B4B"
    cor_reais = "#00FF00" if total_variacao_reais > 0 else "#FF4B4B"

    # Criar linha de totais na tabela
    total_cols = st.columns([2.4, 2.1, 3, 2.3, 2.5, 3, 2.5, 2.5, 3.2])

    total_cols[0].markdown(
        f"<p style='text-align: center; margin: 0; white-space: nowrap;'><b>Total</b></p>",
        unsafe_allow_html=True
    )
    for i in [1, 2, 3, 4, 6]:
        total_cols[i].markdown(
            f"<p style='text-align: left; margin: 0; white-space: nowrap;'></p>",
            unsafe_allow_html=True
        )
    total_cols[5].markdown(
        f"<p style='text-align: left; margin: 0; white-space: nowrap;'><b>{total_investido_str}</b></p>",
        unsafe_allow_html=True
    )
    total_cols[7].markdown(
        f"<p style='text-align: left; margin: 0; white-space: nowrap; color: {cor_percentual};'><b>{total_variacao_percentual_str}</b></p>",
        unsafe_allow_html=True
    )
    total_cols[8].markdown(
        f"<p style='text-align: left; margin: 0; white-space: nowrap; color: {cor_reais};'><b>{total_variacao_reais_str}</b></p>",
        unsafe_allow_html=True
    )
else:
    st.info("Nenhum ativo na carteira. Adicione usando o formulário acima.")

# Placeholder para dados de preço ao vivo e cálculo de desempenho
st.subheader("🚀 Desempenho da Carteira (em desenvolvimento)")
st.info("Aqui serão exibidos os cálculos de valorização, dividendos e distribuição da carteira.")