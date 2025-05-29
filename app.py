import streamlit as st
from utils import obter_usuario

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide"
)

# 🔗 Campo de entrada para o nome do usuário com persistência via URL
query_params = st.query_params
usuario_inicial = query_params.get("usuario", st.session_state.get("usuario", ""))

with st.sidebar:
    if not st.session_state.get("usuario"):
        usuario_input = st.text_input("Informe seu nome de usuário:", value=usuario_inicial, key="usuario_input")
    else:
        st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")

if not st.session_state.get("usuario"):
    usuario_input_normalizado = usuario_input.strip().lower()
    usuario_inicial_normalizado = usuario_inicial.strip().lower()
    if usuario_input_normalizado and usuario_input_normalizado != usuario_inicial_normalizado:
        st.query_params.update({"usuario": usuario_input_normalizado})
        st.rerun()
    st.session_state.usuario = usuario_input_normalizado
    usuario = usuario_input_normalizado
    if usuario:
        st.success("Login realizado com sucesso!")
else:
    usuario = st.session_state.usuario.strip().lower()

# 🔁 Atualiza a URL com ?usuario=... para persistência em refresh
if "usuario" in st.session_state:
    st.query_params.update({"usuario": st.session_state.usuario})

dados = obter_usuario(usuario)

st.title("📊 Dashboard Financeiro")
st.subheader(f"Bem-vindo, {usuario}, ao seu WebApp de Análise de Ações e Dados Econômicos.")

st.markdown(
    """
    ### 🔍 Funcionalidades disponíveis:
    - **Análise Financeira:** Consulte informações detalhadas sobre empresas.
    - **Painel Econômico:** Acompanhe câmbio, commodities, juros e indicadores macroeconômicos.
    - **Carteira:** Veja o desempenho da sua carteira de ações.
    - **Sobre o Projeto:** Informações gerais, créditos e documentação.
    
    Use o menu lateral esquerdo para navegar entre as páginas.
    """
)

st.success("✅ Dados atualizados em tempo real.")

# Redireciona automaticamente após preenchimento da URL
if "usuario" in query_params and not st.session_state.get("redirected", False):
    st.session_state.redirected = True
    st.switch_page("pages/1_Análise_Financeira.py")