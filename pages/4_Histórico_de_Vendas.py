import streamlit as st
from utils import carregar_vendas, deletar_venda
from datetime import datetime

st.set_page_config(page_title="Histórico de Vendas", layout="wide")

st.title("📜 Histórico de Vendas")

# 🔗 Sincronização entre URL e sessão para o usuário
query_params = st.query_params or {}
usuario_inicial = query_params.get("usuario", st.session_state.get("usuario", ""))

if usuario_inicial and ("usuario" not in st.session_state or not st.session_state.usuario):
    st.session_state.usuario = usuario_inicial.strip().lower()

# 🔁 Forçar sincronização da URL com o nome de usuário da sessão, se necessário
if "usuario" in st.session_state and st.session_state.usuario and query_params.get("usuario") != st.session_state.usuario:
    st.query_params.update({"usuario": st.session_state.usuario})
    st.rerun()

with st.sidebar:
    if "usuario" not in st.session_state or not st.session_state.usuario:
        usuario_input = st.text_input("Informe seu nome de usuário:", value=usuario_inicial, key="usuario_input")
        if usuario_input and usuario_input != usuario_inicial:
            st.query_params.update({"usuario": usuario_input})
            st.session_state.usuario = usuario_input
            st.rerun()
        usuario = usuario_input
    else:
        st.markdown(f"👤 Usuário: **{st.session_state.usuario}**")
        if st.button("🚪 Logout"):
            st.session_state.clear()
            st.markdown("<meta http-equiv='refresh' content='0;url=/?usuario=' />", unsafe_allow_html=True)
            st.stop()
        usuario = st.session_state.usuario

# 🔸 Carregar dados das vendas
dados_vendas = carregar_vendas(usuario)

# Ordenar por data de compra (mais antiga primeiro)
def parse_data_compra(v):
    try:
        return datetime.strptime(v["data_compra"], "%Y-%m-%d")
    except ValueError:
        return datetime.strptime(v["data_compra"], "%d/%m/%y")

dados_vendas.sort(key=parse_data_compra)

remover_venda = st.query_params.get("remover_venda", None)
if remover_venda is not None:
    deletar_venda(remover_venda)
    st.query_params.pop("remover_venda")
    st.rerun()

editar_venda_id = st.query_params.get("editar_venda", None)

if not dados_vendas:
    st.info("Nenhuma venda registrada até o momento.")
    st.stop()

# 🔢 Montar tabela formatada
st.subheader("💼 Operações Realizadas")

total_lucro = 0

# Cabeçalho
cols_header = st.columns([2.2, 2, 2.8, 2.4, 2.4, 2.6, 2.4, 3.2])
headers = ["", "Compra", "Ticker", "Quant.", "Compra (R$)", "Venda (R$)", "Venda", "Resultado (R$)"]
for i, (col, header) in enumerate(zip(cols_header, headers)):
    if i == 0:
        col.markdown("<p style='text-align: center; margin: 0; white-space: nowrap;'>&nbsp;</p>", unsafe_allow_html=True)
    else:
        col.markdown(f"<div style='margin: 2px 0; padding: 0; line-height: 1.1;'><b>{header}</b></div>", unsafe_allow_html=True)

# Linhas
for venda in dados_vendas:
    preco_compra = float(venda["preco_compra"])
    preco_venda = float(venda["preco_venda"])
    quantidade = int(venda["quantidade"])

    resultado = (preco_venda - preco_compra) * quantidade
    total_lucro += resultado

    resultado_formatado = f"R$ {resultado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    cor = "green" if resultado >= 0 else "red"
    acoes = f"""
    <div style='display: flex; justify-content: center; align-items: center; gap: 10px; height: 100%;'>
        <a href='?usuario={usuario}&remover_venda={venda['id']}' target="_self" style='color:red; text-decoration:none; font-size:18px;'>ⓧ</a>
        <a href='?usuario={usuario}&editar_venda={venda["id"]}' target="_self" style='color:#1a73e8; text-decoration:none; font-size:18px;'>✏️</a>
    </div>
    """.strip()
    valores = [
        acoes,
        datetime.strptime(venda["data_compra"], "%Y-%m-%d").strftime("%d/%m/%y") if "-" in venda["data_compra"] else venda["data_compra"],
        venda["ticker"],
        quantidade,
        f"R$ {preco_compra:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"R$ {preco_venda:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        datetime.strptime(venda["data_venda"], "%Y-%m-%d").strftime("%d/%m/%y") if "-" in venda["data_venda"] else venda["data_venda"],
        f"<span style='color:{'limegreen' if cor == 'green' else 'red'}; font-weight: 600;'>{resultado_formatado}</span>"
    ]

    cols = st.columns([2.2, 2, 2.8, 2.4, 2.4, 2.6, 2.4, 3])
    for col, val in zip(cols, valores):
        col.markdown(f"<div style='margin: 2px 0; padding: 0; line-height: 1.1;'>{val}</div>", unsafe_allow_html=True)

    # Formulário de edição logo abaixo da venda correspondente
    if editar_venda_id and editar_venda_id.strip().lower() == str(venda["id"]).strip().lower():
        with st.form(f"form_edicao_{venda['id']}"):
            st.markdown("**✏️ Editar Venda:**")
            try:
                data_compra_formatada = datetime.strptime(venda["data_compra"], "%Y-%m-%d").date()
            except ValueError:
                data_compra_formatada = datetime.strptime(venda["data_compra"], "%d/%m/%y").date()

            data_compra_str = st.text_input("Data de Compra (DD/MM/YY)", value=data_compra_formatada.strftime("%d/%m/%y"))
            nova_data_compra = datetime.strptime(data_compra_str, "%d/%m/%y").date()
            novo_ticker = st.text_input("Ticker", value=venda["ticker"])
            nova_quantidade = st.number_input("Quantidade", min_value=1, value=int(venda["quantidade"]), step=1)
            novo_preco_compra = st.number_input("Preço de Compra", min_value=0.0, format="%.2f", value=float(venda["preco_compra"]))
            novo_preco_venda = st.number_input("Preço de Venda", min_value=0.0, format="%.2f", value=float(venda["preco_venda"]))

            try:
                data_venda_formatada = datetime.strptime(venda["data_venda"], "%Y-%m-%d").date()
            except ValueError:
                data_venda_formatada = datetime.strptime(venda["data_venda"], "%d/%m/%y").date()

            data_venda_str = st.text_input("Data de Venda (DD/MM/YY)", value=data_venda_formatada.strftime("%d/%m/%y"))
            nova_data_venda = datetime.strptime(data_venda_str, "%d/%m/%y").date()

            submit = st.form_submit_button("Salvar alterações")
            if submit:
                from utils import editar_venda
                editar_venda(venda["id"], {
                    "data_compra": nova_data_compra.isoformat(),
                    "ticker": novo_ticker.strip().upper(),
                    "quantidade": nova_quantidade,
                    "preco_compra": novo_preco_compra,
                    "preco_venda": novo_preco_venda,
                    "data_venda": nova_data_venda.isoformat()
                })
                st.query_params.update({"usuario": usuario})
                st.query_params.pop("editar_venda")
                st.rerun()

# 🔥 Resultado total
st.markdown("---")
cor_final = "green" if total_lucro >= 0 else "red"
st.markdown(
    f"### 💰 Resultado Total: <span style='color:{cor_final};'>R$ {total_lucro:,.2f}</span>".replace(",", "X").replace(".", ",").replace("X", "."),
    unsafe_allow_html=True
)