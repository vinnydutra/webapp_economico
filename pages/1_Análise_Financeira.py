import streamlit as st
import yfinance as yf
from datetime import datetime
import plotly.graph_objects as go
import plotly.express as px
import wikipedia
import re

# Restaura token de sessão antes de qualquer chamada ao Supabase
from utils import restaurar_usuario_sessao
restaurar_usuario_sessao()


st.set_page_config(page_title="Dashboard Financeiro", page_icon="💰", layout="wide")

# Reduz espaçamento superior do container padrão do Streamlit
st.markdown("""
    <style>
        .block-container {
            padding-top: 1rem;
        }
    </style>
""", unsafe_allow_html=True)

# Bloco de usuário e logout com layout responsivo
usuario_logado = st.session_state.get("usuario", "desconhecido")

st.markdown(f"""
<br>
<div style='display: flex; justify-content: flex-end; align-items: center; gap: 10px; margin-bottom: 12px;'>
    <span style='color: #ccc; font-size: 14px;'>👤 {usuario_logado}</span>
    <form action='/?logout=true' method='get'>
        <button type='submit' title='Logout' style='background: none; border: none; color: #ccc; font-size: 18px; cursor: pointer;'>⏻</button>
    </form>
</div>
""", unsafe_allow_html=True)

# Lógica de logout
if st.query_params.get("logout") == "true":
    for chave in ["usuario", "carteira", "ticker", "favoritos_analise", "uid"]:
        if chave in st.session_state:
            del st.session_state[chave]
    st.query_params.clear()
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()

# Funções utilitárias centralizadas
from utils import (
    carregar_favoritos,
    adicionar_favorito,
    remover_favorito,
    formatar_valor,
    obter_usuario,
    supabase_autenticado,
    traduzir_recomendacao,
)

# Função de análise de dividendos
def analisar_dividendos(dy, payout):
    try:
        dy = float(dy)
        payout = float(payout)
    except:
        return "Dados insuficientes para análise."

    analise = ""

    if dy >= 10:
        analise += "O Dividend Yield está extremamente alto, indicando alta geração de renda. "
    elif 5 <= dy < 10:
        analise += "O Dividend Yield é saudável e equilibrado. "
    else:
        analise += "O Dividend Yield é baixo, sugerindo foco em reinvestimento. "

    if payout > 100:
        analise += "O Payout Ratio acima de 100% indica que a empresa distribui mais do que lucra, o que pode não ser sustentável no longo prazo."
    elif payout >= 50:
        analise += "O Payout Ratio está em patamar saudável, mostrando equilíbrio entre dividendos e retenção de lucros."
    else:
        analise += "O Payout Ratio é baixo, indicando forte retenção de lucros para expansão ou segurança financeira."

    return analise

# Função de análise de crescimento
def analisar_crescimento(earnings_growth, revenue_growth, roe, roa, profit_margin):
    try:
        earnings_growth = float(earnings_growth) * 100
        revenue_growth = float(revenue_growth) * 100
        roe = float(roe) * 100
        roa = float(roa) * 100
        profit_margin = float(profit_margin) * 100
    except:
        return "Dados insuficientes para análise."

    analise = ""

    if earnings_growth >= 20:
        analise += "O crescimento de lucros é excelente, indicando expansão robusta. "
    elif 10 <= earnings_growth < 20:
        analise += "O crescimento de lucros é bom, demonstrando consistência. "
    else:
        analise += "O crescimento de lucros é modesto, sugerindo estabilidade ou maturidade da empresa. "

    if revenue_growth >= 20:
        analise += "O crescimento de receita é excelente, reforçando expansão de mercado. "
    elif 10 <= revenue_growth < 20:
        analise += "O crescimento de receita é saudável, acima da média. "
    else:
        analise += "O crescimento de receita é baixo, indicando possível estagnação de mercado. "

    if roe >= 15:
        analise += "O ROE é excelente, revelando alta rentabilidade sobre o patrimônio dos acionistas. "
    elif 10 <= roe < 15:
        analise += "O ROE é bom e demonstra gestão eficiente. "
    else:
        analise += "O ROE é baixo, indicando menor eficiência na geração de valor para os acionistas. "

    if roa >= 7:
        analise += "O ROA é saudável, evidenciando boa utilização dos ativos. "
    elif 3 <= roa < 7:
        analise += "O ROA é mediano, dentro dos parâmetros aceitáveis. "
    else:
        analise += "O ROA é baixo, sugerindo baixa eficiência no uso dos ativos. "

    if profit_margin >= 20:
        analise += "A margem líquida é excelente, demonstrando forte capacidade de retenção de lucro. "
    elif 10 <= profit_margin < 20:
        analise += "A margem líquida é boa, indicando operação eficiente. "
    else:
        analise += "A margem líquida é baixa, apontando maiores custos ou menor eficiência operacional."

    return analise

