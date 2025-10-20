import yfinance as yf

def calcular_oscilacao_mes(ticker_obj):
    """
    Calcula a variação percentual do preço da ação no último mês.
    Retorna o valor percentual ou None se não for possível calcular.
    """
    try:
        hist = ticker_obj.history(period="1mo")
        if hist is None or len(hist) < 2:
            return None
        preco_inicio = hist["Close"].iloc[0]
        preco_fim = hist["Close"].iloc[-1]
        return (preco_fim - preco_inicio) / preco_inicio * 100
    except Exception:
        return None

def calcular_oscilacao_30d(ticker_obj):
    """
    Calcula a variação percentual do preço da ação nos últimos 30 dias.
    Retorna o valor percentual ou None se não for possível calcular.
    """
    try:
        hist = ticker_obj.history(period="31d")
        if hist is None or len(hist) < 2:
            return None
        preco_inicio = hist["Close"].iloc[0]
        preco_fim = hist["Close"].iloc[-1]
        return (preco_fim - preco_inicio) / preco_inicio * 100
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_oscilacao_12m
def calcular_oscilacao_12m(ticker_obj):
    """
    Calcula a variação percentual do preço da ação nos últimos 12 meses.
    Retorna o valor percentual ou None se não for possível calcular.
    """
    try:
        hist = ticker_obj.history(period="1y")
        if hist is None or len(hist) < 2:
            return None
        preco_inicio = hist["Close"].iloc[0]
        preco_fim = hist["Close"].iloc[-1]
        return (preco_fim - preco_inicio) / preco_inicio * 100
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_oscilacao_ano
from datetime import datetime

def calcular_oscilacao_ano(ano, ticker_obj):
    """
    Calcula a variação percentual do preço da ação em um ano específico.
    Para o ano atual, calcula até a data de hoje (YTD).
    """
    try:
        start = f"{ano}-01-01"
        if ano == datetime.now().year:
            end = datetime.today().strftime("%Y-%m-%d")
        else:
            end = f"{ano}-12-31"

        hist = ticker_obj.history(start=start, end=end)
        if hist is None or len(hist) < 2:
            return None
        preco_inicio = hist["Close"].iloc[0]
        preco_fim = hist["Close"].iloc[-1]
        return (preco_fim - preco_inicio) / preco_inicio * 100
    except Exception:
        return None

