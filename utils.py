from __future__ import annotations

import json
import os
import re
import uuid
from functools import lru_cache
try:
    import requests
except ImportError:  # fallback para import em ambientes sem dependências instaladas
    requests = None
from datetime import datetime, date
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    import fitz  # PyMuPDF
except ImportError:  # fallback para import em ambientes sem dependências instaladas
    fitz = None
try:
    import streamlit as st
except ImportError:  # fallback para import em ambientes sem dependências instaladas
    class _DummyStreamlit:
        def cache_data(self, *args, **kwargs):  # decorator no-op
            def _decorator(fn):
                return fn
            return _decorator

        def cache_resource(self, *args, **kwargs):  # decorator no-op
            def _decorator(fn):
                return fn
            return _decorator

        def __getattr__(self, name):
            # Métodos usados em redirecionamentos (markdown, stop, etc.) levantam erro claro.
            def _missing(*_args, **_kwargs):
                raise ImportError("streamlit não está instalado no ambiente atual.")
            return _missing
    st = _DummyStreamlit()
try:
    import yfinance as yf  # opcional; checado em runtime antes de uso
except ImportError:
    yf = None

if load_dotenv is not None:
    load_dotenv()

def _obter_secret_streamlit(nome: str) -> str | None:
    try:
        valor = st.secrets.get(nome)
    except Exception:
        valor = None
    if valor is None:
        return None
    valor = str(valor).strip()
    return valor or None


def _obter_config_supabase(nome_env: str, nome_secret: str) -> str | None:
    valor = os.getenv(nome_env)
    if valor:
        return valor.strip()

    valor = _obter_secret_streamlit(nome_secret)
    if valor:
        return valor

    return None


@lru_cache(maxsize=1)
def obter_credenciais_supabase() -> tuple[str, str]:
    supabase_url = _obter_config_supabase("SUPABASE_URL", "SUPABASE_URL")
    if not supabase_url:
        raise RuntimeError(
            "Configuração ausente do Supabase: defina SUPABASE_URL no ambiente "
            "ou SUPABASE_URL em st.secrets."
        )

    supabase_key = _obter_config_supabase("SUPABASE_KEY", "SUPABASE_KEY")
    if not supabase_key:
        raise RuntimeError(
            "Configuração ausente do Supabase: defina SUPABASE_KEY no ambiente "
            "ou SUPABASE_KEY em st.secrets."
        )

    return supabase_url, supabase_key


def supabase_configurado() -> bool:
    try:
        obter_credenciais_supabase()
        return True
    except RuntimeError:
        return False


def _limpar_sessao():
    for chave in ["usuario", "uid", "carteira", "ticker", "favoritos_analise", "access_token"]:
        if chave in st.session_state:
            del st.session_state[chave]


def redirecionar_para_login():
    _limpar_sessao()
    try:
        st.query_params.clear()
    except Exception:
        pass
    st.markdown("<meta http-equiv='refresh' content='0;url=/' />", unsafe_allow_html=True)
    st.stop()


def tratar_erro_autenticacao(exc) -> bool:
    """
    Retorna True se o erro indicar sessão expirada/credencial inválida e redireciona para o login.
    """
    try:
        from postgrest.exceptions import APIError
    except Exception:
        APIError = Exception  # fallback para evitar ImportError em ambientes sem postgrest

    msg = str(exc) if exc else ""
    code = None
    if isinstance(exc, APIError):
        code = getattr(exc, "code", None)
        if code is None and exc.args and isinstance(exc.args[0], dict):
            code = exc.args[0].get("code")

    if exc is None or code == "PGRST301" or "JWT expired" in msg or "Invalid JWT" in msg:
        redirecionar_para_login()
        return True
    return False


def executar_query_supabase(builder):
    """
    Executa uma query do Supabase e, se detectar sessão expirada (JWT), redireciona para o login.
    Retorna o objeto de resposta do client Supabase.
    """
    try:
        return builder.execute()
    except Exception as exc:
        tratar_erro_autenticacao(exc)
        raise


def _invalidate_ir_after_write(user_id: str, ano: int | None = None, mes: int | None = None):
    """Import tardio para evitar dependência circular com utils_ir."""
    try:
        from utils_ir import invalidate_ir_caches_for_ops
        invalidate_ir_caches_for_ops(user_id, ano=ano, mes=mes)
    except Exception:
        # Invalidação fiscal não deve mascarar sucesso da escrita.
        pass


# Função utilitária para formatar números com vírgula para float, aceitando None, string, int ou float
def formatar_numero_para_float(valor_str):
    if valor_str is None:
        return 0.0
    if isinstance(valor_str, str):
        try:
            return float(valor_str.replace(",", "."))
        except ValueError:
            return 0.0
    if isinstance(valor_str, (int, float)):
        return float(valor_str)
    return 0.0
# Helper: classificar ativo por ticker para fins de isenção (20k só ações à vista)
def _classe_ativo(ticker: str) -> str:
    """
    Retorna 'acao', 'bdr', 'etf_ou_fii' ou 'outro'.
    Heurística para isenção de 20k:
      - Considera o ticker BASE (antes de sufixos como .SA, .B3 e antes de hífen).
      - Usa os dois dígitos finais do base:
          11  -> etf_ou_fii (sem isenção)
          32–39 -> bdr (sem isenção)
      - Demais casos -> acao (candidata à isenção)
    """
    t = (ticker or "").upper().strip()
    if not t:
        return "outro"

    # Remove sufixos de mercado (.SA, .B3 etc.) e qualquer coisa após hífen
    base = t.split(".", 1)[0].split("-", 1)[0]

    # Detecta padrão de ticker de OPÇÃO (ex.: PETRA12, VALEJ32, PETRA123)
    # Letras (4 ou 5) + 1 letra de série + 2 ou 3 dígitos
    try:
        if re.match(r"^[A-Z]{4,5}[A-Z][0-9]{2,3}$", base):
            return "opcao"
    except Exception:
        pass

    # Captura os dois dígitos finais do ticker base (se houver)
    m = re.search(r"(\d{2})$", base)
    suf2 = m.group(1) if m else ""

    if suf2 in {"32", "33", "34", "35", "36", "37", "38", "39"}:
        return "bdr"
    if suf2 == "11":
        return "etf_ou_fii"  # inclui FII e ETF
    return "acao"
def conectar_supabase():
    from supabase import create_client
    supabase_url, supabase_key = obter_credenciais_supabase()
    return create_client(supabase_url, supabase_key)

# Tabela de mapeamento de nomes XP para tickers
def carregar_mapa_tickers():
    response = executar_query_supabase(
        supabase_autenticado().table("mapa_tickers").select("nome_xp, ticker_bdr")
    )
    if response.data:
        return {item["nome_xp"].upper(): item["ticker_bdr"].upper() for item in response.data}
    return {}

def salvar_mapa_ticker(nome_xp, ticker_bdr):
    garantir_usuario_sessao()
    if "uid" not in st.session_state:
        st.error("Usuário não autenticado. Faça login novamente.")
        st.stop()
    dados = {
        "nome_xp": nome_xp.upper(),
        "ticker_bdr": ticker_bdr.upper(),
        "user_id": st.session_state.uid
    }
    executar_query_supabase(supabase_autenticado().table("mapa_tickers").insert(dados))

#
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
            "id, ticker, quantidade, custo, data_compra, usuario, custo_operacional"
        ).eq("user_id", user_id).execute()
        return response.data
    except Exception as e:
        if not tratar_erro_autenticacao(e):
            raise e


