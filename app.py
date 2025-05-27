import streamlit as st
from utils import obter_usuario

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide"
)

# Bloco para manter o nome do usuário salvo na URL como parâmetro de consulta (query_params)
query_params = st.query_params

if "usuario" in query_params:
    st.session_state.usuario = query_params["usuario"]

usuario = obter_usuario()

st.query_params["usuario"] = usuario

st.sidebar.title("Navegação")
st.sidebar.markdown("Bem-vindo ao Dashboard Financeiro!")
st.sidebar.info("Use o menu lateral para acessar as páginas.")

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