# Função de análise de endividamento
def analisar_endividamento(debt_to_equity, current_ratio, quick_ratio):
    try:
        debt_to_equity = float(debt_to_equity)
        current_ratio = float(current_ratio)
        quick_ratio = float(quick_ratio)
    except:
        return "Dados insuficientes para análise."

    analise = ""

    # Debt to Equity
    if debt_to_equity <= 50:
        analise += "O endividamento é muito baixo, indicando perfil bastante conservador. "
    elif 50 < debt_to_equity <= 100:
        analise += "O endividamento é moderado e saudável, bem equilibrado. "
    elif 100 < debt_to_equity <= 200:
        analise += "O endividamento é elevado, mas pode ser aceitável dependendo do setor. "
    else:
        analise += "O endividamento é muito alto, o que representa risco financeiro significativo. "

    # Current Ratio
    if current_ratio >= 2.0:
        analise += "A liquidez corrente é excelente, mostrando conforto para honrar obrigações de curto prazo. "
    elif 1.5 <= current_ratio < 2.0:
        analise += "A liquidez corrente é boa e estável. "
    elif 1.0 <= current_ratio < 1.5:
        analise += "A liquidez corrente é razoável, mas exige atenção. "
    else:
        analise += "A liquidez corrente está abaixo de 1, indicando que a empresa pode não ter ativos circulantes suficientes para cobrir suas dívidas de curto prazo. "

    # Quick Ratio
    if quick_ratio >= 1.5:
        analise += "A liquidez imediata (Quick Ratio) é excelente, garantindo segurança sem depender de estoques. "
    elif 1.0 <= quick_ratio < 1.5:
        analise += "A liquidez imediata é boa. "
    elif 0.7 <= quick_ratio < 1.0:
        analise += "A liquidez imediata é limitada, requerendo cautela. "
    else:
        analise += "A liquidez imediata é muito baixa, o que representa risco financeiro em situações adversas."

    return analise




def buscar_fundacao(nome_empresa):
    try:
        # 🔍 Primeiro tenta na Wikipedia em português
        wikipedia.set_lang("pt")
        try:
            pagina = wikipedia.page(nome_empresa)
        except wikipedia.exceptions.PageError:
            # 🔄 Se não encontrar, tenta na Wikipedia em inglês
            wikipedia.set_lang("en")
            pagina = wikipedia.page(nome_empresa)
        
        conteudo = pagina.content.lower()

        # 🔍 Procura padrões comuns
        marcadores = [
            "fundada em", "fundada no", "fundada a", "criada em", "criada no", "criada a",
            "founded in", "founded on", "founded at", "incorporated in", "incorporated on"
        ]

        for marcador in marcadores:
            if marcador in conteudo:
                parte = conteudo.split(marcador)[1]
                trecho = parte.split(".")[0].split("\n")[0].strip()

                # 🔍 Extrair o primeiro ano (número com 4 dígitos)
                ano = re.search(r'\b(17|18|19|20)\d{2}\b', trecho)
                if ano:
                    return ano.group()

                return trecho.capitalize()

        return "Não encontrado"
    except Exception:
        return "Não disponível"




if "uid" in st.session_state and st.session_state.uid:
    if "favoritos_analise" not in st.session_state or not isinstance(st.session_state["favoritos_analise"], list):
        st.session_state["favoritos_analise"] = carregar_favoritos(st.session_state.uid)
else:
    st.warning("Usuário não autenticado. Faça login para acessar a carteira.")
    st.stop()

carteira = st.session_state.get("favoritos_analise", [])

if 'ticker' not in st.session_state:
    st.session_state.ticker = "PETR4.SA"

# Campo de busca de ticker na barra lateral
ticker = st.session_state.ticker
# Ordenar tickers
tickers_ordenados = sorted(carteira)

