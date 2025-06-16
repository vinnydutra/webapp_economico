import streamlit as st
from utils import carregar_vendas, deletar_venda, obter_total_dividendos_para_lote_intervalado
from datetime import datetime



st.set_page_config(page_title="Histórico de Vendas", layout="wide")

# Remover margens laterais excessivas (mesmo CSS da Página 3)
st.markdown("""
    <style>
    .main .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 0.5rem;
        max-width: 100%;
    }
    .block-container {
        max-width: 100%;
        width: 100%;
    }
    </style>
""", unsafe_allow_html=True)

# CSS para linhas da tabela (igual ao estilo da Página 3)
st.markdown("""
    <style>
    .tabela-linha {
        padding: 10px 6px;
        border: 1px solid #444;
    }
    </style>
""", unsafe_allow_html=True)

# CSS para cabeçalho de tabela (tabela-header) igual ao da Página 3
st.markdown("""
    <style>
    .tabela-header {
        font-weight: bold;
        background-color: #262730;
        padding: 8px;
        border-bottom: 1px solid #444;
        border: 1px solid #555;
        text-align: center;
    }
    </style>
""", unsafe_allow_html=True)

# Verificar sessão do usuário e restaurar se necessário
if "usuario" not in st.session_state or "uid" not in st.session_state:
    from utils import restaurar_sessao_via_query_param
    restaurar_sessao_via_query_param()
    st.experimental_rerun()

st.title("📜 Histórico de Vendas")

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

# 🔸 Carregar dados das vendas
dados_vendas = carregar_vendas(st.session_state.uid)

# Ordenar por data de compra (mais antiga primeiro)
def parse_data_compra(v):
    try:
        return datetime.strptime(v["data_compra"], "%Y-%m-%d")
    except ValueError:
        return datetime.strptime(v["data_compra"], "%d/%m/%y")

dados_vendas.sort(key=parse_data_compra)

editar_venda_id = st.session_state.get("editar_venda_id")

if not dados_vendas:
    st.info("Nenhuma venda registrada até o momento.")
    st.stop()

#
# 📊 Balões de desempenho consolidados por ativo
desempenho_ativos = {}

for venda in dados_vendas:
    ticker = venda["ticker"].strip().upper()
    preco_compra = float(venda["preco_compra"])
    preco_venda = float(venda["preco_venda"])
    quantidade = int(venda["quantidade"])

    if ticker not in desempenho_ativos:
        desempenho_ativos[ticker] = {
            "quantidade_total": 0,
            "custo_total": 0.0,
            "valor_venda_total": 0.0
        }

    desempenho_ativos[ticker]["quantidade_total"] += quantidade
    desempenho_ativos[ticker]["custo_total"] += preco_compra * quantidade
    desempenho_ativos[ticker]["valor_venda_total"] += preco_venda * quantidade

# 🔥 Resultado total
total_lucro = 0
for venda in dados_vendas:
    preco_compra = float(venda["preco_compra"])
    preco_venda = float(venda["preco_venda"])
    quantidade = int(venda["quantidade"])
    data_compra = venda["data_compra"]
    data_venda = venda["data_venda"]
    ticker = venda["ticker"].strip().upper()
    dividendos_recebidos = obter_total_dividendos_para_lote_intervalado(st.session_state.uid, ticker, data_compra, data_venda)
    custo_ajustado = max(preco_compra - dividendos_recebidos, 0)
    resultado = (preco_venda - custo_ajustado) * quantidade
    total_lucro += resultado

st.markdown("---")
cor_final = "green" if total_lucro >= 0 else "red"
st.markdown(
    f"###  Resultado Total: <span style='color:{cor_final};'>R$ {total_lucro:,.2f}</span>".replace(",", "X").replace(".", ",").replace("X", "."),
    unsafe_allow_html=True
)
st.markdown("###  Desempenho Consolidado por Ativo")

