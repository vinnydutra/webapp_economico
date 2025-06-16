import streamlit as st
from utils import calcular_custo_ajustado
from datetime import date

from utils import supabase_autenticado
supabase = supabase_autenticado()
import time
import re

from utils import restaurar_usuario_sessao
restaurar_usuario_sessao()

from utils import carregar_carteira_supabase

st.set_page_config(page_title="Posição Atual", page_icon="📊", layout="wide")

from utils import calcular_desempenho_consolidado
from utils import importar_nota_xp_pdf
from utils import obter_total_dividendos_para_lote
from utils import carregar_dividendos_usuario, inserir_dividendo
import tempfile
import os

from datetime import datetime
import pandas as pd

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

# Nova função para obter preço float
def obter_preco_ativo_float(ticker):
    try:
        ticker_yf = yf.Ticker(ticker)
        hist = ticker_yf.history(period="5d")
        preco_atual = hist['Close'].dropna().iloc[-1]
        return round(float(preco_atual), 2)
    except Exception:
        return 0.0


with st.sidebar:
    if "usuario" in st.session_state and st.session_state.usuario:
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
    else:
        st.info("Usuário não autenticado.")
        st.stop()


usuario = st.session_state.uid



# Importa funções utilitárias para carregar e salvar a carteira
from utils import (
    carregar_carteira_supabase,
    inserir_ativo_carteira,
    deletar_ativo_carteira,
    inserir_venda,
    adicionar_favorito,
    remover_favorito
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

# Elimina o espaçamento entre linhas da tabela
st.markdown("""
<style>
section.main > div.block-container > div {
    margin-bottom: -1px !important;
    padding-bottom: 0px !important;
}
</style>
""", unsafe_allow_html=True)


st.title("Posição Atual da Carteira")




# Reset do campo de upload após importação
if st.session_state.get("pdf_upload_done"):
    st.session_state["pdf_upload_done"] = False
    st.rerun()

# Geração e controle da chave do file_uploader
if "file_uploader_key" not in st.session_state:
    st.session_state["file_uploader_key"] = str(time.time())

with st.expander("Importar Nota de Negociação"):
    arquivos_pdf = st.file_uploader(
        "Importar Nota XP (PDF)",
        type=["pdf"],
        accept_multiple_files=True,
        key=st.session_state["file_uploader_key"],
        label_visibility="collapsed"
    )
    ativos_importados_total = []
    if arquivos_pdf:
        for arquivo_pdf in arquivos_pdf:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(arquivo_pdf.read())
                caminho_temp = temp_file.name
            try:
                ativos_importados = importar_nota_xp_pdf(caminho_temp, usuario)
                import fitz
                with fitz.open(caminho_temp) as doc:
                    texto = "\n".join([page.get_text() for page in doc])
                os.remove(caminho_temp)

                if ativos_importados:
                    ativos_importados_total.extend(ativos_importados)
                    st.markdown(f"### ✅ Ativos identificados na nota: `{arquivo_pdf.name}`")
                    for ativo in ativos_importados:
                        st.markdown(
                            f"- **Ticker:** `{ativo['Ticker']}` | **Quantidade:** {ativo['Quantidade']} | "
                            f"**Custo unitário:** R$ {ativo['Custo']} | **Data:** {ativo['Data de Compra']}"
                        )
                else:
                    st.warning(f"Nenhum ativo encontrado na nota: `{arquivo_pdf.name}`")
            except Exception as e:
                st.error(f"Erro ao importar `{arquivo_pdf.name}`: {str(e)}")

        if ativos_importados_total and st.button("Importar ativos para a carteira"):
            for ativo in ativos_importados_total:
                preco_float = float(ativo["Custo"].replace(",", "."))
                inserir_ativo_carteira(
                    usuario,
                    ativo["Ticker"],
                    ativo["Quantidade"],
                    preco_float,
                    ativo["Data de Compra"]
                )
            # Recarrega a carteira direto da Supabase para evitar duplicações
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
            st.success(f"{len(ativos_importados_total)} ativo(s) importado(s) com sucesso!")
            st.session_state["file_uploader_key"] = str(time.time())
            st.rerun()






# Carrega dados da carteira do usuário e inicializa o estado da sessão
if "posicao_atual" not in st.session_state or not st.session_state.posicao_atual:
    dados_carteira = carregar_carteira_supabase(usuario)
    st.session_state.posicao_atual = [
        {
            "UUID": item["id"],
            "Ticker": item["ticker"],
            "Quantidade": item["quantidade"],
            "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
            "Data de Compra": item["data_compra"]
        }
        for item in dados_carteira
    ]

# Ordena os ativos pela data de compra do mais antigo para o mais recente
st.session_state.posicao_atual.sort(
    key=lambda x: parse_data_compra(x.get("Data de Compra", "01/01/1900"))
)

# Corrige dados antigos que usam "Preço Pago (R$)"
for item in st.session_state.posicao_atual:
    if "Preço Pago (R$)" in item:
        item["Custo"] = item.pop("Preço Pago (R$)")






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
        # Recarrega a carteira diretamente da fonte (Supabase) para garantir sincronização
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
        st.success("Ativo adicionado com sucesso!")
    else:
        st.warning("Preencha todos os campos corretamente.")





#
# Novo cálculo direto do desempenho usando função utilitária consolidada
# Após o cálculo, consolidar tickers únicos
desempenho = calcular_desempenho_consolidado(st.session_state.posicao_atual)
# Consolidar tickers únicos (mantendo a ordem do primeiro aparecimento)
desempenho = list(dict((ativo["ticker"].upper(), ativo) for ativo in desempenho).values())
# Ordenar pelo campo variacao_percentual do maior para o menor
desempenho.sort(key=lambda x: x["variacao_percentual"], reverse=True)

st.markdown("""
<style>
.balao {
    display: inline-block;
    padding: 10px 15px;
    margin: 5px;
    border-radius: 12px;
    background-color: #262730;  /* mesma cor escura da barra lateral */
    font-family: sans-serif;
    text-align: center;
    min-width: 120px;
}
.balao .ticker {
    font-weight: bold;
    font-size: 16px;
    color: white;
}
.balao .percentual, .balao .reais {
    font-size: 14px;
}
</style>
""", unsafe_allow_html=True)

html_baloes = ""
tickers_exibidos = set()
for ativo in desempenho:
    ticker = ativo["ticker"].upper()
    if ticker in tickers_exibidos:
        continue
    tickers_exibidos.add(ticker)
    cor = "#00cc00" if ativo["variacao_reais"] > 0 else "#ff3333"
    variacao_r = f'R$ {ativo["variacao_reais"]:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".")
    variacao_p = f'{ativo["variacao_percentual"]:+.2f}%'.replace(".", ",")
    html_baloes += (
        f"<a href='/Analise_Financeira?ticker={ticker}' target='_self' style='text-decoration: none;'>"
        f"<div class='balao'>"
        f"<div class='ticker'>{ticker}</div>"
        f"<div class='percentual' style='color:{cor};'>{variacao_p}</div>"
        f"<div class='reais' style='color:{cor};'>{variacao_r}</div>"
        f"</div></a>"
    )

st.markdown(f"""
    <div style='display:flex; flex-wrap:wrap; margin-bottom: 30px;'>
        {html_baloes}
    </div>
""", unsafe_allow_html=True)


# Exibe a tabela da carteira como linhas clicáveis
st.subheader("Carteira Atual")

st.markdown("""
<style>
.tabela-header {
    font-weight: bold;
    background-color: #262730;
    padding: 8px;
    border-bottom: 1px solid #444;
    border: 1px solid #555;
}
.tabela-linha {
    padding: 6px;
    border-bottom: 1px solid #333;
    border: 1px solid #444;
}
.tabela-linha:hover {
    background-color: #333 !important;
    cursor: default;
}
</style>
""", unsafe_allow_html=True)

header_cols = st.columns([1.5, 1.6, 1.2, 1.5, 2, 1.8, 1.5, 1.8, 1])
header_cols[0].markdown("<div class='tabela-header'>Compra</div>", unsafe_allow_html=True)
header_cols[1].markdown("<div class='tabela-header'>Ticker</div>", unsafe_allow_html=True)
header_cols[2].markdown("<div class='tabela-header'>Quant.</div>", unsafe_allow_html=True)
header_cols[3].markdown("<div class='tabela-header'>Custo</div>", unsafe_allow_html=True)
header_cols[4].markdown("<div class='tabela-header'>Total</div>", unsafe_allow_html=True)
header_cols[5].markdown("<div class='tabela-header'>Preço</div>", unsafe_allow_html=True)
header_cols[6].markdown("<div class='tabela-header'>Var. %</div>", unsafe_allow_html=True)
header_cols[7].markdown("<div class='tabela-header'>Var. R$</div>", unsafe_allow_html=True)
header_cols[8].markdown("<div class='tabela-header'>Ação</div>", unsafe_allow_html=True)

for item in st.session_state.posicao_atual:
    row = st.columns([1.5, 1.6, 1.2, 1.5, 2, 1.8, 1.5, 1.8, 1])
    row[0].markdown(f"<div class='tabela-linha'>{item['Data de Compra']}</div>", unsafe_allow_html=True)
    row[1].markdown(f"<div class='tabela-linha'>{item['Ticker']}</div>", unsafe_allow_html=True)
    row[2].markdown(f"<div class='tabela-linha'>{item['Quantidade']}</div>", unsafe_allow_html=True)
    # NOVA LÓGICA PARA A CÉLULA "Custo"
    ticker = item["Ticker"]
    data_compra = parse_data_compra(item["Data de Compra"])
    quantidade = item["Quantidade"]
    custo_original = float(item["Custo"].replace(",", "."))
    res = supabase.table("dividendos_recebidos").select("*").eq("ticker", ticker).gte("data", str(data_compra)).lte("data", str(date.today())).execute()
    dividendos_brutos = res.data or []
    dividendos_formatados = [{"valor": d["valor"], "quantidade": 1} for d in dividendos_brutos]
    custo_ajustado = calcular_custo_ajustado(custo_original, quantidade, dividendos_formatados)
    dividendos_unitarios_total = sum(d["valor"] for d in dividendos_brutos)
    if dividendos_unitarios_total > 0:
        tooltip = f"Custo real: R$ {custo_original:,.2f} | Dividendos: R$ {dividendos_unitarios_total:,.2f}"
        custo_formatado = f"<span title='{tooltip}'>R$ {custo_ajustado:,.2f}*</span>"
    else:
        custo_formatado = f"R$ {custo_original:,.2f}"
    row[3].markdown(f"<div class='tabela-linha'>{custo_formatado}</div>", unsafe_allow_html=True)
    # O campo "Total (R$)" agora reflete o custo ajustado por dividendos:
    total = quantidade * custo_ajustado
    total_formatado = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    row[4].markdown(f"<div class='tabela-linha'>{total_formatado}</div>", unsafe_allow_html=True)
    preco_ultimo = obter_preco_ativo(item["Ticker"])
    row[5].markdown(f"<div class='tabela-linha'>{preco_ultimo}</div>", unsafe_allow_html=True)
    try:
        preco_atual = float(obter_preco_ativo_float(item["Ticker"]))
        custo = float(item["Custo"].replace(",", "."))
        variacao_percentual = ((preco_atual - custo) / custo) * 100 if custo > 0 else 0
        cor = "#00cc00" if variacao_percentual >= 0 else "#ff3333"
        variacao_formatada = f"{variacao_percentual:+.2f}%".replace(".", ",")
        row[6].markdown(f"<div class='tabela-linha' style='color:{cor};'>{variacao_formatada}</div>", unsafe_allow_html=True)
    except Exception:
        row[6].markdown("<div class='tabela-linha'>Erro</div>", unsafe_allow_html=True)
    try:
        preco_atual = float(obter_preco_ativo_float(item["Ticker"]))
        custo = float(item["Custo"].replace(",", "."))
        quantidade = item["Quantidade"]
        variacao_reais = (preco_atual - custo) * quantidade
        cor_reais = "#00cc00" if variacao_reais >= 0 else "#ff3333"
        variacao_reais_formatada = f"R$ {variacao_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        row[7].markdown(f"<div class='tabela-linha' style='color:{cor_reais};'>{variacao_reais_formatada}</div>", unsafe_allow_html=True)
    except Exception:
        row[7].markdown("<div class='tabela-linha'>Erro</div>", unsafe_allow_html=True)
    if row[8].button("⚙️", key=f"selec_{item['UUID']}"):
        st.session_state.ativo_selecionado = item
        st.session_state.modo_edicao = None
        st.rerun()
    if isinstance(st.session_state.get("ativo_selecionado"), dict) and item["UUID"] == st.session_state.ativo_selecionado["UUID"]:
        # Bloco de edição de ativo: formulário de edição
        if st.session_state.get("modo_edicao") == item["UUID"]:
            with st.form(f"form_edicao_{item['UUID']}"):
                col_qtd, col_custo, col_data = st.columns([2, 2, 3])
                with col_qtd:
                    nova_quantidade = st.number_input("Nova Quantidade", min_value=1, value=item["Quantidade"], step=1)
                with col_custo:
                    novo_custo = st.number_input("Novo Custo (R$)", min_value=0.0, value=float(item["Custo"].replace(",", ".")), step=0.01)
                with col_data:
                    # Novo widget de data
                    nova_data_obj = datetime.strptime(item["Data de Compra"], "%d/%m/%y")
                    nova_data = st.date_input("Nova Data de Compra", value=nova_data_obj, format="DD/MM/YYYY")
                col1, col2, col3 = st.columns([3, 10, 2])
                with col1:
                    salvar = st.form_submit_button("💾 Salvar Alterações")
                with col3:
                    cancelar = st.form_submit_button("↩️ Cancelar")

                if cancelar:
                    st.session_state.modo_edicao = None
                    st.rerun()
                if salvar:
                    from utils import editar_ativo_carteira, carregar_carteira_supabase
                    try:
                        # nova_data já é date, garantir formato
                        novos_dados = {
                            "quantidade": int(nova_quantidade),
                            "custo": float(novo_custo),
                            "data_compra": nova_data.strftime("%d/%m/%y")
                        }
                        resposta = editar_ativo_carteira(item["UUID"], novos_dados)
                        if resposta:
                            st.session_state.posicao_atual = [
                                {
                                    "UUID": reg["id"],
                                    "Ticker": reg["ticker"],
                                    "Quantidade": reg["quantidade"],
                                    "Custo": f'{reg["custo"]:.2f}'.replace('.', ','),
                                    "Data de Compra": reg["data_compra"]
                                }
                                for reg in carregar_carteira_supabase(usuario)
                            ]
                            st.success("Ativo atualizado com sucesso!")
                            st.session_state.ativo_selecionado = None
                            st.session_state.modo_edicao = None
                            st.rerun()
                        else:
                            st.error("Erro ao atualizar ativo.")
                    except Exception as e:
                        st.error("Data inválida. Use o formato DD/MM/YY.")
        elif st.session_state.get("modo_venda") == item["UUID"]:
            with st.form(f"form_venda_{item['UUID']}"):
                col_qtd_venda, col_preco_venda, col_data_venda = st.columns([2, 2, 3])
                with col_qtd_venda:
                    qtd_venda = st.number_input(
                        "Quantidade Vendida",
                        min_value=1,
                        max_value=item["Quantidade"],
                        value=item["Quantidade"],
                        step=1
                    )
                with col_preco_venda:
                    preco_venda = st.number_input(
                        "Preço de Venda (R$)",
                        min_value=0.0,
                        step=0.01,
                        value=obter_preco_ativo_float(item["Ticker"])
                    )
                with col_data_venda:
                    data_venda = st.date_input("Data da Venda", value=datetime.now(), format="DD/MM/YYYY")

                col1_venda, col2_venda, col3_venda = st.columns([3, 10, 2])
                with col1_venda:
                    confirmar_venda = st.form_submit_button("💾 Confirmar Venda")
                with col3_venda:
                    cancelar_venda = st.form_submit_button("↩️ Cancelar")

                if cancelar_venda:
                    st.session_state.modo_venda = None
                    st.rerun()

                if confirmar_venda:
                    from utils import inserir_venda, editar_ativo_carteira, deletar_ativo_carteira, carregar_carteira_supabase
                    try:
                        venda_ok = inserir_venda(
                            usuario,
                            item["Ticker"],
                            qtd_venda,
                            float(item["Custo"].replace(",", ".")),
                            item["Data de Compra"],
                            float(preco_venda),
                            data_venda.strftime("%d/%m/%y")
                        )
                        if venda_ok:
                            nova_qtd = item["Quantidade"] - qtd_venda
                            if nova_qtd > 0:
                                editar_ativo_carteira(item["UUID"], {"quantidade": nova_qtd})
                            else:
                                deletar_ativo_carteira(item["UUID"])
                            st.session_state.posicao_atual = [
                                {
                                    "UUID": reg["id"],
                                    "Ticker": reg["ticker"],
                                    "Quantidade": reg["quantidade"],
                                    "Custo": f'{reg["custo"]:.2f}'.replace('.', ','),
                                    "Data de Compra": reg["data_compra"]
                                }
                                for reg in carregar_carteira_supabase(usuario)
                            ]
                            st.success("Venda registrada com sucesso!")
                            st.session_state.ativo_selecionado = None
                            st.session_state.modo_venda = None
                            st.rerun()
                        else:
                            st.error("Erro ao registrar venda.")
                    except Exception as e:
                        st.error("Erro ao processar a venda.")
        # Estilo aprimorado para a tabela de botões de ação
        st.markdown("""
<style>
.botoes-tabela {
    display: flex;
    gap: 10px;
    padding: 10px;
    border: 1px solid #888;
    border-radius: 6px;
    margin: 10px 0;
    background-color: #1a1a1a;
}
.botoes-tabela > div {
    flex: 1;
    border: 1px solid #444;
}
</style>
""", unsafe_allow_html=True)
        with st.container():
            # CSS para remover o espaço entre a linha da tabela e os botões de forma mais eficaz e restrita
            st.markdown("""
<style>
div.botoes-container {
    margin-top: -30px !important;
    padding-top: 0 !important;
}
.botoes-container > div {
    margin-top: 0 !important;
}
</style>
""", unsafe_allow_html=True)
            st.markdown('<div class="botoes-container">', unsafe_allow_html=True)
            # NOVA LÓGICA DE BOTÕES (condicional modo_edicao ou modo_venda)
            if st.session_state.get("modo_edicao") == item["UUID"] or st.session_state.get("modo_venda") == item["UUID"]:
                pass
            else:
                botoes = st.columns([0.19, 0.12, 0.14, 0.55], gap="small")
                with botoes[0]:
                    if st.button("✅ Registrar Venda", key=f"vender_{item['UUID']}"):
                        st.session_state.modo_venda = item["UUID"]
                        st.session_state.modo_edicao = None
                        st.rerun()
                with botoes[1]:
                    if st.button("✏️ Editar", key=f"editar_{item['UUID']}"):
                        st.session_state.modo_edicao = item["UUID"]
                        st.rerun()
                with botoes[2]:
                    if st.button("❌ Excluir", key=f"excluir_{item['UUID']}"):
                        resposta = deletar_ativo_carteira(item["UUID"])
                        if hasattr(resposta, "data") and resposta.data:
                            st.session_state.posicao_atual = [
                                ativo for ativo in st.session_state.posicao_atual
                                if ativo["UUID"] != item["UUID"]
                            ]
                            st.success("Ativo excluído com sucesso.")
                            st.session_state.ativo_selecionado = None
                            st.rerun()
                        else:
                            st.error("Erro ao tentar excluir o ativo.")
                with botoes[3]:
                    col_a, col_b = st.columns([4, 2])
                    with col_b:
                        if st.button("↩️ Cancelar", key=f"cancelar_{item['UUID']}"):
                            st.session_state.ativo_selecionado = None
                            st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