# 🔝 Bloco de botões de favoritos no topo da página (fora da sidebar)
if tickers_ordenados:
    st.markdown("""
    <style>
        div[data-testid="stColumn"] {
            width: fit-content !important;
            flex: unset;
        }
        div[data-testid="stColumn"] * {
            width: fit-content !important;
        }
    </style>
    """, unsafe_allow_html=True)

    cols = st.columns(len(tickers_ordenados))
    for col, ticker_item in zip(cols, tickers_ordenados):
        with col:
            if st.button(ticker_item, key=f"botao_topo_{ticker_item}", use_container_width=False):
                st.session_state.ticker = ticker_item
                st.rerun()

    # Espaçamento vertical após os botões de tickers favoritos
    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

col1, col2, col3 = st.columns([1, 5, 4])

with col1:
    estrela_ativa = ticker in carteira
    estrela = "⭐" if estrela_ativa else "☆"
    if st.button(estrela, key="star-button", help="Adicionar ou remover da carteira"):
        if estrela_ativa:
            carteira.remove(ticker)
        else:
            carteira.append(ticker)
        st.session_state.favoritos_analise = carteira
        if estrela_ativa:
            remover_favorito(ticker)
        else:
            # Verifica autenticação antes de favoritar
            if not supabase_autenticado():
                st.error("Você não está autenticado. Faça login para favoritar ativos.")
            else:
                adicionar_favorito(ticker)
        estrela_ativa = not estrela_ativa
        estrela = "⭐" if estrela_ativa else "☆"
        st.rerun()

