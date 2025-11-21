import streamlit as st
from datetime import date
import pandas as pd
from utils_ir import (
    get_param,
    pf_set_vigencia_rpc,
    pf_update_vigencia,
    pf_delete_vigencia,
    pf_can_delete,
    normalizar_valor_parametro,
)
from utils import supabase_autenticado, get_logo_img_tag
import re

ALLOWED_KEYS = [
    "ALIQUOTA_NORMAL",
    "ALIQUOTA_DAYTRADE",
    "ALIQUOTA_FII",
    "LIMITE_ISENCAO_ACOES",
    "LIMIAR_MINIMO_DARF",
]

def _normalize_ticker_logo(value: str) -> str:
    return (value or "").upper().replace(".SA", "")

def _ticker_display(value: str) -> str:
    return _normalize_ticker_logo(value)

# Normaliza string de valor conforme tipo de chave (delegado ao utils_ir)
def _normalize_valor(chave: str, valor_str: str) -> str:
    return normalizar_valor_parametro(chave, valor_str)

# Helper para formatar datas em BR
def _fmt_date_br(v):
    from datetime import datetime, date
    if v is None:
        return ""
    # strings ISO ou timestamp -> para date
    try:
        if isinstance(v, str):
            # tenta fatiar só a parte de data
            v = v.split(" ")[0].split("T")[0]
            d = datetime.fromisoformat(v).date()
        elif isinstance(v, datetime):
            d = v.date()
        elif isinstance(v, date):
            d = v
        else:
            return str(v)
        return d.strftime("%d/%m/%Y")
    except Exception:
        try:
            # fallback: só formata os 10 primeiros caracteres se for ISO
            return str(v)[:10][8:10] + "/" + str(v)[:10][5:7] + "/" + str(v)[:10][0:4]
        except Exception:
            return str(v)

st.set_page_config(page_title="Admin – Parâmetros Fiscais", layout="wide")


st.title("⚙️ Administração – Parâmetros Fiscais")

# Sessão alinhada ao padrão do app (mesmo fluxo da Pag8)
if "uid" not in st.session_state:
    st.warning("Usuário não autenticado. Faça login para continuar.")
    st.stop()
supabase = supabase_autenticado()
user_id = st.session_state["uid"]

# Retry helper idêntico ao da Pag8
def _retry_jwt(fn):
    try:
        return fn(supabase_autenticado())
    except Exception as e:
        # Se o token expirou, renova o client e tenta de novo
        if "JWT expired" in str(e) or getattr(e, "code", None) == "PGRST301":
            return fn(supabase_autenticado())
        raise

# Verificação de role admin
role = None
if user_id:
    def _q_role(sb):
        return sb.table("app_roles").select("role").eq("user_id", user_id).eq("active", True).execute()
    res = _retry_jwt(_q_role) if _retry_jwt else _q_role(supabase)
    if getattr(res, "data", None):
        role = res.data[0].get("role")

if role != "admin":
    st.error("⛔ Acesso negado. Esta página é exclusiva para administradores.")
    st.stop()

st.success("✅ Você está logado como administrador.")


# Listagem de parâmetros atuais
st.subheader("📄 Parâmetros vigentes")
def _q_params(sb):
    return sb.table("parametros_fiscais").select("*").order("chave").order("efetivo_de").execute()
res = _retry_jwt(_q_params) if _retry_jwt else _q_params(supabase)
rows = res.data or []

if not rows:
    st.info("Nenhum parâmetro encontrado.")
