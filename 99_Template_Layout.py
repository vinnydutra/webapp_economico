import streamlit as st

from utils import (
    restaurar_usuario_sessao,
    supabase_autenticado,
    formatar_valor,
)

# Página template para novos layouts do WebApp Econômico.
# Substitua os placeholders desta tela quando criar uma página real.
restaurar_usuario_sessao()

st.set_page_config(page_title="Template Layout", page_icon="🧩", layout="wide")

# Mantém o mesmo ajuste de margens utilizado nas páginas existentes.
st.markdown(
    """
    <style>
        .block-container {
            padding-top: 1rem;
            padding-left: 0.6rem !important;
            padding-right: 0.6rem !important;
        }
    </style>
    """,
    unsafe_allow_html=True,
)

# Copia exatamente o estilo de cards da página 1 (fin-card-marker + classes associadas).
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

if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

if "uid" not in st.session_state or not st.session_state.uid:
    st.warning("Usuário não autenticado. Faça login para visualizar o template.")
    st.stop()

# Mantemos o padrão de criar o client autenticado para facilitar futuros dados reais.
supabase_client = supabase_autenticado()
user_id = st.session_state.uid


def format_percent(value: float) -> str:
    """Formatador de percentuais no padrão brasileiro (+12,3%)."""
    return f"{value:+.1f}%".replace(".", ",")


def load_template_context() -> dict:
    """
    Centraliza os placeholders da página.
    TODO: substituir por consultas reais (Supabase, APIs, cálculos) quando usar o template.
    """
    return {
        "main_card": {
            "title": "Card Principal (exemplo)",
            "subtitle": "Área para overview geral",
            "description": (
                "Use este espaço para destacar KPIs críticos: resumo da carteira, status de IR "
                "ou outra visão principal."
            ),
            "indicators": [
                {"label": "Indicador A", "value": 123456.78, "kind": "currency"},
                {"label": "Indicador B", "value": 12.3, "kind": "percent"},
                {"label": "Indicador C", "value": 42, "kind": "count"},
            ],
        },
        "left_card": {
            "title": "Card Esquerda (exemplo)",
            "body": [
                "Insira uma tabela, gráfico ou lista de operações.",
                "Você pode posicionar filtros no topo usando st.columns().",
                "Combine este card com dados agregados ou componentes customizados.",
            ],
        },
        "right_card": {
            "title": "Card Direita (exemplo)",
            "body": [
                "Use KPIs adicionais, alertas ou totais específicos.",
                "Também é um bom local para status de tarefas ou próximos passos.",
            ],
            "kpis": [
                {"label": "Meta do mês", "value": formatar_valor(85000.00)},
                {"label": "Execução", "value": format_percent(64.8)},
                {"label": "Itens monitorados", "value": "18 ativos"},
            ],
        },
    }


def format_indicator_value(indicator: dict) -> str:
    tipo = indicator.get("kind")
    if tipo == "currency":
        return formatar_valor(indicator.get("value", 0.0))
    if tipo == "percent":
        return format_percent(float(indicator.get("value", 0.0)))
    return str(indicator.get("value", "—"))


def render_header_section():
    """Cabeçalho padrão do template."""
    st.caption("Template • Layout base")
    st.title("Template de Layout – WebApp Econômico")
    st.markdown("Use esta página como base para novas telas. Substitua os textos e cards por conteúdo real.")


def render_main_card(card_data: dict):
    """Card hero com o mesmo visual da página 1."""
    with st.container():
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='fin-title'>{card_data['title']} <span class='fin-badge'>{card_data.get('subtitle', 'Resumo')}</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<div class='fin-label'>{card_data['description']}</div>", unsafe_allow_html=True)
        cols = st.columns(len(card_data["indicators"]))
        for col, indicador in zip(cols, card_data["indicators"]):
            with col:
                st.caption(indicador["label"])
                st.markdown(f"**{format_indicator_value(indicador)}**")


def render_secondary_cards(context: dict):
    """Linha com dois cards menores seguindo o padrão de colunas."""
    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='fin-title'>{context['left_card']['title']} <span class='fin-badge'>Placeholder</span></div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "Lista onde você pode explicar o conteúdo que entrará neste espaço:",
            unsafe_allow_html=False,
        )
        st.markdown(
            "<ul>"
            + "".join(f"<li>{item}</li>" for item in context["left_card"]["body"])
            + "</ul>",
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown("<div class='fin-card-marker'></div>", unsafe_allow_html=True)
        st.markdown(
            f"<div class='fin-title'>{context['right_card']['title']} <span class='fin-badge'>Placeholder</span></div>",
            unsafe_allow_html=True,
        )
        for text in context["right_card"]["body"]:
            st.markdown(f"- {text}")
        st.markdown("<div class='fin-divider'></div>", unsafe_allow_html=True)
        for kpi in context["right_card"]["kpis"]:
            st.markdown(f"<div class='fin-label'>{kpi['label']}</div>", unsafe_allow_html=True)
            st.markdown(f"<div class='fin-value'>{kpi['value']}</div>", unsafe_allow_html=True)


def render_template_layout():
    """Orquestra o layout da página template."""
    render_header_section()
    context = load_template_context()
    render_main_card(context["main_card"])
    st.divider()
    render_secondary_cards(context)


# Orquestra a renderização final.
render_template_layout()

# Evita lint no import até que dados reais sejam usados.
_ = (supabase_client, user_id)