def inserir_ativo_carteira(usuario, ticker, quantidade, custo, data_compra, custo_operacional):
    """
    Insere um ativo na carteira do usuário autenticado no Supabase.
    """
    # Garantir que quantidade é int, custo e custo_operacional estão em float (tratando vírgula)
    quantidade = int(formatar_numero_para_float(quantidade))
    custo = formatar_numero_para_float(custo)
    custo_operacional = formatar_numero_para_float(custo_operacional)
    dados = {
        "usuario": usuario,
        "user_id": st.session_state.uid,
        "ticker": ticker,
        "quantidade": quantidade,
        "custo": custo,
        "data_compra": data_compra,
        "custo_operacional": custo_operacional
    }
    executar_query_supabase(supabase_autenticado().table("carteira").insert(dados))
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
        resposta = executar_query_supabase(
            supabase_autenticado().table("carteira")
            .delete()
            .eq("id", uuid)
            .eq("user_id", st.session_state.uid)
        )
        return resposta
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao deletar ativo: {exc}")
        return {"erro": str(exc)}


def editar_ativo_carteira(uuid, novos_dados: dict):
    """
    Atualiza os dados de um ativo da carteira com base no seu UUID.
    Espera um dicionário com os campos: ticker, quantidade, custo, data_compra, custo_operacional.
    """
    # Garantir que quantidade seja int e custo/custo_operacional estejam em float (tratando vírgula)
    if "quantidade" in novos_dados:
        novos_dados["quantidade"] = int(formatar_numero_para_float(novos_dados["quantidade"]))
    if "custo" in novos_dados:
        novos_dados["custo"] = formatar_numero_para_float(novos_dados["custo"])
    if "custo_operacional" in novos_dados:
        novos_dados["custo_operacional"] = formatar_numero_para_float(novos_dados["custo_operacional"])
    try:
        resposta = executar_query_supabase(
            supabase_autenticado().table("carteira")
            .update(novos_dados)
            .eq("id", uuid)
        )
        if hasattr(resposta, "data") and resposta.data:
            return resposta
        else:
            print("[ERRO] Resposta sem dados ao editar ativo:", resposta)
            return None
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print("[ERRO] ao editar ativo:", exc)
        return None




# Funções para gerenciamento de favoritos no Supabase

def carregar_favoritos(user_id):
    try:
        response = executar_query_supabase(
            supabase_autenticado().table("favoritos").select("ticker").eq("user_id", user_id)
        )
        if response.data:
            return [item["ticker"] for item in response.data]
        return []
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print("Erro ao carregar favoritos:", exc)
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
    executar_query_supabase(supabase_autenticado().table("favoritos").insert(dados))


def remover_favorito(ticker):
    """
    Remove um ticker dos favoritos do usuário atualmente logado (obtido de st.session_state).
    """
    garantir_usuario_sessao()
    try:
        executar_query_supabase(
            supabase_autenticado().table("favoritos")
            .delete()
            .eq("user_id", st.session_state.uid)
            .eq("ticker", ticker)
        )
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print("Erro ao remover favorito:", exc)





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

def _normalizar_data_para_date(valor):
    """
    Converte datas flexíveis para objeto date.
    Aceita: date/datetime, ISO (YYYY-MM-DD), dd/mm/yyyy, dd/mm/yy e variantes simples.
    Retorna None se não conseguir converter.
    """
    if valor is None:
        return None
    if isinstance(valor, date) and not isinstance(valor, datetime):
        return valor
    if isinstance(valor, datetime):
        return valor.date()
    s = str(valor).strip()
    if not s:
        return None
    # Tenta ISO primeiro
    try:
        return datetime.fromisoformat(s.replace("T", " ").split("+")[0].split(".")[0]).date()
    except Exception:
        pass
    # Tenta formatos comuns BR
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def inserir_venda(usuario, ticker, quantidade, preco_compra, data_compra, preco_venda, data_venda, custo_operacional, irrf: float = 0.0):
    try:
        data_venda_dt = _normalizar_data_para_date(data_venda)
        data_compra_dt = _normalizar_data_para_date(data_compra)
        data_venda_iso = data_venda_dt.isoformat() if data_venda_dt else data_venda
        data_compra_iso = data_compra_dt.isoformat() if data_compra_dt else data_compra
        # Sanitiza IRRF (não-negativo, aceita string com vírgula)
        try:
            irrf_sanit = formatar_numero_para_float(irrf)
            if irrf_sanit < 0:
                irrf_sanit = 0.0
        except Exception:
            irrf_sanit = 0.0
        dados = {
            "usuario": usuario,
            "user_id": st.session_state.uid,
            "ticker": ticker,
            "quantidade": quantidade,
            "preco_compra": preco_compra,
            "data_compra": data_compra_iso,
            "preco_venda": preco_venda,
            "data_venda": data_venda_iso,
            "custo_operacional": custo_operacional,
            "irrf": irrf_sanit
        }
        resposta = executar_query_supabase(supabase_autenticado().table("ativos_vendidos").insert(dados))
        if hasattr(resposta, "data") and resposta.data and data_venda_dt:
            _invalidate_ir_after_write(st.session_state.uid, data_venda_dt.year, data_venda_dt.month)
        return hasattr(resposta, "data") and resposta.data
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"Erro ao inserir venda: {exc}")
        return False


def normalizar_datas_legadas_ativos_vendidos(user_id: str | None = None):
    """
    Utilitário manual para padronizar datas de compra/venda em ativos_vendidos para ISO (YYYY-MM-DD).
    - Usa _normalizar_data_para_date para converter.
    - Atualiza somente quando o valor ISO difere do armazenado.
    - Idempotente, sem UI; logs no console.
    """
    uid = user_id or st.session_state.get("uid")
    if not uid:
        print("[normalizar_datas_legadas] user_id ausente; abortando.")
        return {"analisados": 0, "corrigidos": 0, "erros": []}

    try:
        sb = supabase_autenticado()
        resp = executar_query_supabase(
            sb.table("ativos_vendidos").select("id,data_compra,data_venda").eq("user_id", uid)
        )
        rows = getattr(resp, "data", []) or []
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[normalizar_datas_legadas] erro ao buscar linhas: {exc}")
        return {"analisados": 0, "corrigidos": 0, "erros": ["fetch_error"]}

    analisados = len(rows)
    corrigidos = 0
    erros: list = []
    competencias_invalidadas: set[tuple[int, int]] = set()

    def _iso_if_convertible(valor):
        dt = _normalizar_data_para_date(valor)
        return dt.isoformat() if dt else None

    for r in rows:
        rid = r.get("id")
        try:
            dv_raw = r.get("data_venda")
            dc_raw = r.get("data_compra")
            dv_iso = _iso_if_convertible(dv_raw)
            dc_iso = _iso_if_convertible(dc_raw)
            update_payload = {}

            # Só atualiza se temos valor convertível e diferente do armazenado
            if dv_iso and str(dv_raw).strip() != dv_iso:
                update_payload["data_venda"] = dv_iso
            if dc_iso and str(dc_raw).strip() != dc_iso:
                update_payload["data_compra"] = dc_iso

            if not update_payload:
                continue

            executar_query_supabase(
                sb.table("ativos_vendidos").update(update_payload).eq("id", rid).eq("user_id", uid)
            )
            corrigidos += 1
            if dv_iso:
                try:
                    dt_venda = _normalizar_data_para_date(dv_iso)
                    if dt_venda:
                        competencias_invalidadas.add((dt_venda.year, dt_venda.month))
                except Exception:
                    pass
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
            erros.append(rid)
            print(f"[normalizar_datas_legadas] falha ao atualizar id={rid}: {exc}")
            continue

    for ano_mes in competencias_invalidadas:
        try:
            _invalidate_ir_after_write(uid, ano_mes[0], ano_mes[1])
        except Exception:
            pass

    print(
        f"[normalizar_datas_legadas] analisados={analisados} corrigidos={corrigidos} erros={len(erros)} ids_erro={erros}"
    )
    return {"analisados": analisados, "corrigidos": corrigidos, "erros": erros}


