import streamlit as st


def apply_global_dark_theme() -> None:
    """
    Força a aplicação do tema escuro via CSS para todo o app,
    independentemente da escolha de tema do usuário no menu do Streamlit.
    """
    if st.session_state.get("_global_dark_theme_applied"):
        return

    st.session_state["_global_dark_theme_applied"] = True

    st.markdown(
        """
        <style>
        :root {
            color-scheme: dark;
        }

        html, body, .stApp {
            background-color: #050816 !important;
            color: #E5E7EB !important;
        }

        .stApp * {
            color: #E5E7EB;
        }

        /* Sidebar fixa em fundo escuro */
        section[data-testid="stSidebar"], div[data-testid="stSidebar"] {
            background-color: #050816 !important;
            color: #E5E7EB !important;
        }
        section[data-testid="stSidebar"] * {
            color: #E5E7EB;
        }

        /* Header e toolbars alinhados ao fundo escuro */
        header, [data-testid="stHeader"] {
            background-color: #050816 !important;
            color: #E5E7EB !important;
        }

        /* Ajusta inputs padrão para manter contraste em tema dark forçado */
        .stTextInput > div > div input,
        .stNumberInput input,
        .stSelectbox > div > div,
        .stDateInput input {
            color: #E5E7EB !important;
        }

        /* Fundo de widgets com base escura quando possível */
        .stSelectbox > div > div,
        .stMultiSelect > div > div,
        .stTextInput > div > div,
        .stDateInput > div > div {
            background-color: rgba(255, 255, 255, 0.04) !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