else:
    # Constrói DF para edição mantendo tipos corretos (datas como date)
    def _to_date_obj(v):
        from datetime import datetime, date
        if v is None:
            return None
        if isinstance(v, date):
            return v
        if isinstance(v, str):
            v = v.split(" ")[0].split("T")[0]
            return datetime.fromisoformat(v).date()
        try:
            return v.to_pydatetime().date()  # pandas Timestamp
        except Exception:
            return None

    base_rows = []
    for r in rows:
        base_rows.append({
            "id": r.get("id"),
            "Chave": r.get("chave"),
            "Valor": str(r.get("valor")),
            "Efetivo De": _to_date_obj(r.get("efetivo_de")),
            "Efetivo Até": _to_date_obj(r.get("efetivo_ate")),
        })
    df_edit = pd.DataFrame(base_rows)

    # DataFrame mostrado (sem a coluna id)
    show_df = df_edit.drop(columns=["id"]) if "id" in df_edit.columns else df_edit.copy()
    edited = st.data_editor(
        show_df.assign(Excluir=False),
        hide_index=True,
        width="stretch",
        num_rows="fixed",
        column_config={
            "Chave": st.column_config.TextColumn("Chave", disabled=True),
            "Valor": st.column_config.TextColumn("Valor"),
            "Efetivo De": st.column_config.DateColumn("Efetivo De", format="DD/MM/YYYY"),
            "Efetivo Até": st.column_config.DateColumn("Efetivo Até", format="DD/MM/YYYY"),
            "Excluir": st.column_config.CheckboxColumn("Excluir"),
        },
    )
    if st.button("💾 Salvar alterações / 🗑️ Aplicar exclusões"):
        try:
            # We need the original rows with ids to map changes
            # Re-query original data with ids to get mapping
            def _q_params_with_id(sb):
                return sb.table("parametros_fiscais").select("*").order("chave").order("efetivo_de").execute()
            res_full = _retry_jwt(_q_params_with_id) if _retry_jwt else _q_params_with_id(supabase)
            rows_full = res_full.data or []
            df_full = pd.DataFrame(rows_full)
            if df_full.empty:
                st.error("Dados originais não encontrados para salvar alterações.")
            else:
                error_msgs = []
                for idx, edited_row in edited.iterrows():
                    chave = edited_row["Chave"]
                    valor_new = edited_row["Valor"]
                    de_new = edited_row["Efetivo De"]
                    ate_new = edited_row["Efetivo Até"]
                    excluir = edited_row["Excluir"]

                    if idx >= len(df_full):
                        error_msgs.append(f"Linha {idx} não encontrada nos dados originais.")
                        continue

                    original_row = df_full.iloc[idx]
                    rid = original_row["id"]
                    valor_old = str(original_row["valor"])
                    de_old_dt = date.fromisoformat(str(original_row["efetivo_de"]))
                    ate_old_dt = date.fromisoformat(str(original_row["efetivo_ate"]))

                    if excluir:
                        try:
                            # Checagem preventiva
                            def _can(sb):
                                return pf_can_delete(sb, rid)
                            can_res = _retry_jwt(_can)
                            ok_del, reason = (can_res[0], can_res[1]) if isinstance(can_res, (list, tuple)) else (False, str(can_res))
                            if not ok_del:
                                error_msgs.append(f"Não é possível excluir id {rid}: {reason}")
                                continue
                            def _del(sb):
                                return pf_delete_vigencia(sb, rid)
                            _retry_jwt(_del)
                        except Exception as e:
                            msg = getattr(e, "message", None) or getattr(e, "args", [None])[0] or str(e)
                            error_msgs.append(f"Erro ao excluir id {rid}: {msg}")
                    else:
                        try:
                            de_new_dt = de_new if isinstance(de_new, date) else date.fromisoformat(str(de_new))
                            ate_new_dt = ate_new if isinstance(ate_new, date) else date.fromisoformat(str(ate_new))
                            changed = (str(valor_new) != valor_old) or (de_new_dt != de_old_dt) or (ate_new_dt != ate_old_dt)
                            if changed:
                                valor_norm = _normalize_valor(chave, str(valor_new))
                                def _upd(sb):
                                    return pf_update_vigencia(sb, rid, valor=valor_norm, efetivo_de=de_new_dt, efetivo_ate=ate_new_dt)
                                _retry_jwt(_upd)
                        except Exception as e:
                            error_msgs.append(f"Erro ao atualizar id {rid}: {e}")

                if error_msgs:
                    st.session_state["last_errors"] = error_msgs
                    md = "Algumas alterações não puderam ser aplicadas:\n\n" + "\n".join([f"- {m}" for m in error_msgs])
                    st.error(md)
                else:
                    # Limpa erros anteriores e confirma sucesso
                    st.session_state["last_errors"] = []
                    st.success("Alterações aplicadas.")
                    st.rerun()
        except Exception as e:
            st.error(f"Falha ao aplicar alterações: {e}")

# Histórico de alterações
st.subheader("📜 Histórico de alterações")
def _q_audit(sb):
    return sb.table("parametros_fiscais_audit").select("*").order("created_at", desc=True).limit(20).execute()
audit = _retry_jwt(_q_audit) if _retry_jwt else _q_audit(supabase)
audit_rows = audit.data or []
if not audit_rows:
    st.info("Sem registros de auditoria.")
else:
    adf = pd.DataFrame(audit_rows)
    if "id" in adf.columns:
        adf = adf.drop(columns=["id"])  # requisito 1
    for c in ["efetivo_de", "efetivo_ate", "created_at"]:
        if c in adf.columns:
            adf[c] = adf[c].apply(_fmt_date_br)
    adf = adf.rename(columns={
        "user_id": "Usuário",
        "acao": "Ação",
        "chave": "Chave",
        "valor": "Valor",
        "efetivo_de": "Efetivo De",
        "efetivo_ate": "Efetivo Até",
        "created_at": "Criado Em",
    })
    st.dataframe(adf, width="stretch")

