import streamlit as st
from utils import inserir_opcao_carteira, excluir_operacao_opcao, atualizar_operacao_opcao, excluir_operacao_finalizada

st.set_page_config(layout="wide")
st.markdown("""
<style>
main > div.block-container, section.main > div.block-container, .block-container {
    padding-left: 0.5rem !important;
    padding-right: 0.5rem !important;
    max-width: 100% !important;
}
</style>
""", unsafe_allow_html=True)
st.title("📘 Registro de Opções")

# Aumentar a fonte das abas (seletores robustos)
st.markdown(
    """
    <style>
    /* Streamlit Tabs: aumentar fonte das abas */
    /* Seletores por aria-role e data-baseweb para cobrir diferentes versões */
    div.stTabs > div[role="tablist"] > div[role="tab"] {
        font-size: 1.15rem !important;
    }
    .stTabs [role="tab"] {
        font-size: 1.15rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        font-size: 1.15rem !important;
    }
    /* Algumas builds renderizam o texto em <p> ou <span> dentro do tab */
    .stTabs [role="tab"] p,
    .stTabs [role="tab"] span,
    .stTabs [data-baseweb="tab"] p,
    .stTabs [data-baseweb="tab"] span {
        font-size: 1.15rem !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Abas separando os formulários: Compra e Venda
aba_compra, aba_venda = st.tabs(["Compra", "Venda"])

# ----------------------
# Aba: COMPRA (sem IRRF)
# ----------------------
with aba_compra:
    with st.form("form_insercao_opcao_compra"):
        # Linha 1 — Identificação da operação
        linha1 = st.columns([1.6, 0.9, 1.1, 1.1])
        with linha1[0]:
            ticker = st.text_input("Código da Opção (Ticker)").upper()
        with linha1[1]:
            quantidade = st.number_input("Quantidade", min_value=1, step=1)
        with linha1[2]:
            preco = st.number_input("Preço do Prêmio (R$)", min_value=0.0, step=0.01, format="%.2f")
        with linha1[3]:
            strike = st.number_input("Strike (R$)", min_value=0.0, step=0.01, format="%.2f")

        # Linha 2 — Contexto e custos
        linha2 = st.columns([1.6, 1.1, 0.9, 1.1])
        with linha2[0]:
            ativo_base = st.text_input("Código da Ação (Ticker)").upper()
        with linha2[1]:
            tipo_opcao = st.radio("Tipo da Opção", ["CALL", "PUT"], horizontal=True)
        with linha2[2]:
            venda_coberta = False  # não se aplica para compra
        with linha2[3]:
            custo = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f")

        # Linha 3 — Datas e botão (sem IRRF na compra)
        linha3 = st.columns([1.1, 1.1, 2.6, 1.2])
        with linha3[0]:
            data_operacao = st.date_input("Data da Operação", format="DD/MM/YYYY")
        with linha3[1]:
            data_vencimento = st.date_input("Data de Vencimento", format="DD/MM/YYYY")
        with linha3[2]:
            st.markdown("&nbsp;", unsafe_allow_html=True)
        with linha3[3]:
            submitted = st.form_submit_button("➕ Registrar Operação", use_container_width=True)

        tipo_operacao = "Compra"
        irrf_abertura = 0.0

        if submitted:
            if "uid" not in st.session_state:
                st.error("Usuário não autenticado.")
            elif not ticker:
                st.warning("O campo 'Ticker' não pode estar vazio.")
            elif not ativo_base:
                st.warning("O campo 'Ativo Subjacente' não pode estar vazio.")
            else:
                data_operacao_fmt = data_operacao.strftime("%Y-%m-%d")
                data_vencimento_fmt = data_vencimento.strftime("%Y-%m-%d")
                inserir_opcao_carteira(
                    usuario=st.session_state.get("usuario"),
                    tipo_operacao=tipo_operacao,
                    ticker=ticker,
                    tipo_opcao=tipo_opcao,
                    strike=strike,
                    quantidade=quantidade,
                    preco=preco,
                    custo=custo,
                    data_operacao=data_operacao_fmt,
                    data_vencimento=data_vencimento_fmt,
                    venda_coberta=venda_coberta,
                    ativo_base=ativo_base,
                    irrf_abertura=irrf_abertura,
                )
                st.success("✅ Operação registrada com sucesso!")

# ---------------------
# Aba: VENDA (com IRRF)
# ---------------------
with aba_venda:
    with st.form("form_insercao_opcao_venda"):
        # Linha 1 — Identificação da operação
        v_linha1 = st.columns([1.6, 0.9, 1.1, 1.1])
        with v_linha1[0]:
            ticker = st.text_input("Código da Opção (Ticker)", key="ticker_venda").upper()
        with v_linha1[1]:
            quantidade = st.number_input("Quantidade", min_value=1, step=1, key="quantidade_venda")
        with v_linha1[2]:
            preco = st.number_input("Preço do Prêmio (R$)", min_value=0.0, step=0.01, format="%.2f", key="preco_venda")
        with v_linha1[3]:
            strike = st.number_input("Strike (R$)", min_value=0.0, step=0.01, format="%.2f", key="strike_venda")

        # Linha 2 — Contexto e custos
        v_linha2 = st.columns([1.6, 1.1, 0.9, 1.1])
        with v_linha2[0]:
            ativo_base = st.text_input("Código da Ação (Ticker)", key="ativo_venda").upper()
        with v_linha2[1]:
            tipo_opcao = st.radio("Tipo da Opção", ["CALL", "PUT"], horizontal=True, key="tipoop_venda")
        with v_linha2[2]:
            venda_coberta = st.checkbox("Venda Coberta", key="coberta_venda")
        with v_linha2[3]:
            custo = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f", key="custo_venda")

        # Linha 3 — Datas, IRRF e botão
        v_linha3 = st.columns([1.1, 1.1, 1.1, 1.2])
        with v_linha3[0]:
            data_operacao = st.date_input("Data da Operação", format="DD/MM/YYYY", key="data_venda")
        with v_linha3[1]:
            data_vencimento = st.date_input("Data de Vencimento", format="DD/MM/YYYY", key="venc_venda")
        with v_linha3[2]:
            irrf_abertura = st.number_input("IRRF (R$)", min_value=0.0, step=0.01, format="%.2f", key="irrf_venda")
        with v_linha3[3]:
            submitted = st.form_submit_button("➕ Registrar Operação", use_container_width=True)

        tipo_operacao = "Venda"

        if submitted:
            if "uid" not in st.session_state:
                st.error("Usuário não autenticado.")
            elif not ticker:
                st.warning("O campo 'Ticker' não pode estar vazio.")
            elif not ativo_base:
                st.warning("O campo 'Ativo Subjacente' não pode estar vazio.")
            else:
                data_operacao_fmt = data_operacao.strftime("%Y-%m-%d")
                data_vencimento_fmt = data_vencimento.strftime("%Y-%m-%d")
                inserir_opcao_carteira(
                    usuario=st.session_state.get("usuario"),
                    tipo_operacao=tipo_operacao,
                    ticker=ticker,
                    tipo_opcao=tipo_opcao,
                    strike=strike,
                    quantidade=quantidade,
                    preco=preco,
                    custo=custo,
                    data_operacao=data_operacao_fmt,
                    data_vencimento=data_vencimento_fmt,
                    venda_coberta=venda_coberta,
                    ativo_base=ativo_base,
                    irrf_abertura=irrf_abertura,
                )
                st.success("✅ Operação registrada com sucesso!")

# ================================
# Tabela de Operações em Andamento
# ================================
st.markdown("&nbsp;", unsafe_allow_html=True)
st.subheader("Operações em Andamento")

if "uid" not in st.session_state:
    st.warning("Usuário não autenticado. Faça login para visualizar suas operações.")
else:
    from utils import supabase_autenticado
    supabase = supabase_autenticado()
    import pandas as pd
    import yfinance as yf


    # Buscar dados da Supabase
    response = supabase.table("opcoes_carteira").select("*").eq("user_id", st.session_state["uid"]).order("data_operacao", desc=False).execute()
    dados = response.data

    precos_cache = {}

    def obter_preco_acao(ticker):
        if ticker in precos_cache:
            return precos_cache[ticker]
        try:
            preco = yf.Ticker(ticker).info["regularMarketPrice"]
            precos_cache[ticker] = preco
            return preco
        except:
            return None

    if not dados:
        st.info("Nenhuma operação em andamento encontrada.")
    else:
        df = pd.DataFrame(dados)
        df["id"] = [item["id"] for item in dados]
        df["data_operacao"] = pd.to_datetime(df["data_operacao"], format="%Y-%m-%d").dt.strftime("%d/%m/%y")
        df["data_vencimento"] = pd.to_datetime(df["data_vencimento"], format="%Y-%m-%d").dt.strftime("%d/%m/%y")

        df = df.rename(columns={
            "tipo_operacao": "Operação",
            "tipo_opcao": "Tipo",
            "ticker": "Ticker",
            "strike": "Strike (R$)",
            "preco": "Prêmio (R$)",
            "custo": "Custo (R$)",
            "quantidade": "Qtd",
            "data_operacao": "Data Op.",
            "data_vencimento": "Vencimento",
            "venda_coberta": "Coberta?"
        })

        df["Coberta?"] = df["Coberta?"].apply(lambda x: "✔️" if x else "❌")

        # Estilo CSS
        st.markdown("""
        <style>
            .celula.header {
                background-color: #212121;
                font-weight: bold;
                text-align: left;
            }
            .celula {
                border: 1px solid #444;
                padding: 6px 10px;
                border-radius: 4px;
            }
        </style>
        """, unsafe_allow_html=True)

        # Cabeçalho
        header = st.columns([1.4, 1.0, 1.4, 1.0, 1.4, 1.8, 1.4, 1.4, 1.3, 1.3, 0.9])
        labels = ["Operação", "Tipo", "Ticker", "Qtd", "Prêmio", "Resul. (R$)", "Strike",
                  "À Vista", "Venci.", "Data", "⚙️"]

        for i, label in enumerate(labels):
            header[i].markdown(f"<div class='celula header'>{label}</div>", unsafe_allow_html=True)

        # Linhas da tabela
        for i, row in df.iterrows():
            if row["Operação"].lower() == "compra":
                custo_total = (row["Qtd"] * row["Prêmio (R$)"]) + row["Custo (R$)"]
            else:
                custo_total = (row["Qtd"] * row["Prêmio (R$)"]) - row["Custo (R$)"]
            cols = st.columns([1.4, 1.0, 1.4, 1.0, 1.4, 1.8, 1.4, 1.4, 1.3, 1.3, 0.9])
            operacao = row["Operação"]
            is_coberta = row["Coberta?"] == "✔️" and operacao.lower() == "venda"
            tooltip = "Venda Coberta" if is_coberta else ""
            texto_operacao = operacao + "*" if is_coberta else operacao
            cols[0].markdown(f"<div class='celula' title='{tooltip}'>{texto_operacao}</div>", unsafe_allow_html=True)
            cols[1].markdown(f"<div class='celula'>{row['Tipo']}</div>", unsafe_allow_html=True)
            cols[2].markdown(f"<div class='celula'>{row['Ticker']}</div>", unsafe_allow_html=True)
            cols[3].markdown(f"<div class='celula'>{row['Qtd']}</div>", unsafe_allow_html=True)
            cols[4].markdown(f"<div class='celula'>R$ {row['Prêmio (R$)']:.2f}".replace('.', ',') + "</div>", unsafe_allow_html=True)
            tooltip = f"Custo Operacional: R$ {row['Custo (R$)']:.2f}".replace('.', ',')
            cols[5].markdown(f"<div class='celula' title='{tooltip}'>R$ {custo_total:.2f}".replace('.', ',') + "</div>", unsafe_allow_html=True)
            cols[6].markdown(f"<div class='celula'>R$ {row['Strike (R$)']:.2f}".replace('.', ',') + "</div>", unsafe_allow_html=True)
            preco_acao = obter_preco_acao(row.get("ativo_base"))
            if preco_acao is not None:
                preco_formatado = f"R$ {preco_acao:.2f}".replace(".", ",")
                cols[7].markdown(f"<div class='celula'>{preco_formatado}</div>", unsafe_allow_html=True)
            else:
                cols[7].markdown(f"<div class='celula' title='Não foi possível obter o preço'>N/D</div>", unsafe_allow_html=True)
            cols[8].markdown(f"<div class='celula'>{row['Vencimento']}</div>", unsafe_allow_html=True)
            cols[9].markdown(f"<div class='celula'>{row['Data Op.']}</div>", unsafe_allow_html=True)
            with cols[10]:
                if st.button("⚙️", key=f"eng_{i}"):
                    chave = f"mostrar_acoes_{i}"
                    estava_ativo = st.session_state.get(chave, False)

                    # Fecha todos os menus
                    for k in list(st.session_state.keys()):
                        if k.startswith("mostrar_acoes_"):
                            st.session_state[k] = False

                    # Se estava fechado, abre o atual
                    if not estava_ativo:
                        st.session_state[chave] = True

                    st.rerun()

            if st.session_state.get(f"mostrar_acoes_{i}", False) and not st.session_state.get(f"registrar_operacao_{i}", False):
                acoes_cols = st.columns([3, 1.5, 1.5, 4])
                with acoes_cols[0]:
                    if f"registrar_operacao_{i}" not in st.session_state:
                        st.session_state[f"registrar_operacao_{i}"] = False

                    if st.button("📥 Finalizar Operação", key=f"nova_operacao_{i}"):
                        # Fecha qualquer formulário de edição
                        for k in list(st.session_state.keys()):
                            if k.startswith("editando_opcao_") or k.startswith("registrar_operacao_"):
                                st.session_state[k] = False
                        st.session_state[f"registrar_operacao_{i}"] = True
                        st.rerun()

                with acoes_cols[1]:
                    if st.button("✏️ Editar", key=f"editar_{i}"):
                        # Fecha todos os menus abertos e edições em andamento
                        for k in list(st.session_state.keys()):
                            if k.startswith("mostrar_acoes_") or k.startswith("editando_opcao_"):
                                st.session_state[k] = False
                        st.session_state[f"editando_opcao_{i}"] = True
                        st.rerun()
                with acoes_cols[2]:
                    if st.button("🗑️ Excluir", key=f"excluir_{i}"):
                        excluir_operacao_opcao(row["id"])
                        del st.session_state[f"mostrar_acoes_{i}"]
                        st.rerun()
            # Formulário de edição em abas (espelhando registro inicial)
            if st.session_state.get(f"editando_opcao_{i}", False):
                # Abas de edição espelhando o Registro Inicial (aba padrão de acordo com a operação)
                if str(row["Operação"]).lower() == "venda":
                    aba_ed_venda, aba_ed_compra = st.tabs(["Venda", "Compra"])
                else:
                    aba_ed_compra, aba_ed_venda = st.tabs(["Compra", "Venda"])

                # =====================
                # Edição: COMPRA (sem IRRF)
                # =====================
                with aba_ed_compra:
                    from datetime import datetime
                    data_op_original = datetime.strptime(row["Data Op."], "%d/%m/%y")
                    data_venc_original = datetime.strptime(row["Vencimento"], "%d/%m/%y")
                    with st.form(f"form_edicao_compra_{i}"):
                        # Linha 1 — Identificação
                        l1 = st.columns([1.6, 0.9, 1.1, 1.1])
                        with l1[0]:
                            novo_ticker_c = st.text_input("Código da Opção (Ticker)", value=row["Ticker"], key=f"ed_ticker_c_{i}").upper()
                        with l1[1]:
                            novo_quantidade_c = st.number_input("Quantidade", min_value=1, step=1, value=int(row["Qtd"]), key=f"ed_qtd_c_{i}")
                        with l1[2]:
                            novo_preco_c = st.number_input("Preço do Prêmio (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Prêmio (R$)"]), key=f"ed_preco_c_{i}")
                        with l1[3]:
                            novo_strike_c = st.number_input("Strike (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Strike (R$)"]), key=f"ed_strike_c_{i}")

                        # Linha 2 — Contexto e custos
                        l2 = st.columns([1.6, 1.1, 0.9, 1.1])
                        with l2[0]:
                            novo_ativo_c = st.text_input("Código da Ação (Ticker)", value=row.get("ativo_base", ""), key=f"ed_ativo_c_{i}").upper()
                        with l2[1]:
                            novo_tipo_opcao_c = st.radio("Tipo da Opção", ["CALL", "PUT"], index=0 if row["Tipo"] == "CALL" else 1, horizontal=True, key=f"ed_tipoop_c_{i}")
                        with l2[2]:
                            novo_venda_coberta_c = False  # não se aplica para compra
                        with l2[3]:
                            novo_custo_c = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Custo (R$)"]), key=f"ed_custo_c_{i}")

                        # Linha 3 — Datas e botões
                        l3 = st.columns([1.1, 1.1, 2.2, 1.6])
                        with l3[0]:
                            novo_data_op_c = st.date_input("Data da Operação", value=data_op_original, format="DD/MM/YYYY", key=f"ed_dataop_c_{i}")
                        with l3[1]:
                            novo_data_venc_c = st.date_input("Data de Vencimento", value=data_venc_original, format="DD/MM/YYYY", key=f"ed_venc_c_{i}")
                        with l3[2]:
                            st.markdown("&nbsp;", unsafe_allow_html=True)
                        with l3[3]:
                            btns = st.columns([1, 1.2])
                            with btns[0]:
                                salvar_c = st.form_submit_button("✅ Salvar", use_container_width=True)
                            with btns[1]:
                                cancelar_c = st.form_submit_button("❌ Cancelar", use_container_width=True)

                        if salvar_c:
                            dados_atualizados = {
                                "tipo_operacao": "Compra",
                                "tipo_opcao": novo_tipo_opcao_c,
                                "ticker": novo_ticker_c,
                                "ativo_base": novo_ativo_c,
                                "strike": float(novo_strike_c),
                                "quantidade": int(novo_quantidade_c),
                                "preco": float(novo_preco_c),
                                "custo": float(novo_custo_c),
                                "data_operacao": novo_data_op_c.strftime("%Y-%m-%d"),
                                "data_vencimento": novo_data_venc_c.strftime("%Y-%m-%d"),
                                "venda_coberta": False,
                            }
                            atualizar_operacao_opcao(row["id"], dados_atualizados)
                            del st.session_state[f"editando_opcao_{i}"]
                            st.success("✅ Operação atualizada com sucesso.")
                            st.rerun()

                        if cancelar_c:
                            del st.session_state[f"editando_opcao_{i}"]
                            st.rerun()

                # =====================
                # Edição: VENDA (com IRRF Pendente)
                # =====================
                with aba_ed_venda:
                    from datetime import datetime
                    data_op_original = datetime.strptime(row["Data Op."], "%d/%m/%y")
                    data_venc_original = datetime.strptime(row["Vencimento"], "%d/%m/%y")
                    irrf_pendente_val = float(row.get("irrf_abertura_pendente") or 0.0)
                    with st.form(f"form_edicao_venda_{i}"):
                        # Linha 1 — Identificação
                        vl1 = st.columns([1.6, 0.9, 1.1, 1.1])
                        with vl1[0]:
                            novo_ticker_v = st.text_input("Código da Opção (Ticker)", value=row["Ticker"], key=f"ed_ticker_v_{i}").upper()
                        with vl1[1]:
                            novo_quantidade_v = st.number_input("Quantidade", min_value=1, step=1, value=int(row["Qtd"]), key=f"ed_qtd_v_{i}")
                        with vl1[2]:
                            novo_preco_v = st.number_input("Preço do Prêmio (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Prêmio (R$)"]), key=f"ed_preco_v_{i}")
                        with vl1[3]:
                            novo_strike_v = st.number_input("Strike (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Strike (R$)"]), key=f"ed_strike_v_{i}")

                        # Linha 2 — Contexto e custos
                        vl2 = st.columns([1.6, 1.1, 0.9, 1.1])
                        with vl2[0]:
                            novo_ativo_v = st.text_input("Código da Ação (Ticker)", value=row.get("ativo_base", ""), key=f"ed_ativo_v_{i}").upper()
                        with vl2[1]:
                            novo_tipo_opcao_v = st.radio("Tipo da Opção", ["CALL", "PUT"], index=0 if row["Tipo"] == "CALL" else 1, horizontal=True, key=f"ed_tipoop_v_{i}")
                        with vl2[2]:
                            novo_venda_coberta_v = st.checkbox("Venda Coberta", value=(row["Coberta?"] == "✔️"), key=f"ed_coberta_v_{i}")
                        with vl2[3]:
                            novo_custo_v = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["Custo (R$)"]), key=f"ed_custo_v_{i}")

                        # Linha 3 — Datas, IRRF Pendente e botões
                        vl3 = st.columns([1.1, 1.1, 1.1, 1.2])
                        with vl3[0]:
                            novo_data_op_v = st.date_input("Data da Operação", value=data_op_original, format="DD/MM/YYYY", key=f"ed_dataop_v_{i}")
                        with vl3[1]:
                            novo_data_venc_v = st.date_input("Data de Vencimento", value=data_venc_original, format="DD/MM/YYYY", key=f"ed_venc_v_{i}")
                        with vl3[2]:
                            novo_irrf_pendente = st.number_input("IRRF Pendente (R$)", min_value=0.0, step=0.01, format="%.2f", value=irrf_pendente_val, key=f"ed_irrfpend_v_{i}")
                        with vl3[3]:
                            btns = st.columns([1, 1])
                            with btns[0]:
                                salvar_v = st.form_submit_button("✅ Salvar", use_container_width=True)
                            with btns[1]:
                                cancelar_v = st.form_submit_button("❌ Cancelar", use_container_width=True)

                        if salvar_v:
                            dados_atualizados = {
                                "tipo_operacao": "Venda",
                                "tipo_opcao": novo_tipo_opcao_v,
                                "ticker": novo_ticker_v,
                                "ativo_base": novo_ativo_v,
                                "strike": float(novo_strike_v),
                                "quantidade": int(novo_quantidade_v),
                                "preco": float(novo_preco_v),
                                "custo": float(novo_custo_v),
                                "data_operacao": novo_data_op_v.strftime("%Y-%m-%d"),
                                "data_vencimento": novo_data_venc_v.strftime("%Y-%m-%d"),
                                "venda_coberta": novo_venda_coberta_v,
                                "irrf_abertura_pendente": float(novo_irrf_pendente),
                            }
                            atualizar_operacao_opcao(row["id"], dados_atualizados)
                            del st.session_state[f"editando_opcao_{i}"]
                            st.success("✅ Operação atualizada com sucesso.")
                            st.rerun()

                        if cancelar_v:
                            del st.session_state[f"editando_opcao_{i}"]
                            st.rerun()
            # Formulário de finalização fora das colunas de ações e ocupando largura total
            if st.session_state.get(f"registrar_operacao_{i}", False):
                
                with st.form(f"form_finalizacao_{i}"):
                    cols = st.columns([1.1, 1, 1, 1, 1])

                    with cols[0]:
                        st.text_input("Código da Opção (Ticker)", value=row["Ticker"], disabled=True)
                        st.radio("Tipo de Operação", ["Compra", "Venda"], index=0 if row["Operação"] == "Compra" else 1, disabled=True, horizontal=True)
                        st.radio("Tipo da Opção", ["CALL", "PUT"], index=0 if row["Tipo"] == "CALL" else 1, disabled=True, horizontal=True)

                    with cols[1]:
                        st.text_input("Código da Ação (Ticker)", value=row.get("ativo_base", ""), disabled=True)
                        st.number_input("Strike (R$)", value=float(row["Strike (R$)"]), disabled=True, format="%.2f")
                        st.text_input("Coberta?", value="Sim" if row["Coberta?"] == "✔️" else "Não", disabled=True)

                    with cols[2]:
                        from datetime import datetime, date
                        data_op = datetime.strptime(row["Data Op."], "%d/%m/%y").date()
                        data_encerramento = st.date_input("Data de Encerramento", value=date.today(), format="DD/MM/YYYY")
                        if row["Operação"].lower() == "compra":
                            primeira_opcao = "Revenda"
                        else:
                            primeira_opcao = "Recompra"
                        forma_encerramento = st.selectbox("Forma de Encerramento", [primeira_opcao, "Exercício", "Expiração"])
                        # Campo IRRF (R$) dinâmico — só aparece quando Compra → Revenda/Exercício/Expiração
                        mostra_irrf_fech = (row["Operação"].lower() == "compra" and forma_encerramento in ["Revenda", "Exercício", "Expiração"])
                        irrf_fechamento = 0.0
                        if mostra_irrf_fech:
                            irrf_fechamento = st.number_input("IRRF (R$)", min_value=0.0, step=0.01, format="%.2f")

                    with cols[3]:
                        quantidade_finalizada = st.number_input("Quantidade Finalizada", min_value=1, max_value=int(row["Qtd"]), value=int(row["Qtd"]), step=1)
                        preco_inicial = st.number_input("Prêmio Inicial (R$)", value=float(row["Prêmio (R$)"]), disabled=True, format="%.2f")

                    with cols[4]:
                        preco_final = st.number_input("Prêmio Final (R$)", min_value=0.0, step=0.01, format="%.2f")
                        custo_final = st.number_input("Custo Final (R$)", min_value=0.0, step=0.01, format="%.2f")

                    # Linha de botões após todos os campos
                    botao_cols = st.columns([6, 1.5, 1.5])
                    with botao_cols[1]:
                        confirmar = st.form_submit_button("✅ Confirmar", use_container_width=True)
                    with botao_cols[2]:
                        cancelar = st.form_submit_button("❌ Cancelar", use_container_width=True)

                    if confirmar:
                        from utils import finalizar_operacao_opcao
                        dados_vivos = {
                            "id": row["id"],
                            "ticker": row["Ticker"],
                            "tipo_opcao": row["Tipo"],
                            "tipo_operacao": row["Operação"],
                            "quantidade": row["Qtd"],
                            "preco": row["Prêmio (R$)"],
                            "strike": row["Strike (R$)"],
                            "custo": row["Custo (R$)"],
                            "data_operacao": data_op.strftime("%Y-%m-%d"),
                            "data_vencimento": datetime.strptime(row["Vencimento"], "%d/%m/%y").strftime("%Y-%m-%d"),
                            "venda_coberta": row["Coberta?"] == "✔️",
                            "ativo_base": row.get("ativo_base")
                        }
                        # Anexa IRRF de fechamento quando aplicável (campo só é mostrado em Compra)
                        try:
                            dados_vivos["irrf_fechamento"] = float(irrf_fechamento)
                        except Exception:
                            dados_vivos["irrf_fechamento"] = 0.0
                        try:
                            data_encerramento_fmt = data_encerramento.strftime("%Y-%m-%d")
                            finalizar_operacao_opcao(
                                dados_vivos=dados_vivos,
                                quantidade_finalizada=quantidade_finalizada,
                                preco_final=preco_final,
                                custo_final=custo_final,
                                forma_encerramento=forma_encerramento,
                                data_encerramento=data_encerramento_fmt
                            )
                            st.success("✅ Operação finalizada com sucesso.")
                            del st.session_state[f"registrar_operacao_{i}"]
                            del st.session_state[f"mostrar_acoes_{i}"]
                            st.rerun()
                        except Exception as e:
                            st.error(f"Erro ao finalizar operação: {e}")
                    if cancelar:
                        # Esconde o formulário e os botões de ação
                        del st.session_state[f"registrar_operacao_{i}"]
                        del st.session_state[f"mostrar_acoes_{i}"]
                        st.rerun()
#
# ================================
# Tabela de Operações Finalizadas
# ================================
st.markdown("---")
st.subheader("Operações Finalizadas")

from utils import carregar_operacoes_finalizadas
dados_finalizadas = carregar_operacoes_finalizadas(st.session_state["uid"])

if not dados_finalizadas:
    st.info("Nenhuma operação finalizada encontrada.")
else:
    import pandas as pd
    df = pd.DataFrame(dados_finalizadas)
    df["data_operacao"] = pd.to_datetime(df["data_operacao"]).dt.strftime("%d/%m/%y")
    df["data_encerramento"] = pd.to_datetime(df["data_encerramento"]).dt.strftime("%d/%m/%y")

    # Adiciona coluna "Coberta?" (✔️/❌)
    df["Coberta?"] = df["venda_coberta"].apply(lambda x: "✔️" if x else "❌")

    # Cálculo do resultado
    def calcular_resultado(row):
        if row["tipo_operacao_inicial"].lower() == "compra":
            return (row["preco_final"] - row["preco_inicial"]) * row["quantidade"] - row["custo"]
        else:
            return (row["preco_inicial"] - row["preco_final"]) * row["quantidade"] - row["custo"]

    df["Resultado"] = df.apply(calcular_resultado, axis=1)

    # Estilo CSS
    st.markdown("""
    <style>
        .celula.header {
            background-color: #111;
            font-weight: bold;
            text-align: left;
        }
        .celula {
            border: 1px solid #444;
            padding: 6px 10px;
            border-radius: 4px;
        }
    </style>
    """, unsafe_allow_html=True)

    # Cabeçalho
    header = st.columns([1.9, 1.8, 1.2, 1.3, 1.7, 1.7, 1.8, 1.7, 1.7, 2, 1])
    labels = ["Ticker", "Op Inicial", "Tipo", "Qtd", "Prêmio I", "Prêmio F", "Op Final", "Data I", "Data F", "Resultado", "⚙️"]
    for i, label in enumerate(labels):
        header[i].markdown(f"<div class='celula header'>{label}</div>", unsafe_allow_html=True)

    # Linhas da tabela
    for i, row in df.iterrows():
        cols = st.columns([1.9, 1.8, 1.2, 1.3, 1.7, 1.7, 1.8, 1.7, 1.7, 2, 1])
        cols[0].markdown(f"<div class='celula'>{row['ticker']}</div>", unsafe_allow_html=True)
        # Novo bloco simplificado para "Op Inicial"
        op_inicial = row["tipo_operacao_inicial"]
        is_coberta = row["Coberta?"] == "✔️" and op_inicial.lower() == "venda"
        tooltip_op = "Venda Coberta" if is_coberta else ""
        texto_op = op_inicial + "*" if is_coberta else op_inicial
        cols[1].markdown(f"<div class='celula' title='{tooltip_op}'>{texto_op}</div>", unsafe_allow_html=True)
        cols[2].markdown(f"<div class='celula'>{row['tipo_opcao']}</div>", unsafe_allow_html=True)
        cols[3].markdown(f"<div class='celula'>{row['quantidade']}</div>", unsafe_allow_html=True)
        cols[4].markdown(f"<div class='celula'>R$ {row['preco_inicial']:.2f}".replace('.', ',') + "</div>", unsafe_allow_html=True)
        cols[5].markdown(f"<div class='celula'>R$ {row['preco_final']:.2f}".replace('.', ',') + "</div>", unsafe_allow_html=True)
        cols[6].markdown(f"<div class='celula'>{row['forma_encerramento']}</div>", unsafe_allow_html=True)
        cols[7].markdown(f"<div class='celula'>{row['data_operacao']}</div>", unsafe_allow_html=True)
        cols[8].markdown(f"<div class='celula'>{row['data_encerramento']}</div>", unsafe_allow_html=True)
        resultado_formatado = "R$ {:,.2f}".format(row["Resultado"]).replace(",", "X").replace(".", ",").replace("X", ".")
        tooltip_resultado = f"Custo Operacional: R$ {row['custo']:.2f}".replace('.', ',')
        cor_resultado = "#4CAF50" if row["Resultado"] > 0 else "red" if row["Resultado"] < 0 else "inherit"
        cols[9].markdown(
            f"<div class='celula' title='{tooltip_resultado}' style='color: {cor_resultado};'>{resultado_formatado}</div>",
            unsafe_allow_html=True
        )
        with cols[10]:
            if st.button("⚙️", key=f"eng_finalizada_{i}"):
                chave = f"mostrar_acoes_finalizadas_{i}"
                estava_ativo = st.session_state.get(chave, False)

                # Fecha todos os menus de finalizadas
                for k in list(st.session_state.keys()):
                    if k.startswith("mostrar_acoes_finalizadas_"):
                        st.session_state[k] = False

                # Se estava fechado, abre o atual
                if not estava_ativo:
                    st.session_state[chave] = True

                st.rerun()

        # Bloco de menu de ações para operações finalizadas
        if st.session_state.get(f"mostrar_acoes_finalizadas_{i}", False):
            acoes_cols = st.columns([1.5, 1.5, 7])
            with acoes_cols[0]:
                if st.button("✏️ Editar", key=f"editar_finalizada_{i}"):
                    # Fecha todos os formulários de edição de finalizadas
                    for k in list(st.session_state.keys()):
                        if k.startswith("editando_operacao_finalizada_"):
                            st.session_state[k] = False
                    st.session_state[f"editando_operacao_finalizada_{i}"] = True
                    st.rerun()
            with acoes_cols[1]:
                if st.button("🗑️ Excluir", key=f"excluir_finalizada_{i}"):
                    excluir_operacao_finalizada(row["id"])
                    del st.session_state[f"mostrar_acoes_finalizadas_{i}"]
                    st.rerun()

        # Formulário de edição inline para operações finalizadas
        if st.session_state.get(f"editando_operacao_finalizada_{i}", False):
            from datetime import datetime
            with st.form(f"form_edicao_finalizada_{i}"):
                cols_form = st.columns([1.1, 1, 1, 1, 1])

                with cols_form[0]:
                    novo_tipo_operacao = st.radio("Tipo de Operação", ["Compra", "Venda"], index=0 if row["tipo_operacao_inicial"] == "Compra" else 1, horizontal=True)
                    novo_venda_coberta = st.checkbox("Venda Coberta", value=(row["Coberta?"] == "✔️"))
                    novo_tipo_opcao = st.radio("Tipo da Opção", ["CALL", "PUT"], index=0 if row["tipo_opcao"] == "CALL" else 1, horizontal=True)

                with cols_form[1]:
                    novo_ticker = st.text_input("Código da Opção (Ticker)", value=row["ticker"]).upper()
                    novo_forma_encerramento = st.selectbox("Forma de Encerramento", ["Recompra", "Revenda", "Exercício", "Expiração"], index=["Recompra", "Revenda", "Exercício", "Expiração"].index(row["forma_encerramento"]))

                with cols_form[2]:
                    novo_quantidade = st.number_input("Quantidade", min_value=1, step=1, value=int(row["quantidade"]))
                    novo_custo = st.number_input("Custo Operacional (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["custo"]))

                with cols_form[3]:
                    novo_preco_inicial = st.number_input("Prêmio Inicial (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["preco_inicial"]))
                    novo_preco_final = st.number_input("Prêmio Final (R$)", min_value=0.0, step=0.01, format="%.2f", value=float(row["preco_final"]))

                with cols_form[4]:
                    data_op = datetime.strptime(row["data_operacao"], "%d/%m/%y")
                    data_enc = datetime.strptime(row["data_encerramento"], "%d/%m/%y")
                    novo_data_op = st.date_input("Data da Operação", value=data_op, format="DD/MM/YYYY")
                    novo_data_enc = st.date_input("Data de Encerramento", value=data_enc, format="DD/MM/YYYY")

                # Botões
                botoes = st.columns([6, 1.2, 1.2])
                with botoes[1]:
                    salvar = st.form_submit_button("✅ Salvar")
                with botoes[2]:
                    cancelar = st.form_submit_button("❌ Cancelar")

                if cancelar:
                    del st.session_state[f"editando_operacao_finalizada_{i}"]
                    st.rerun()

                if salvar:
                    from utils import atualizar_operacao_finalizada
                    dados_atualizados = {
                        "ticker": novo_ticker,
                        "tipo_opcao": novo_tipo_opcao,
                        "tipo_operacao_inicial": novo_tipo_operacao,
                        "forma_encerramento": novo_forma_encerramento,
                        "quantidade": int(novo_quantidade),
                        "preco_inicial": float(novo_preco_inicial),
                        "preco_final": float(novo_preco_final),
                        "custo": float(novo_custo),
                        "data_operacao": novo_data_op.strftime("%Y-%m-%d"),
                        "data_encerramento": novo_data_enc.strftime("%Y-%m-%d"),
                        "venda_coberta": novo_venda_coberta
                    }
                    atualizar_operacao_finalizada(row["id"], dados_atualizados)
                    del st.session_state[f"editando_operacao_finalizada_{i}"]
                    st.success("✅ Operação atualizada com sucesso.")
                    st.rerun()