baloes_html = []
for ticker, dados in desempenho_ativos.items():
    quantidade = dados["quantidade_total"]
    total_compra = dados["custo_total"]
    total_venda = dados["valor_venda_total"]
    resultado = total_venda - total_compra
    variacao_percentual = (resultado / total_compra) * 100 if total_compra > 0 else 0

    cor_resultado = "#00FF00"
    cor_percentual = "#00FF00"

    sinal_resultado = "+" if resultado > 0 else ""
    sinal_percentual = "+" if variacao_percentual > 0 else ""

    variacao_valor = f"{sinal_resultado}R$ {resultado:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    variacao_pct = f"{sinal_percentual}{variacao_percentual:.1f}%".replace('.', ',')

    link = f"/Analise_Financeira?ticker={ticker}"
    baloes_html.append((resultado, f"""
<a href='{link}' target='_self' style='text-decoration: none;'>
  <div style="background-color:#262730; border-radius:10px; padding:8px; margin:5px 5px 0 0; text-align:center; display:inline-block; min-width:120px;">
    <div style="color:white; font-weight:700; font-size:17px;">{ticker}</div>
    <div style="color:{cor_percentual}; font-weight:700; font-size:16px;">{variacao_pct}</div>
    <div style="color:{cor_resultado}; font-weight:700; font-size:16px;">{variacao_valor}</div>
  </div>
</a>
"""))

 # Ordenar por variação percentual descrescente
baloes_html.sort(
    key=lambda x: float(
        x[1].split('font-size:16px;">')[1].split('%')[0].replace(",", ".")
    ), reverse=True
)
html_final = "".join([b[1] for b in baloes_html])
st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
st.markdown(html_final, unsafe_allow_html=True)


# 🆕 NOVO BLOCO – Operações Realizadas (Novo Estilo)
st.markdown("---")
st.subheader("🧾 Operações Realizadas")

if st.session_state.get("editar_venda_id") is None:
    acao_id = st.query_params.get("acao")
    if acao_id:
        st.session_state["editar_venda_id"] = acao_id
        st.rerun()

nova_cols_header = st.columns([1.5, 1.2, 1.6, 1.6, 1.6, 1.8, 1.4, 1.4, 1.0])
nova_headers = ["Ticker", "Quant.", "Custo", "Total", "Venda", "Resultado", "Data C.", "Data V.", "Ação"]

for col, header in zip(nova_cols_header, nova_headers):
    col.markdown(f"<div class='tabela-header'>{header}</div>", unsafe_allow_html=True)