def calcular_roic(ticker_obj):
    """
    Calcula o ROIC (Return on Invested Capital) como:
    ROIC = EBIT / Capital Investido
    Onde o Capital Investido = Total Assets - Current Liabilities,
    ou se não disponível, usa Total Assets - Total Liabilities como fallback.
    """
    try:
        ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
        total_assets = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]

        try:
            current_liabilities = ticker_obj.balance_sheet.loc["Current Liabilities"].iloc[0]
        except KeyError:
            current_liabilities = None

        if current_liabilities is not None:
            capital_investido = total_assets - current_liabilities
        else:
            total_liabilities = ticker_obj.balance_sheet.loc["Total Liabilities"].iloc[0]
            capital_investido = total_assets - total_liabilities

        if capital_investido == 0:
            return None

        roic = ebit / capital_investido * 100
        return roic
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_roic_real
def calcular_roic_real(ticker_obj):
    """
    Calcula o ROIC Real como:
    ROIC Real = NOPAT / Capital Investido
    Onde NOPAT = EBIT * (1 - Taxa Efetiva de Imposto)
    Capital Investido = Total Assets - Current Liabilities (ou Total Liabilities como fallback)
    """
    try:
        ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
        total_assets = ticker_obj.balance_sheet.loc["Total Assets"].iloc[0]

        try:
            current_liabilities = ticker_obj.balance_sheet.loc["Current Liabilities"].iloc[0]
        except KeyError:
            current_liabilities = None

        if current_liabilities is not None:
            capital_investido = total_assets - current_liabilities
        else:
            total_liabilities = ticker_obj.balance_sheet.loc["Total Liabilities"].iloc[0]
            capital_investido = total_assets - total_liabilities

        if capital_investido == 0:
            return None

        income_tax = ticker_obj.financials.loc["Tax Provision"].iloc[0]
        earnings_before_tax = ticker_obj.financials.loc["Pretax Income"].iloc[0]

        if earnings_before_tax != 0:
            tax_rate = income_tax / earnings_before_tax
        else:
            tax_rate = 0.25  # fallback padrão

        nopat = ebit * (1 - tax_rate)
        roic_real = nopat / capital_investido * 100
        return roic_real
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_roic_ajustado
def calcular_roic_ajustado(ticker_obj):
    """
    Calcula o ROIC ajustado como:
    ROIC = EBIT / (Patrimônio Líquido + Dívida Total - Caixa e Equivalentes)
    Retorna o valor percentual ou None se não for possível calcular.
    """
    try:
        ebit = ticker_obj.financials.loc["EBIT"].iloc[0]
        patrimonio_liquido = ticker_obj.balance_sheet.loc["Total Stockholder Equity"].iloc[0]
        total_divida = ticker_obj.balance_sheet.loc["Total Debt"].iloc[0]
        caixa = ticker_obj.balance_sheet.loc["Cash And Cash Equivalents"].iloc[0]

        capital_investido = patrimonio_liquido + total_divida - caixa

        if capital_investido == 0:
            return None

        roic_ajustado = ebit / capital_investido * 100
        return roic_ajustado
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_crescimento_receita
def calcular_crescimento_receita(ticker_obj):
    """
    Calcula a taxa de crescimento anual composta (CAGR) da Receita Total com base nos anos válidos.
    Ignora entradas com valores nulos e calcula a diferença real de anos entre os registros.
    """
    try:
        revenues = ticker_obj.financials.loc["Total Revenue"].dropna()
        if len(revenues) < 2:
            return None

        receita_mais_nova = revenues.iloc[0]
        receita_mais_antiga = revenues.iloc[-1]

        ano_novo = revenues.index[0].year
        ano_antigo = revenues.index[-1].year
        anos = ano_novo - ano_antigo

        if receita_mais_antiga == 0 or receita_mais_nova == 0 or anos == 0:
            return None

        cagr = (receita_mais_nova / receita_mais_antiga) ** (1 / anos) - 1
        return cagr * 100
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_crescimento_lucro
def calcular_crescimento_lucro(ticker_obj):
    """
    Calcula a taxa de crescimento anual composta (CAGR) do Lucro Líquido com base nos anos válidos.
    Ignora entradas com valores nulos ou zero e calcula a diferença real de anos.
    Se o lucro mais antigo for negativo, retorna None pois não é possível calcular CAGR.
    """
    try:
        lucros = ticker_obj.financials.loc["Net Income"].dropna()
        lucros = lucros[lucros != 0]  # Ignora valores zero
        if len(lucros) < 2:
            return None

        lucro_mais_novo = lucros.iloc[0]
        lucro_mais_antigo = lucros.iloc[-1]

        ano_novo = lucros.index[0].year
        ano_antigo = lucros.index[-1].year
        anos = ano_novo - ano_antigo

        if lucro_mais_antigo <= 0 or lucro_mais_novo <= 0 or anos == 0:
            return None

        cagr = (lucro_mais_novo / lucro_mais_antigo) ** (1 / anos) - 1
        return cagr * 100
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_div_patrimonio
def calcular_div_patrimonio(ticker_obj):
    """
    Calcula o índice Dívida/Patrimônio como:
    Dív/Patrimônio = Dívida Total / Patrimônio Líquido
    Tenta diferentes nomes de índices conforme a disponibilidade no balance_sheet.
    Procura o valor mais recente válido (não nulo) nas colunas disponíveis.
    """
    try:
        bs = ticker_obj.balance_sheet

        # Nomes possíveis para dívida total
        possiveis_dividas = [
            "Total Liab",
            "Total Liabilities Net Minority Interest"
        ]

        # Nomes possíveis para patrimônio líquido
        possiveis_patrimonios = [
            "Total Stockholder Equity",
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest"
        ]

        import pandas as pd

        def encontrar_valor_valido(nomes_possiveis):
            for nome in nomes_possiveis:
                if nome in bs.index:
                    for col in reversed(bs.columns):
                        valor = bs.loc[nome, col]
                        if not pd.isna(valor):
                            return valor
            return None

        total_liabilities = encontrar_valor_valido(possiveis_dividas)
        total_equity = encontrar_valor_valido(possiveis_patrimonios)

        if total_liabilities is None or total_equity is None or total_equity == 0:
            return None

        return total_liabilities / total_equity
    except Exception:
        return None

# NOVA FUNÇÃO: calcular_div_patrimonio_finance (Yahoo Finance style)
def calcular_div_patrimonio_finance(ticker_obj):
    """
    Calcula o índice Dívida/Patrimônio com base apenas na dívida financeira (como exibido no Yahoo Finance):
    Dív/Patrimônio = (Short Term Debt + Long Term Debt) / Patrimônio Líquido
    """
    try:
        bs = ticker_obj.balance_sheet
        import pandas as pd

        def encontrar_valor_valido(chave):
            if chave in bs.index:
                for col in reversed(bs.columns):
                    valor = bs.loc[chave, col]
                    if not pd.isna(valor):
                        return valor
            return 0  # assume 0 se não houver

        # Dívidas financeiras
        short_term_debt = encontrar_valor_valido("Current Debt")
        long_term_debt = encontrar_valor_valido("Long Term Debt")
        total_debt = short_term_debt + long_term_debt

        # Patrimônio Líquido
        possiveis_patrimonios = [
            "Total Stockholder Equity",
            "Stockholders Equity",
            "Common Stock Equity",
            "Total Equity Gross Minority Interest"
        ]
        equity = None
        for nome in possiveis_patrimonios:
            if nome in bs.index:
                for col in reversed(bs.columns):
                    valor = bs.loc[nome, col]
                    if not pd.isna(valor):
                        equity = valor
                        break
            if equity is not None:
                break

        if equity is None or equity == 0:
            return None

        return total_debt / equity
    except Exception:
        return None