def carregar_vendas(usuario):
    try:
        response = executar_query_supabase(
            supabase_autenticado().table("ativos_vendidos").select("*").eq("user_id", st.session_state.uid)
        )
        return response.data
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"Erro ao carregar vendas: {exc}")
        return []

def deletar_venda(uuid):
    data_venda_dt = None
    try:
        resp = executar_query_supabase(
            supabase_autenticado().table("ativos_vendidos").select("data_venda").eq("id", uuid).eq("user_id", st.session_state.uid).single()
        )
        row = getattr(resp, "data", None) or {}
        data_venda_dt = _normalizar_data_para_date((row or {}).get("data_venda"))
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
    executar_query_supabase(
        supabase_autenticado().table("ativos_vendidos").delete().eq("id", uuid).eq("user_id", st.session_state.uid)
    )
    if data_venda_dt:
        _invalidate_ir_after_write(st.session_state.uid, data_venda_dt.year, data_venda_dt.month)
    else:
        _invalidate_ir_after_write(st.session_state.uid)



# Função para editar vendas
def editar_venda(uuid, novos_dados: dict):
    try:
        competencias_alvo: set[tuple[int, int]] = set()
        try:
            resp_prev = executar_query_supabase(
                supabase_autenticado().table("ativos_vendidos").select("data_venda").eq("id", uuid).eq("user_id", st.session_state.uid).single()
            )
            prev_row = getattr(resp_prev, "data", None) or {}
            prev_dt = _normalizar_data_para_date((prev_row or {}).get("data_venda"))
            if prev_dt:
                competencias_alvo.add((prev_dt.year, prev_dt.month))
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
        new_dt = _normalizar_data_para_date((novos_dados or {}).get("data_venda"))
        if new_dt:
            competencias_alvo.add((new_dt.year, new_dt.month))
        executar_query_supabase(
            supabase_autenticado().table("ativos_vendidos").update(novos_dados).eq("id", uuid).eq("user_id", st.session_state.uid)
        )
        if competencias_alvo:
            for ano_mes in competencias_alvo:
                _invalidate_ir_after_write(st.session_state.uid, ano_mes[0], ano_mes[1])
        else:
            _invalidate_ir_after_write(st.session_state.uid)
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"Erro ao editar venda: {exc}")

# Função para atualizar venda no Supabase

def atualizar_venda(id, preco_compra, preco_venda, quantidade, data_compra, data_venda, irrf: float = None):
    """
    Atualiza os dados de uma venda no Supabase.
    """
    data_venda_dt = _normalizar_data_para_date(data_venda)
    data_compra_dt = _normalizar_data_para_date(data_compra)
    novos_dados = {
        "preco_compra": preco_compra,
        "preco_venda": preco_venda,
        "quantidade": quantidade,
        "data_compra": data_compra_dt.isoformat() if data_compra_dt else data_compra,
        "data_venda": data_venda_dt.isoformat() if data_venda_dt else data_venda
    }
    if irrf is not None:
        try:
            irrf_sanit = formatar_numero_para_float(irrf)
            if irrf_sanit < 0:
                irrf_sanit = 0.0
            novos_dados["irrf"] = irrf_sanit
        except Exception:
            novos_dados["irrf"] = 0.0
    try:
        competencias_alvo: set[tuple[int, int]] = set()
        try:
            resp_prev = executar_query_supabase(
                supabase_autenticado().table("ativos_vendidos").select("data_venda").eq("id", id).eq("user_id", st.session_state.uid).single()
            )
            prev_row = getattr(resp_prev, "data", None) or {}
            prev_dt = _normalizar_data_para_date((prev_row or {}).get("data_venda"))
            if prev_dt:
                competencias_alvo.add((prev_dt.year, prev_dt.month))
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
        executar_query_supabase(
            supabase_autenticado().table("ativos_vendidos").update(novos_dados).eq("id", id).eq("user_id", st.session_state.uid)
        )
        if data_venda_dt:
            competencias_alvo.add((data_venda_dt.year, data_venda_dt.month))
        if competencias_alvo:
            for ano_mes in competencias_alvo:
                _invalidate_ir_after_write(st.session_state.uid, ano_mes[0], ano_mes[1])
        else:
            _invalidate_ir_after_write(st.session_state.uid)
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao atualizar venda com ID {id}: {exc}")




# Função utilitária para cálculo de desempenho consolidado por ativo
from collections import defaultdict

def calcular_desempenho_ativos(lista_entradas, origem="carteira"):
    if yf is None:
        raise ImportError("yfinance não está instalado no ambiente atual.")

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
    if yf is None:
        return "N/D"
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

    # Estimativa do custo operacional: soma das taxas conhecidas (busca baseada em linhas)
    total_taxas = 0.0
    nomes_taxas = ["Taxa de liquidação", "Emolumentos", "Corretagem", "Outros", "ISS", "Impostos", "Taxa Operacional"]
    taxas_identificadas = []
    for i, linha in enumerate(linhas):
        for nome in nomes_taxas:
            if nome.lower() in linha.lower():
                if i > 0:
                    linha_valor = linhas[i-1].strip()
                    try:
                        valor_taxa = float(linha_valor.replace(".", "").replace(",", "."))
                        taxas_identificadas.append((nome, valor_taxa))
                        total_taxas += valor_taxa
                    except:
                        pass


    ativos_lista = list(ativos.values())
    # Distribuição proporcional do custo operacional
    valor_total_nota = 0.0
    for ativo in ativos_lista:
        preco_unitario = float(ativo["Custo"].replace(",", "."))
        quantidade = ativo["Quantidade"]
        valor_total_nota += preco_unitario * quantidade

    for ativo in ativos_lista:
        preco_unitario = float(ativo["Custo"].replace(",", "."))
        quantidade = ativo["Quantidade"]
        valor_ativo = preco_unitario * quantidade
        proporcao = valor_ativo / valor_total_nota if valor_total_nota > 0 else 0
        custo_operacional = total_taxas * proporcao
        ativo["Custo Operacional"] = round(custo_operacional, 2)
    return ativos_lista


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
            data_compra=ativo["Data de Compra"],
            custo_operacional=ativo.get("Custo Operacional", 0.0)
        )
    st.success(f"{len(ativos_extraidos)} ativos foram inseridos com sucesso na carteira.")

def carregar_dividendos_usuario(usuario):
    try:
        response = executar_query_supabase(
            supabase_autenticado()
            .table("dividendos_recebidos")
            .select("id, ticker, tipo, valor, quantidade, data")
            .eq("user_id", st.session_state.uid)
            .order("data", desc=True)
        )
        if response.data:
            return response.data
        return []
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"Erro ao carregar dividendos: {exc}")
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
        resultado = executar_query_supabase(
            supabase_autenticado().table("dividendos_recebidos").insert(dados)
        )
        return resultado.data is not None
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao inserir dividendo: {exc}")
        return False



# Função para excluir dividendo por ID
def excluir_dividendo(id):
    try:
        executar_query_supabase(
            supabase_autenticado().table("dividendos_recebidos").delete().eq("id", id).eq("user_id", st.session_state.uid)
        )
        print(f"[DEBUG] Dividendo com ID {id} excluído com sucesso.")
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao excluir dividendo com ID {id}: {exc}")


# Função para atualizar dividendo existente

