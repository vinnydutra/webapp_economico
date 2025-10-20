from datetime import datetime
import streamlit as st
import yfinance as yf
import pandas as pd
from finance_calcs import calcular_oscilacao_mes, calcular_oscilacao_30d, calcular_oscilacao_12m, calcular_oscilacao_ano
from finance_calcs import calcular_fcf_yield
from finance_calcs import calcular_componentes_fcf_yield


# Função utilitária para formatar números grandes com sufixos
def format_number_short(value):
    if value is None:
        return "N/D"
    
    negativo = value < 0
    valor_abs = abs(value)

    if valor_abs >= 1_000_000_000_000:
        resultado = f"{valor_abs / 1_000_000_000_000:.2f} Tri"
    elif valor_abs >= 1_000_000_000:
        resultado = f"{valor_abs / 1_000_000_000:.2f} Bi"
    elif valor_abs >= 1_000_000:
        resultado = f"{valor_abs / 1_000_000:.2f} Mi"
    else:
        resultado = f"{valor_abs:,.0f}"

    if negativo:
        resultado = f"-{resultado}"
        
    return resultado.replace('.', ',')

if 'ticker' not in st.session_state:
    st.session_state.ticker = "PETR4.SA"

ticker = st.session_state.ticker
ticker_obj = yf.Ticker(ticker)
try:
    info = ticker_obj.info
except Exception as e:
    st.error(f"Erro ao buscar dados do ticker: {ticker} — {e}")
    st.stop()
empresa = info.get("longName", "N/D")
setor = info.get("sector", "N/D")
subsetor = info.get("industry", "N/D")
market_cap = info.get("marketCap", None)
valor_firma = info.get("enterpriseValue", None)
data_cotacao_ts = info.get("regularMarketTime", None)
data_cotacao = datetime.fromtimestamp(data_cotacao_ts).strftime("%d/%m/%Y") if data_cotacao_ts else "N/D"
volume_medio = info.get("averageVolume", None)
num_acoes = info.get("sharesOutstanding", None)
variacao_dia = info.get("regularMarketChangePercent", None)

col1, col2, col3 = st.columns([1, 5, 4])

with col1:
    pass  # espaço reservado para botão de estrela, se necessário futuramente

with col2:
    st.markdown(
        f"""
        <h1 style='margin: 0; padding: 0; display: inline-block;'>{ticker}</h1>
        """,
        unsafe_allow_html=True
    )

with col3:
    novo_ticker = st.text_input(
        "Digite o ticker:",
        ticker,
        label_visibility="collapsed"
    ).upper()
    if novo_ticker != ticker:
        st.session_state.ticker = novo_ticker
        st.rerun()

st.markdown("---")

# 8. 📊 Oscilações de Preço
with st.container():
    st.markdown("### 📊 Oscilações de Preço")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"🟢 **Dia:** {f'{variacao_dia:.2f}%'.replace('.', ',')}" if variacao_dia is not None else "🔴 **Dia:** N/D")
        variacao_mes = calcular_oscilacao_mes(ticker_obj)
        st.markdown(
            f"🟢 **Mês:** {f'{variacao_mes:.2f}%'.replace('.', ',')}" if variacao_mes is not None else "🔴 **Mês:** N/D"
        )
        variacao_30d = calcular_oscilacao_30d(ticker_obj)
        st.markdown(
            f"🟢 **30 dias:** {f'{variacao_30d:.2f}%'.replace('.', ',')}" if variacao_30d is not None else "🔴 **30 dias:** N/D"
        )
    with col2:
        variacao_12m = calcular_oscilacao_12m(ticker_obj)
        st.markdown(
            f"🟢 **12 meses:** {variacao_12m:.2f}%" if variacao_12m is not None else "🔴 **12 meses:** N/D"
        )
        ano_atual = datetime.now().year
        variacao_ytd = calcular_oscilacao_ano(ano_atual, ticker_obj)
        st.markdown(
            f"🟢 **YTD ({ano_atual}):** {variacao_ytd:.2f}%" if variacao_ytd is not None else f"🔴 **YTD ({ano_atual}):** N/D"
        )
        variacao_ano_1 = calcular_oscilacao_ano(ano_atual - 1, ticker_obj)
        st.markdown(
            f"🟢 **{ano_atual - 1}:** {variacao_ano_1:.2f}%" if variacao_ano_1 is not None else f"🔴 **{ano_atual - 1}:** N/D"
        )
    with col3:
        variacao_ano_2 = calcular_oscilacao_ano(ano_atual - 2, ticker_obj)
        st.markdown(
            f"🟢 **{ano_atual - 2}:** {variacao_ano_2:.2f}%" if variacao_ano_2 is not None else f"🔴 **{ano_atual - 2}:** N/D"
        )
        variacao_ano_3 = calcular_oscilacao_ano(ano_atual - 3, ticker_obj)
        st.markdown(
            f"🟢 **{ano_atual - 3}:** {variacao_ano_3:.2f}%" if variacao_ano_3 is not None else f"🔴 **{ano_atual - 3}:** N/D"
        )
        variacao_ano_4 = calcular_oscilacao_ano(ano_atual - 4, ticker_obj)
        st.markdown(
            f"🟢 **{ano_atual - 4}:** {variacao_ano_4:.2f}%" if variacao_ano_4 is not None else f"🔴 **{ano_atual - 4}:** N/D"
        )

