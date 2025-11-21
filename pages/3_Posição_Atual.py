import streamlit as st
from utils import calcular_custo_ajustado
from utils import get_logo_img_tag
from datetime import date
from utils import supabase_autenticado
from utils import alocar_coberturas_por_lote
supabase = supabase_autenticado()
import time
import re

from utils import restaurar_usuario_sessao
restaurar_usuario_sessao()

from utils import carregar_carteira_supabase

# Importa função para formatação correta do número
from utils import formatar_numero_para_float


st.set_page_config(page_title="Posição Atual", page_icon="📊", layout="wide")

# Margens e largura + redução do espaçamento superior para igualar a Página 4
st.markdown("""
<style>
/* Margens e largura + redução do espaçamento superior para igualar a Página 4 */
main > div.block-container, section.main > div.block-container, .block-container {
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    max-width: 100% !important;
    padding-top: 1rem !important;
}
/* Remove a margem superior do título principal */
h1 { margin-top: 0rem !important; }
</style>
""", unsafe_allow_html=True)

# Bloco de logout e usuário no topo
if "usuario" not in st.session_state or not st.session_state.usuario:
    st.info("Usuário não autenticado.")
    st.stop()

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

if st.query_params.get("logout") == "true":
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

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

 
# --- HELPERS DE CUSTO (pag3) ---
def _custo_final_unit_para_item(item, alloc_por_ticker, supabase_client):
    """
    Calcula o custo final unitário econômico do lote:
    (custo_original + custo_operacional/qtde) - dividendos_unitarios_acumulados - (credito_liquido_opcoes_alocado/qtde)
    Retorna: (custo_final_unit, detalhes_dict)
    """
    ticker = item["Ticker"].upper()
    data_compra = parse_data_compra(item["Data de Compra"])
    quantidade = int(item["Quantidade"]) if item.get("Quantidade") is not None else 0
    if quantidade <= 0:
        return 0.0, {"custo_base_unit": 0.0, "div_por_acao": 0.0, "opc_por_acao": 0.0}

    # custo original e custo operacional
    custo_original = formatar_numero_para_float(item["Custo"])
    custo_oper_total = formatar_numero_para_float(item.get("Custo Operacional"))
    custo_base_unit = custo_original + (custo_oper_total / quantidade if quantidade > 0 else 0.0)

    # dividendos (unitários por ação) no intervalo [data_compra, hoje]
    res = supabase_client.table("dividendos_recebidos").select("*") \
        .eq("ticker", ticker) \
        .gte("data", str(data_compra)) \
        .lte("data", str(date.today())) \
        .execute()
    dividendos_brutos = res.data or []
    dividendos_unit_total = sum(float(d.get("valor") or 0.0) for d in dividendos_brutos)  # somatório unitário

    # créditos de opções alocados ao lote
    alloc = (alloc_por_ticker.get(ticker) or {}).get("por_lote", {})
    lote_alloc = alloc.get(item.get("UUID"), {}) if item.get("UUID") else {}
    credito_total_opcoes = float(lote_alloc.get("credito_total", 0.0))

    # composição em totais do lote → voltar para unitário
    custo_bruto_total = custo_base_unit * quantidade
    desconto_div_total = dividendos_unit_total * quantidade
    desconto_opc_total = credito_total_opcoes

    custo_final_unit = max(
        0.0,
        (custo_bruto_total - desconto_div_total - desconto_opc_total) / quantidade
    )

    detalhes = {
        "custo_base_unit": custo_base_unit,
        "div_por_acao": dividendos_unit_total,
        "opc_por_acao": (desconto_opc_total / quantidade) if quantidade > 0 else 0.0,
    }
    return custo_final_unit, detalhes
# --- FIM HELPERS DE CUSTO ---

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

st.title("Posição Atual da Carteira")