def atualizar_dividendo(id, novos_dados: dict):
    try:
        # Faz update dos campos fornecidos no dicionário
        executar_query_supabase(
            supabase_autenticado().table("dividendos_recebidos").update(novos_dados).eq("id", id).eq("user_id", st.session_state.uid)
        )
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao atualizar dividendo com ID {id}: {exc}")


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
        try:
            from supabase import create_client
            supabase_url, supabase_key = obter_credenciais_supabase()
            cliente = create_client(supabase_url, supabase_key)
            sessao = cliente.auth.get_session()
            if sessao and sessao.access_token:
                st.session_state.access_token = sessao.access_token
        except Exception:
            pass

def garantir_usuario_sessao():
    if "usuario" not in st.session_state or "uid" not in st.session_state:
        query_params = st.query_params or {}
        usuario = query_params.get("usuario", "")
        uid = query_params.get("uid", "")
        if usuario:
            st.session_state.usuario = usuario.strip().lower()
        if uid:
            st.session_state.uid = uid

# Função canônica chamada pelas páginas para restaurar sessão via query params
# Mantém compatibilidade com o padrão já aprovado no app
def restaurar_sessao_via_query_param():
    """
    Restaura `usuario`, `uid` e tenta recuperar `access_token` a partir dos
    parâmetros da URL, seguindo o fluxo já aprovado no app.
    """
    # 1) Garante usuario/uid do query param -> session_state
    garantir_usuario_sessao()
    # 2) Tenta restaurar access_token se ainda não estiver presente
    restaurar_usuario_sessao()


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
        from supabase import create_client
        from supabase.lib.client_options import ClientOptions

        headers = {"Authorization": f"Bearer {st.session_state['access_token']}"}
        client_options = ClientOptions(headers=headers)
        supabase_url, supabase_key = obter_credenciais_supabase()

        return create_client(supabase_url, supabase_key, options=client_options)
    else:
        redirecionar_para_login()


# 🔹 Função: inserir_opcao_carteira
# Objetivo: Insere uma nova posição viva na tabela opcoes_carteira
def inserir_opcao_carteira(
    usuario,
    tipo_operacao,
    ticker,
    tipo_opcao,
    strike,
    quantidade,
    preco,
    custo,
    data_operacao,
    data_vencimento,
    venda_coberta=False,
    ativo_base=None,
    irrf_abertura: float | None = None
):
    """
    Insere uma nova posição viva na tabela opcoes_carteira.
    """
    quantidade = int(formatar_numero_para_float(quantidade))
    preco = formatar_numero_para_float(preco)
    custo = formatar_numero_para_float(custo)
    nova_opcao = {
        "user_id": st.session_state.uid,
        "ticker": ticker,
        "tipo_opcao": tipo_opcao,
        "tipo_operacao": tipo_operacao,
        "strike": strike,
        "quantidade": quantidade,
        "preco": preco,
        "custo": custo,
        "data_operacao": data_operacao,
        "data_vencimento": data_vencimento,
        "venda_coberta": venda_coberta,
        "ativo_base": ativo_base
    }
    irrf_total = 0.0
    irrf_pendente = 0.0
    if tipo_operacao == "Venda" and irrf_abertura is not None:
        try:
            irrf_valor = formatar_numero_para_float(irrf_abertura)
            if irrf_valor < 0:
                irrf_valor = 0.0
            irrf_total = irrf_valor
            irrf_pendente = irrf_valor
        except Exception:
            irrf_total = 0.0
            irrf_pendente = 0.0
    nova_opcao["irrf_abertura_total"] = irrf_total
    nova_opcao["irrf_abertura_pendente"] = irrf_pendente
    executar_query_supabase(supabase_autenticado().table("opcoes_carteira").insert(nova_opcao))
    dt_op = _normalizar_data_para_date(data_operacao)
    if dt_op:
        _invalidate_ir_after_write(st.session_state.uid, dt_op.year, dt_op.month)
    else:
        _invalidate_ir_after_write(st.session_state.uid)


# 🔹 Função: atualizar_opcao_carteira
# Objetivo: Atualiza uma posição viva existente (quantidade, preço, etc.)
def atualizar_opcao_carteira(uuid, nova_quantidade, novo_custo, invalidate_ir: bool = True):
    """
    Atualiza a quantidade e o custo restante de uma posição viva na opcoes_carteira.
    """
    nova_quantidade = int(formatar_numero_para_float(nova_quantidade))
    novo_custo = formatar_numero_para_float(novo_custo)
    dados = {
        "quantidade": nova_quantidade,
        "custo": novo_custo
    }
    data_operacao_dt = None
    if invalidate_ir:
        try:
            resp_prev = executar_query_supabase(
                supabase_autenticado().table("opcoes_carteira").select("data_operacao").eq("id", uuid).eq("user_id", st.session_state.uid).single()
            )
            prev_row = getattr(resp_prev, "data", None) or {}
            data_operacao_dt = _normalizar_data_para_date((prev_row or {}).get("data_operacao"))
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
    executar_query_supabase(
        supabase_autenticado().table("opcoes_carteira").update(dados).eq("id", uuid).eq("user_id", st.session_state.uid)
    )
    if invalidate_ir:
        if data_operacao_dt:
            _invalidate_ir_after_write(st.session_state.uid, data_operacao_dt.year, data_operacao_dt.month)
        else:
            _invalidate_ir_after_write(st.session_state.uid)



# 🔹 Função: registrar_operacao_opcao
# Objetivo: Registra operação finalizada na tabela opcoes_operacoes e atualiza ou remove da carteira
def registrar_operacao_opcao(
    usuario,
    ticker,
    tipo_opcao,
    tipo_operacao_inicial,
    quantidade,
    preco_inicial,
    preco_final,
    strike,
    custo,
    data_operacao,
    data_vencimento,
    forma_encerramento,
    data_encerramento,
    venda_coberta=False
):
    """
    Registra uma operação finalizada na tabela opcoes_operacoes.
    """
    quantidade = int(formatar_numero_para_float(quantidade))
    preco_inicial = formatar_numero_para_float(preco_inicial)
    preco_final = formatar_numero_para_float(preco_final)
    custo = formatar_numero_para_float(custo)
    dados = {
        "user_id": st.session_state.uid,
        "ticker": ticker,
        "tipo_opcao": tipo_opcao,
        "tipo_operacao_inicial": tipo_operacao_inicial,
        "quantidade": quantidade,
        "preco_inicial": preco_inicial,
        "preco_final": preco_final,
        "strike": strike,
        "custo": custo,
        "data_operacao": data_operacao,
        "data_vencimento": data_vencimento,
        "forma_encerramento": forma_encerramento,
        "data_encerramento": data_encerramento,
        "venda_coberta": venda_coberta
    }
    executar_query_supabase(supabase_autenticado().table("opcoes_operacoes").insert(dados))
    dt_comp = _normalizar_data_para_date(data_encerramento) or _normalizar_data_para_date(data_operacao)
    if dt_comp:
        _invalidate_ir_after_write(st.session_state.uid, dt_comp.year, dt_comp.month)
    else:
        _invalidate_ir_after_write(st.session_state.uid)