# 1. 🧾 Dados da Empresa
with st.container():
    st.markdown("### 🧾 Dados da Empresa")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"🟢 **Empresa:** {empresa}")
        st.markdown(f"🟢 **Setor:** {setor}")
        st.markdown(f"🟢 **Subsetor:** {subsetor}")
    with col2:
        st.markdown(f"🟢 **Ticker:** {ticker}")
        st.markdown(f"🟢 **Valor de Mercado:** US$ {format_number_short(market_cap)}" if market_cap else "🔴 **Valor de Mercado:** N/D")
        st.markdown(f"🟢 **Valor da Firma:** US$ {format_number_short(valor_firma)}" if valor_firma else "🔴 **Valor da Firma:** N/D")
    with col3:
        st.markdown(f"🟢 **Volume Médio:** {format_number_short(volume_medio)}/dia" if volume_medio else "🔴 **Volume Médio:** N/D")
        st.markdown(f"🟢 **Ações Emitidas:** {format_number_short(num_acoes)}" if num_acoes else "🔴 **Ações Emitidas:** N/D")
        preco_atual = info.get("regularMarketPrice", None)
        if volume_medio and preco_atual:
            volume_financeiro_medio = volume_medio * preco_atual
            st.markdown(f"🟢 **Vol. Fin. Médio:** US$ {format_number_short(volume_financeiro_medio)}/dia")
        else:
            st.markdown("🔴 **Vol. Fin. Médio:** N/D")

# 2. 📊 Valuation
with st.container():
    st.markdown("### 📊 Valuation")
    col1, col2, col3 = st.columns(3)
    with col1:
        valor = info.get("trailingPE", None)
        if valor is not None:
            st.markdown(f"🟢 **P/L:** {str(round(valor, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/L:** N/D")
        valor = info.get("priceToBook", None)
        if valor is not None:
            st.markdown(f"🟢 **P/VP:** {str(round(valor, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/VP:** N/D")
        market_cap = info.get("marketCap", None)
        try:
            ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
        except:
            ebit = None
        if market_cap and ebit:
            p_ebit = market_cap / ebit
            st.markdown(f"🟢 **P/EBIT:** {str(round(p_ebit, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/EBIT:** N/D")
    with col2:
        try:
            ativos = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
        except:
            ativos = None
        market_cap = info.get("marketCap", None)
        if market_cap and ativos:
            p_ativos = market_cap / ativos
            st.markdown(f"🟢 **P/Ativos:** {str(round(p_ativos, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/Ativos:** N/D")
        valor = info.get("priceToSalesTrailing12Months", None)
        if valor is not None:
            st.markdown(f"🟢 **PSR:** {str(round(valor, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **PSR:** N/D")
        valor_firma = info.get("enterpriseValue", None)
        try:
            ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
        except:
            ebit = None
        if valor_firma and ebit:
            ev_ebit = valor_firma / ebit
            st.markdown(f"🟢 **EV/EBIT:** {str(round(ev_ebit, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **EV/EBIT:** N/D")
    with col3:
        valor_firma = info.get("enterpriseValue", None)
        valor_ebitda = info.get("ebitda", None)
        if valor_firma and valor_ebitda:
            ev_ebitda = valor_firma / valor_ebitda
            st.markdown(f"🟢 **EV/EBITDA:** {str(round(ev_ebitda, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **EV/EBITDA:** N/D")
        try:
            ativo_circulante = ticker_obj.balance_sheet.loc["Current Assets"].iloc[0]
            passivo_circulante = ticker_obj.balance_sheet.loc["Current Liabilities"].iloc[0]
            capital_giro = ativo_circulante - passivo_circulante
        except:
            capital_giro = None
        market_cap = info.get("marketCap", None)
        if market_cap and capital_giro and capital_giro != 0:
            p_cap_giro = market_cap / capital_giro
            st.markdown(f"🟢 **P/Cap. Giro:** {str(round(p_cap_giro, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/Cap. Giro:** N/D")

        # Novo bloco: P/Cap. Giro Operacional
        try:
            contas_a_receber = ticker_obj.balance_sheet.loc["Accounts Receivable"].iloc[0]
            estoques = ticker_obj.balance_sheet.loc["Inventory"].iloc[0]
            fornecedores = ticker_obj.balance_sheet.loc["Accounts Payable"].iloc[0]
            cap_giro_operacional = contas_a_receber + estoques - fornecedores
        except:
            cap_giro_operacional = None
        if market_cap and cap_giro_operacional and cap_giro_operacional != 0:
            p_cap_giro_op = market_cap / cap_giro_operacional
            st.markdown(f"🟢 **P/Cap. Giro Operacional:** {str(round(p_cap_giro_op, 2)).replace('.', ',')}")
        else:
            st.markdown("🔴 **P/Cap. Giro Operacional:** N/D")