# Inclusão de novo parâmetro (com vigência)
st.subheader("➕ Incluir novo parâmetro")
with st.form("form_novo_param", clear_on_submit=True):
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    with c1:
        chave_new = st.selectbox("Chave", ALLOWED_KEYS, index=0, help="Selecione a chave fiscal a versionar")
    with c2:
        valor_new_in = st.text_input("Valor", placeholder="Ex.: 0.17 ou 17% para alíquotas; 20000 para limites")
    with c3:
        inicio_new = st.date_input("Efetivo de", value=date.today(), format="DD/MM/YYYY")
    with c4:
        fim_new = st.date_input("Efetivo até", value=date(2099, 12, 31), format="DD/MM/YYYY")

    ok = st.form_submit_button("Salvar novo parâmetro")
    if ok:
        try:
            valor_norm = _normalize_valor(chave_new, valor_new_in)
            if not valor_norm:
                st.error("Informe um valor válido.")
            else:
                def _rpc_set(sb):
                    return pf_set_vigencia_rpc(sb, chave_new, valor_norm, inicio_new, fim_new)
                _retry_jwt(_rpc_set)
                st.success(
                    f"Parâmetro incluído: {chave_new} = {valor_norm} de {_fmt_date_br(inicio_new)} até {_fmt_date_br(fim_new)}."
                )
                st.rerun()
        except Exception as e:
            st.error(f"Erro ao incluir novo parâmetro: {e}")

# --- Consolidação de logos existentes ---
def _q_logos(sb):
    return sb.table("tickers_logos").select("*").order("ticker").execute()

try:
    logo_resp = _retry_jwt(_q_logos) if _retry_jwt else _q_logos(supabase)
    logo_rows = logo_resp.data or []
    logo_map = {_normalize_ticker_logo(row.get("ticker")): row for row in logo_rows}
except Exception as e:
    logo_rows = []
    logo_map = {}
    st.error(f"Não foi possível carregar os logos salvos: {e}")


st.subheader("📋 Tickers com logos exibidos atualmente")
st.caption(
    "Consolidamos todos os tickers já presentes em `carteira` ou `ativos_vendidos` e mostramos abaixo o que o app renderiza hoje."
)

def _q_all_carteira(sb):
    return sb.table("carteira").select("ticker").execute()

def _q_all_vendidos(sb):
    return sb.table("ativos_vendidos").select("ticker").execute()

try:
    resp_carteira = _retry_jwt(_q_all_carteira) if _retry_jwt else _q_all_carteira(supabase)
    resp_vendidos = _retry_jwt(_q_all_vendidos) if _retry_jwt else _q_all_vendidos(supabase)
    tickers_carteira = {_normalize_ticker_logo(row.get("ticker")) for row in (resp_carteira.data or []) if row.get("ticker")}
    tickers_vendidos = {_normalize_ticker_logo(row.get("ticker")) for row in (resp_vendidos.data or []) if row.get("ticker")}
    tickers_unicos = sorted(tickers_carteira.union(tickers_vendidos))
except Exception as e:
    tickers_unicos = []
    st.error(f"Não foi possível carregar os tickers consolidados: {e}")

if tickers_unicos:
    chunk_size = 5
    for i in range(0, len(tickers_unicos), chunk_size):
        cols = st.columns(chunk_size)
        for col, ticker in zip(cols, tickers_unicos[i:i + chunk_size]):
            logo_html = get_logo_img_tag(ticker, size=56)
            col.markdown(f"**{_ticker_display(ticker)}**")
            col.markdown(logo_html, unsafe_allow_html=True)

            ticker_norm = _normalize_ticker_logo(ticker)
            if col.button("Editar logo", key=f"edit-logo-{ticker_norm}"):
                st.session_state["logo_edit_ticker"] = ticker_norm
else:
    st.info("Nenhum ticker encontrado nas tabelas `carteira` ou `ativos_vendidos`.")

edit_ticker = st.session_state.get("logo_edit_ticker")
if edit_ticker:
    st.markdown("---")
    st.subheader(f"✏️ Editar logo para {edit_ticker}")
    meta = logo_map.get(edit_ticker) or {}
    default_url = meta.get("logo_url") or ""
    default_domain = meta.get("domain") or ""
    default_source = meta.get("source") or "manual"

    with st.form("form_editar_logo", clear_on_submit=False):
        url_logo = st.text_input("Logo URL (https://...)", value=default_url, placeholder="https://logo.exemplo.com/arquivo.png")
        dominio_logo = st.text_input("Domínio (opcional, usado como fallback Clearbit)", value=default_domain, placeholder="empresa.com.br")
        fonte_logo = st.text_input("Fonte (informativo)", value=default_source)
        submitted = st.form_submit_button("Salvar logo")

        if submitted:
            payload = {
                "ticker": edit_ticker,
                "logo_url": url_logo.strip() or None,
                "domain": dominio_logo.strip() or None,
                "source": (fonte_logo or "manual").strip(),
            }

            def _upsert_logo(sb, item=payload):
                return sb.table("tickers_logos").upsert(item).execute()

            try:
                _retry_jwt(_upsert_logo) if _retry_jwt else _upsert_logo(supabase)
                st.success(f"Logo atualizado para {edit_ticker}.")
                st.session_state.pop("logo_edit_ticker", None)
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao salvar logo: {e}")

    if st.button("Cancelar edição", key="cancelar-edicao-logo"):
        st.session_state.pop("logo_edit_ticker", None)
        st.rerun()
