import streamlit as st
from supabase import create_client, Client
from utils import conectar_supabase
from utils import restaurar_usuario_sessao

@st.cache_resource
def get_supabase():
    return conectar_supabase()

# Inicializa sessão apenas se ainda não existir
if "usuario" not in st.session_state:
    st.session_state.usuario = None
if "uid" not in st.session_state:
    st.session_state.uid = None
if "access_token" not in st.session_state:
    st.session_state.access_token = None

if st.session_state.get("usuario"):
    restaurar_usuario_sessao()

st.set_page_config(
    page_title="Dashboard Financeiro",
    page_icon="💰",
    layout="wide"
)

# Reduz espaçamento superior do container padrão do Streamlit
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Lógica de logout moderna
if st.query_params.get("logout") == "true":
    for key in ["usuario", "uid", "access_token"]:
        if key in st.session_state:
            del st.session_state[key]
    st.query_params.clear()
    st.session_state._rerun = True
    st.query_params.update({})
    st.rerun()

# Bloco do usuário e logout no topo da tela
usuario_logado = st.session_state.get("usuario", "desconhecido")
st.markdown(f"""
<br>
<div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 0px;'>
    <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
    <form action='/?logout=true' method='get'>
        <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
    </form>
</div>
""", unsafe_allow_html=True)

if st.session_state.get("_rerun"):
    st.session_state._rerun = False
    st.rerun()

# === BLOQUEIO DE ACESSO ===
if not st.session_state.usuario:
    st.title("🔐 Acesso ao WebApp Financeiro")

    aba = st.radio("Escolha uma opção", ["Entrar", "Criar Conta", "Recuperar Senha"])

    if aba == "Entrar":
        def handle_login():
            email = st.session_state.get("login_email")
            senha = st.session_state.get("login_senha")

            if not email or not senha:
                st.error("Preencha todos os campos.")
                return

            try:
                res = get_supabase().auth.sign_in_with_password({"email": email, "password": senha})
                if res.session and res.user:
                    access_token = res.session.access_token
                    st.session_state.usuario = res.user.email
                    st.session_state.uid = res.user.id
                    st.session_state.access_token = access_token

                    st.session_state._rerun = True
                    st.rerun()
                else:
                    st.error("E-mail ou senha inválidos.")
            except Exception as e:
                st.error("Erro no login. Verifique seus dados.")

        with st.form(key="login_form"):
            st.text_input("E-mail", key="login_email")
            st.text_input("Senha", type="password", key="login_senha")
            submitted = st.form_submit_button("Entrar")
            if submitted:
                handle_login()

    elif aba == "Criar Conta":
        email = st.text_input("Novo e-mail")
        senha = st.text_input("Nova senha", type="password")
        if st.button("Criar conta"):
            try:
                get_supabase().auth.sign_up({"email": email, "password": senha})
                st.success("Verifique seu e-mail para confirmar a conta.")
            except Exception as e:
                st.error("Erro ao criar conta. Conta já existe ou formato inválido.")

    elif aba == "Recuperar Senha":
        email = st.text_input("Seu e-mail")
        if st.button("Enviar link de recuperação"):
            try:
                get_supabase().auth.reset_password_email(email)
                st.success("Verifique seu e-mail para redefinir a senha.")
            except:
                st.error("Erro ao enviar link de recuperação.")

    st.stop()

# === INTERFACE PÓS-LOGIN ===

# Navegação com parâmetros preservados
usuario = st.session_state.usuario
uid = st.session_state.uid
access_token = st.session_state.access_token


# === CONTEÚDO INICIAL DO APP ===
st.title("Dashboard Financeiro")
st.subheader(f"Bem-vindo, {st.session_state.usuario}!")

st.markdown(
    """
    ### 🔍 Funcionalidades disponíveis:
    - **Análise Financeira:**
    - **Painel Econômico:**
    - **Posição Atual:**
    - **Histórico de Vendas:** 
    - **Dividendos:** 

    Use o menu lateral esquerdo para navegar entre as páginas.
    """
)

st.success("✅ Sessão ativa com autenticação segura.")