# 3. 💸 Rentabilidade
with st.container():
    st.markdown("### 💸 Rentabilidade")
    col1, col2, col3 = st.columns(3)
    with col1:
        # ROE
        valor = info.get("returnOnEquity", None)
        if valor is not None:
            st.markdown(f"🟢 **ROE:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **ROE:** N/D")
        from finance_calcs import calcular_roic
        roic = calcular_roic(ticker_obj)
        if roic is not None:
            st.markdown(f"🟢 **ROIC:** {str(round(roic, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **ROIC:** N/D")
        from finance_calcs import calcular_roic_real
        roic_real = calcular_roic_real(ticker_obj)
        if roic_real is not None:
            st.markdown(f"🟢 **ROIC Real:** {str(round(roic_real, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **ROIC Real:** N/D")

    with col2:
        try:
            ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
            total_assets = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
            if total_assets != 0:
                ebit_ativo = ebit / total_assets * 100
                st.markdown(f"🟢 **EBIT / Ativo:** {str(round(ebit_ativo, 2)).replace('.', ',')}%")
            else:
                st.markdown("🔴 **EBIT / Ativo:** N/D")
        except:
            st.markdown("🔴 **EBIT / Ativo:** N/D")
        # ROA
        valor = info.get("returnOnAssets", None)
        if valor is not None:
            st.markdown(f"🟢 **ROA:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **ROA:** N/D")
        # Margem Bruta
        valor = info.get("grossMargins", None)
        if valor is not None:
            st.markdown(f"🟢 **Margem Bruta:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **Margem Bruta:** N/D")
    with col3:
        # Margem EBIT
        valor = info.get("operatingMargins", None)
        if valor is not None:
            st.markdown(f"🟢 **Margem EBIT:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **Margem EBIT:** N/D")
        # Margem Líquida
        valor = info.get("profitMargins", None)
        if valor is not None:
            st.markdown(f"🟢 **Marg. Líquida:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **Marg. Líquida:** N/D")
        # Margem EBITDA
        valor = info.get("ebitdaMargins", None)
        if valor is not None:
            st.markdown(f"🟢 **Margem EBITDA:** {str(round(valor * 100, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **Margem EBITDA:** N/D")

# 4. 📈 Crescimento
with st.container():
    st.markdown("### 📈 Crescimento")
    col1, col2, col3 = st.columns(3)
    with col1:
        from finance_calcs import calcular_crescimento_receita, calcular_crescimento_lucro
        crescimento_receita = calcular_crescimento_receita(ticker_obj)
        if crescimento_receita is not None:
            st.markdown(f"🟢 **Cresc. Receita (5 anos):** {str(round(crescimento_receita, 2)).replace('.', ',')}%")
        else:
            st.markdown("🔴 **Cresc. Receita (5 anos):** N/D")

        crescimento_lucro = calcular_crescimento_lucro(ticker_obj)
        lucro_5_anos = f"{crescimento_lucro:.2f}%" if crescimento_lucro is not None else "N/D"
        st.markdown(f"🟢 Cresc. Lucro (5 anos): {lucro_5_anos}")

        # Detectar anos disponíveis
        anos_financeiros = sorted(ticker_obj.financials.columns, reverse=True)
        ano_referencia = datetime.now().year - 1
        coluna_referencia = pd.Timestamp(f"{ano_referencia}-12-31")

        try:
            receita_1 = ticker_obj.financials.loc["Total Revenue", coluna_referencia]
        except:
            receita_1 = None

        st.markdown(
            f"🟢 **Receita {coluna_referencia.year}:** US$ {format_number_short(receita_1)}"
            if receita_1 else
            f"🔴 **Receita {coluna_referencia.year}:** N/D"
        )

        try:
            lucro_1 = ticker_obj.financials.loc["Net Income", coluna_referencia]
        except:
            lucro_1 = None

        st.markdown(
            f"🟢 **Lucro {coluna_referencia.year}:** US$ {format_number_short(lucro_1)}"
            if lucro_1 else
            f"🔴 **Lucro {coluna_referencia.year}:** N/D"
        )

        ano_2 = datetime.now().year - 2
        coluna_referencia_2 = pd.Timestamp(f"{ano_2}-12-31")

        try:
            receita_2 = ticker_obj.financials.loc["Total Revenue", coluna_referencia_2]
        except:
            receita_2 = None

        st.markdown(
            f"🟢 **Receita {coluna_referencia_2.year}:** US$ {format_number_short(receita_2)}"
            if receita_2 else
            f"🔴 **Receita {coluna_referencia_2.year}:** N/D"
        )

    with col2:
        try:
            lucro_2 = ticker_obj.financials.loc["Net Income", coluna_referencia_2]
        except:
            lucro_2 = None

        st.markdown(
            f"🟢 **Lucro {coluna_referencia_2.year}:** US$ {format_number_short(lucro_2)}"
            if lucro_2 else
            f"🔴 **Lucro {coluna_referencia_2.year}:** N/D"
        )

        ano_3 = datetime.now().year - 3
        coluna_referencia_3 = pd.Timestamp(f"{ano_3}-12-31")

        try:
            receita_3 = ticker_obj.financials.loc["Total Revenue", coluna_referencia_3]
        except:
            receita_3 = None

        st.markdown(
            f"🟢 **Receita {coluna_referencia_3.year}:** US$ {format_number_short(receita_3)}"
            if receita_3 else
            f"🔴 **Receita {coluna_referencia_3.year}:** N/D"
        )

        try:
            lucro_3 = ticker_obj.financials.loc["Net Income", coluna_referencia_3]
        except:
            lucro_3 = None

        st.markdown(
            f"🟢 **Lucro {coluna_referencia_3.year}:** US$ {format_number_short(lucro_3)}"
            if lucro_3 else
            f"🔴 **Lucro {coluna_referencia_3.year}:** N/D"
        )

        # Receita 1T - Ano vigente dinâmico
        ano_1t = datetime.now().year
        data_1t = pd.Timestamp(f"{ano_1t}-03-31")
        try:
            receita_1t = ticker_obj.quarterly_financials.loc["Total Revenue", data_1t]
        except:
            receita_1t = None
        st.markdown(
            f"🟢 **Receita 1T {ano_1t}:** US$ {format_number_short(receita_1t)}"
            if receita_1t else
            f"🔴 **Receita 1T {ano_1t}:** N/D"
        )

        data_1t_lucro = pd.Timestamp(f"{ano_1t}-03-31")
        try:
            lucro_1t = ticker_obj.quarterly_financials.loc["Net Income", data_1t_lucro]
        except:
            lucro_1t = None
        st.markdown(
            f"🟢 **Lucro 1T {ano_1t}:** US$ {format_number_short(lucro_1t)}"
            if lucro_1t else
            f"🔴 **Lucro 1T {ano_1t}:** N/D"
        )

