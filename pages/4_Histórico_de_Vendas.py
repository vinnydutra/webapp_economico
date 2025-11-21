import streamlit as st
from utils import carregar_vendas, deletar_venda, obter_total_dividendos_para_lote_intervalado, obter_credito_opcoes_para_lote_intervalado
from datetime import datetime
from utils import get_logo_img_tag



st.set_page_config(page_title="Histórico de Vendas", layout="wide")

# CSS para remover margens laterais e limitações de largura, e ajustar espaçamento superior
st.markdown("""
<style>
/* Remove margens laterais e limitações de largura em qualquer versão do Streamlit */
main > div.block-container, section.main > div.block-container, .block-container {
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    max-width: 100% !important;
    padding-top: 1rem;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Tooltip padrão (mesmo estilo conceitual da Pág. 3) */
.tipwrap {
  position: relative;
  display: inline-block;
  cursor: help;
}
.tipwrap::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  transform: translateX(-50%);
  bottom: 125%;
  background: #333;
  color: #fff;
  padding: 6px 8px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.2;
  white-space: nowrap;
  border: 1px solid #444;
  box-shadow: 0 2px 8px rgba(0,0,0,0.5);
  opacity: 0;
  pointer-events: none;
  transition: opacity .12s ease-in-out;
  z-index: 9999;
  width: fit-content;
}
.tipwrap:hover::after {
  opacity: 1;
}
</style>
""", unsafe_allow_html=True)

# Verificar sessão do usuário e restaurar se necessário
if "usuario" not in st.session_state or not st.session_state.usuario:
    st.info("Usuário não autenticado.")
    st.stop()
usuario_logado = st.session_state.get("usuario", "desconhecido")

# Restaurar sessão via query_params se uid estiver ausente
if "uid" not in st.session_state:
    from utils import restaurar_sessao_via_query_param
    restaurar_sessao_via_query_param()
    st.experimental_rerun()

# Lógica de logout
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

# Bloco do usuário e logout no topo da tela
st.markdown(f"""
<br>
<div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 0px;'>
    <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
    <form action='/?logout=true' method='get'>
        <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
    </form>
</div>
""", unsafe_allow_html=True)

# CSS para remover margem superior do título <h1> gerado por st.title
st.markdown("""
    <style>
    h1 {
        margin-top: 0rem;
    }
    </style>
""", unsafe_allow_html=True)


st.title("Histórico de Vendas")

with st.sidebar:
    pass

# 🔸 Carregar dados das vendas
uid = st.session_state.get("uid")
dados_vendas = carregar_vendas(uid) if uid else []

# Ordenar por data de compra (mais antiga primeiro)
def parse_data_compra(v):
    try:
        return datetime.strptime(v["data_compra"], "%Y-%m-%d")
    except ValueError:
        return datetime.strptime(v["data_compra"], "%d/%m/%y")

dados_vendas.sort(key=lambda v: datetime.strptime(v["data_venda"], "%Y-%m-%d") if "-" in v["data_venda"] else datetime.strptime(v["data_venda"], "%d/%m/%y"), reverse=True)

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
    data_compra = venda["data_compra"]
    data_venda = venda["data_venda"]

    dividendos_recebidos = obter_total_dividendos_para_lote_intervalado(
        st.session_state.uid,
        ticker,
        data_compra,
        data_venda
    )
    creditos_opcoes = obter_credito_opcoes_para_lote_intervalado(
        st.session_state.uid,
        ticker,
        data_compra,
        data_venda,
        quantidade
    )
    custo_ajustado = max(preco_compra - dividendos_recebidos - creditos_opcoes, 0)

    if ticker not in desempenho_ativos:
        desempenho_ativos[ticker] = {
            "quantidade_total": 0,
            "custo_total": 0.0,
            "valor_venda_total": 0.0
        }

    desempenho_ativos[ticker]["quantidade_total"] += quantidade
    desempenho_ativos[ticker]["custo_total"] += custo_ajustado * quantidade
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
    creditos_opcoes = obter_credito_opcoes_para_lote_intervalado(
        st.session_state.uid,
        ticker,
        data_compra,
        data_venda,
        quantidade
    )
    custo_ajustado = max(preco_compra - dividendos_recebidos - creditos_opcoes, 0)
    resultado = (preco_venda - custo_ajustado) * quantidade
    total_lucro += resultado

st.markdown("---")
cor_final = "green" if total_lucro >= 0 else "red"
st.markdown(
    f"###  Resultado Total: <span style='color:{cor_final};'>R$ {total_lucro:,.2f}</span>".replace(",", "X").replace(".", ",").replace("X", "."),
    unsafe_allow_html=True
)
# 🆕 NOVO BLOCO – Operações Realizadas (Novo Estilo)
st.markdown("---")
st.subheader("🧾 Operações Realizadas")

# CSS reaplicado no local correto, antes da renderização da tabela

st.markdown("""
    <style>
    .tabela-linha {
        padding: 10px 6px;
        border: 1px solid #444;
    }
    </style>
""", unsafe_allow_html=True)

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

nova_cols_header = st.columns([1, 1.5, 1.2, 1.6, 1.6, 1.6, 1.8, 1.4, 1.4, 1.0])
nova_headers = ["Logo", "Ticker", "Quant.", "Custo", "Total", "Venda", "Resultado", "Data C.", "Data V.", "Ação"]

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
    creditos_opcoes = obter_credito_opcoes_para_lote_intervalado(
        st.session_state.uid,
        ticker,
        data_compra,
        data_venda,
        quantidade
    )
    custo_ajustado = max(preco_compra - dividendos_recebidos - creditos_opcoes, 0)

    resultado = (preco_venda - custo_ajustado) * quantidade
    cor = "#00cc00" if resultado >= 0 else "#ff3333"
    resultado_formatado = f"R$ {resultado:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    total_formatado = f"R$ {(custo_ajustado * quantidade):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


    col_acao = venda["id"]  # Usado como referência de ID para botão

    logo_html = get_logo_img_tag(ticker)

    # Exibir célula “Custo” com * e tooltip quando houver ajuste:
    if (dividendos_recebidos > 0) or (creditos_opcoes > 0):
        tooltip = (
            f"Custo Base: R$ {preco_compra:,.2f} | "
            f"Dividendos: R$ {dividendos_recebidos:,.2f} | "
            f"Opções: R$ {creditos_opcoes:,.2f}"
        )
        custo_cell = (
            f"<span class='tipwrap' data-tip='{tooltip}'>R$ {custo_ajustado:,.2f}*</span>"
        ).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        custo_cell = f"R$ {preco_compra:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

    valores = [
        f"<div style='text-align:center'>{logo_html}</div>",
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

    linha = st.columns([1, 1.5, 1.2, 1.6, 1.6, 1.6, 1.8, 1.4, 1.4, 1.0])
    for i, (col, val) in enumerate(zip(linha, valores)):
        if i == 9:  # coluna "Ação"
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
            col1, col2, col3, col4, col5, col6 = st.columns([1.0, 1.1, 1.1, 1.1, 1.3, 1.2])

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

            with col6:
                novo_irrf = st.number_input("IRRF (R$)", min_value=0.0, value=float(venda.get("irrf") or 0.0), step=0.01, format="%.2f")

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
                        data_venda=nova_data_venda.strftime("%Y-%m-%d"),
                        irrf=novo_irrf
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