# Debug visual para relações com venda coberta (fase 1)


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
                # Removido debug visual do conteúdo bruto do PDF
                os.remove(caminho_temp)

                if ativos_importados:
                    # Removido debug visual dos ativos importados em JSON
                    ativos_importados_total.extend(ativos_importados)
                    st.markdown(f"### ✅ Ativos identificados na nota: `{arquivo_pdf.name}`")
                    for ativo in ativos_importados:
                        custo_unitario = str(ativo.get("Custo", "")).strip()
                        custo_op = float(ativo.get("Custo Operacional", 0.0))
                        data_compra = ativo.get("Data de Compra", "").strip()

                        st.markdown(
                            f"""
                            <span style='font-weight:bold'>Ticker:</span> <span style='font-family: monospace;'>{ativo['Ticker']}</span> |
                            <span style='font-weight:bold'>Quantidade:</span> {ativo['Quantidade']} |
                            <span style='font-weight:bold'>Custo unitário:</span> R&#36; {custo_unitario} |
                            <span style='font-weight:bold'>Custo operacional:</span> R&#36; {custo_op:.2f} |
                            <span style='font-weight:bold'>Data:</span> {data_compra}
                            """,
                            unsafe_allow_html=True
                        )
                else:
                    st.warning(f"Nenhum ativo encontrado na nota: `{arquivo_pdf.name}`")
            except Exception as e:
                st.error(f"Erro ao importar `{arquivo_pdf.name}`: {str(e)}")

        if ativos_importados_total and st.button("Importar ativos para a carteira"):
            for ativo in ativos_importados_total:
                preco_float = float(ativo["Custo"].replace(",", "."))
                custo_op = ativo.get("Custo Operacional", 0.0)
                inserir_ativo_carteira(
                    usuario,
                    ativo["Ticker"],
                    ativo["Quantidade"],
                    preco_float,
                    ativo["Data de Compra"],
                    custo_op
                )
            # Recarrega a carteira direto da Supabase para evitar duplicações
            st.session_state.posicao_atual = [
                {
                    "UUID": item["id"],
                    "Ticker": item["ticker"],
                    "Quantidade": item["quantidade"],
                    "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
                    "Data de Compra": item["data_compra"],
                    "Custo Operacional": f'{float(item.get("custo_operacional") or 0):.2f}'.replace('.', ',')
                }
                for item in carregar_carteira_supabase(usuario)
            ]
            st.success(f"{len(ativos_importados_total)} ativo(s) importado(s) com sucesso!")
            st.session_state["file_uploader_key"] = str(time.time())
            st.rerun()






# Carrega dados da carteira do usuário e inicializa o estado da sessão
if "posicao_atual" not in st.session_state or not st.session_state.posicao_atual:
    # Consulta à tabela "carteira" com custo_operacional incluído
    dados_carteira = (
        supabase.table("carteira")
        .select("id, ticker, quantidade, custo, data_compra, custo_operacional")
        .eq("usuario", usuario)
        .execute()
        .data
        if hasattr(supabase.table("carteira").select("id, ticker, quantidade, custo, data_compra, custo_operacional").eq("usuario", usuario).execute(), "data")
        else []
    )
    st.session_state.posicao_atual = [
        {
            "UUID": item["id"],
            "Ticker": item["ticker"],
            "Quantidade": item["quantidade"],
            "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
            "Data de Compra": item["data_compra"],
            "Custo Operacional": f'{float(item.get("custo_operacional") or 0):.2f}'.replace('.', ',')
        }
        for item in dados_carteira
    ]

# Ordena os ativos pela data de compra do mais antigo para o mais recente
st.session_state.posicao_atual.sort(
    key=lambda x: parse_data_compra(x.get("Data de Compra", "01/01/1900"))
)

# Corrige dados antigos que usam "Preço Pago (R$)"
for idx, item in enumerate(st.session_state.posicao_atual):
    if "Preço Pago (R$)" in item:
        item["Custo"] = item.pop("Preço Pago (R$)")


# --------------------
# Pré-cálculo de alocações de coberturas por ticker (uma chamada por ticker)
# --------------------
from collections import defaultdict
_allocacoes_por_ticker = {}
_lotes_por_ticker = defaultdict(list)

# Monta os lotes por ticker (na ordem cronológica, já ordenado acima)
for _it in st.session_state.posicao_atual:
    _lotes_por_ticker[_it["Ticker"].upper()].append({
        "uuid": _it["UUID"],
        "data_compra": parse_data_compra(_it["Data de Compra"]),
        "quantidade": int(_it["Quantidade"]),
    })