for venda in dados_vendas:
    preco_compra = float(venda["preco_compra"])
    preco_venda = float(venda["preco_venda"])
    quantidade = int(venda["quantidade"])

    data_compra = venda["data_compra"]
    data_venda = venda["data_venda"]
    ticker = venda["ticker"].strip().upper()
    # Corrigir chamada para aplicar filtro correto ao intervalo:
    dividendos_recebidos = obter_total_dividendos_para_lote_intervalado(
        st.session_state.uid,
        ticker,
        data_compra,
        data_venda
    )
    custo_ajustado = max(preco_compra - dividendos_recebidos, 0)

    resultado = (preco_venda - custo_ajustado) * quantidade
    cor = "#00cc00" if resultado >= 0 else "#ff3333"
    resultado_formatado = f"R$ {resultado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    total_formatado = f"R$ {(custo_ajustado * quantidade):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    col_acao = venda["id"]  # Usado como referência de ID para botão

    # Exibir célula “Custo” com * e tooltip quando houver ajuste:
    if dividendos_recebidos > 0:
        custo_cell = (
            f"<span title='Custo real: R$ {preco_compra:,.2f} | Dividendos: R$ {dividendos_recebidos:,.2f}'>R$ {custo_ajustado:,.2f}*</span>"
        ).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        custo_cell = f"R$ {preco_compra:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    valores = [
        ticker,
        quantidade,
        custo_cell,
        total_formatado,
        f"R$ {preco_venda:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        f"<span style='color:{cor}; font-weight:600;'>{resultado_formatado}</span>",
        datetime.strptime(data_compra, "%Y-%m-%d").strftime("%d/%m/%y") if "-" in data_compra else data_compra,
        datetime.strptime(data_venda, "%Y-%m-%d").strftime("%d/%m/%y") if "-" in data_venda else data_venda,
        col_acao
    ]

    linha = st.columns([1.5, 1.2, 1.6, 1.6, 1.6, 1.8, 1.4, 1.4, 1.0])
    for i, (col, val) in enumerate(zip(linha, valores)):
        if i == 8:  # coluna "Ação"
            with col:
                # Renderizar botão diretamente, sem colunas internas
                if st.button("⚙️", key=f"acao_{col_acao}"):
                    st.session_state["editar_venda_id"] = col_acao
                    st.session_state["modo_edicao"] = False
                    st.rerun()
        else:
            col.markdown(f"<div class='tabela-linha'>{val}</div>", unsafe_allow_html=True)

    # Se a linha está em modo edição, renderizar botões de ação (Editar, Excluir, Cancelar)
    if st.session_state.get("editar_venda_id") == venda["id"] and not st.session_state.get("modo_edicao"):
        with st.container():
            botoes = st.columns([0.2, 0.2, 0.2, 0.4])
            with botoes[0]:
                if st.button("✏️ Editar", key=f"editar_{venda['id']}"):
                    st.session_state["modo_edicao"] = True
                    st.rerun()
            with botoes[1]:
                if st.button("ⓧ Excluir", key=f"excluir_{venda['id']}"):
                    deletar_venda(venda["id"])
                    st.session_state.pop("editar_venda_id", None)
                    st.rerun()
            with botoes[3]:
                if st.button("↩️ Cancelar", key=f"cancelar_{venda['id']}"):
                    st.session_state.pop("editar_venda_id", None)
                    st.rerun()

    # Bloco de formulário de edição deve ser fora do bloco acima
    if st.session_state.get("modo_edicao") and st.session_state.get("editar_venda_id") == venda["id"]:
        with st.form(key=f"form_editar_{venda['id']}"):
            col1, col2, col3, col4, col5 = st.columns([1.1, 1.1, 1.1, 1.3, 1.3])

            with col1:
                nova_quantidade = st.number_input("Quantidade", min_value=1, value=quantidade, step=1)

            with col2:
                novo_preco_compra = st.number_input("Preço de Compra", min_value=0.0, value=preco_compra, step=0.01, format="%.2f")

            with col3:
                novo_preco_venda = st.number_input("Preço de Venda", min_value=0.0, value=preco_venda, step=0.01, format="%.2f")

            with col4:
                nova_data_compra = st.date_input(
                    "Data de Compra",
                    value=datetime.strptime(data_compra, "%Y-%m-%d") if "-" in data_compra else datetime.strptime(data_compra, "%d/%m/%y"),
                    format="DD/MM/YYYY"
                )

            with col5:
                nova_data_venda = st.date_input(
                    "Data de Venda",
                    value=datetime.strptime(data_venda, "%Y-%m-%d") if "-" in data_venda else datetime.strptime(data_venda, "%d/%m/%y"),
                    format="DD/MM/YYYY"
                )

            col1, col2, col3 = st.columns([3, 10, 2])
            with col1:
                if st.form_submit_button("💾 Salvar Alterações"):
                    from utils import atualizar_venda
                    atualizar_venda(
                        id=venda["id"],
                        preco_compra=novo_preco_compra,
                        preco_venda=novo_preco_venda,
                        quantidade=nova_quantidade,
                        data_compra=nova_data_compra.strftime("%Y-%m-%d"),
                        data_venda=nova_data_venda.strftime("%Y-%m-%d")
                    )
                    st.success("Venda atualizada com sucesso!")
                    st.session_state.pop("editar_venda_id", None)
                    st.session_state.pop("modo_edicao", None)
                    st.rerun()
            with col3:
                if st.form_submit_button("↩️ Cancelar"):
                    st.session_state.pop("editar_venda_id", None)
                    st.session_state.pop("modo_edicao", None)
                    st.rerun()