with col3:
    # Captura dinâmica das datas trimestrais mais recentes
    datas_quarters = sorted(ticker_obj.quarterly_financials.columns, reverse=True)
    ano_2t = datetime.now().year
    data_2t = pd.Timestamp(f"{ano_2t}-06-30")
    try:
        receita_2t_2025 = ticker_obj.quarterly_financials.loc["Total Revenue", data_2t]
    except:
        receita_2t_2025 = None

    data_2t_lucro = pd.Timestamp(f"{datetime.now().year}-06-30")
    try:
        lucro_2t = ticker_obj.quarterly_financials.loc["Net Income", data_2t_lucro]
    except:
        lucro_2t = None

    if receita_2t_2025:
        st.markdown(f"🟢 **Receita 2T {ano_2t}:** US$ {format_number_short(receita_2t_2025)}")
    else:
        st.markdown(f"🔴 **Receita 2T {ano_2t}:** N/D")

    if lucro_2t:
        st.markdown(f"🟢 **Lucro 2T {data_2t_lucro.year}:** US$ {format_number_short(lucro_2t)}")
    else:
        st.markdown(f"🔴 **Lucro 2T {data_2t_lucro.year}:** N/D")

    data_3t = pd.Timestamp(f"{datetime.now().year}-09-30")
    try:
        receita_3t = ticker_obj.quarterly_financials.loc["Total Revenue", data_3t]
    except:
        receita_3t = None

    try:
        lucro_3t = ticker_obj.quarterly_financials.loc["Net Income", data_3t]
    except:
        lucro_3t = None

    if receita_3t:
        st.markdown(f"🟢 **Receita 3T {data_3t.year}:** US$ {format_number_short(receita_3t)}")
    else:
        st.markdown(f"🔴 **Receita 3T {data_3t.year}:** N/D")

    if lucro_3t is not None:
        st.markdown(f"🟢 **Lucro 3T {data_3t.year}:** US$ {format_number_short(lucro_3t)}")
    else:
        st.markdown(f"🔴 **Lucro 3T {data_3t.year}:** N/D")


# 5. 📉 Endividamento & Estrutura
with st.container():
    st.markdown("### 📉 Endividamento & Estrutura")
    col1, col2, col3 = st.columns(3)