# Função auxiliar para finalizar operações de opções (total ou parcial)
def finalizar_operacao_opcao(dados_vivos: dict, quantidade_finalizada: int, preco_final: float, custo_final: float, forma_encerramento: str, data_encerramento: str):
    """
    Finaliza uma operação de opção:
    - Registra a operação em 'opcoes_operacoes'
    - Remove ou atualiza a linha original em 'opcoes_carteira', conforme o caso
    """
    if "uid" not in st.session_state:
        raise RuntimeError("Usuário não autenticado.")

    uid = st.session_state["uid"]
    quantidade_viva = int(dados_vivos["quantidade"])
    preco_inicial = float(dados_vivos["preco"])
    custo_original = float(dados_vivos["custo"])
    custo = float(dados_vivos.get("custo", 0))
    # Determina o custo a inserir conforme finalização total ou parcial
    if quantidade_finalizada == quantidade_viva:
        custo_a_inserir = custo + float(custo_final)
    else:
        custo_proporcional = custo_original * (quantidade_finalizada / quantidade_viva)
        custo_a_inserir = custo_proporcional + float(custo_final)

    # IRRF no fechamento (quando aplicável: Compra -> Revenda/Exercício/Expiração)
    irrf_no_fechamento = 0.0
    try:
        if "irrf_fechamento" in dados_vivos:
            irrf_calc = formatar_numero_para_float(dados_vivos.get("irrf_fechamento", 0.0))
            if irrf_calc < 0:
                irrf_calc = 0.0
            irrf_no_fechamento = irrf_calc
    except Exception:
        irrf_no_fechamento = 0.0

    # =======================
    # [IRRF][ALOCACAO] Venda → Recompra (aloca pendente proporcionalmente)
    # =======================
    irrf_alocado_recompra = 0.0
    try:
        tipo_inicial_lower = str(dados_vivos.get("tipo_operacao", "")).lower()
        forma_lower = str(forma_encerramento).lower()
    except Exception:
        tipo_inicial_lower = ""
        forma_lower = ""

    if tipo_inicial_lower == "venda" and forma_lower == "recompra":
        # Buscar pendente e quantidade viva atuais na carteira
        try:
            resp_vivo = executar_query_supabase(
                supabase_autenticado().table("opcoes_carteira")
                .select("quantidade, irrf_abertura_pendente")
                .eq("id", dados_vivos["id"])
                .eq("user_id", st.session_state.uid)
                .single()
            )
            vivo = getattr(resp_vivo, "data", None) or (resp_vivo.get("data") if isinstance(resp_vivo, dict) else None)
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
            vivo = None

        qtd_viva_atual = int((vivo or {}).get("quantidade") or dados_vivos.get("quantidade") or 0)
        try:
            irrf_pendente = float(((vivo or {}).get("irrf_abertura_pendente")) or 0.0)
        except Exception:
            irrf_pendente = 0.0

        # Rateio proporcional do IRRF pendente pela fração encerrada
        if qtd_viva_atual <= 0:
            irrf_alocado_recompra = 0.0
        elif quantidade_finalizada >= qtd_viva_atual:
            irrf_alocado_recompra = irrf_pendente
        else:
            irrf_alocado_recompra = round(irrf_pendente * (quantidade_finalizada / qtd_viva_atual), 2)

        # Atualiza pendente no vivo (fecha resíduo no último fechamento)
        novo_pendente = round(max(0.0, irrf_pendente - irrf_alocado_recompra), 2)
        try:
            executar_query_supabase(
                supabase_autenticado().table("opcoes_carteira")
                .update({"irrf_abertura_pendente": novo_pendente})
                .eq("id", dados_vivos["id"])
                .eq("user_id", st.session_state.uid)
            )
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
            print(f"[IRRF][WARN] Falha ao atualizar irrf_abertura_pendente: {exc}")

    # IRRF final desta operação: fechamento (compra) + alocado (recompra de venda)
    irrf_final_operacao = round(float(irrf_no_fechamento) + float(irrf_alocado_recompra), 2)

    # Inserção na tabela opcoes_operacoes
    dados_op_finalizada = {
        "user_id": uid,
        "ticker": dados_vivos["ticker"],
        "tipo_opcao": dados_vivos["tipo_opcao"],
        "tipo_operacao_inicial": dados_vivos["tipo_operacao"],
        "quantidade": quantidade_finalizada,
        "preco_inicial": preco_inicial,
        "preco_final": preco_final,
        "strike": dados_vivos["strike"],
        "custo": custo_a_inserir,
        "data_operacao": dados_vivos["data_operacao"],
        "data_vencimento": dados_vivos["data_vencimento"],
        "forma_encerramento": forma_encerramento,
        "data_encerramento": data_encerramento,
        "venda_coberta": dados_vivos.get("venda_coberta", False),
        "ativo_base": dados_vivos.get("ativo_base"),  # agora presente na tabela
        "irrf": irrf_final_operacao,
    }

    executar_query_supabase(supabase_autenticado().table("opcoes_operacoes").insert(dados_op_finalizada))

    # Finalização total
    if quantidade_finalizada == quantidade_viva:
        excluir_operacao_opcao(dados_vivos["id"], invalidate_ir=False)
    # Finalização parcial
    else:
        nova_quantidade = quantidade_viva - quantidade_finalizada
        custo_proporcional = custo_original * (nova_quantidade / quantidade_viva)
        atualizar_opcao_carteira(dados_vivos["id"], nova_quantidade, custo_proporcional, invalidate_ir=False)

    _invalidate_ir_after_write(uid)


# 🔹 Função: excluir_operacao_opcao
# Objetivo: Remove uma posição da tabela opcoes_carteira com base no ID e validação por user_id
def excluir_operacao_opcao(id_opcao, invalidate_ir: bool = True):
    """
    Exclui uma operação viva da tabela opcoes_carteira com base no ID.
    Garante que apenas o dono (user_id) possa realizar a exclusão.
    """
    try:
        data_operacao_dt = None
        if invalidate_ir:
            try:
                resp_prev = executar_query_supabase(
                    supabase_autenticado().table("opcoes_carteira").select("data_operacao").eq("id", id_opcao).eq("user_id", st.session_state.uid).single()
                )
                prev_row = getattr(resp_prev, "data", None) or {}
                data_operacao_dt = _normalizar_data_para_date((prev_row or {}).get("data_operacao"))
            except Exception as exc:
                if exc.__class__.__name__ in {"StopException", "RerunException"}:
                    raise
                if tratar_erro_autenticacao(exc):
                    raise
        executar_query_supabase(
            supabase_autenticado().table("opcoes_carteira")
            .delete()
            .eq("id", id_opcao)
            .eq("user_id", st.session_state.uid)
        )
        if invalidate_ir:
            if data_operacao_dt:
                _invalidate_ir_after_write(st.session_state.uid, data_operacao_dt.year, data_operacao_dt.month)
            else:
                _invalidate_ir_after_write(st.session_state.uid)
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao excluir operação com ID {id_opcao}: {exc}")


# 🔹 Função: atualizar_operacao_opcao
# Objetivo: Atualiza uma linha da tabela opcoes_carteira para o usuário autenticado
def atualizar_operacao_opcao(id_opcao, dados):
    """Atualiza uma linha da tabela opcoes_carteira para o usuário autenticado"""
    if "uid" not in st.session_state:
        raise RuntimeError("Usuário não autenticado.")

    # Sanitiza campos opcionais de IRRF, se presentes
    dados_sanit = dict(dados) if isinstance(dados, dict) else {}
    if "irrf_abertura_total" in dados_sanit:
        try:
            v = formatar_numero_para_float(dados_sanit["irrf_abertura_total"])
            dados_sanit["irrf_abertura_total"] = 0.0 if v < 0 else v
        except Exception:
            dados_sanit["irrf_abertura_total"] = 0.0
    if "irrf_abertura_pendente" in dados_sanit:
        try:
            v = formatar_numero_para_float(dados_sanit["irrf_abertura_pendente"])
            dados_sanit["irrf_abertura_pendente"] = 0.0 if v < 0 else v
        except Exception:
            dados_sanit["irrf_abertura_pendente"] = 0.0

    supabase = supabase_autenticado()
    competencias_alvo: set[tuple[int, int]] = set()
    try:
        resp_prev = executar_query_supabase(
            supabase.table("opcoes_carteira")
            .select("data_operacao")
            .eq("id", id_opcao)
            .eq("user_id", st.session_state["uid"])
            .single()
        )
        prev_row = getattr(resp_prev, "data", None) or {}
        prev_dt = _normalizar_data_para_date((prev_row or {}).get("data_operacao"))
        if prev_dt:
            competencias_alvo.add((prev_dt.year, prev_dt.month))
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
    new_dt = _normalizar_data_para_date(dados_sanit.get("data_operacao"))
    if new_dt:
        competencias_alvo.add((new_dt.year, new_dt.month))
    response = executar_query_supabase(
        supabase.table("opcoes_carteira")
        .update(dados_sanit)
        .eq("id", id_opcao)
        .eq("user_id", st.session_state["uid"])
    )

    if len(response.data) == 0:
        raise RuntimeError("❌ Falha ao atualizar: operação não encontrada ou não pertence ao usuário.")
    if competencias_alvo:
        for ano_mes in competencias_alvo:
            _invalidate_ir_after_write(st.session_state["uid"], ano_mes[0], ano_mes[1])
    else:
        _invalidate_ir_after_write(st.session_state["uid"])
