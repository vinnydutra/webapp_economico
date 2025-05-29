import json
import os
import streamlit as st
from supabase import create_client, Client

SUPABASE_URL = "https://iaealuasigceyzpbarvf.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZWFsdWFzaWdjZXl6cGJhcnZmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NDgzNzQ1NTEsImV4cCI6MjA2Mzk1MDU1MX0.ohrzecHP0MuQq-T9lyUdu2Jo6NAH5OWsgk8oKjXEQV8"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Todas as funções agora dependem de uma variável 'usuario' que precisa ser capturada no início da execução via obter_usuario()

# Função para capturar o nome do usuário
def obter_usuario(usuario=None):
    if usuario:
        return usuario.strip().lower()
    if "usuario" not in st.session_state:
        usuario = st.sidebar.text_input("Digite seu nome de usuário:", key="usuario_input")
        if usuario:
            st.session_state.usuario = usuario.strip().lower()
            st.rerun()
        else:
            st.stop()
    return st.session_state.usuario.strip().lower()


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
    response = supabase.table("carteira").select("id, ticker, quantidade, custo, data_compra, usuario").ilike("usuario", usuario).execute()
    if response.data:
        return response.data
    else:
        return []


def inserir_ativo_carteira(usuario, ticker, quantidade, custo, data_compra):
    dados = {
        "usuario": usuario,
        "ticker": ticker,
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra
    }
    supabase.table("carteira").insert(dados).execute()


def deletar_ativo_carteira(uuid):
    supabase.table("carteira").delete().eq("id", uuid).execute()


def atualizar_ativo_carteira(uuid, quantidade, custo, data_compra):
    dados = {
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra
    }
    supabase.table("carteira").update(dados).eq("id", uuid).execute()


# Funções para gerenciamento de favoritos no Supabase

def carregar_favoritos(usuario):
    response = supabase.table("favoritos").select("*").ilike("usuario", usuario).execute()
    if response.data:
        return [item["ticker"] for item in response.data]
    else:
        return []


def adicionar_favorito(usuario, ticker):
    dados = {
        "usuario": usuario,
        "ticker": ticker
    }
    supabase.table("favoritos").insert(dados).execute()


def remover_favorito(usuario, ticker):
    supabase.table("favoritos").delete().ilike("usuario", usuario).eq("ticker", ticker).execute()


# Função utilitária para formatar grandes números com ou sem moeda
def formatar_valor(valor, moeda=True):
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


# Funções para gerenciamento de ativos vendidos

def inserir_venda(usuario, ticker, quantidade, preco_compra, data_compra, preco_venda, data_venda):
    try:
        dados = {
            "usuario": usuario,
            "ticker": ticker,
            "quantidade": quantidade,
            "preco_compra": preco_compra,
            "data_compra": data_compra,
            "preco_venda": preco_venda,
            "data_venda": data_venda
        }
        supabase.table("ativos_vendidos").insert(dados).execute()
    except Exception as e:
        print(f"Erro ao inserir venda: {e}")


def carregar_vendas(usuario):
    try:
        response = supabase.table("ativos_vendidos").select("*").ilike("usuario", usuario).execute()
        return response.data
    except Exception as e:
        print(f"Erro ao carregar vendas: {e}")
        return []

def deletar_venda(uuid):
    supabase.table("ativos_vendidos").delete().eq("id", uuid).execute()


# Função para editar vendas
def editar_venda(uuid, novos_dados: dict):
    try:
        supabase.table("ativos_vendidos").update(novos_dados).eq("id", uuid).execute()
    except Exception as e:
        print(f"Erro ao editar venda: {e}")