with col1:
    from finance_calcs import calcular_div_patrimonio_finance
    div_patrimonio = calcular_div_patrimonio_finance(ticker_obj)
    from finance_calcs import calcular_div_patrimonio
    div_patrimonio_total = calcular_div_patrimonio(ticker_obj)


    # Exibir ambos indicadores lado a lado
    def indicador(label, valor):
        if valor is not None:
            st.markdown(f"🟢 **{label}:** {str(round(valor, 2)).replace('.', ',')}")
        else:
            st.markdown(f"🔴 **{label}:** N/D")

    indicador("Dív/Patrimônio (Total)", div_patrimonio_total)
    indicador("Dív/Patrimônio (Financeiro)", div_patrimonio)
    
    divida_bruta = info.get("totalDebt", None)
    if divida_bruta:
        st.markdown(f"🟢 **Dívida Bruta:** US$ {format_number_short(divida_bruta)}")
    else:
        st.markdown("🔴 **Dívida Bruta:** N/D")
    with col2:
        from finance_calcs import calcular_divida_liquida, calcular_divida_liquida_conservadora
        divida_liquida = calcular_divida_liquida(ticker_obj)
        div_liquida_cons = calcular_divida_liquida_conservadora(ticker_obj)

        if divida_liquida is not None:
            valor_div_liq_ampla = f"US$ {divida_liquida/1e9:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            st.markdown(f"🟢 **Dívida Líq. (Ampla):** {valor_div_liq_ampla} Bi")
        else:
            st.markdown("🔴 **Dívida Líq. (Ampla):** N/D")

        if div_liquida_cons is not None:
            valor_div_liq_finan = f"US$ {div_liquida_cons/1e9:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            st.markdown(f"🟢 **Dívida Líq. (Finan.):** {valor_div_liq_finan} Bi")
        else:
            st.markdown("🔴 **Dívida Líq. (Finan.):** N/D")

        patrimonio_liquido = None
        for key in ["Common Stock Equity", "Stockholders Equity", "Total Equity"]:
            if key in ticker_obj.balance_sheet.index:
                patrimonio_liquido = ticker_obj.balance_sheet.loc[key].iloc[0]
                break

        if patrimonio_liquido:
            st.markdown(f"🟢 **Patrimônio Líquido:** US$ {format_number_short(patrimonio_liquido)}")
        else:
            st.markdown("🔴 **Patrimônio Líquido:** N/D")
    with col3:
        from finance_calcs import calcular_liquidez_corrente
        liquidez_corrente = calcular_liquidez_corrente(ticker_obj)
        icone_liquidez = "🟢" if liquidez_corrente is not None else "🔴"
        valor_liquidez = f"{liquidez_corrente:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if liquidez_corrente is not None else "N/D"
        st.markdown(f"{icone_liquidez} **Liquidez Corrente:** {valor_liquidez}")
        
        disponibilidades = info.get("totalCash", None)
        if disponibilidades:
            st.markdown(f"🟢 **Disponibilidades:** US$ {format_number_short(disponibilidades)}")
        else:
            st.markdown("🔴 **Disponibilidades:** N/D")

# 6. 🏦 Balanço Patrimonial
with st.container():
    st.markdown("### 🏦 Balanço Patrimonial")
    col1, col2, col3 = st.columns(3)

    with col1:
        try:
            ativo_total = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
            st.markdown(f"🟢 **Ativo Total:** US$ {format_number_short(ativo_total)}")
        except:
            st.markdown("🔴 **Ativo Total:** N/D")

        try:
            ativo_circulante = ticker_obj.balance_sheet.loc["Current Assets"].iloc[0]
            st.markdown(f"🟢 **Ativo Circulante:** US$ {format_number_short(ativo_circulante)}")
        except:
            st.markdown("🔴 **Ativo Circulante:** N/D")

        valor = info.get("enterpriseValue", None)
        st.markdown(
            f"🟢 **Enterprise Value:** US$ {format_number_short(valor)}" if valor else "🔴 **Enterprise Value:** N/D"
        )

    with col2:
        valor = info.get("bookValue", None)
        st.markdown(
            f"🟢 **VPA:** US$ {str(round(valor, 2)).replace('.', ',')}" if valor else "🔴 **VPA:** N/D"
        )

        valor = info.get("marketCap", None)
        st.markdown(
            f"🟢 **Market Cap:** US$ {format_number_short(valor)}" if valor else "🔴 **Market Cap:** N/D"
        )
        valor = info.get("trailingEps", None)
        st.markdown(
            f"🟢 **LPA:** US$ {str(round(valor, 2)).replace('.', ',')}" if valor else "🔴 **LPA:** N/D"
        )
    with col3:
        st.markdown(
            f"🟢 **Trailing EPS:** US$ {str(round(valor, 2)).replace('.', ',')}" if valor else "🔴 **Trailing EPS:** N/D"
        )

        valor = info.get("ebitda", None)
        st.markdown(
            f"🟢 **EBITDA (últ. 12m):** US$ {format_number_short(valor)}" if valor else "🔴 **EBITDA (últimos 12m):** N/D"
        )