with col2:
    # Exibe o ticker com o nome da empresa ao lado, estilizado
    nome_empresa_topo = ""
    try:
        acao_tmp = yf.Ticker(ticker)
        info_tmp = acao_tmp.info
        nome_empresa_topo = info_tmp.get('shortName', '')
    except Exception:
        nome_empresa_topo = ""
    st.markdown(
        f"""
        <h1 style='margin: 0; padding: 0; display: inline-block;'>
            {ticker} <span style='font-size: 16px; color: #aaa;'>({nome_empresa_topo})</span>
        </h1>
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

st.markdown("""
<style>
section[data-testid="stSidebar"] h2 {
    margin-bottom: 2px !important;
}
section[data-testid="stSidebar"] .block-container > div {
    margin-top: 0px !important;
    padding-top: 0px !important;
}
section[data-testid="stSidebar"] {
    padding-top: 0px !important;
    margin-top: 0px !important;
}
</style>
""", unsafe_allow_html=True)

# Blocos de CSS relacionados aos botões da sidebar e ao topo da página
st.markdown(
    """
    <style>
    /* ✅ Botão da estrela fora da sidebar */
    div.stButton > button {
        font-size: 18px !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# Bloco de CSS para estilizar st.success() com fundo igual à sidebar (ajustado para #31333F, borda e sombra)
st.markdown("""
    <style>
    div.stAlert {
        background-color: #31333F !important;  /* Mesma cor da sidebar */
        color: white !important;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.3);
        box-shadow: 0px 0px 8px rgba(0,0,0,0.6);
    }
    </style>
    """, unsafe_allow_html=True)




# CSS aprimorado para os botões da sidebar e espaçamento dos balões de análise
st.markdown(
    """
    <style>
    .sidebar-botao {
        background-color: rgba(255, 255, 255, 0.05);
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.5);
        border-radius: 8px;
        padding: 8px 14px;
        font-size: 1rem;
        cursor: pointer;
        text-decoration: none !important;
        display: inline-block;
        transition: all 0.3s ease;
        box-shadow: 1px 1px 3px rgba(0,0,0,0.5);
    }

    .sidebar-botao:hover {
        background-color: rgba(255, 255, 255, 0.15);
        box-shadow: 2px 2px 6px rgba(0,0,0,0.7);
        border: 1px solid rgba(255, 255, 255, 0.7);
        text-decoration: none !important;
        /* Não alterar color no hover para garantir texto branco */
    }

    .sidebar-container {
        display: flex;
        flex-wrap: wrap;
        column-gap: 10px;
        row-gap: 6px;
        justify-content: flex-start;
        margin-bottom: 16px;
    }

    .sidebar-analysis {
        margin-bottom: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("""
<style>
/* Estilo para botões dos tickers na sidebar */
div.botao-ticker-container button {
    display: inline-block !important;
    width: auto !important;
    margin: 0px 6px 0px 0 !important;
    white-space: nowrap;
    padding: 8px 14px !important;
    border-radius: 8px !important;
    border: 1px solid rgba(255, 255, 255, 0.5) !important;
    background-color: rgba(255, 255, 255, 0.05) !important;
    color: white !important;
    font-size: 1rem !important;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.5) !important;
    text-align: center !important;
}

div.botao-ticker-container button:hover {
    background-color: rgba(255, 255, 255, 0.15) !important;
    border: 1px solid rgba(255, 255, 255, 0.7) !important;
    box-shadow: 2px 2px 6px rgba(0,0,0,0.7) !important;
}

div.botao-ticker-container button:focus {
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.4) !important;
}
</style>
""", unsafe_allow_html=True)



if ticker:
    try:
        acao = yf.Ticker(ticker)
        historico = acao.history(period="1mo")
        info = acao.info
        nome_empresa_topo = info.get("shortName", "Empresa não identificada")
        agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")

        st.markdown(
            f"""
            <div style='
                background-color: #31333F;
                color: white;
                padding: 10px 16px;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.3);
                box-shadow: 0px 0px 8px rgba(0,0,0,0.6);
                margin-top: -36px;
                margin-bottom: 10px;
            '>
                ✅ Dados coletados em {agora} &nbsp;&nbsp;|&nbsp;&nbsp; <a href="https://finance.yahoo.com/quote/{ticker}" target="_blank" style="color: white; text-decoration: underline;">Yahoo! Finance</a>
            </div>
            """,
            unsafe_allow_html=True
        )

        janela = 20  # janela padrão fixa
        historico['MA'] = historico['Close'].rolling(window=janela).mean()
        historico['Upper'] = historico['MA'] + 2 * historico['Close'].rolling(window=janela).std()
        historico['Lower'] = historico['MA'] - 2 * historico['Close'].rolling(window=janela).std()

        delta = historico['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        historico['RSI'] = 100 - (100 / (1 + rs))

        exp1 = historico['Close'].ewm(span=12, adjust=False).mean()
        exp2 = historico['Close'].ewm(span=26, adjust=False).mean()
        historico['MACD'] = exp1 - exp2
        historico['Signal'] = historico['MACD'].ewm(span=9, adjust=False).mean()

        dados_ultimos = acao.history(period="5d").dropna()

        # Definir proximo_resultado antes do bloco st.container()
        proximo_resultado = info.get('nextEarningsDate') or info.get('earningsTimestamp')
        if proximo_resultado:
            try:
                proximo_resultado = datetime.fromtimestamp(proximo_resultado).strftime('%d/%m/%Y')
            except:
                proximo_resultado = str(proximo_resultado)
        else:
            proximo_resultado = "Não disponível"

        with st.container():
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("💲 Preço Atual")
                if not dados_ultimos.empty and len(dados_ultimos) >= 2:
                    preco_atual = dados_ultimos['Close'].iloc[-1]
                    fechamento_anterior = dados_ultimos['Close'].iloc[-2]
                else:
                    preco_atual = dados_ultimos['Close'].iloc[-1] if not dados_ultimos.empty else None
                    fechamento_anterior = "Não disponível"

                if preco_atual is not None:
                    texto_variacao = ""
                    if fechamento_anterior != "Não disponível" and fechamento_anterior != 0:
                        variacao_percentual = ((preco_atual - fechamento_anterior) / fechamento_anterior) * 100
                        cor_variacao = "rgb(0, 255, 0)" if variacao_percentual >= 0 else "rgb(255, 70, 70)"
                        sinal = "+" if variacao_percentual >= 0 else ""
                        texto_variacao = f" <span style='font-size: 24px; color: {cor_variacao};'>({sinal}{variacao_percentual:.2f}%)</span>"
                    st.markdown(
                        f"""
                        <div style='display: flex; align-items: center;'>
                            <h1 style='margin: 0;'>{info.get('currency', 'Moeda não disponível')} {preco_atual:.2f}</h1>
                            {texto_variacao}
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                else:
                    st.metric(label="", value="Não disponível")

                # Preparar dados para a tabela
                abertura = dados_ultimos['Open'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
                if not dados_ultimos.empty:
                    volume_acoes = dados_ultimos['Volume'].iloc[-1]
                    preco_medio = (dados_ultimos['High'].iloc[-1] + dados_ultimos['Low'].iloc[-1]) / 2
                    volume_financeiro = volume_acoes * preco_medio
                    volume_formatado = formatar_valor(volume_financeiro)
                else:
                    volume_formatado = "Não disponível"
                maxima = dados_ultimos['High'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
                minima = dados_ultimos['Low'].iloc[-1] if not dados_ultimos.empty else "Não disponível"
                if maxima != "Não disponível" and minima != "Não disponível":
                    media_dia = (maxima + minima) / 2
                else:
                    media_dia = "Não disponível"

                # Preparar strings formatadas para exibição na tabela
                moeda = info.get('currency', 'Moeda não disponível')
                fechamento_anterior_str = f"{fechamento_anterior:.2f}" if fechamento_anterior != "Não disponível" and isinstance(fechamento_anterior, (int, float)) else fechamento_anterior
                maxima_str = f"{maxima:.2f}" if maxima != "Não disponível" and isinstance(maxima, (int, float)) else maxima
                abertura_str = f"{abertura:.2f}" if abertura != "Não disponível" and isinstance(abertura, (int, float)) else abertura
                media_dia_str = f"{media_dia:.2f}" if media_dia != "Não disponível" and isinstance(media_dia, (int, float)) else media_dia
                minima_str = f"{minima:.2f}" if minima != "Não disponível" and isinstance(minima, (int, float)) else minima
                # CSS para remover completamente as linhas cinzas da tabela
                st.markdown(
                    """
                    <style>
                    table, th, td, tr {
                        border: none !important;
                        border-bottom: none !important;
                        border-collapse: collapse !important;
                        outline: none !important;
                        box-shadow: none !important;
                    }

                    table tr {
                        border: none !important;
                        border-bottom: none !important;
                    }

                    table td {
                        border: none !important;
                        border-bottom: none !important;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True
                )
                st.markdown(
                    f"""
                    <table style='border-collapse: collapse; width: 100%; border: none; outline: none; box-shadow: none;'>
                        <tr>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Fech. Ant.:</strong> {moeda} {fechamento_anterior_str}</td>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Preço Máx.:</strong> {moeda} {maxima_str}</td>
                        </tr>
                        <tr>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Abertura:</strong> {moeda} {abertura_str}</td>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Preço Méd.:</strong> {moeda} {media_dia_str}</td>
                        </tr>
                        <tr>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Volume:</strong> {moeda} {volume_formatado}</td>
                            <td style='padding: 4px; border: none; outline: none; box-shadow: none;'><strong>Preço Mín.:</strong> {moeda} {minima_str}</td>
                        </tr>
                    </table>
                    """,
                    unsafe_allow_html=True
                )
                # Espaço extra visual entre a tabela de preços e o próximo bloco
                st.markdown("<div style='height: 18px;'></div>", unsafe_allow_html=True)
                st.markdown(f"**📅 Próxima divulgação de resultados:** {proximo_resultado}")

            with col2:
                st.subheader("Consenso das Casas de Análise")

                # Conteúdo do antigo expander "📊 Consenso das Casas de Análise" agora aqui:
                try:
                    preco_atual = historico['Close'].iloc[-1]
                    preco_alvo = info.get("targetMeanPrice")
                    preco_alvo_max = info.get("targetHighPrice")
                    preco_alvo_min = info.get("targetLowPrice")
                    numero_analistas = info.get("numberOfAnalystOpinions")
                    consenso = traduzir_recomendacao(info.get("recommendationKey", ""))

                    if preco_alvo and numero_analistas:
                        variacao = ((preco_alvo - preco_atual) / preco_atual) * 100
                        sinal = "+" if variacao >= 0 else ""
                        cor = "#00FF00" if variacao >= 0 else "#FF4C4C"

                        st.markdown(f"- **Recomendação geral:** {consenso}")
                        st.markdown(f"- **Número de analistas:** {numero_analistas}")
                        st.markdown(
                            f"""
                            <div style='font-size: 18px;'>
                                Preço atual: {preco_atual:.2f}  
                                <br>Preço-alvo médio: {preco_alvo:.2f}
                                <br>Preço-alvo máx.: {preco_alvo_max:.2f}
                                <br>Preço-alvo mín.: {preco_alvo_min:.2f}
                                <br><span style='color:{cor};'>Potencial: {sinal}{variacao:.2f}%</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    else:
                        st.markdown("❌ Dados de consenso não disponíveis para este ativo.")
                except Exception as e:
                    st.markdown(f"❌ Erro ao obter dados de consenso: {e}")

            # === Bloco "Sobre a Empresa" movido para logo após a tabela de preços ===
            with st.expander("📝 Sobre a Empresa"):
                data_fundacao = buscar_fundacao(info.get('shortName', ticker))

                ceo = "Não disponível"
                officers = info.get('companyOfficers')
                if officers and isinstance(officers, list):
                    for officer in officers:
                        if officer.get('title') and 'CEO' in officer.get('title'):
                            ceo = officer.get('name', 'Não disponível')
                            break

                descricao = info.get('longBusinessSummary', 'Descrição não disponível')

                col_esq, col_dir = st.columns(2)

                with col_esq:
                    st.markdown(f"**Empresa:** {info.get('shortName', 'Não disponível')}")
                    st.markdown(f"**Setor:** {info.get('sector', 'Não disponível')}")
                    st.markdown(f"**País:** {info.get('country', 'Não disponível')}")
                    st.markdown(f"**Moeda:** {info.get('currency', 'Não disponível')}")
                    st.markdown(f"**Fundação:** {data_fundacao}")

                with col_dir:
                    valor_mercado = info.get('marketCap')
                    st.markdown(f"**Valor de mercado:** {formatar_valor(valor_mercado)}")
                    funcionarios = info.get('fullTimeEmployees')
                    if funcionarios:
                        funcionarios = f"{funcionarios:,}".replace(',', '.')
                    else:
                        funcionarios = "Não disponível"
                    st.markdown(f"**Funcionários:** {funcionarios}")
                    st.markdown(f"**CEO:** {ceo}")

                st.markdown(descricao)


        # === Bloco Métricas de Mercado e Projeções ===
        with st.expander("📈 Métricas de Mercado e Projeções", expanded=False):
            try:
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.markdown(f"""
                        <div class="sidebar-card" style='background-color:#1e1e1e; padding:16px; border-radius:10px; box-shadow:0px 0px 6px rgba(0,0,0,0.5);'>
                        <h3>🔥 Crescimento</h3>
                        <ul>
                            <li><strong>Lucros (YoY):</strong> {round(info.get('earningsGrowth',0)*100,2)}%</li>
                            <li><strong>Receita (YoY):</strong> {round(info.get('revenueGrowth',0)*100,2)}%</li>
                            <li><strong>ROE:</strong> {round(info.get('returnOnEquity',0)*100,2)}%</li>
                            <li><strong>ROA:</strong> {round(info.get('returnOnAssets',0)*100,2)}%</li>
                            <li><strong>Margem Líquida:</strong> {round(info.get('profitMargins',0)*100,2)}%</li>
                        </ul>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown(analisar_crescimento(
                        info.get('earningsGrowth',0),
                        info.get('revenueGrowth',0),
                        info.get('returnOnEquity',0),
                        info.get('returnOnAssets',0),
                        info.get('profitMargins',0)
                    ))

                with col2:
                    dy = info.get('dividendYield', 0)
                    payout = info.get('payoutRatio', 0) * 100
                    st.markdown(f"""
                        <div class="sidebar-card" style='background-color:#1e1e1e; padding:16px; border-radius:10px; box-shadow:0px 0px 6px rgba(0,0,0,0.5);'>
                        <h3>💰 Dividendos</h3>
                        <ul>
                            <li><strong>Dividend Yield:</strong> {round(dy, 2)}%</li>
                            <li><strong>Payout Ratio:</strong> {round(payout,2)}%</li>
                        </ul>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown(analisar_dividendos(dy, payout))

                with col3:
                    st.markdown(f"""
                        <div class="sidebar-card" style='background-color:#1e1e1e; padding:16px; border-radius:10px; box-shadow:0px 0px 6px rgba(0,0,0,0.5);'>
                        <h3>⚖️ Endividamento</h3>
                        <ul>
                            <li><strong>Dívida/Patrimônio:</strong> {round(info.get('debtToEquity',0),2)}%</li>
                            <li><strong>Current Ratio:</strong> {round(info.get('currentRatio',0),2)}</li>
                            <li><strong>Quick Ratio:</strong> {round(info.get('quickRatio',0),2)}</li>
                        </ul>
                        </div>
                    """, unsafe_allow_html=True)
                    st.markdown(analisar_endividamento(
                        info.get('debtToEquity',0),
                        info.get('currentRatio',0),
                        info.get('quickRatio',0)
                    ))
            except Exception as e:
                st.markdown(f"❌ Erro ao obter métricas de mercado: {e}")


        # CSS para uniformizar o espaçamento entre títulos e listas dos cards (sidebar-card)
        st.markdown(
            """
            <style>
            .sidebar-card h3 {
                margin-bottom: 4px;
                line-height: 1.2;
                white-space: nowrap;
            }
            </style>
            """,
            unsafe_allow_html=True
        )

        with st.expander("📊 Dados Históricos e Gráficos", expanded=False):
            col1, col2 = st.columns(2)

            with col1:
                fig = go.Figure(data=[go.Candlestick(
                    x=historico.index,
                    open=historico['Open'],
                    high=historico['High'],
                    low=historico['Low'],
                    close=historico['Close']
                )])
                fig.add_trace(go.Scatter(
                    x=historico.index, y=historico['MA'],
                    line=dict(color='blue', width=1),
                    name=f'Média {janela}'
                ))
                fig.add_trace(go.Scatter(
                    x=historico.index, y=historico['Upper'],
                    line=dict(color='gray', width=1, dash='dot'),
                    name='Upper Band'
                ))
                fig.add_trace(go.Scatter(
                    x=historico.index, y=historico['Lower'],
                    line=dict(color='gray', width=1, dash='dot'),
                    name='Lower Band'
                ))
                fig.update_layout(
                    title="Preço",
                    xaxis_title="Data",
                    yaxis_title="Preço",
                    xaxis_rangeslider_visible=False,
                    template="plotly_white",
                    height=500,
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=1.02,
                        xanchor="right",
                        x=1
                    )
                )
                st.plotly_chart(fig, use_container_width=True)

            with col2:
                fig_volume = px.bar(
                    historico,
                    x=historico.index,
                    y="Volume",
                    labels={"x": "Data", "Volume": "Volume"},
                )
                fig_volume.update_layout(
                    title="Volume",
                    template="plotly_white",
                    height=500,
                    xaxis_title="Data",
                    yaxis_title="Volume"
                )
                st.plotly_chart(fig_volume, use_container_width=True)

            st.subheader("🔍 Indicadores Técnicos")

            # Exibir o campo Volume formatado
            volume_atual = historico['Volume'].iloc[-1] if not historico.empty else None
            volume_formatado = formatar_valor(volume_atual) if volume_atual is not None else "Não disponível"
            st.markdown(f"**Volume:** {info.get('currency', 'Moeda não disponível')} {volume_formatado}")

            col3, col4 = st.columns(2)

            with col3:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=historico.index, y=historico['RSI'], name='RSI'))
                fig_rsi.add_hline(y=70, line_dash="dot", line_color="red")
                fig_rsi.add_hline(y=30, line_dash="dot", line_color="green")
                fig_rsi.update_layout(title="RSI", template="plotly_white", height=300)
                st.plotly_chart(fig_rsi, use_container_width=True)

            with col4:
                fig_macd = go.Figure()
                fig_macd.add_trace(go.Scatter(x=historico.index, y=historico['MACD'], name='MACD'))
                fig_macd.add_trace(go.Scatter(x=historico.index, y=historico['Signal'], name='Signal'))
                fig_macd.update_layout(title="MACD", template="plotly_white", height=300)
                st.plotly_chart(fig_macd, use_container_width=True)

    except Exception as e:
        st.error(f"❌ Não foi possível obter dados para {ticker}. Verifique se o ticker está correto.")
        from difflib import get_close_matches
        tickers_disponiveis = st.session_state.favoritos_analise
        sugestoes = get_close_matches(ticker, tickers_disponiveis, n=3, cutoff=0.4)

        if sugestoes:
            st.markdown("#### 🔍 Você quis dizer:")
            for sugestao in sugestoes:
                if st.button(sugestao, key=f"sugestao_{sugestao}"):
                    st.session_state.ticker = sugestao
                    st.rerun()


# Verificação de segurança complementar: garante que os botões só renderizem quando favoritos estiverem prontos
if "favoritos_analise" not in st.session_state or not isinstance(st.session_state.favoritos_analise, list):
    st.warning("⏳ Carregando carteira...")
    st.stop()