# NOVA FUNÇÃO: calcular_divida_liquida
def calcular_divida_liquida(ticker_obj):
    """
    Calcula a Dívida Líquida:
    Dívida Líquida = (Current Debt + Long Term Debt) - (Caixa e Equivalentes + Investimentos de Curto Prazo)
    """
    try:
        bs = ticker_obj.balance_sheet
        import pandas as pd

        def pegar_valor_mais_recente(campo):
            if campo in bs.index:
                for col in reversed(bs.columns):
                    valor = bs.loc[campo, col]
                    if not pd.isna(valor):
                        return valor
            return 0

        # Dívida Bruta
        current_debt = pegar_valor_mais_recente("Current Debt")
        long_term_debt = pegar_valor_mais_recente("Long Term Debt")
        total_debt = current_debt + long_term_debt

        # Disponibilidades
        cash = pegar_valor_mais_recente("Cash And Cash Equivalents")
        short_term_investments = pegar_valor_mais_recente("Other Short Term Investments")
        marketable_securities = pegar_valor_mais_recente("Available For Sale Securities")
        other_investments = pegar_valor_mais_recente("Other Investments")
        total_disponibilidades = cash + short_term_investments + marketable_securities + other_investments

        return total_debt - total_disponibilidades
    except Exception:
        return None

# NOVA FUNÇÃO: calcular_divida_liquida_conservadora
def calcular_divida_liquida_conservadora(ticker_obj):
    """
    Calcula a Dívida Líquida (versão conservadora):
    Dívida Líquida = (Current Debt + Long Term Debt) - (Caixa + Investimentos de curto prazo altamente líquidos)
    Exclui campos menos líquidos como Other Investments e Available For Sale Securities.
    """
    try:
        bs = ticker_obj.balance_sheet
        import pandas as pd

        def pegar_valor_mais_recente(campo):
            if campo in bs.index:
                for col in reversed(bs.columns):
                    valor = bs.loc[campo, col]
                    if not pd.isna(valor):
                        return valor
            return 0

        # Dívida Bruta
        current_debt = pegar_valor_mais_recente("Current Debt")
        long_term_debt = pegar_valor_mais_recente("Long Term Debt")
        total_debt = current_debt + long_term_debt

        # Disponibilidades altamente líquidas
        cash = pegar_valor_mais_recente("Cash And Cash Equivalents")
        short_term_investments = pegar_valor_mais_recente("Other Short Term Investments")
        total_liquido = cash + short_term_investments

        return total_debt - total_liquido
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_liquidez_corrente
def calcular_liquidez_corrente(ticker_obj):
    """
    Calcula a Liquidez Corrente:
    Liquidez Corrente = Ativo Circulante / Passivo Circulante
    """
    try:
        bs = ticker_obj.balance_sheet
        import pandas as pd

        def pegar_valor_mais_recente(campo):
            if campo in bs.index:
                for col in reversed(bs.columns):
                    valor = bs.loc[campo, col]
                    if not pd.isna(valor):
                        return valor
            return None

        current_assets = pegar_valor_mais_recente("Current Assets")
        current_liabilities = pegar_valor_mais_recente("Current Liabilities")

        if current_assets is None or current_liabilities is None or current_liabilities == 0:
            return None

        return current_assets / current_liabilities
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_fcf_yield
def calcular_fcf_yield(ticker_obj):
    """
    Calcula o FCF Yield (%) como:
    FCF Yield = (Free Cash Flow / Valor de Mercado) * 100
    Onde:
    Free Cash Flow = Total Cash From Operating Activities - Capital Expenditures
    """
    try:
        cf = ticker_obj.cashflow
        info = ticker_obj.info

        fcf_operacional = cf.loc["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cf.index else None
        capex = cf.loc["Capital Expenditure"].iloc[0] if "Capital Expenditure" in cf.index else None
        market_cap = info.get("marketCap", None)

        if fcf_operacional is not None and capex is not None:
            fcf = fcf_operacional + capex
            if market_cap and market_cap != 0:
                return fcf / market_cap * 100

        return None
    except Exception:
        return None


# NOVA FUNÇÃO: calcular_componentes_fcf_yield
def calcular_componentes_fcf_yield(ticker_obj):
    """
    Retorna os componentes usados no cálculo do FCF Yield para debug visual.
    """
    try:
        cf = ticker_obj.cashflow
        info = ticker_obj.info

        fcf_operacional = cf.loc["Operating Cash Flow"].iloc[0] if "Operating Cash Flow" in cf.index else None
        capex = cf.loc["Capital Expenditure"].iloc[0] if "Capital Expenditure" in cf.index else None
        market_cap = info.get("marketCap", None)

        if fcf_operacional is not None and capex is not None:
            fcf = fcf_operacional + capex
        else:
            fcf = None

        return {
            "fcf_operacional": fcf_operacional,
            "capex": capex,
            "fcf": fcf,
            "market_cap": market_cap
        }
    except:
        return {
            "fcf_operacional": None,
            "capex": None,
            "fcf": None,
            "market_cap": None
        }