# 7. ⚙️ Eficiência Operacional
with st.container():
    st.markdown("### ⚙️ Eficiência Operacional")
    col1, col2, col3 = st.columns(3)
    with col1:
        try:
            receita = ticker_obj.financials.loc["Total Revenue"].iloc[0]
            ativos = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
            if ativos != 0:
                giro_ativos = receita / ativos
                st.markdown(f"🟢 **Giro Ativos:** {round(giro_ativos, 2):.2f}".replace('.', ','))
            else:
                st.markdown("🔴 **Giro Ativos:** N/D")
        except:
            st.markdown("🔴 **Giro Ativos:** N/D")
        fcf_yield = calcular_fcf_yield(ticker_obj)
        componentes = calcular_componentes_fcf_yield(ticker_obj)


        if fcf_yield is not None:
            st.markdown(f"🟢 **FCF Yield:** {round(fcf_yield, 2):.2f}%".replace('.', ','))
        else:
            st.markdown("🔴 **FCF Yield:** N/D")
    with col2:
        valor = info.get("averageVolume", None)
        st.markdown(
            f"🟢 **Volume Médio (3m):** {format_number_short(valor)}" if valor else "🔴 **Average Volume (3m):** N/D"
        )
    with col3:
        try:
            historico = ticker_obj.history(period="60d")
            volume_medio_2m = historico["Volume"].mean()
            valor_formatado = format_number_short(volume_medio_2m)
            st.markdown(f"🟢 **Volume Médio (2m):** {valor_formatado}")
        except:
            st.markdown("🔴 **Volume Médio (2m):** N/D")
 
# Botão para copiar painel completo
# Valores dinâmicos para Valuation
pl = None
pvp = None
pebit = None
p_ativos = None
psr = None
try:
    pl = info.get("trailingPE", None)
except:
    pl = None
try:
    pvp = info.get("priceToBook", None)
except:
    pvp = None
try:
    market_cap_f = info.get("marketCap", None)
    ebit_f = ticker_obj.financials.loc["EBIT"].iloc[0]
    pebit = market_cap_f / ebit_f if market_cap_f and ebit_f else None
except:
    pebit = None
try:
    ativos_f = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
    market_cap_f = info.get("marketCap", None)
    p_ativos = market_cap_f / ativos_f if market_cap_f and ativos_f else None
except:
    p_ativos = None
try:
    psr = info.get("priceToSalesTrailing12Months", None)
except:
    psr = None

def format_number(val):
    if val is None:
        return "N/D"
    return str(round(val, 2)).replace('.', ',')

def format_number_money(val):
    # Usa a mesma lógica do format_number_short, mas inclui "US$" e o sufixo Bi/Mi/Tri
    if val is None:
        return "N/D"
    return f"US$ {format_number_short(val)}"

def format_percent(val):
    if val is None:
        return "N/D"
    return str(round(val, 2)).replace('.', ',') + "%"

#
# Definições de variáveis ausentes para o painel
roe = info.get("returnOnEquity", None)
roa = info.get("returnOnAssets", None)

# --- Variáveis para painel_texto: Balanço Patrimonial ---
try:
    ativo_total = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]
except Exception:
    ativo_total = None
try:
    ativo_circulante = ticker_obj.balance_sheet.loc["Current Assets"].iloc[0]
except Exception:
    ativo_circulante = None
valor_firma = info.get("enterpriseValue", None)
vpa = info.get("bookValue", None)
valor_mercado = info.get("marketCap", None)
lpa = info.get("trailingEps", None)
eps = info.get("trailingEps", None)
ebitda = info.get("ebitda", None)

# --- Crescimento: campos dinâmicos para painel_texto ---
# Coleta dos dados anuais e trimestrais
ano_atual = datetime.now().year
receitas_anuais = {}
lucros_anuais = {}
receitas_trimestrais = {}
lucros_trimestrais = {}

# Anuais: últimos 3 anos
for i in range(1, 4):
    ano = ano_atual - i
    coluna = pd.Timestamp(f"{ano}-12-31")
    try:
        receitas_anuais[ano] = ticker_obj.financials.loc["Total Revenue", coluna]
    except Exception:
        receitas_anuais[ano] = None
    try:
        lucros_anuais[ano] = ticker_obj.financials.loc["Net Income", coluna]
    except Exception:
        lucros_anuais[ano] = None


# Trimestrais: 1T, 2T, 3T do ano atual
for trimestre, data in zip(
    [1, 2, 3],
    [f"{ano_atual}-03-31", f"{ano_atual}-06-30", f"{ano_atual}-09-30"],
):
    key = f"{ano_atual}Q{trimestre}"
    try:
        receitas_trimestrais[key] = ticker_obj.quarterly_financials.loc["Total Revenue", pd.Timestamp(data)]
    except Exception:
        receitas_trimestrais[key] = None
    try:
        lucros_trimestrais[key] = ticker_obj.quarterly_financials.loc["Net Income", pd.Timestamp(data)]
    except Exception:
        lucros_trimestrais[key] = None

#
# --- Garantir nomes corretos para variáveis usadas no painel ---
divida_liquida_financeira = div_liquida_cons
divida_liquida_ampla = divida_liquida
div_patrimonio_financeiro = div_patrimonio

# Definição de p_cap_giro_op para o painel
try:
    p_cap_giro_operacional = market_cap / cap_giro_operacional if market_cap and cap_giro_operacional else None