def carregar_operacoes_finalizadas(uid):
    """
    Carrega todas as operações finalizadas da tabela opcoes_operacoes para o usuário autenticado.
    Retorna uma lista de dicionários com os dados brutos.
    """
    try:
        resposta = executar_query_supabase(
            supabase_autenticado().table("opcoes_operacoes")
            .select(
                "id, ticker, tipo_opcao, tipo_operacao_inicial, quantidade, preco_inicial, preco_final, "
                "forma_encerramento, data_operacao, data_encerramento, custo, venda_coberta"
            )
            .eq("user_id", uid)
            .order("data_encerramento", desc=True)
        )

        if hasattr(resposta, "data") and resposta.data:
            return resposta.data
        else:
            return []
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao carregar operações finalizadas: {exc}")
        return []


# 🔹 Função: excluir_operacao_finalizada
# Objetivo: Remove uma linha da tabela opcoes_operacoes com base no ID e validação por user_id
def excluir_operacao_finalizada(id_operacao):
    """
    Exclui uma operação finalizada da tabela opcoes_operacoes com base no ID.
    Garante que apenas o dono (user_id) possa realizar a exclusão.
    """
    try:
        competencias_alvo: set[tuple[int, int]] = set()
        try:
            resp_prev = executar_query_supabase(
                supabase_autenticado().table("opcoes_operacoes")
                .select("data_operacao,data_encerramento")
                .eq("id", id_operacao)
                .eq("user_id", st.session_state.uid)
                .single()
            )
            prev_row = getattr(resp_prev, "data", None) or {}
            prev_dt_enc = _normalizar_data_para_date((prev_row or {}).get("data_encerramento"))
            prev_dt_op = _normalizar_data_para_date((prev_row or {}).get("data_operacao"))
            if prev_dt_enc:
                competencias_alvo.add((prev_dt_enc.year, prev_dt_enc.month))
            if prev_dt_op:
                competencias_alvo.add((prev_dt_op.year, prev_dt_op.month))
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
        executar_query_supabase(
            supabase_autenticado().table("opcoes_operacoes")
            .delete()
            .eq("id", id_operacao)
            .eq("user_id", st.session_state.uid)
        )
        if competencias_alvo:
            for ano_mes in competencias_alvo:
                _invalidate_ir_after_write(st.session_state.uid, ano_mes[0], ano_mes[1])
        else:
            _invalidate_ir_after_write(st.session_state.uid)
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao excluir operação finalizada com ID {id_operacao}: {exc}")


# 🔹 Função: atualizar_operacao_finalizada
# Objetivo: Atualiza uma operação finalizada na tabela opcoes_operacoes


# Inserido: Função para listar opções cobertas até uma data limite
from datetime import datetime as _dt, date as _date

def _coerce_data_limite_iso(data_limite) -> str:
    """
    Converte uma data (str/date/datetime) em string ISO 'YYYY-MM-DD'.
    Aceita formatos: 'DD/MM/YY', 'DD/MM/YYYY', 'YYYY-MM-DD'.
    """
    if isinstance(data_limite, str):
        for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
            try:
                return _dt.strptime(data_limite, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        # fallback seguro: hoje
        return _dt.today().strftime("%Y-%m-%d")
    if isinstance(data_limite, _dt):
        return data_limite.strftime("%Y-%m-%d")
    if isinstance(data_limite, _date):
        return data_limite.strftime("%Y-%m-%d")
    # fallback
    return _dt.today().strftime("%Y-%m-%d")



# Helpers para janela e normalização de ticker

def _ticker_variantes(ativo_base: str):
    """Retorna variantes do ticker para cobrir casos com/sem sufixo .SA."""
    if not isinstance(ativo_base, str):
        return [ativo_base]
    t = ativo_base.upper()
    sem_sa = t[:-3] if t.endswith(".SA") else t
    com_sa = t if t.endswith(".SA") else f"{t}.SA"
    return list({t, sem_sa, com_sa})



def calcular_credito_opcao(op: dict) -> float:
    """Calcula o crédito líquido de uma operação de opção finalizada.
    Fórmula acordada: (preco_inicial - preco_final) * quantidade - custo
    Campos esperados no dict: preco_inicial, preco_final, quantidade, custo.
    """
    try:
        quantidade = int(formatar_numero_para_float(op.get("quantidade")))
        preco_inicial = formatar_numero_para_float(op.get("preco_inicial"))
        preco_final = formatar_numero_para_float(op.get("preco_final"))
        custo = formatar_numero_para_float(op.get("custo"))
        return (preco_inicial - preco_final) * quantidade - custo
    except Exception as e:
        print(f"[ERRO] calcular_credito_opcao: {e}")
        return 0.0

# Nova função: alocar_coberturas_por_lote
def alocar_coberturas_por_lote(user_id: str, ativo_base: str, lots: list) -> dict:
    """
    Distribui operações de venda coberta (quantidades) entre lotes de um mesmo ticker.

    Args:
        user_id: identificador do usuário
        ativo_base: ticker do ativo base (pode ser com/sem .SA)
        lots: lista de lotes em ordem cronológica, cada item com:
              {"uuid": str, "data_compra": date|str, "quantidade": int}

    Retorna:
        dict com alocações:
        {
          "por_lote": {
              uuid_lote: {
                  "q_total": int,           # quantidade total alocada
                  "ops": {op_id: q_alocada}
              },
              ...
          },
          "ops": {
              op_id: {
                  "ticker": str,
                  "q_total": int,
                  "preco_inicial": float,
                  "preco_final": float,
                  "custo": float,
                  "data_encerramento": str
              }
          }
        }
    """
    try:
        if not lots:
            return {"por_lote": {}, "ops": {}}

        # ordenar lotes por data_compra
        for lot in lots:
            if isinstance(lot.get("data_compra"), str):
                lot["data_compra"] = parse_data_flexivel(lot["data_compra"])
        lots_sorted = sorted(lots, key=lambda lot: lot["data_compra"])

        variantes = _ticker_variantes(ativo_base)
        ini_iso = _coerce_data_limite_iso(lots_sorted[0]["data_compra"])
        from datetime import datetime as _dt
        hoje_iso = _dt.today().strftime("%Y-%m-%d")

        resposta = executar_query_supabase(
            supabase_autenticado().table("opcoes_operacoes")
            .select(
                "id, ticker, tipo_operacao_inicial, venda_coberta, quantidade, preco_inicial, preco_final, custo, data_encerramento, ativo_base"
            ) \
            .eq("user_id", user_id) \
            .in_("ativo_base", variantes) \
            .eq("venda_coberta", True) \
            .ilike("tipo_operacao_inicial", "Venda%") \
            .gte("data_encerramento", ini_iso) \
            .lte("data_encerramento", hoje_iso) \
            .order("data_encerramento", desc=False) \
        )

        ops = resposta.data if hasattr(resposta, "data") and resposta.data else []

        # inicializa estrutura
        alocacoes = {"por_lote": {}, "ops": {}}
        for lot in lots_sorted:
            alocacoes["por_lote"][lot["uuid"]] = {"q_total": 0, "ops": {}, "creditos": {}, "credito_total": 0.0}

        # processa cada operação
        for op in ops:
            op_id = op.get("id")
            q_restante = int(formatar_numero_para_float(op.get("quantidade")))
            q_total_op = q_restante
            credito_total_op = calcular_credito_opcao(op)
            preco_inicial = formatar_numero_para_float(op.get("preco_inicial"))
            preco_final = formatar_numero_para_float(op.get("preco_final"))
            custo = formatar_numero_para_float(op.get("custo"))

            alocacoes["ops"][op_id] = {
                "ticker": op.get("ticker"),
                "q_total": q_restante,
                "preco_inicial": preco_inicial,
                "preco_final": preco_final,
                "custo": custo,
                "data_encerramento": op.get("data_encerramento"),
            }

            # distribuir pelos lotes *por operação*, sem carregar ocupação entre operações
            # somente lotes cuja data_compra <= data_encerramento da operação são elegíveis
            try:
                op_dt = parse_data_flexivel(op.get("data_encerramento"))
            except Exception:
                # se a data estiver inválida, pula a operação
                continue

            # lotes elegiveis: em ordem cronológica, até a data da operação
            lots_elegiveis = [l for l in lots_sorted if l["data_compra"] <= op_dt]

            for lot in lots_elegiveis:
                if q_restante <= 0:
                    break
                # capacidade do lote por operação é a própria quantidade do lote
                capacidade_lote = int(lot["quantidade"]) if isinstance(lot.get("quantidade"), int) else int(formatar_numero_para_float(lot.get("quantidade")))
                if capacidade_lote <= 0:
                    continue
                q_aloc = min(capacidade_lote, q_restante)
                # acumula no lote (soma total de alocações de TODAS as operações)
                alocacoes["por_lote"][lot["uuid"]]["q_total"] += q_aloc
                # acumula por operação neste lote
                prev = alocacoes["por_lote"][lot["uuid"]]["ops"].get(op_id, 0)
                alocacoes["por_lote"][lot["uuid"]]["ops"][op_id] = prev + q_aloc
                # distribui crédito proporcional à quantidade alocada neste lote
                if q_total_op > 0:
                    _cred_parcial = (credito_total_op * (q_aloc / q_total_op))
                    # acumula crédito por operação neste lote
                    prevc = alocacoes["por_lote"][lot["uuid"]]["creditos"].get(op_id, 0.0)
                    alocacoes["por_lote"][lot["uuid"]]["creditos"][op_id] = prevc + _cred_parcial
                    # acumula crédito total do lote
                    alocacoes["por_lote"][lot["uuid"]]["credito_total"] += _cred_parcial
                q_restante -= q_aloc

        return alocacoes
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] alocar_coberturas_por_lote: {exc}")
        return {"por_lote": {}, "ops": {}}


