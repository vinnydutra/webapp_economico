from datetime import datetime
import json
import os
import streamlit as st
from supabase import create_client, Client
import fitz  # PyMuPDF
import re

SUPABASE_URL = "https://iaealuasigceyzpbarvf.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZWFsdWFzaWdjZXl6cGJhcnZmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgzNzQ1NTEsImV4cCI6MjA2Mzk1MDU1MX0.ohrzecHP0MuQq-T9lyUdu2Jo6NAH5OWsgk8oKjXEQV8"
def conectar_supabase():
    return create_client(SUPABASE_URL, SUPABASE_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Tabela de mapeamento de nomes XP para tickers
def carregar_mapa_tickers():
    response = supabase_autenticado().table("mapa_tickers").select("nome_xp, ticker_bdr").execute()
    if response.data:
        return {item["nome_xp"].upper(): item["ticker_bdr"].upper() for item in response.data}
    return {}

def salvar_mapa_ticker(nome_xp, ticker_bdr):
    dados = {
        "nome_xp": nome_xp.upper(),
        "ticker_bdr": ticker_bdr.upper()
    }
    supabase.table("mapa_tickers").insert(dados).execute()

# Todas as funções agora dependem de uma variável 'usuario' que precisa ser capturada no início da execução via obter_usuario()

# Função para capturar o nome do usuário
def obter_usuario(usuario=None):
    if usuario:
        return usuario.strip().lower()
    if "usuario" in st.query_params:
        st.session_state.usuario = st.query_params["usuario"]
        return st.session_state.usuario
    elif "usuario" in st.session_state:
        return st.session_state.usuario
    else:
        st.warning("Usuário não identificado. Certifique-se de acessar via URL com '?usuario=seu_nome'")
        st.stop()


# Função para gerar o caminho do arquivo da carteira com base no usuário
def caminho_arquivo_carteira(usuario):
    if isinstance(usuario, str) and not isinstance(usuario, list):
        usuario_limpo = usuario.lower().replace('carteira_', '').replace(' ', '_')
        return f"carteira_{usuario_limpo}.json"
    else:
        raise ValueError("O nome de usuário deve ser uma string e não uma lista.")


def carregar_carteira(usuario):
    caminho = caminho_arquivo_carteira(usuario)
    if os.path.exists(caminho):
        with open(caminho, "r") as file:
            dados = json.load(file)
            return dados
    else:
        return {"favoritos_analise": [], "posicao_atual": []}


# Função para salvar a carteira do usuário
def salvar_carteira(dados, usuario):
    caminho = caminho_arquivo_carteira(usuario)
    with open(caminho, "w") as file:
        json.dump(dados, file, indent=4)


def carregar_carteira_supabase(usuario):
    user_id = obter_usuario(usuario)
    try:
        response = supabase_autenticado().table("carteira").select(
            "id, ticker, quantidade, custo, data_compra, usuario"
        ).eq("user_id", user_id).execute()
        return response.data
    except Exception as e:
        # Importa APIError para identificar o erro corretamente
        try:
            from postgrest.exceptions import APIError
        except ImportError:
            APIError = Exception  # fallback
        if isinstance(e, APIError):
            if getattr(e, "code", "") == "PGRST301" or "JWT expired" in str(e):
                st.session_state.clear()
                st.error("Sua sessão expirou. Faça login novamente.")
                st.stop()
            else:
                raise e
        elif "JWT expired" in str(e):
            st.session_state.clear()
            st.error("Sua sessão expirou. Faça login novamente.")
            st.stop()
        else:
            raise e


def inserir_ativo_carteira(usuario, ticker, quantidade, custo, data_compra):
    """
    Insere um ativo na carteira do usuário autenticado no Supabase.
    """
    dados = {
        "usuario": usuario,
        "user_id": st.session_state.uid,
        "ticker": ticker,
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra
    }
    supabase_autenticado().table("carteira").insert(dados).execute()
    # Atualiza a session_state.posicao_atual com os dados atuais do banco
    st.session_state.posicao_atual = [
        {
            "UUID": item["id"],
            "Ticker": item["ticker"],
            "Quantidade": item["quantidade"],
            "Custo": f'{item["custo"]:.2f}'.replace('.', ','),
            "Data de Compra": item["data_compra"]
        }
        for item in carregar_carteira_supabase(st.session_state.uid)
    ]


def deletar_ativo_carteira(uuid):
    if not uuid:
        print(f"[ERRO] UUID inválido: {uuid}")
        return {"erro": "UUID inválido"}

    try:
        resposta = supabase_autenticado().table("carteira") \
            .delete() \
            .eq("id", uuid) \
            .eq("user_id", st.session_state.uid) \
            .execute()
        print("[DEBUG] Exclusão resposta Supabase:", resposta)
        return resposta
    except Exception as e:
        print(f"[ERRO] Falha ao deletar ativo: {e}")
        return {"erro": str(e)}


def editar_ativo_carteira(uuid, novos_dados: dict):
    """
    Atualiza os dados de um ativo da carteira com base no seu UUID.
    Espera um dicionário com os campos: ticker, quantidade, custo, data_compra.
    """
    try:
        resposta = supabase_autenticado().table("carteira") \
            .update(novos_dados) \
            .eq("id", uuid) \
            .execute()
        if hasattr(resposta, "data") and resposta.data:
            return resposta
        else:
            print("[ERRO] Resposta sem dados ao editar ativo:", resposta)
            return None
    except Exception as e:
        print("[ERRO] ao editar ativo:", e)
        return None




# Funções para gerenciamento de favoritos no Supabase

def carregar_favoritos(user_id):
    try:
        response = supabase_autenticado().table("favoritos").select("ticker").eq("user_id", user_id).execute()
        if response.data:
            return [item["ticker"] for item in response.data]
        return []
    except Exception as e:
        print("Erro ao carregar favoritos:", e)
        return []


def adicionar_favorito(ticker):
    """
    Adiciona um ticker aos favoritos do usuário atualmente logado (obtido de st.session_state.usuario).
    """
    garantir_usuario_sessao()
    dados = {
        "user_id": st.session_state.uid,
        "ticker": ticker
    }
    if not st.session_state.get("uid"):
        st.error("ID de usuário (uid) não disponível.")
        return
    supabase_autenticado().table("favoritos").insert(dados).execute()


def remover_favorito(ticker):
    """
    Remove um ticker dos favoritos do usuário atualmente logado (obtido de st.session_state).
    """
    garantir_usuario_sessao()
    try:
        supabase_autenticado().table("favoritos") \
            .delete() \
            .eq("user_id", st.session_state.uid) \
            .eq("ticker", ticker) \
            .execute()
    except Exception as e:
        print("Erro ao remover favorito:", e)





# Função utilitária para formatar grandes números com escala (milhões, bilhões, trilhões)
def formatar_valor_escalar(valor, moeda=True):
    if valor is None:
        return "Não disponível"
    if moeda:
        if valor >= 1_000_000_000_000:
            return f"R$ {valor/1_000_000_000_000:.2f} Trilhões"
        elif valor >= 1_000_000_000:
            return f"R$ {valor/1_000_000_000:.2f} Bilhões"
        elif valor >= 1_000_000:
            return f"R$ {valor/1_000_000:.2f} Milhões"
        else:
            return f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    else:
        if valor >= 1_000_000_000_000:
            return f"{valor/1_000_000_000_000:.2f} Trilhões"
        elif valor >= 1_000_000_000:
            return f"{valor/1_000_000_000:.2f} Bilhões"
        elif valor >= 1_000_000:
            return f"{valor/1_000_000:.2f} Milhões"
        else:
            return f"{valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')

# Função utilitária para formatar valores com casas decimais fixas (sem escala)
def formatar_valor(valor, moeda=True, casas=2):
    if valor is None:
        return "Não disponível"
    formato = f"{{:,.{casas}f}}"
    if moeda:
        return "R$ " + formato.format(valor).replace(",", "X").replace(".", ",").replace("X", ".")
    else:
        return formato.format(valor).replace(",", "X").replace(".", ",").replace("X", ".")

# Função utilitária para traduzir códigos de recomendação para português
def traduzir_recomendacao(codigo):
    mapa = {
        "strong_buy": "Compra Forte",
        "buy": "Compra",
        "hold": "Manter",
        "underperform": "Desempenho Abaixo da Média",
        "sell": "Venda",
        "strong_sell": "Venda Forte",
        "none": "Sem recomendação",
        "nan": "Sem recomendação",
        "null": "Sem recomendação",
    }
    return mapa.get(str(codigo).lower(), str(codigo).replace("_", " ").capitalize())


# Funções para gerenciamento de ativos vendidos

def inserir_venda(usuario, ticker, quantidade, preco_compra, data_compra, preco_venda, data_venda):
    try:
        dados = {
            "usuario": usuario,
            "user_id": st.session_state.uid,
            "ticker": ticker,
            "quantidade": quantidade,
            "preco_compra": preco_compra,
            "data_compra": data_compra,
            "preco_venda": preco_venda,
            "data_venda": data_venda
        }
        resposta = supabase_autenticado().table("ativos_vendidos").insert(dados).execute()
        return hasattr(resposta, "data") and resposta.data
    except Exception as e:
        print(f"Erro ao inserir venda: {e}")
        return False


def carregar_vendas(usuario):
    try:
        response = supabase_autenticado().table("ativos_vendidos").select("*").eq("user_id", st.session_state.uid).execute()
        return response.data
    except Exception as e:
        print(f"Erro ao carregar vendas: {e}")
        return []

def deletar_venda(uuid):
    supabase_autenticado().table("ativos_vendidos").delete().eq("id", uuid).eq("user_id", st.session_state.uid).execute()



# Função para editar vendas
def editar_venda(uuid, novos_dados: dict):
    try:
        supabase_autenticado().table("ativos_vendidos").update(novos_dados).eq("id", uuid).eq("user_id", st.session_state.uid).execute()
    except Exception as e:
        print(f"Erro ao editar venda: {e}")

# Função para atualizar venda no Supabase
def atualizar_venda(id, preco_compra, preco_venda, quantidade, data_compra, data_venda):
    """
    Atualiza os dados de uma venda no Supabase.
    """
    novos_dados = {
        "preco_compra": preco_compra,
        "preco_venda": preco_venda,
        "quantidade": quantidade,
        "data_compra": data_compra,
        "data_venda": data_venda
    }
    try:
        supabase_autenticado().table("ativos_vendidos").update(novos_dados).eq("id", id).eq("user_id", st.session_state.uid).execute()
        print(f"[DEBUG] Venda com ID {id} atualizada com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar venda com ID {id}: {e}")


# Função utilitária para cálculo de desempenho consolidado por ativo
from collections import defaultdict
import yfinance as yf

def calcular_desempenho_ativos(lista_entradas, origem="carteira"):
    desempenho = defaultdict(lambda: {"quantidade": 0, "valor_total": 0, "valor_atual": 0, "resultado": 0})

    if origem == "carteira":
        for entrada in lista_entradas:
            ticker = entrada["ticker"].upper()
            quantidade = entrada["quantidade"]
            custo_total = quantidade * entrada["custo"]
            desempenho[ticker]["quantidade"] += quantidade
            desempenho[ticker]["valor_total"] += custo_total

        for ticker, dados in desempenho.items():
            try:
                if not ticker.endswith(".SA"):
                    ticker_ajustado = ticker + ".SA"
                else:
                    ticker_ajustado = ticker
                preco_atual = yf.Ticker(ticker_ajustado).history(period="1d")["Close"].dropna().iloc[-1]
                dados["valor_atual"] = dados["quantidade"] * preco_atual
                dados["resultado"] = dados["valor_atual"] - dados["valor_total"]
            except:
                dados["valor_atual"] = 0
                dados["resultado"] = 0

    elif origem == "vendas":
        for entrada in lista_entradas:
            ticker = entrada["ticker"].upper()
            quantidade = entrada["quantidade"]
            valor_compra = entrada["preco_compra"] * quantidade
            valor_venda = entrada["preco_venda"] * quantidade
            resultado = valor_venda - valor_compra
            desempenho[ticker]["resultado"] += resultado

    resultado_final = []
    for ticker, dados in desempenho.items():
        if origem == "carteira":
            variacao_percentual = (dados["resultado"] / dados["valor_total"]) * 100 if dados["valor_total"] else 0
            resultado_final.append({
                "ticker": ticker,
                "variacao_percentual": round(variacao_percentual, 2),
                "variacao_reais": round(dados["resultado"], 2)
            })
        elif origem == "vendas":
            resultado_final.append({
                "ticker": ticker,
                "variacao_percentual": None,
                "variacao_reais": round(dados["resultado"], 2)
            })

    return sorted(resultado_final, key=lambda x: x["variacao_reais"], reverse=True)


# Função alternativa para calcular o desempenho consolidado com base nos dados já carregados na carteira
def calcular_desempenho_consolidado(posicao_atual: list) -> list:
    desempenho_agrupado = {}

    for item in posicao_atual:
        ticker = item["Ticker"]
        try:
            quantidade = item["Quantidade"]
            custo_unitario = float(item["Custo"].replace(",", "."))
            custo_total = quantidade * custo_unitario

            if ticker not in desempenho_agrupado:
                desempenho_agrupado[ticker] = {
                    "quantidade_total": 0,
                    "custo_total": 0.0
                }

            desempenho_agrupado[ticker]["quantidade_total"] += quantidade
            desempenho_agrupado[ticker]["custo_total"] += custo_total

        except Exception:
            continue

    resultado_final = []
    for ticker, dados in desempenho_agrupado.items():
        try:
            preco_str = obter_preco_ativo(ticker)
            if "R$" not in preco_str:
                raise ValueError("Preço inválido")
            preco_float = float(preco_str.replace("R$ ", "").replace(".", "").replace(",", "."))

            custo_medio = dados["custo_total"] / dados["quantidade_total"]
            valor_atual_total = dados["quantidade_total"] * preco_float
            valor_investido = dados["custo_total"]
            variacao_reais = valor_atual_total - valor_investido
            variacao_percentual = ((preco_float - custo_medio) / custo_medio) * 100

            resultado_final.append({
                "ticker": ticker,
                "variacao_reais": variacao_reais,
                "variacao_percentual": variacao_percentual
            })
        except Exception:
            resultado_final.append({
                "ticker": ticker,
                "variacao_reais": 0.0,
                "variacao_percentual": 0.0
            })

    return resultado_final

# Função para obter o preço atual do ativo via yfinance, com fallback
def obter_preco_ativo(ticker):
    try:
        ticker_yf = yf.Ticker(ticker)
        if hasattr(ticker_yf, 'fast_info') and ticker_yf.fast_info and 'last_price' in ticker_yf.fast_info:
            preco_atual = ticker_yf.fast_info['last_price']
        else:
            hist = ticker_yf.history(period="7d")
            preco_atual = hist['Close'].dropna().iloc[-1]
        return f"R$ {preco_atual:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "N/D"


# Nova versão da função para importar nota XP PDF (parser baseado em blocos de 8 linhas fixas)
def importar_nota_xp_pdf(caminho_pdf: str, usuario: str):
    garantir_usuario_sessao()
    if "uid" not in st.session_state:
        st.error("Usuário não autenticado. Faça login para continuar.")
        st.stop()
    from datetime import datetime
    doc = fitz.open(caminho_pdf)
    texto = "\n".join([page.get_text() for page in doc])
    linhas = texto.splitlines()

    mapa_tickers = carregar_mapa_tickers()

    data_compra_match = re.search(r"Data pregão\s+(\d{2}/\d{2}/\d{4})", texto)
    data_formatada = datetime.strptime(data_compra_match.group(1), "%d/%m/%Y").strftime("%d/%m/%y") if data_compra_match else datetime.today().strftime("%d/%m/%y")

    ativos = {}
    # Percorre os blocos de 8 linhas
    for i in range(0, len(linhas)-7):
        # Padrão: linha 0 termina com BOVESPA, linha 2 é VISTA
        if linhas[i].strip().endswith("BOVESPA") and linhas[i+2].strip() == "VISTA":
            info_linha = linhas[i+3].strip()  # Ex: 'ALIBABAGR        DRN'
            partes = info_linha.split()
            if len(partes) >= 1:
                nome = partes[0]
                ticker_base = mapa_tickers.get(nome.upper())
                if not ticker_base:
                    ticker_input = st.text_input(f"Informe o ticker BDR para: {nome}", key=f"ticker_{i}")
                    if not ticker_input:
                        st.warning(f"Você precisa informar o ticker para {nome} para continuar.")
                        st.stop()
                    salvar_mapa_ticker(nome, ticker_input)
                    mapa_tickers = carregar_mapa_tickers()
                    ticker_base = mapa_tickers[nome.upper()]

                try:
                    linha_qtd = linhas[i+4].strip()
                    if not linha_qtd.replace("#", "").strip().isdigit():
                        linha_qtd = linhas[i+5].strip()
                        linha_preco = linhas[i+6].strip()
                    else:
                        linha_preco = linhas[i+5].strip()

                    quantidade = int(re.sub(r'\D', '', linha_qtd))
                    preco = float(linha_preco.replace(",", "."))
                except Exception:
                    continue

                ticker = f"{ticker_base}.SA"
                if ticker in ativos:
                    ativos[ticker]["Quantidade"] += quantidade
                else:
                    ativos[ticker] = {
                        "Ticker": ticker,
                        "Quantidade": quantidade,
                        "Custo": f"{preco:.2f}".replace(".", ","),
                        "Data de Compra": data_formatada
                    }

    return list(ativos.values())


# Função para importar uma nota XP PDF e inserir os ativos na carteira do usuário
def importar_e_inserir_pdf(caminho_pdf: str, usuario: str):
    garantir_usuario_sessao()
    if "uid" not in st.session_state:
        st.error("Usuário não autenticado. Faça login para continuar.")
        st.stop()

    ativos_extraidos = importar_nota_xp_pdf(caminho_pdf, usuario)
    for ativo in ativos_extraidos:
        inserir_ativo_carteira(
            usuario=usuario,
            ticker=ativo["Ticker"],
            quantidade=ativo["Quantidade"],
            custo=float(ativo["Custo"].replace(",", ".")),
            data_compra=ativo["Data de Compra"]
        )
    st.success(f"{len(ativos_extraidos)} ativos foram inseridos com sucesso na carteira.")

def carregar_dividendos_usuario(usuario):
    try:
        response = supabase_autenticado().table("dividendos_recebidos").select("id, ticker, tipo, valor, quantidade, data").eq("user_id", st.session_state.uid).order("data", desc=True).execute()
        if response.data:
            return response.data
        return []
    except Exception as e:
        print(f"Erro ao carregar dividendos: {e}")
        return []

def parse_data_flexivel(data_str):
    for formato in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(data_str, formato)
        except ValueError:
            continue
    raise ValueError(f"Formato de data inválido: {data_str}")

def obter_total_dividendos_para_lote(usuario, ticker, data_compra, data_venda=None):
    dividendos = carregar_dividendos_usuario(usuario)
    total = 0.0
    try:
        # print(f"[DEBUG] Dividendos encontrados: {dividendos}")
        data_compra_dt = parse_data_flexivel(data_compra)
        data_venda_dt = parse_data_flexivel(data_venda) if data_venda else None
        for d in dividendos:
            # print(f"[DEBUG] Verificando dividendo: {d}")
            if d["ticker"].upper() != ticker.upper():
                # print(f"[DEBUG] Ticker não confere: {d['ticker']} vs {ticker}")
                continue
            data_dividendo_dt = datetime.strptime(d["data"], "%Y-%m-%d")
            # print(f"[DEBUG] Data compra: {data_compra_dt}, Data venda: {data_venda_dt}, Data dividendo: {data_dividendo_dt}")
            if data_dividendo_dt >= data_compra_dt and (data_venda_dt is None or data_dividendo_dt <= data_venda_dt):
                # print(f"[DEBUG] Aplicando dividendo: {d['valor']} para {ticker}")
                total += float(d["valor"])
    except Exception as e:
        print(f"Erro ao calcular dividendos para {ticker}: {e}")
    return total


# Função para obter total de dividendos de um lote, considerando apenas dividendos entre data_compra e data_venda (ambos inclusivos)
def obter_total_dividendos_para_lote_intervalado(usuario, ticker, data_compra, data_venda):
    """
    Calcula o total de dividendos recebidos para um determinado lote entre data_compra e data_venda (inclusive).
    Exige obrigatoriamente data_venda.
    """
    if data_venda is None:
        raise ValueError("data_venda deve ser fornecida e não pode ser None.")
    dividendos = carregar_dividendos_usuario(usuario)
    total = 0.0
    try:
        data_compra_dt = parse_data_flexivel(data_compra)
        data_venda_dt = parse_data_flexivel(data_venda)
        for d in dividendos:
            if d["ticker"].upper() != ticker.upper():
                continue
            data_dividendo_dt = datetime.strptime(d["data"], "%Y-%m-%d")
            if data_compra_dt <= data_dividendo_dt <= data_venda_dt:
                total += float(d["valor"])
    except Exception as e:
        print(f"Erro ao calcular dividendos intervalados para {ticker}: {e}")
    return total




# Função para inserir dividendo (nova versão com tratamento de erros)
# (Localizada ao final do arquivo, conforme solicitado)
def inserir_dividendo(usuario, ticker, data_pagamento, valor, quantidade, tipo):
    """
    Insere um dividendo recebido para o usuário autenticado no Supabase.
    """
    dados = {
        "usuario": usuario,
        "user_id": st.session_state.uid,
        "ticker": str(ticker).upper(),
        "valor": float(str(valor).replace(",", ".").strip()),
        "quantidade": int(quantidade),
        "tipo": tipo.upper(),
        "data": data_pagamento if isinstance(data_pagamento, str) else data_pagamento.isoformat()
    }
    try:
        print("[DEBUG] Enviando para Supabase:", dados)
        resultado = supabase_autenticado().table("dividendos_recebidos").insert(dados).execute()
        print("[DEBUG] Resposta Supabase:", resultado)
        return resultado.data is not None
    except Exception as e:
        print(f"[ERRO] Falha ao inserir dividendo: {e}")
        return False



# Função para excluir dividendo por ID
def excluir_dividendo(id):
    try:
        supabase_autenticado().table("dividendos_recebidos").delete().eq("id", id).eq("user_id", st.session_state.uid).execute()
        print(f"[DEBUG] Dividendo com ID {id} excluído com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao excluir dividendo com ID {id}: {e}")


# Função para atualizar dividendo existente

def atualizar_dividendo(id, novos_dados: dict):
    try:
        # Faz update dos campos fornecidos no dicionário
        supabase_autenticado().table("dividendos_recebidos").update(novos_dados).eq("id", id).eq("user_id", st.session_state.uid).execute()
        print(f"[DEBUG] Dividendo com ID {id} atualizado com sucesso.")
    except Exception as e:
        print(f"[ERRO] Falha ao atualizar dividendo com ID {id}: {e}")


# Função para restaurar usuario, uid e access_token do session_state a partir dos parâmetros da URL
def restaurar_usuario_sessao():
    query = st.query_params
    if "usuario" in query and "usuario" not in st.session_state:
        st.session_state.usuario = query["usuario"]
    if "uid" in query and "uid" not in st.session_state:
        st.session_state.uid = query["uid"]
    if "access_token" in query and "access_token" not in st.session_state:
        st.session_state.access_token = query["access_token"]
    
    # Se uid e usuario existem mas access_token sumiu (reload sem query), tenta restaurar
    if (
        "access_token" not in st.session_state
        and "usuario" in st.session_state
        and "uid" in st.session_state
    ):
        from supabase import create_client
        url = SUPABASE_URL
        key = SUPABASE_KEY
        cliente = create_client(url, key)
        try:
            sessao = cliente.auth.get_session()
            if sessao and sessao.access_token:
                st.session_state.access_token = sessao.access_token
        except Exception as e:
            st.warning("Não foi possível restaurar token de acesso.")

# Função para garantir usuario e uid no session_state a partir dos parâmetros da URL
def garantir_usuario_sessao():
    if "usuario" not in st.session_state or "uid" not in st.session_state:
        query_params = st.query_params or {}
        usuario = query_params.get("usuario", "")
        uid = query_params.get("uid", "")
        if usuario:
            st.session_state.usuario = usuario.strip().lower()
        if uid:
            st.session_state.uid = uid


# Função utilitária para cálculo do custo ajustado por dividendos unitários
def calcular_custo_ajustado(custo_original, quantidade, dividendos):
    """
    Ajusta o custo unitário original com base nos dividendos recebidos por ação.
    - custo_original: valor unitário pago originalmente
    - quantidade: número de ações compradas
    - dividendos: lista de dicts contendo {"valor": float, "quantidade": 1}, somando os valores unitários
    Retorna: novo custo unitário ajustado
    """
    if dividendos is None or len(dividendos) == 0:
        return custo_original
    total_dividendo_unitario = sum([d["valor"] for d in dividendos])
    return custo_original - total_dividendo_unitario

# Função para obter cliente Supabase autenticado via access_token do session_state
def supabase_autenticado():
    if "access_token" in st.session_state:
        from httpx import Client as HTTPXClient
        from supabase.lib.client_options import ClientOptions

        headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
        client_options = ClientOptions(headers=headers)

        return create_client(SUPABASE_URL, SUPABASE_KEY, options=client_options)
    else:
        st.error("Token de acesso não encontrado. Usuário pode não estar autenticado corretamente.")
        st.stop()