# Chama o alocador uma vez por ticker
for _tk, _lots in _lotes_por_ticker.items():
    try:
        _alloc = alocar_coberturas_por_lote(st.session_state.uid, _tk, _lots)
        _allocacoes_por_ticker[_tk] = _alloc
    except Exception as _e:
        _allocacoes_por_ticker[_tk] = {"por_lote": {}, "ops": {}}






col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    ticker = st.text_input("Ticker").upper()
with col2:
    quantidade = st.number_input("Quantidade", min_value=0, step=1, format="%d")
with col3:
    preco = st.number_input("Custo (R$)", min_value=0.0, step=0.01)
with col4:
    data_compra_obj = st.date_input("Data de Compra", value=datetime.now(), format="DD/MM/YYYY")
with col5:
    custo_operacional = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f")

adicionar = st.button("Adicionar")

if adicionar:
    try:
        data_formatada = data_compra_obj.strftime("%d/%m/%y")
    except Exception:
        st.error("Data inválida! Use o formato DD/MM/YY.")
        st.stop()
    if ticker and quantidade > 0 and preco > 0:
        preco_str = f"{preco:.2f}".replace(".", ",")
        uuid_ativo = inserir_ativo_carteira(
            usuario,
            ticker,
            quantidade,
            float(preco),
            data_formatada,
            custo_operacional  # novo argumento
        )
        # Recarrega a carteira diretamente da fonte (Supabase) para garantir sincronização
        st.session_state.posicao_atual = [
            {
                "UUID": item["id"],
                "Ticker": item["ticker"],
                "Quantidade": item["quantidade"],
                "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
                "Data de Compra": item["data_compra"],
                "Custo Operacional": f'{float(item.get("custo_operacional") or 0):.2f}'.replace('.', ',')
            }
            for item in carregar_carteira_supabase(usuario)
        ]
        st.success("Ativo adicionado com sucesso!")
    else:
        st.warning("Preencha todos os campos corretamente.")





#
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

# Tooltip CSS for tipwrap class
st.markdown("""
<style>
.tipwrap {
    position: relative;
    cursor: default;
}
.tipwrap[data-tip]:hover::after {
    content: attr(data-tip);
    position: absolute;
    left: 0;
    top: -2.0rem;
    background: #2a2a2a;
    color: #eee;
    border: 1px solid #444;
    padding: 6px 8px;
    border-radius: 6px;
    white-space: nowrap;
    font-size: 12px;
    z-index: 9999;
}
</style>
""", unsafe_allow_html=True)

header_cols = st.columns([1.5, 1, 1.6, 1.2, 1.6, 2, 1.8, 1.5, 2.2, 1])
header_cols[0].markdown("<div class='tabela-header'>Compra</div>", unsafe_allow_html=True)
header_cols[1].markdown("<div class='tabela-header'>Logo</div>", unsafe_allow_html=True)
header_cols[2].markdown("<div class='tabela-header'>Ticker</div>", unsafe_allow_html=True)
header_cols[3].markdown("<div class='tabela-header'>Quant</div>", unsafe_allow_html=True)
header_cols[4].markdown("<div class='tabela-header'>Custo</div>", unsafe_allow_html=True)
header_cols[5].markdown("<div class='tabela-header'>Total</div>", unsafe_allow_html=True)
header_cols[6].markdown("<div class='tabela-header'>Preço</div>", unsafe_allow_html=True)
header_cols[7].markdown("<div class='tabela-header'>Var. %</div>", unsafe_allow_html=True)
header_cols[8].markdown("<div class='tabela-header'>Var. R$</div>", unsafe_allow_html=True)
header_cols[9].markdown("<div class='tabela-header'>Ação</div>", unsafe_allow_html=True)

# Cálculo do total geral da coluna "Total" (usando o custo unificado: dividendos + opções + custo operacional)
total_geral = 0.0
for _item in st.session_state.posicao_atual:
    try:
        _qt = int(_item.get("Quantidade") or 0)
        if _qt <= 0:
            continue
        _custo_unit, _ = _custo_final_unit_para_item(_item, _allocacoes_por_ticker, supabase)
        total_geral += _qt * _custo_unit
    except Exception:
        continue