# Nova função: obter_credito_opcoes_para_lote_intervalado
def obter_credito_opcoes_para_lote_intervalado(
    uid: str,
    ticker: str,
    data_compra,
    data_venda,
    quantidade_lote: int,
) -> float:
    """
    Retorna o CRÉDITO POR AÇÃO (float) de vendas cobertas de opções alocado a um lote específico,
    considerando apenas operações até `data_venda` (inclusive).

    Estratégia:
      1) Monta um único "lote-alvo" com (data_compra, quantidade_lote).
      2) Reusa `alocar_coberturas_por_lote` para distribuir créditos de opções por lote.
      3) Filtra as operações cuja `data_encerramento` seja <= `data_venda`.
      4) Soma os créditos válidos para o lote-alvo e divide por `quantidade_lote` para obter o valor POR AÇÃO.

    Observações:
      - Caso não haja créditos aplicáveis ou `quantidade_lote` <= 0, retorna 0.0.
      - As datas de entrada podem ser str nos formatos "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d" ou objetos date/datetime.
    """
    try:
        # Normalizações de data
        data_compra_dt = parse_data_flexivel(data_compra) if not isinstance(data_compra, (int, float)) else None
        data_venda_dt = parse_data_flexivel(data_venda) if not isinstance(data_venda, (int, float)) else None

        if quantidade_lote is None:
            return 0.0
        try:
            quantidade_lote = int(formatar_numero_para_float(quantidade_lote))
        except Exception:
            return 0.0
        if quantidade_lote <= 0:
            return 0.0

        # Monta o lote-alvo (UUID sintético apenas para alocação)
        lote_uuid = str(uuid.uuid4())
        lote_alvo = {
            "uuid": lote_uuid,
            "data_compra": data_compra_dt if data_compra_dt else data_compra,
            "quantidade": quantidade_lote,
        }

        # Rodar alocação para este ticker/lote
        aloc = alocar_coberturas_por_lote(uid, ticker, [lote_alvo])

        # Se não veio estrutura esperada, não há créditos
        if not isinstance(aloc, dict) or "por_lote" not in aloc or "ops" not in aloc:
            return 0.0
        if lote_uuid not in aloc["por_lote"]:
            return 0.0

        creditos_por_op = aloc["por_lote"][lote_uuid].get("creditos", {}) or {}
        ops_info = aloc.get("ops", {}) or {}

        # Filtro por data_venda (somente operações encerradas <= data_venda)
        credito_total_valido = 0.0
        for op_id, cred in creditos_por_op.items():
            op_info = ops_info.get(op_id)
            if not op_info:
                continue
            try:
                dt_enc = parse_data_flexivel(op_info.get("data_encerramento"))
            except Exception:
                # se a data da operação estiver inválida, ignora
                continue
            if data_venda_dt and dt_enc > data_venda_dt:
                # ignora operações após a data de venda
                continue
            # acumula crédito desta operação para o lote-alvo
            try:
                credito_float = float(cred)
            except Exception:
                credito_float = formatar_numero_para_float(cred)
            credito_total_valido += credito_float

        if credito_total_valido <= 0.0:
            return 0.0

        # Retorna crédito POR AÇÃO
        credito_por_acao = credito_total_valido / float(quantidade_lote)
        # Arredonda levemente para evitar ruído visual
        return round(credito_por_acao, 6)
    except Exception as e:
        print(f"[ERRO] obter_credito_opcoes_para_lote_intervalado: {e}")
        return 0.0

def obter_creditos_venda_coberta(uid):
    """
    Retorna um dicionário com os créditos líquidos provenientes de vendas cobertas finalizadas,
    agrupados por ativo_base. Cada item inclui quantidade, valor líquido e data.
    """
    try:
        resposta = executar_query_supabase(
            supabase_autenticado().table("opcoes_operacoes")
            .select("ativo_base, tipo_operacao_inicial, venda_coberta, quantidade, preco_inicial, preco_final, custo, data_encerramento") \
            .eq("user_id", uid) \
            .eq("venda_coberta", True) \
            .eq("tipo_operacao_inicial", "venda") \
        )

        dados = resposta.data if resposta and hasattr(resposta, "data") else []
        creditos = {}

        for item in dados:
            ativo = item.get("ativo_base")
            if not ativo:
                continue

            preco_inicial = formatar_numero_para_float(item.get("preco_inicial"))
            preco_final = formatar_numero_para_float(item.get("preco_final"))
            quantidade = int(formatar_numero_para_float(item.get("quantidade")))
            custo = formatar_numero_para_float(item.get("custo"))
            data_encerramento = item.get("data_encerramento")

            resultado = (preco_inicial - preco_final) * quantidade - custo

            if resultado == 0:
                continue  # ignora neutros

            if ativo not in creditos:
                creditos[ativo] = []

            creditos[ativo].append({
                "quantidade": quantidade,
                "valor_liquido": resultado,
                "data_encerramento": data_encerramento
            })

        return creditos

    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao obter créditos de venda coberta: {exc}")
        return {}

