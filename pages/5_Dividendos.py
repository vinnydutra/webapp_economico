import streamlit as st
from utils import carregar_dividendos_usuario, inserir_dividendo, excluir_dividendo
from datetime import datetime
# Modificação de teste para forçar salvamento



st.set_page_config(page_title="Dividendos", page_icon="💰", layout="wide")

# Normaliza o espaçamento superior da página
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Bloco de usuário e logout padronizado na sidebar
with st.sidebar:
    st.markdown("""
        <style>
            .user-block {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 12px 10px;
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

# Captura do usuário logado (padrão do app)
if (
    "usuario" not in st.session_state
    or not st.session_state.usuario
    or "uid" not in st.session_state
    or not st.session_state.uid
):
    st.warning("Sessão inválida. Faça login novamente.")
    st.stop()

usuario = st.session_state.usuario.strip().lower()

st.title("Controle de Dividendos")

edit_id = st.session_state.get("edit_id")
editando = "edit_id" in st.session_state

if not editando:
    st.markdown("### Registro Manual de Dividendos")

import pandas as pd

dividendos = carregar_dividendos_usuario(st.session_state.usuario)
if dividendos:
    df = pd.DataFrame(dividendos)
    colunas_esperadas = ["id", "ticker", "tipo", "valor", "quantidade", "data"]
    df = df[[c for c in colunas_esperadas if c in df.columns]]
    df.columns = ["ID", "Ticker", "Tipo", "Valor (R$)", "Quantidade", "Data de Pagamento"]
    df = df[["ID", "Ticker", "Valor (R$)", "Quantidade", "Data de Pagamento", "Tipo"]]
    df["Total (R$)"] = df["Valor (R$)"] * df["Quantidade"]
    df = df[["ID", "Ticker", "Valor (R$)", "Quantidade", "Total (R$)", "Data de Pagamento", "Tipo"]]
    df["Data de Pagamento"] = pd.to_datetime(df["Data de Pagamento"]).dt.strftime("%d/%m/%Y")
else:
    df = pd.DataFrame(columns=["ID", "Ticker", "Valor (R$)", "Quantidade", "Total (R$)", "Data de Pagamento", "Tipo"])


# Se estiver editando, busca os dados da linha correspondente
if editando:
    registro = df[df["ID"] == st.session_state["edit_id"]].iloc[0]
    valor_inicial = float(registro["Valor (R$)"])
    quantidade_inicial = int(registro["Quantidade"])
    ticker_inicial = registro["Ticker"]
    tipo_inicial = registro["Tipo"]
    data_inicial = datetime.strptime(registro["Data de Pagamento"], "%d/%m/%Y")
else:
    valor_inicial = 0.0
    quantidade_inicial = 0
    ticker_inicial = ""
    tipo_inicial = "DIVIDENDO"
    data_inicial = datetime.today()

if not editando:
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
                st.session_state["erro_dividendo"] = str(e)
                st.rerun()

st.markdown("""
    <style>
        .celula.header {
            background-color: #212121;
            font-weight: bold;
            text-align: left;
        }
        .celula {
            border: 1px solid #444;
            padding: 6px 10px;
            border-radius: 4px;
        }
    </style>
""", unsafe_allow_html=True)

if not df.empty:
    st.markdown('<div class="tabela-dividendos">', unsafe_allow_html=True)
    header = st.columns([2, 2, 2, 2, 2, 2, 1])
    header[0].markdown("<div class='celula header'>Ticker</div>", unsafe_allow_html=True)
    header[1].markdown("<div class='celula header'>Valor (R$)</div>", unsafe_allow_html=True)
    header[2].markdown("<div class='celula header'>Quantidade</div>", unsafe_allow_html=True)
    header[3].markdown("<div class='celula header'>Total (R$)</div>", unsafe_allow_html=True)
    header[4].markdown("<div class='celula header'>Data</div>", unsafe_allow_html=True)
    header[5].markdown("<div class='celula header'>Tipo</div>", unsafe_allow_html=True)
    header[6].markdown("<div class='celula header'>Ação</div>", unsafe_allow_html=True)

    for i, row in df.iterrows():
        col1, col2, col3, col4, col5, col6, col7 = st.columns([2, 2, 2, 2, 2, 2, 1], gap="small")
        col1.markdown(f"<div class='celula'>{row['Ticker']}</div>", unsafe_allow_html=True)
        col2.markdown(f"<div class='celula'>R$ {row['Valor (R$)']:.2f}".replace(".", ",") + "</div>", unsafe_allow_html=True)
        col3.markdown(f"<div class='celula'>{int(row['Quantidade']):,}".replace(",", ".") + "</div>", unsafe_allow_html=True)
        col4.markdown(f"<div class='celula'>R$ {row['Total (R$)']:.2f}".replace(".", ",") + "</div>", unsafe_allow_html=True)
        col5.markdown(f"<div class='celula'>{row['Data de Pagamento']}</div>", unsafe_allow_html=True)
        col6.markdown(f"<div class='celula'>{row['Tipo']}</div>", unsafe_allow_html=True)
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
                    nova_data = st.date_input("Data", value=datetime.strptime(row["Data de Pagamento"], "%d/%m/%Y"), format="DD/MM/YYYY")
                with col5:
                    novo_tipo = st.radio("Tipo", ["DIVIDENDO", "JCP"], horizontal=True, index=0 if row["Tipo"] == "DIVIDENDO" else 1)
                botoes = st.columns([3, 2, 5])
                with botoes[0]:
                    salvar = st.form_submit_button("💾 Salvar Alterações")
                with botoes[1]:
                    cancelar = st.form_submit_button("↩️ Cancelar")

                if salvar:
                    from utils import atualizar_dividendo
                    atualizar_dividendo(
                        row["ID"],
                        {
                            "ticker": novo_ticker,
                            "valor": novo_valor,
                            "quantidade": nova_quantidade,
                            "data": nova_data.strftime("%Y-%m-%d"),
                            "tipo": novo_tipo
                        }
                    )
                    st.success(f"Alterações salvas para {novo_ticker}.")
                    del st.session_state["edit_id"]
                    st.rerun()

                if cancelar:
                    del st.session_state["edit_id"]
                    st.rerun()
        if st.session_state.get("editar_dividendo_id") == row["ID"]:
            col_acao = st.columns([2, 2, 2, 2, 2, 2, 1])
            with col_acao[0]:
                if st.button("✏️ Editar", key=f"editar_{row['ID']}"):
                    st.session_state["edit_id"] = row["ID"]
                    if "editar_dividendo_id" in st.session_state:
                        del st.session_state["editar_dividendo_id"]
                    st.rerun()
            with col_acao[1]:
                if st.button("ⓧ Excluir", key=f"excluir_{row['ID']}"):
                    excluir_dividendo(row["ID"])
                    st.success(f"Dividendo de {row['Ticker']} excluído com sucesso.")
                    del st.session_state["editar_dividendo_id"]
                    st.rerun()
            with col_acao[2]:
                if st.button("↩️ Cancelar", key=f"cancelar_{row['ID']}"):
                    if "editar_dividendo_id" in st.session_state:
                        del st.session_state["editar_dividendo_id"]
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)