for idx, item in enumerate(st.session_state.posicao_atual):
    row = st.columns([1.5, 1, 1.6, 1.2, 1.6, 2, 1.8, 1.5, 2.2, 1])
    row[0].markdown(f"<div class='tabela-linha'>{item['Data de Compra']}</div>", unsafe_allow_html=True)
    logo_html = get_logo_img_tag(item["Ticker"])
    row[1].markdown(f"<div class='tabela-linha' style='text-align:center'>{logo_html}</div>", unsafe_allow_html=True)
    _ticker_atual = item["Ticker"].upper()
    row[2].markdown(
        f"<div class='tabela-linha'>{_ticker_atual}</div>",
        unsafe_allow_html=True
    )
    row[3].markdown(f"<div class='tabela-linha'>{item['Quantidade']}</div>", unsafe_allow_html=True)
    # NOVA LÓGICA PARA A CÉLULA "Custo"
    # Reutiliza a função unificadora (custo base + custo operacional − dividendos − opções)
    custo_final_unit, det = _custo_final_unit_para_item(item, _allocacoes_por_ticker, supabase)

    # Monta tooltip com valores por ação
    tooltip = (
        f"Custo base: R$ {det['custo_base_unit']:,.2f}&nbsp;| "
        f"Dividendos: R$ {det['div_por_acao']:,.2f}&nbsp;| "
        f"Opções: R$ {det['opc_por_acao']:,.2f}"
    )
    # Ajusta para formatação PT-BR sem quebrar o HTML
    tooltip = tooltip.replace(",", "X").replace(".", ",").replace("X", ".")

    # Asterisco se houver influência (dividendos ou opções)
    marcador_influencia = "*" if (det["div_por_acao"] > 0 or det["opc_por_acao"] > 0) else ""

    custo_formatado = (
        f"<span class='tipwrap' data-tip=\"{tooltip}\">R$ {custo_final_unit:,.2f}</span>"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )
    if marcador_influencia:
        custo_formatado += marcador_influencia

    row[4].markdown(f"<div class='tabela-linha'>{custo_formatado}</div>", unsafe_allow_html=True)

    # O campo "Total (R$)" da linha deve refletir o mesmo custo unificado
    quantidade = int(item.get("Quantidade") or 0)
    total = quantidade * custo_final_unit
    total_formatado = f"R$ {total:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    participacao = (total / total_geral * 100) if total_geral > 0 else 0
    participacao_formatada = f"{participacao:.2f}%".replace(".", ",")
    row[5].markdown(
        f"<div class='tabela-linha' title='Participação: {participacao_formatada}'>{total_formatado}</div>",
        unsafe_allow_html=True
    )
    preco_ultimo = obter_preco_ativo(item["Ticker"])
    row[6].markdown(f"<div class='tabela-linha'>{preco_ultimo}</div>", unsafe_allow_html=True)
    try:
        preco_atual = float(obter_preco_ativo_float(item["Ticker"]))
        # custo = float(item["Custo"].replace(",", "."))
        custo = custo_final_unit
        variacao_percentual = ((preco_atual - custo) / custo) * 100 if custo > 0 else 0
        cor = "#00cc00" if variacao_percentual >= 0 else "#ff3333"
        variacao_formatada = f"{variacao_percentual:+.2f}%".replace(".", ",")
        row[7].markdown(f"<div class='tabela-linha' style='color:{cor};'>{variacao_formatada}</div>", unsafe_allow_html=True)
    except Exception:
        row[7].markdown("<div class='tabela-linha'>Erro</div>", unsafe_allow_html=True)
    try:
        preco_atual = float(obter_preco_ativo_float(item["Ticker"]))
        # custo = float(item["Custo"].replace(",", "."))
        custo = custo_final_unit
        quantidade = item["Quantidade"]
        variacao_reais = (preco_atual - custo) * quantidade
        cor_reais = "#00cc00" if variacao_reais >= 0 else "#ff3333"
        variacao_reais_formatada = f"R$ {variacao_reais:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        row[8].markdown(f"<div class='tabela-linha' style='color:{cor_reais};'>{variacao_reais_formatada}</div>", unsafe_allow_html=True)
    except Exception:
        row[8].markdown("<div class='tabela-linha'>Erro</div>", unsafe_allow_html=True)
    if row[9].button("⚙️", key=f"selec_{item['UUID']}"):
        st.session_state.ativo_selecionado = item
        st.session_state.modo_edicao = None
    if isinstance(st.session_state.get("ativo_selecionado"), dict) and item["UUID"] == st.session_state.ativo_selecionado["UUID"]:
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
            with botoes[1]:
                if st.button("✏️ Editar", key=f"editar_{item['UUID']}"):
                    st.session_state.modo_edicao = item["UUID"]
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
                    else:
                        st.error("Erro ao tentar excluir o ativo.")
            with botoes[3]:
                col_a, col_b = st.columns([4, 2])
                with col_b:
                    if st.button("↩️ Cancelar", key=f"cancelar_{item['UUID']}"):
                        st.session_state.ativo_selecionado = None
        st.markdown('</div>', unsafe_allow_html=True)
        # Bloco de edição de ativo: formulário de edição
        if st.session_state.get("modo_edicao") == item["UUID"]:
            with st.form(f"form_edicao_{item['UUID']}"):
                col_qtd, col_custo, col_data, col_cop = st.columns([2, 2, 3, 2])
                with col_qtd:
                    nova_quantidade = st.number_input("Nova Quantidade", min_value=1, value=item["Quantidade"], step=1)
                with col_custo:
                    novo_custo = st.number_input("Novo Custo (R$)", min_value=0.0, value=float(item["Custo"].replace(",", ".")), step=0.01)
                with col_data:
                    # Novo widget de data
                    nova_data_obj = datetime.strptime(item["Data de Compra"], "%d/%m/%y")
                    nova_data = st.date_input("Nova Data de Compra", value=nova_data_obj, format="DD/MM/YYYY")
                with col_cop:
                    novo_custo_operacional = st.number_input(
                        "Novo Custo Operacional (R$)",
                        min_value=0.0,
                        format="%.2f",
                        value=formatar_numero_para_float(item.get("Custo Operacional", 0.0))
                    )
                col1, col2, col3 = st.columns([3, 10, 2])
                with col1:
                    salvar = st.form_submit_button("💾 Salvar Alterações")
                with col3:
                    cancelar = st.form_submit_button("↩️ Cancelar")

                if cancelar:
                    st.session_state.modo_edicao = None
                if salvar:
                    from utils import editar_ativo_carteira, carregar_carteira_supabase
                    try:
                        # nova_data já é date, garantir formato
                        novos_dados = {
                            "quantidade": int(nova_quantidade),
                            "custo": float(novo_custo),
                            "data_compra": nova_data.strftime("%d/%m/%y"),
                            "custo_operacional": novo_custo_operacional,
                        }
                        resposta = editar_ativo_carteira(item["UUID"], novos_dados)
                        if resposta:
                            st.session_state.posicao_atual = [
                                {
                                    "UUID": reg["id"],
                                    "Ticker": reg["ticker"],
                                    "Quantidade": reg["quantidade"],
                                    "Custo": f'{reg["custo"]:.2f}'.replace('.', ','),
                                    "Data de Compra": reg["data_compra"],
                                    "Custo Operacional": f'{float(reg.get("custo_operacional") or 0):.2f}'.replace('.', ',')
                                }
                                for reg in carregar_carteira_supabase(usuario)
                            ]
                            st.success("Ativo atualizado com sucesso!")
                            st.session_state.ativo_selecionado = None
                            st.session_state.modo_edicao = None
                        else:
                            st.error("Erro ao atualizar ativo.")
                    except Exception as e:
                        st.error(f"Não foi possível salvar as alterações. Erro: {e}")
        elif st.session_state.get("modo_venda") == item["UUID"]:
            with st.form(f"form_venda_{item['UUID']}"):
                col_qtd_venda, col_preco_venda, col_data_venda, col_custo_op_venda, col_irrf_venda = st.columns([2, 2, 2, 2, 2])
                with col_qtd_venda:
                    qtd_venda = st.number_input(
                        "Quantidade Vendida",
                        min_value=1,
                        max_value=item["Quantidade"],
                        value=item["Quantidade"],
                        step=1,
                        key=f"qtd_venda_{item['UUID']}"
                    )
                with col_preco_venda:
                    preco_venda = st.number_input(
                        "Preço de Venda (R$)",
                        min_value=0.0,
                        step=0.01,
                        value=0.0,
                        key=f"preco_venda_{item['UUID']}"
                    )
                with col_data_venda:
                    data_venda = st.date_input(
                        "Data da Venda",
                        value=datetime.now(),
                        format="DD/MM/YYYY",
                        key=f"data_venda_{item['UUID']}"
                    )
                with col_custo_op_venda:
                    custo_operacional_venda = st.number_input(
                        "Custo Operacional (R$)",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key=f"custo_op_venda_{item['UUID']}"
                    )
                with col_irrf_venda:
                    irrf_venda = st.number_input(
                        "IRRF (R$)",
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key=f"irrf_venda_{item['UUID']}"
                    )

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
                        # Conversão do custo operacional da compra
                        custo_operacional_compra_total = float(item["Custo Operacional"].replace(",", "."))

                        # Se for venda total, usa o custo inteiro da compra
                        if qtd_venda == item["Quantidade"]:
                            custo_operacional_compra_proporcional = custo_operacional_compra_total
                            custo_operacional_restante = 0.0
                        else:
                            # Calcula custo proporcional
                            custo_operacional_compra_proporcional = round(
                                custo_operacional_compra_total * qtd_venda / item["Quantidade"], 2
                            )
                            custo_operacional_restante = round(
                                custo_operacional_compra_total - custo_operacional_compra_proporcional, 2
                            )

                        custo_operacional_total = custo_operacional_compra_proporcional + custo_operacional_venda

                        # Registra venda com custo operacional total e IRRF
                        venda_ok = inserir_venda(
                            usuario,
                            item["Ticker"],
                            qtd_venda,
                            float(item["Custo"].replace(",", ".")),
                            item["Data de Compra"],
                            float(preco_venda),
                            data_venda.strftime("%d/%m/%y"),
                            custo_operacional_total,
                            irrf=irrf_venda
                        )

                        if venda_ok:
                            nova_qtd = int(item["Quantidade"] - qtd_venda)
                            if nova_qtd > 0:
                                resposta = editar_ativo_carteira(item["UUID"], {
                                    "quantidade": nova_qtd,
                                    "custo_operacional": custo_operacional_restante
                                })
                                if not resposta:
                                    st.error("Erro ao atualizar a carteira com a nova quantidade e custo operacional.")
                            else:
                                deletar_ativo_carteira(item["UUID"])

                            st.session_state.posicao_atual = [
                                {
                                    "UUID": reg["id"],
                                    "Ticker": reg["ticker"],
                                    "Quantidade": reg["quantidade"],
                                    "Custo": f'{reg["custo"]:.2f}'.replace('.', ','),
                                    "Data de Compra": reg["data_compra"],
                                    "Custo Operacional": f'{float(reg.get("custo_operacional") or 0):.2f}'.replace('.', ',')
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


total_geral_formatado = f"R$ {total_geral:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# Renderiza a linha final da tabela com o total geral
row_total = st.columns([1.5, 1, 1.6, 1.2, 1.6, 2, 1.8, 1.5, 2.2, 1])

row_total[0].markdown("<div class='tabela-linha'><strong>Total</strong></div>", unsafe_allow_html=True)
row_total[1].markdown(f"<div class='tabela-linha'>&nbsp;</div>", unsafe_allow_html=True)
row_total[5].markdown(f"<div class='tabela-linha'><strong>{total_geral_formatado}</strong></div>", unsafe_allow_html=True)


# Cálculo do total da variação em reais (coluna 7) — usando custo unificado
total_variacao_reais = 0.0
for _item in st.session_state.posicao_atual:
    try:
        preco_atual = float(obter_preco_ativo_float(_item["Ticker"]))
        _custo_unit, _ = _custo_final_unit_para_item(_item, _allocacoes_por_ticker, supabase)
        _qt = int(_item.get("Quantidade") or 0)
        if _qt <= 0:
            continue
        variacao_reais = (preco_atual - _custo_unit) * _qt
        total_variacao_reais += variacao_reais
    except Exception:
        continue

total_variacao_reais_formatado = f"R$ {total_variacao_reais:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
cor_total = "#00cc00" if total_variacao_reais >= 0 else "#ff3333"
row_total[8].markdown(
    f"<div class='tabela-linha' style='color:{cor_total};'><strong>{total_variacao_reais_formatado}</strong></div>",
    unsafe_allow_html=True
)