def atualizar_operacao_finalizada(id_operacao, novos_dados: dict):
    """
    Atualiza os dados de uma operação finalizada da tabela opcoes_operacoes com base no ID.
    Garante que apenas o dono (user_id) possa realizar a atualização.
    """
    try:
        competencias_alvo: set[tuple[int, int]] = set()
        try:
            resp_prev = executar_query_supabase(
                supabase_autenticado().table("opcoes_operacoes")
                .select("data_operacao,data_encerramento")
                .eq("id", id_operacao)
                .eq("user_id", st.session_state.uid)
                .single()
            )
            prev_row = getattr(resp_prev, "data", None) or {}
            prev_dt_enc = _normalizar_data_para_date((prev_row or {}).get("data_encerramento"))
            prev_dt_op = _normalizar_data_para_date((prev_row or {}).get("data_operacao"))
            if prev_dt_enc:
                competencias_alvo.add((prev_dt_enc.year, prev_dt_enc.month))
            if prev_dt_op:
                competencias_alvo.add((prev_dt_op.year, prev_dt_op.month))
        except Exception as exc:
            if exc.__class__.__name__ in {"StopException", "RerunException"}:
                raise
            if tratar_erro_autenticacao(exc):
                raise
        new_dt_enc = _normalizar_data_para_date((novos_dados or {}).get("data_encerramento"))
        new_dt_op = _normalizar_data_para_date((novos_dados or {}).get("data_operacao"))
        if new_dt_enc:
            competencias_alvo.add((new_dt_enc.year, new_dt_enc.month))
        if new_dt_op:
            competencias_alvo.add((new_dt_op.year, new_dt_op.month))
        executar_query_supabase(
            supabase_autenticado().table("opcoes_operacoes")
            .update(novos_dados)
            .eq("id", id_operacao)
            .eq("user_id", st.session_state.uid)
        )
        if competencias_alvo:
            for ano_mes in competencias_alvo:
                _invalidate_ir_after_write(st.session_state.uid, ano_mes[0], ano_mes[1])
        else:
            _invalidate_ir_after_write(st.session_state.uid)
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print(f"[ERRO] Falha ao atualizar operação finalizada com ID {id_operacao}: {exc}")
#
# ==============================
# Funções para logotipos de empresas
# ==============================

@st.cache_data(ttl=86400)
def get_logo_url(ticker: str) -> str | None:
    """
    Retorna a URL do logotipo de uma empresa com base no ticker.
    Estratégia:
      1. Normaliza ticker (ex: NVDC34.SA -> NVDC34).
      2. Busca na tabela tickers_logos do Supabase.
         - Se logo_url existe, valida se é imagem e retorna se for válida.
      3. Se não encontrar ou não for válida, tenta Clearbit com domínio salvo (se houver), valida e atualiza Supabase se for válida.
      4. Se ainda não, tenta heurística de domínio (mapa_excecoes ou {tnorm.lower()}.com), tenta Clearbit, valida e upserta no Supabase se for válida.
      5. Se falhar, retorna None.
    """
    try:
        tnorm = ticker.upper().replace(".SA", "")
        # 1) buscar no Supabase
        resp = executar_query_supabase(
            supabase_autenticado().table("tickers_logos").select("*").eq("ticker", tnorm)
        )
        row = resp.data[0] if resp.data and len(resp.data) > 0 else None

        # 2) Se logo_url já existe, valida se é imagem
        if row and row.get("logo_url"):
            logo_url = row.get("logo_url")
            try:
                r = requests.get(logo_url, timeout=5)
                if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                    return logo_url
            except Exception:
                pass  # Não válido, tenta outros métodos

        # 3) Se domínio existe no Supabase, tenta Clearbit
        domain = row.get("domain") if row and row.get("domain") else None
        if domain:
            url_clearbit = f"https://logo.clearbit.com/{domain}"
            try:
                r = requests.get(url_clearbit, timeout=5)
                if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                    # Atualiza Supabase se necessário
                    dados = {"ticker": tnorm, "domain": domain, "logo_url": url_clearbit, "source": "clearbit"}
                    try:
                        executar_query_supabase(supabase_autenticado().table("tickers_logos").upsert(dados))
                    except Exception as exc:
                        if exc.__class__.__name__ in {"StopException", "RerunException"}:
                            raise
                        if tratar_erro_autenticacao(exc):
                            raise
                        print("[WARN] Falha ao salvar logo no Supabase:", exc)
                    return url_clearbit
            except Exception:
                pass

        # 4) heurística de domínio
        mapa_excecoes = {
            "NVDC34": "nvidia.com",
            "MSFT34": "microsoft.com",
            "AAPL34": "apple.com",
            "AMZO34": "amazon.com",
            "BABA34": "alibaba.com",
            "TSLA34": "tesla.com",
            "NFLX34": "netflix.com",
            "MELI34": "mercadolivre.com",
            "BERK34": "berkshirehathaway.com",
            "PETR4": "petrobras.com.br",
            "TSMC34": "tsmc.com",
            "AVGO34": "broadcom.com",
            "BITH11": "hashdex.com",
            "U2ST34": "ishares.com",
            "P2LT34": "palantir.com",
            "CPLE6": "copel.com",
            "GOGL34": "abc.xyz",
            "ASML34": "asml.com",
        }
        domain_heur = mapa_excecoes.get(tnorm, f"{tnorm.lower()}.com")
        url_heur = f"https://logo.clearbit.com/{domain_heur}"
        try:
            r = requests.get(url_heur, timeout=5)
            if r.status_code == 200 and r.headers.get("Content-Type", "").startswith("image"):
                # salva/upserta no Supabase
                dados = {"ticker": tnorm, "domain": domain_heur, "logo_url": url_heur, "source": "clearbit"}
                try:
                    executar_query_supabase(supabase_autenticado().table("tickers_logos").upsert(dados))
                except Exception as exc:
                    if exc.__class__.__name__ in {"StopException", "RerunException"}:
                        raise
                    if tratar_erro_autenticacao(exc):
                        raise
                    print("[WARN] Falha ao salvar logo no Supabase:", exc)
                return url_heur
        except Exception:
            pass
        # Se nada funcionou
        return None
    except Exception as exc:
        if exc.__class__.__name__ in {"StopException", "RerunException"}:
            raise
        if tratar_erro_autenticacao(exc):
            raise
        print("[ERRO] get_logo_url:", exc)
        return None


def get_logo_img_tag(ticker: str, size: int = 28) -> str:
    """
    Retorna HTML <img> do logotipo ou fallback com iniciais do ticker.
    """
    url = get_logo_url(ticker)
    if url:
        return f"<img src='{url}' alt='{ticker}' width='{size}' height='{size}' style='border-radius:6px;vertical-align:middle'/>"
    iniciais = "".join([c for c in ticker.upper() if c.isalpha()][:4])
    return f"""<div style='display:inline-flex;align-items:center;justify-content:center;
               width:{size}px;height:{size}px;border-radius:6px;background:#444;color:#fff;
               font-size:{int(size/2)}px;font-weight:bold'>{iniciais}</div>"""