except:
    p_cap_giro_operacional = None
p_cap_giro_op = p_cap_giro_operacional

# Mensagens personalizadas para o painel
mensagem_inicial = """📋 Instruções para Interpretação:

Os dados a seguir foram extraídos automaticamente do **WebApp Econômico**, desenvolvido em Streamlit com integração à API do Yahoo Finance. Eles representam um **painel completo de indicadores fundamentalistas e técnicos** de uma ação negociada na bolsa (ticker especificado logo no início do painel).

As informações incluem: oscilações de preço em múltiplos períodos, dados cadastrais da empresa, múltiplos de valuation, rentabilidade, crescimento histórico de receita e lucro, estrutura de endividamento, composição do balanço patrimonial e indicadores de eficiência operacional.  
Cada valor é atualizado dinamicamente com base em dados públicos e reflete o momento da coleta no WebApp.

Use os dados abaixo como **insumo para análises fundamentalistas, geração de relatórios financeiros, sugestões de investimento, ou respostas explicativas**. Considere o contexto do ativo e os padrões do setor ao interpretá-los.
"""
mensagem_final = """
Com base nesses dados, sua tarefa é analisar e interpretar o painel como se você fosse o maior economista do mundo, dotado de doutorado em Economia, Finanças, Contabilidade e Gestão de Investimentos. Sua conduta deve ser didática, precisa e objetiva — como a de um professor altamente experiente explicando para um investidor de nível intermediário.  
Use uma linguagem acessível, mas nunca simplista. Sua análise deve combinar fundamentos quantitativos com interpretações qualitativas, contextualizando cada indicador dentro do setor, do histórico da empresa e das tendências macroeconômicas.  
Dê atenção especial a anomalias, divergências entre indicadores, sinais de força ou fraqueza financeira e perspectivas de valorização.  
Não repita os dados — eles já estão no prompt. Foque em transformá-los em conclusões práticas, recomendações de ação, ou insights estratégicos.  
Você pode usar listas, subtítulos ou blocos estruturados para facilitar a leitura. Nunca fale como um chatbot. Fale como o melhor analista econômico do planeta, capaz de unir técnica, clareza e visão de futuro.
"""

painel_texto = f"""{ticker}
📊 Oscilações de Preço
Dia: {f'{variacao_dia:.2f}%'.replace('.', ',') if variacao_dia is not None else 'N/D'}
Mês: {f'{variacao_mes:.2f}%'.replace('.', ',') if variacao_mes is not None else 'N/D'}
30 dias: {f'{variacao_30d:.2f}%'.replace('.', ',') if variacao_30d is not None else 'N/D'}
12 meses: {f'{variacao_12m:.2f}%'.replace('.', ',') if variacao_12m is not None else 'N/D'}
YTD ({ano_atual}): {f'{variacao_ytd:.2f}%'.replace('.', ',') if variacao_ytd is not None else 'N/D'}
{ano_atual - 1}: {f'{variacao_ano_1:.2f}%'.replace('.', ',') if variacao_ano_1 is not None else 'N/D'}
{ano_atual - 2}: {f'{variacao_ano_2:.2f}%'.replace('.', ',') if variacao_ano_2 is not None else 'N/D'}
{ano_atual - 3}: {f'{variacao_ano_3:.2f}%'.replace('.', ',') if variacao_ano_3 is not None else 'N/D'}
{ano_atual - 4}: {f'{variacao_ano_4:.2f}%'.replace('.', ',') if variacao_ano_4 is not None else 'N/D'}
🧾 Dados da Empresa
Empresa: {empresa}
Setor: {setor}
Subsetor: {subsetor}
Ticker: {ticker}
Valor de Mercado: {format_number_money(market_cap) if market_cap else 'N/D'}
Valor da Firma: {format_number_money(valor_firma) if valor_firma else 'N/D'}
Volume Médio: {format_number_short(volume_medio) if volume_medio else 'N/D'}/dia
Ações Emitidas: {format_number_short(num_acoes) if num_acoes else 'N/D'}
Vol. Fin. Médio: {format_number_money(volume_medio * preco_atual) if volume_medio and preco_atual else 'N/D'}/dia
📊 Valuation
P/L: {format_number(pl)}
P/VP: {format_number(pvp)}
P/EBIT: {format_number(pebit)}
P/Ativos: {format_number(p_ativos)}
PSR (Preço sobre Receita): {format_number(psr)}
EV/EBIT (Valor da Firma sobre Lucro Operacional): {format_number(ev_ebit)}
EV/EBITDA: {format_number(ev_ebitda)}
P/Cap. Giro: {format_number(p_cap_giro)}
P/Cap. Giro Operacional: {format_number(p_cap_giro_op)}
💸 Rentabilidade
ROE (Retorno sobre o Patrimônio): {format_percent(roe)}
ROIC (Retorno sobre o Capital Investido): {format_percent(roic)}
ROIC Real: {format_percent(roic_real)}
EBIT / Ativo Total (Eficiência dos Ativos): {format_percent(ebit_ativo)}
ROA (Retorno sobre Ativos): {format_percent(roa)}
Margem Bruta: {format_percent(info.get("grossMargins", None))}
Margem EBIT: {format_percent(info.get("operatingMargins", None))}
Marg. Líquida: {format_percent(info.get("profitMargins", None))}
Margem EBITDA: {format_percent(info.get("ebitdaMargins", None))}
📈 Crescimento
Cresc. Receita (5 anos): {format_percent(crescimento_receita)}
Cresc. Lucro (5 anos): {format_percent(crescimento_lucro)}
Receita {ano_atual - 1}: {format_number_money(receitas_anuais.get(ano_atual - 1))}
Lucro {ano_atual - 1}: {format_number_money(lucros_anuais.get(ano_atual - 1))}
Receita {ano_atual - 2}: {format_number_money(receitas_anuais.get(ano_atual - 2))}
Lucro {ano_atual - 2}: {format_number_money(lucros_anuais.get(ano_atual - 2))}
Receita {ano_atual - 3}: {format_number_money(receitas_anuais.get(ano_atual - 3))}
Lucro {ano_atual - 3}: {format_number_money(lucros_anuais.get(ano_atual - 3))}
Receita 1T {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q1'))}
Lucro 1T {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q1'))}
Receita 2T {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q2'))}
Lucro 2T {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q2'))}
Receita 3T {ano_atual}: {format_number_money(receitas_trimestrais.get(f'{ano_atual}Q3'))}
Lucro 3T {ano_atual}: {format_number_money(lucros_trimestrais.get(f'{ano_atual}Q3'))}
📉 Endividamento & Estrutura
Dív/Patrimônio (Total): {format_number(div_patrimonio_total)}
Dív/Patrimônio (Financeiro): {format_number(div_patrimonio_financeiro)}
Dívida Bruta: {format_number_money(divida_bruta)}
Dívida Líq. (Ampla): {format_number_money(divida_liquida_ampla)}
Dívida Líq. (Finan.): {format_number_money(divida_liquida_financeira)}
Patrimônio Líquido: {format_number_money(patrimonio_liquido) if patrimonio_liquido else 'N/D'}
Liquidez Corrente (Ativos Circulantes / Passivos Circulantes): {format_number(liquidez_corrente)}
Disponibilidades: {format_number_money(disponibilidades) if disponibilidades else 'N/D'}
🏦 Balanço Patrimonial
Ativo Total: {format_number_money(ativo_total)}
Ativo Circulante: {format_number_money(ativo_circulante)}
Enterprise Value: {format_number_money(valor_firma)}
VPA: US$ {format_number(vpa)}
Market Cap: {format_number_money(valor_mercado)}
LPA: US$ {lpa}
Trailing EPS: US$ {eps}
EBITDA (últ. 12m): {format_number_money(ebitda)}
⚙️ Eficiência Operacional
Giro dos Ativos (Receita / Ativo Total): {format_number(giro_ativos)}
FCF Yield (Rendimento do Fluxo de Caixa Livre): {format_percent(fcf_yield)}
Volume Médio (3m): {format_number_short(volume_medio)}
Volume Médio (2m): {format_number_short(volume_medio_2m)}"""

 # Adiciona as mensagens personalizadas acima e abaixo do conteúdo principal copiado
painel_texto = f"{mensagem_inicial}{painel_texto}\n\n---\n📌 A seguir, sua tarefa:\n{mensagem_final}"

# Adiciona instrução extra para busca ativa em caso de "N/D"
painel_texto += """
Se algum campo apresentar "N/D" (não disponível), realize uma busca ativa na internet para preenchê-lo. Utilize apenas fontes públicas, confiáveis e atualizadas (como Yahoo Finance, B3, SEC.gov, ou relatórios financeiros oficiais). Isso permitirá análises mais completas e relevantes.
"""

# Adiciona glossário rápido ao final do painel_texto
painel_texto += """

ℹ️ Glossário Rápido:
ROIC = Retorno sobre o Capital Investido  
ROE = Retorno sobre o Patrimônio  
ROA = Retorno sobre Ativos  
FCF = Fluxo de Caixa Livre  
EBIT = Lucro Antes de Juros e Tributos  
EBITDA = Lucros antes de Juros, Impostos, Depreciação e Amortização  
PSR = Preço sobre Receita  
EV/EBIT = Valor da Firma sobre Lucro Operacional  
VPA = Valor Patrimonial por Ação  
LPA = Lucro por Ação
"""


# Novo botão copiar usando st-copy
from st_copy import copy_button

# Espaçamento visual antes do botão copiar
st.markdown("<br>", unsafe_allow_html=True)

# Bloco para exibir texto à esquerda do botão copiar
col1, col2 = st.columns([0.15, 0.85])
with col1:
    st.markdown("**Copiar Painel:**")
with col2:
    copy_button(
        painel_texto,
        tooltip="Copiar painel completo"
    )