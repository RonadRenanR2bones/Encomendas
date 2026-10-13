import datetime
import calendar
import base64
import io
import os
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from supabase import Client, create_client

# 1. Configuração da Página do Streamlit
st.set_page_config(
    page_title="R² Bonés - Controle Gerencial Pro",
    page_icon="🧢",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Estilização CSS Personalizada
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    .main {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    }

    .custom-header-container {
        background: linear-gradient(90deg, #1e293b 0%, #334155 100%);
        padding: 22px 30px;
        border-radius: 16px;
        color: white;
        display: flex;
        align-items: center;
        gap: 25px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.12);
        margin-bottom: 25px;
        width: 100%;
    }

    .header-text h1 {
        margin: 0;
        font-size: 2.1em;
        font-weight: 700;
        color: #ffffff;
    }

    .header-text p {
        margin: 4px 0 0 0;
        opacity: 0.85;
        font-size: 1.05em;
    }

    div[data-testid="stImage"] > img {
        border-radius: 16px;
        box-shadow: 0 8px 20px rgba(0,0,0,0.08);
        margin-bottom: 10px;
        width: 100% !important;
        max-height: 160px !important;
        object-fit: contain !important;
    }

    .kpi-card-advanced {
        background: #ffffff;
        border-radius: 14px;
        padding: 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.05);
        border-top: 4px solid #3b82f6;
        transition: transform 0.3s ease, box-shadow 0.3s ease;
        position: relative;
    }

    .kpi-card-advanced:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 30px rgba(0,0,0,0.12);
    }

    .kpi-title {
        font-size: 0.85em;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        color: #64748b;
        font-weight: 700;
        margin-bottom: 8px;
    }

    .kpi-value {
        font-size: 1.8em;
        font-weight: 800;
        color: #0f172a;
    }

    .tooltip-icon {
        display: inline-block;
        background: #e2e8f0;
        color: #475569;
        border-radius: 50%;
        width: 18px;
        height: 18px;
        text-align: center;
        font-size: 11px;
        line-height: 18px;
        cursor: pointer;
        margin-left: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Cache em sessão
if "extra_costs_cache" not in st.session_state:
    st.session_state["extra_costs_cache"] = {}

if "baixas_estoque_local" not in st.session_state:
    st.session_state["baixas_estoque_local"] = []

if "devolucoes_venda_local" not in st.session_state:
    st.session_state["devolucoes_venda_local"] = []

# Configurações do Banco de Dados SQLite / Supabase
DB_NAME = "ordens_producao.db"
UPLOADS_DIR = "uploads"
COMPROVANTES_DIR = "comprovantes"

if not os.path.exists(UPLOADS_DIR):
    os.makedirs(UPLOADS_DIR)

if not os.path.exists(COMPROVANTES_DIR):
    os.makedirs(COMPROVANTES_DIR)

# 2. Inicialização do Cliente Supabase
@st.cache_resource
def init_supabase() -> Client:
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

def carregar_dataframe(query, params=None):
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    df = pd.read_sql_query(query, conn, params=params)
    conn.close()
    return df

def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=30.0)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id TEXT,
            data_criacao TEXT,
            cor_bone TEXT,
            frase_arte TEXT,
            cor_linha TEXT,
            tipo TEXT,
            preco REAL,
            observacoes TEXT,
            imagem_path TEXT,
            status TEXT,
            valor_estampa_extra REAL DEFAULT 0.0,
            valor_matriz REAL DEFAULT 0.0,
            codigo_produto TEXT,
            total_item REAL
        )
    ''')
    c.execute("PRAGMA table_info(pedidos)")
    colunas_pedidos = [column[1] for column in c.fetchall()]
    if "valor_estampa_extra" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN valor_estampa_extra REAL DEFAULT 0.0")
    if "valor_matriz" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN valor_matriz REAL DEFAULT 0.0")
    if "codigo_produto" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN codigo_produto TEXT")
    if "total_item" not in colunas_pedidos:
        c.execute("ALTER TABLE pedidos ADD COLUMN total_item REAL")

    try:
        c.execute("UPDATE pedidos SET tipo = 'Básico' WHERE tipo = 'Simples'")
    except Exception:
        pass

    c.execute('''
        CREATE TABLE IF NOT EXISTS vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo_bone TEXT,
            codigo TEXT,
            cliente TEXT,
            qtd INTEGER DEFAULT 1,
            valor_venda REAL DEFAULT 0.0,
            tarifa REAL DEFAULT 0.0,
            tarifa_bancaria REAL DEFAULT 0.0,
            tarifa_cartao REAL DEFAULT 0.0,
            valor_recebido REAL DEFAULT 0.0,
            forma_pagto TEXT,
            data TEXT,
            data_venda TEXT,
            data_recebimento TEXT,
            custo REAL DEFAULT 0.0,
            custo_unitario REAL DEFAULT 0.0
        )
    ''')
    c.execute("PRAGMA table_info(vendas)")
    colunas_vendas = [column[1] for column in c.fetchall()]
    colunas_vendas_necessarias = {
        "codigo_bone": "TEXT", "codigo": "TEXT", "cliente": "TEXT",
        "qtd": "INTEGER DEFAULT 1", "valor_venda": "REAL DEFAULT 0.0",
        "tarifa": "REAL DEFAULT 0.0", "tarifa_bancaria": "REAL DEFAULT 0.0",
        "tarifa_cartao": "REAL DEFAULT 0.0", "valor_recebido": "REAL DEFAULT 0.0",
        "forma_pagto": "TEXT", "data": "TEXT", "data_venda": "TEXT",
        "data_recebimento": "TEXT", "custo": "REAL DEFAULT 0.0",
        "custo_unitario": "REAL DEFAULT 0.0"
    }
    for _col, _tipo in colunas_vendas_necessarias.items():
        if _col not in colunas_vendas:
            c.execute(f"ALTER TABLE vendas ADD COLUMN {_col} {_tipo}")

    c.execute('''
        CREATE TABLE IF NOT EXISTS pagamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lote_id TEXT,
            data_pagamento TEXT,
            valor_pago REAL,
            forma_pagamento TEXT,
            observacoes TEXT,
            comprovante_path TEXT
        )
    ''')
    try:
        c.execute("UPDATE pedidos SET status = 'Em Produção' WHERE status = 'Pendente'")
    except Exception:
        pass
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS configuracoes (
            chave TEXT PRIMARY KEY,
            valor_b64 TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS custos_avulsos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subcategoria TEXT,
            data TEXT,
            desc TEXT,
            tipo TEXT,
            valor REAL
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS aportes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            data_aporte TEXT,
            socio TEXT,
            valor REAL,
            tipo TEXT
        )
    ''')

    c.execute('''
        CREATE TABLE IF NOT EXISTS caixa (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT,
            desc TEXT,
            tipo TEXT,
            valor REAL
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS baixas_estoque (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT,
            motivo TEXT,
            observacao TEXT,
            data_baixa TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS devolucoes_vendas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            venda_id INTEGER,
            codigo TEXT,
            cliente TEXT,
            valor_devolvido REAL,
            data_devolucao TEXT,
            motivo TEXT
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ----------------------------------------------------
# FUNÇÕES ROBUSTAS DE TRATAMENTO E FORMATO DE DATAS (YYYY/MM/DD)
# ----------------------------------------------------
def parse_date_str(val):
    hoje = datetime.date.today().strftime("%Y/%m/%d")
    if val is None:
        return hoje
    try:
        if pd.isna(val):
            return hoje
    except Exception:
        pass
    if isinstance(val, pd.Timestamp):
        return val.strftime("%Y/%m/%d")
    if isinstance(val, datetime.datetime):
        return val.strftime("%Y/%m/%d")
    if isinstance(val, datetime.date):
        return val.strftime("%Y/%m/%d")
    s = str(val).strip()
    if not s or s.lower() in {"none", "nat", "nan", "null"}:
        return hoje
    formatos = ["%Y/%m/%d", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"]
    for fmt in formatos:
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y/%m/%d")
        except ValueError:
            pass
    try:
        dt = pd.to_datetime(s, dayfirst=True, errors="coerce")
        return dt.strftime("%Y/%m/%d") if pd.notna(dt) else hoje
    except Exception:
        return hoje

def format_data_br(val):
    if val is None:
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    s = str(val).strip()
    if not s or s.lower() in {"none", "nat", "nan", "null"}:
        return ""
    return parse_date_str(val)

def parse_money(val):
    if pd.isna(val) or val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace('R$', '').strip()
    if ',' in s and '.' in s:
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return float(s)
    except Exception:
        import re
        cleaned = re.sub(r'[^\d.]', '', s)
        return float(cleaned) if cleaned else 0.0

def get_numeric_series(df: pd.DataFrame, col_name: str, default_value: float = 0.0) -> pd.Series:
    if df.empty or col_name not in df.columns:
        return pd.Series([default_value] * len(df), index=df.index, dtype=float)
    return df[col_name].apply(parse_money)

def fetch_data(table_name: str) -> pd.DataFrame:
    local_df = pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        if table_name == "vendas":
            local_df = pd.read_sql_query("SELECT * FROM vendas ORDER BY id DESC", conn)
        elif table_name == "custos_avulsos":
            local_df = pd.read_sql_query("SELECT * FROM custos_avulsos ORDER BY id DESC", conn)
        elif table_name == "aportes":
            local_df = pd.read_sql_query("SELECT * FROM aportes ORDER BY id DESC", conn)
        elif table_name == "caixa":
            local_df = pd.read_sql_query("SELECT * FROM caixa ORDER BY id DESC", conn)
        elif table_name == "produtos":
            local_df = pd.read_sql_query("SELECT * FROM produtos", conn)
        elif table_name == "pedidos":
            local_df = pd.read_sql_query("SELECT * FROM pedidos ORDER BY id ASC", conn)
        conn.close()
    except Exception:
        pass

    if not supabase:
        return local_df
    try:
        res = supabase.table(table_name).select("*").execute()
        remote_df = pd.DataFrame(res.data)
        if remote_df.empty:
            return local_df
        return remote_df
    except Exception as e:
        err_str = str(e)
        if "PGRST205" not in err_str and "schema cache" not in err_str:
            st.warning(f"Aviso de leitura na tabela `{table_name}`: {e}")
        return local_df

def normalizar_df_vendas(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df_res = df.copy()
    col_v = "valor_venda" if "valor_venda" in df_res.columns else ("valor" if "valor" in df_res.columns else "valor_total")
    df_res["valor_bruto_calc"] = get_numeric_series(df_res, col_v)
    
    t_vals = pd.Series([0.0] * len(df_res), index=df_res.index, dtype=float)
    for t_col_cand in ["tarifa", "tarifa_bancaria", "tarifa_cartao"]:
        if t_col_cand in df_res.columns:
            vals_cand = get_numeric_series(df_res, t_col_cand)
            t_vals = t_vals.where(t_vals > 0, vals_cand)
    df_res["tarifa_calc"] = t_vals

    if "valor_recebido" in df_res.columns:
        val_rec_raw = get_numeric_series(df_res, "valor_recebido")
        df_res["liquido_recebido_calc"] = val_rec_raw.where(val_rec_raw > 0, df_res["valor_bruto_calc"] - df_res["tarifa_calc"])
    else:
        df_res["liquido_recebido_calc"] = df_res["valor_bruto_calc"] - df_res["tarifa_calc"]

    return df_res

def sqlite_insert_record(table_name: str, payload: dict, replace: bool = False):
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = {row[1] for row in cur.fetchall()}
        dados = {k: v for k, v in payload.items() if k in cols}
        if not dados:
            return False
        colunas = list(dados.keys())
        placeholders = ", ".join(["?"] * len(colunas))
        cmd = "INSERT OR REPLACE" if replace else "INSERT OR IGNORE"
        cur.execute(
            f"{cmd} INTO {table_name} ({', '.join(colunas)}) VALUES ({placeholders})",
            [dados[c] for c in colunas]
        )
        conn.commit()
        return True
    except Exception as exc:
        st.error(f"Erro ao gravar localmente na tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def sqlite_update_record(table_name: str, record_id, payload: dict):
    if record_id in (None, ""):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        cols = {row[1] for row in cur.fetchall()}
        dados = {k: v for k, v in payload.items() if k in cols and k != "id"}
        if not dados:
            return False
        assignments = ", ".join([f"{c} = ?" for c in dados])
        cur.execute(
            f"UPDATE {table_name} SET {assignments} WHERE id = ?",
            [dados[c] for c in dados] + [record_id]
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        st.error(f"Erro ao atualizar localmente na tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def sqlite_delete_record(table_name: str, record_id):
    if record_id in (None, ""):
        return False
    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cur = conn.cursor()
        cur.execute(f"DELETE FROM {table_name} WHERE id = ?", (record_id,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as exc:
        st.error(f"Erro ao excluir localmente da tabela `{table_name}`: {exc}")
        return False
    finally:
        if conn is not None:
            conn.close()

def safe_insert(table_name: str, payload: dict, replace: bool = False):
    sqlite_insert_record(table_name, payload, replace=replace)
    if not supabase:
        return True
    try:
        if replace and table_name == "produtos":
            supabase.table(table_name).upsert(payload, on_conflict="codigo").execute()
        else:
            supabase.table(table_name).insert(payload).execute()
        return True
    except Exception as err:
        err_str = str(err)
        if "Could not find the '" in err_str and "' column" in err_str:
            col_err = err_str.split("Could not find the '")[1].split("' column")[0]
            if col_err in payload:
                payload_retry = payload.copy()
                del payload_retry[col_err]
                return safe_insert(table_name, payload_retry, replace=replace)
        return True

def safe_update_venda(venda_id, payload: dict):
    if venda_id in (None, ""):
        return False
    sqlite_update_record("vendas", venda_id, payload)
    if not supabase:
        return True
    try:
        supabase.table("vendas").update(payload).eq("id", venda_id).execute()
        return True
    except Exception:
        return True

def safe_delete_venda(venda_id):
    if venda_id in (None, ""):
        return False
    sqlite_delete_record("vendas", venda_id)
    if supabase:
        try:
            supabase.table("vendas").delete().eq("id", venda_id).execute()
        except Exception:
            pass
    return True

def atualizar_caixa_da_venda(venda_antiga: dict, venda_nova: dict | None = None, excluir: bool = False):
    data_rec = venda_antiga.get("data_recebimento") or venda_antiga.get("data")
    codigo = str(venda_antiga.get("codigo_bone", venda_antiga.get("codigo", ""))).strip()
    cliente = str(venda_antiga.get("cliente", "")).strip()
    qtd = int(pd.to_numeric(venda_antiga.get("qtd", 1), errors="coerce") or 1)
    desc_antiga = f"Venda {codigo} ({qtd}un) - {cliente}"
    if not data_rec or not codigo:
        return

    if not supabase:
        return
    try:
        if excluir:
            supabase.table("caixa").delete().eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
        elif venda_nova is not None:
            data_nova = venda_nova.get("data_recebimento") or venda_nova.get("data")
            v_bruto_n = float(venda_nova.get("valor_venda", 0) or 0)
            t_n = float(venda_nova.get("tarifa", venda_nova.get("tarifa_bancaria", venda_nova.get("tarifa_cartao", 0))) or 0)
            valor_novo = float(venda_nova.get("valor_recebido", v_bruto_n - t_n) or (v_bruto_n - t_n))
            codigo_novo = str(venda_nova.get("codigo_bone", codigo)).strip()
            cliente_novo = str(venda_nova.get("cliente", cliente)).strip()
            qtd_nova = int(pd.to_numeric(venda_nova.get("qtd", qtd), errors="coerce") or qtd)
            desc_nova = f"Venda {codigo_novo} ({qtd_nova}un) - {cliente_novo}"
            if data_nova:
                supabase.table("caixa").update({
                    "data": parse_date_str(data_nova),
                    "desc": desc_nova,
                    "tipo": "Venda",
                    "valor": valor_novo
                }).eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
            else:
                supabase.table("caixa").delete().eq("data", parse_date_str(data_rec)).eq("desc", desc_antiga).execute()
    except Exception:
        pass

def safe_upsert_produto(payload: dict):
    cod = payload.get("codigo")
    if cod:
        st.session_state["extra_costs_cache"][cod] = {
            "estampa_extra": payload.get("estampa_extra", 0.0),
            "matriz_bordado": payload.get("matriz_bordado", 0.0),
            "data_aquisicao": payload.get("data_aquisicao", "")
        }
    sqlite_insert_record("produtos", payload, replace=True)
    if not supabase:
        return True
    try:
        supabase.table("produtos").upsert(payload, on_conflict="codigo").execute()
        return True
    except Exception:
        return True

def dar_baixa_estoque_venda(codigo_prod, qtd_venda=1):
    if not codigo_prod or qtd_venda <= 0:
        return False
    
    if supabase:
        try:
            res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
            if res_p.data and len(res_p.data) > 0:
                prod_row = res_p.data[0]
                col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
                qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
                novo_estoque = max(0, qtd_atual - int(qtd_venda))
                supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
        except Exception:
            pass

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {row[1] for row in cur.fetchall()}
        if cols:
            col_qtd_sql = "qtd_estoque" if "qtd_estoque" in cols else ("qtd" if "qtd" in cols else "estoque")
            cur.execute(f"SELECT {col_qtd_sql} FROM produtos WHERE codigo = ?", (codigo_prod,))
            row_p = cur.fetchone()
            if row_p:
                qtd_atual_sql = int(pd.to_numeric(row_p[0], errors="coerce") or 0)
                novo_estoque_sql = max(0, qtd_atual_sql - int(qtd_venda))
                cur.execute(f"UPDATE produtos SET {col_qtd_sql} = ? WHERE codigo = ?", (novo_estoque_sql, codigo_prod))
                conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()

    return True

def estornar_estoque(codigo_prod, qtd_estorno):
    if not codigo_prod or qtd_estorno <= 0:
        return False
    
    if supabase:
        try:
            res_p = supabase.table("produtos").select("*").eq("codigo", codigo_prod).execute()
            if res_p.data and len(res_p.data) > 0:
                prod_row = res_p.data[0]
                col_qtd = "qtd_estoque" if "qtd_estoque" in prod_row else ("qtd" if "qtd" in prod_row else "estoque")
                qtd_atual = int(pd.to_numeric(prod_row.get(col_qtd, 0), errors="coerce") or 0)
                novo_estoque = qtd_atual + int(qtd_estorno)
                supabase.table("produtos").update({col_qtd: novo_estoque}).eq("codigo", codigo_prod).execute()
        except Exception:
            pass

    conn = None
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(produtos)")
        cols = {row[1] for row in cur.fetchall()}
        if cols:
            col_qtd_sql = "qtd_estoque" if "qtd_estoque" in cols else ("qtd" if "qtd" in cols else "estoque")
            cur.execute(f"SELECT {col_qtd_sql} FROM produtos WHERE codigo = ?", (codigo_prod,))
            row_p = cur.fetchone()
            if row_p:
                qtd_atual_sql = int(pd.to_numeric(row_p[0], errors="coerce") or 0)
                novo_estoque_sql = qtd_atual_sql + int(qtd_estorno)
                cur.execute(f"UPDATE produtos SET {col_qtd_sql} = ? WHERE codigo = ?", (novo_estoque_sql, codigo_prod))
                conn.commit()
        else:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS produtos (
                    codigo TEXT PRIMARY KEY,
                    cor TEXT,
                    frase TEXT,
                    cor_estampa TEXT,
                    categoria TEXT,
                    custo REAL,
                    qtd_estoque INTEGER DEFAULT 1
                )
            ''')
            cur.execute("INSERT OR REPLACE INTO produtos (codigo, qtd_estoque) VALUES (?, ?)", (codigo_prod, int(qtd_estorno)))
            conn.commit()
    except Exception:
        pass
    finally:
        if conn is not None:
            conn.close()

    return True

@st.cache_data(ttl=600)
def get_saved_logo():
    if not supabase:
        return None
    try:
        res = supabase.table("configuracoes").select("valor_b64").eq("chave", "logo_header").execute()
        if res.data and len(res.data) > 0:
            val = res.data[0].get("valor_b64")
            if val and val.startswith("data:image"):
                return val
    except Exception:
        pass
    return None

def save_logo_to_db(b64_data_url):
    if not supabase:
        return False
    try:
        supabase.table("configuracoes").upsert(
            {"chave": "logo_header", "valor_b64": b64_data_url}, 
            on_conflict="chave"
        ).execute()
        get_saved_logo.clear()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar logo: {e}")
        return False

def delete_logo_from_db():
    if not supabase:
        return
    try:
        supabase.table("configuracoes").delete().eq("chave", "logo_header").execute()
        get_saved_logo.clear()
    except Exception as e:
        st.error(f"Erro ao remover logo: {e}")

def get_ultimo_codigo_config():
    if supabase:
        try:
            res = supabase.table("configuracoes").select("valor_b64").eq("chave", "ultimo_codigo_bone").execute()
            if res.data and len(res.data) > 0:
                val = res.data[0].get("valor_b64")
                if val:
                    return str(val).strip()
        except Exception:
            pass
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        c = conn.cursor()
        c.execute("SELECT valor_b64 FROM configuracoes WHERE chave = 'ultimo_codigo_bone'")
        row = c.fetchone()
        conn.close()
        if row and row[0]:
            return str(row[0]).strip()
    except Exception:
        pass
    return "BL-0001"

def set_ultimo_codigo_config(novo_codigo):
    novo_codigo = str(novo_codigo).strip()
    if supabase:
        try:
            supabase.table("configuracoes").upsert(
                {"chave": "ultimo_codigo_bone", "valor_b64": novo_codigo},
                on_conflict="chave"
            ).execute()
        except Exception as e:
            st.error(f"Erro ao salvar configuração do código no Supabase: {e}")
    try:
        conn = sqlite3.connect(DB_NAME, timeout=30.0)
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO configuracoes (chave, valor_b64) VALUES ('ultimo_codigo_bone', ?)", (novo_codigo,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Erro ao salvar configuração do código localmente: {e}")
        return False

def gerar_proximo_codigo(codigo_atual):
    codigo_atual = str(codigo_atual).strip()
    import re
    try:
        match = re.search(r'^(.*?)[-_]?(\d+)$', codigo_atual)
        if match:
            prefixo = match.group(1)
            num_str = match.group(2)
            proximo_num = int(num_str) + 1
            tam_num = len(num_str)
            sep = "-" if "-" in codigo_atual else ("_" if "_" in codigo_atual else "")
            return f"{prefixo}{sep}{proximo_num:0{tam_num}d}" if sep else f"{prefixo}{proximo_num:0{tam_num}d}"
        else:
            return f"{codigo_atual}-0001"
    except Exception:
        return "BL-0002"

def get_df_compra_mercadorias():
    df_ped_ent = carregar_dataframe(
        "SELECT * FROM pedidos WHERE status LIKE '%Entregue%' ORDER BY id ASC"
    )
    if df_ped_ent.empty:
        return pd.DataFrame()
    
    df_ped_ent["preco_num"] = get_numeric_series(df_ped_ent, "preco")
    df_ped_ent["estampa_extra_num"] = get_numeric_series(df_ped_ent, "valor_estampa_extra")
    df_ped_ent["matriz_num"] = get_numeric_series(df_ped_ent, "valor_matriz")
    
    df_ped_ent["total_item_calc"] = (
        df_ped_ent["preco_num"] +
        df_ped_ent["estampa_extra_num"] +
        df_ped_ent["matriz_num"]
    )
    if "total_item" in df_ped_ent.columns:
        total_importado = pd.to_numeric(df_ped_ent["total_item"], errors="coerce")
        df_ped_ent["total_item_calc"] = total_importado.where(total_importado.notna(), df_ped_ent["total_item_calc"])
    
    col_dt = "data_criacao" if "data_criacao" in df_ped_ent.columns else "data"
    
    if "codigo_produto" in df_ped_ent.columns:
        codigos_col = df_ped_ent["codigo_produto"].fillna(get_ultimo_codigo_config())
    else:
        codigos_col = get_ultimo_codigo_config()

    df_cm = pd.DataFrame({
        "id": df_ped_ent.get("id"),
        "Data_Raw": df_ped_ent.get(col_dt, ""),
        "Data": df_ped_ent[col_dt].apply(format_data_br) if col_dt in df_ped_ent.columns else "",
        "Código": codigos_col,
        "Cor do Boné": df_ped_ent.get("cor_bone", ""),
        "Arte Estampada": df_ped_ent.get("frase_arte", ""),
        "Cor da Estampa": df_ped_ent.get("cor_linha", ""),
        "Produto": df_ped_ent.get("tipo", ""),
        "preco_num": df_ped_ent["preco_num"],
        "estampa_extra_num": df_ped_ent["estampa_extra_num"],
        "matriz_num": df_ped_ent["matriz_num"],
        "total_item_calc": df_ped_ent["total_item_calc"]
    })
    return df_cm

def calcular_saldo_final_fluxo_caixa(df_vendas_in, df_custos_in, df_aportes_in, df_devolucoes_in):
    lista_movimentos = []

    # 1. Compras de Mercadorias
    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        agrup_cm = df_cm.groupby("data_str").agg(total_custo=("total_item_calc", "sum")).reset_index()
        for _, r in agrup_cm.iterrows():
            tot_c = float(r["total_custo"])
            if tot_c > 0:
                lista_movimentos.append({"Data_Val": r["data_str"], "Valor_Num": -tot_c})

    # 2. Recebimentos Líquidos das Vendas
    if not df_vendas_in.empty:
        df_v_norm = normalizar_df_vendas(df_vendas_in)
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_v_norm.columns else ("data_receb" if "data_receb" in df_v_norm.columns else None)
        if col_dt_rec:
            df_v_recebidas = df_v_norm[df_v_norm[col_dt_rec].notna() & df_v_norm[col_dt_rec].astype(str).str.strip().ne("") & df_v_norm[col_dt_rec].astype(str).str.lower().ne("none")].copy()
            for _, r in df_v_recebidas.iterrows():
                dt_rec_val = r.get(col_dt_rec)
                val_v_calc = float(r.get("liquido_recebido_calc", 0.0))
                if val_v_calc > 0:
                    lista_movimentos.append({"Data_Val": parse_date_str(dt_rec_val), "Valor_Num": val_v_calc})

    # 3. Custos e Despesas
    if not df_custos_in.empty:
        for _, r in df_custos_in.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            if val_c > 0:
                lista_movimentos.append({"Data_Val": parse_date_str(r.get("data")), "Valor_Num": -val_c})

    # 4. Aportes e Devoluções
    if not df_aportes_in.empty:
        for _, r in df_aportes_in.iterrows():
            val_ap = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            tipo_ap = str(r.get("tipo", ""))
            if val_ap != 0:
                is_devolucao = "devoluc" in tipo_ap.lower() or val_ap < 0
                val_final = -abs(val_ap) if is_devolucao else abs(val_ap)
                dt_ap_raw = r.get("data") or r.get("data_aporte") or r.get("created_at")
                dt_ap_str = parse_date_str(dt_ap_raw) if dt_ap_raw else datetime.date.today().strftime("%Y-%m-%d")
                lista_movimentos.append({"Data_Val": dt_ap_str, "Valor_Num": val_final})

    # 5. Devoluções de Vendas
    if not df_devolucoes_in.empty:
        for _, r in df_devolucoes_in.iterrows():
            val_dev = float(pd.to_numeric(r.get("valor_devolvido", 0.0), errors="coerce") or 0.0)
            if val_dev > 0:
                dt_dev_raw = r.get("data_devolucao")
                dt_dev_str = parse_date_str(dt_dev_raw) if dt_dev_raw else datetime.date.today().strftime("%Y-%m-%d")
                lista_movimentos.append({"Data_Val": dt_dev_str, "Valor_Num": -val_dev})

    if lista_movimentos:
        df_ext = pd.DataFrame(lista_movimentos)
        return float(df_ext["Valor_Num"].sum())
    return 0.0

# Carregar tabelas do Supabase / SQLite
df_produtos = fetch_data("produtos")

CODIGOS_REMOVER = ["BL-0001", "BL-0002", "BL-0003", "BL-0004", "Teste1", "Teste 1"]
if not df_produtos.empty and "codigo" in df_produtos.columns:
    df_produtos = df_produtos[~df_produtos["codigo"].astype(str).str.strip().isin(CODIGOS_REMOVER)].reset_index(drop=True)

df_vendas = fetch_data("vendas")
if not df_vendas.empty:
    col_c_v = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
    if col_c_v in df_vendas.columns:
        df_vendas = df_vendas[~df_vendas[col_c_v].astype(str).str.strip().isin(CODIGOS_REMOVER)].reset_index(drop=True)

df_caixa = fetch_data("caixa")
df_aportes = fetch_data("aportes")
df_custos = fetch_data("custos_avulsos")
df_baixas = fetch_data("baixas_estoque")
df_devolucoes = fetch_data("devolucoes_vendas")

if "flash_success" in st.session_state and st.session_state["flash_success"]:
    st.success(st.session_state["flash_success"])
    st.session_state["flash_success"] = None

if "current_logo" not in st.session_state:
    st.session_state["current_logo"] = get_saved_logo()

# 3. Sidebar (Barra Lateral)
with st.sidebar:
    st.markdown("### 📌 Módulos do Sistema")
    menu = st.radio(
        "Navegue entre os módulos:",
        ["📈 Dashboard", "📦 Pedidos", "🛍 Compra de Mercadorias", "📦 Estoque", "🛒 Vendas", "💰 Contas a Receber", "💵 Custos", "💰 Fluxo de Caixa", "🤝 Aportes dos Sócios", "💾 Gestão de Dados", "⚙ Configuração"],
        label_visibility="collapsed"
    )

    st.markdown("---")
    
    with st.expander("🎨 Personalização", expanded=False):
        uploaded_logo = st.file_uploader(
            "Carregar Nova Logo da Marca", 
            type=["png", "jpg", "jpeg", "webp", "svg"],
            help="Envie a logomarca para fixar permanentemente no topo do site."
        )
        if uploaded_logo is not None:
            with st.spinner("Processando e salvando imagem..."):
                bytes_data = uploaded_logo.getvalue()
                b64_str = base64.b64encode(bytes_data).decode("utf-8")
                mime_type = uploaded_logo.type or "image/png"
                data_url = f"data:{mime_type};base64,{b64_str}"
                
                if save_logo_to_db(data_url):
                    st.session_state["current_logo"] = data_url
                    st.success("Logo fixa salva e aplicada!")
                    st.rerun()

        if st.session_state.get("current_logo") is not None:
            if st.button("🗑 Excluir Logo Atual", use_container_width=True, type="secondary"):
                delete_logo_from_db()
                st.session_state["current_logo"] = None
                st.success("Logo removida permanentemente!")
                st.rerun()

# 4. Exibição do Cabeçalho
active_logo = st.session_state.get("current_logo")
if active_logo:
    st.image(active_logo, use_container_width=True)
else:
    st.markdown("""
    <div class="custom-header-container">
        <span style="font-size: 3.2em; margin-right: 10px;">🧢</span>
        <div class="header-text">
            <h1>R² Bonés — Sistema Gerencial Pro</h1>
            <p>Vista o que você pensa • Painel de Controle Operacional</p>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# 5. Módulos do Sistema

if "Dashboard" in menu:
    st.subheader("📈 Dashboard Executivo Avançado")
    
    tab_d1, tab_d2, tab_d3, tab_d4 = st.tabs([
        "Visão Geral & Faturamento", 
        "Lucratividade por Peça", 
        "Giro de Estoque & Ruptura", 
        "Feiras & Eventos"
    ])
    
    col_v_val = "valor_venda" if "valor_venda" in df_vendas.columns else ("valor" if "valor" in df_vendas.columns else ("valor_total" if "valor_total" in df_vendas.columns else None))
    total_faturado = float(df_vendas[col_v_val].sum()) if not df_vendas.empty and col_v_val else 0.0
    
    total_cmv = 0.0
    if not df_vendas.empty:
        df_cm_ref = get_df_compra_mercadorias()
        if not df_cm_ref.empty:
            c_v_col = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
            df_v_cm = df_vendas.merge(df_cm_ref, left_on=c_v_col, right_on="Código", how="inner")
            if "total_item_calc" in df_v_cm.columns:
                col_q = "qtd" if "qtd" in df_v_cm.columns else ("quantidade" if "quantidade" in df_v_cm.columns else None)
                qtds = get_numeric_series(df_v_cm, col_q, 1.0) if col_q else 1.0
                total_cmv = float((df_v_cm["total_item_calc"] * qtds).sum())

    saldo_caixa = calcular_saldo_final_fluxo_caixa(df_vendas, df_custos, df_aportes, df_devolucoes)

    total_qtd_vendida = 0
    if not df_vendas.empty:
        col_q_venda = "qtd" if "qtd" in df_vendas.columns else ("quantidade" if "quantidade" in df_vendas.columns else None)
        if col_q_venda:
            total_qtd_vendida = int(get_numeric_series(df_vendas, col_q_venda).sum())

    # --- ABA 1: Visão Geral & Faturamento ---
    with tab_d1:
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Faturamento Total <span class="tooltip-icon" title="Soma total de todas as vendas confirmadas">ℹ</span></div><div class="kpi-value">R$ {total_faturado:,.2f}</div></div>', unsafe_allow_html=True)
        with k2:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">CMV TOTAL <span class="tooltip-icon" title="Custo das mercadorias vendidas obtido do menu Compra de Mercadoria">ℹ</span></div><div class="kpi-value">R$ {total_cmv:,.2f}</div></div>', unsafe_allow_html=True)
        with k3:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #f59e0b;"><div class="kpi-title">Saldo em Caixa <span class="tooltip-icon" title="Saldo final vindo do menu Fluxo de Caixa">ℹ</span></div><div class="kpi-value">R$ {saldo_caixa:,.2f}</div></div>', unsafe_allow_html=True)
        with k4:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Quantidade Vendida <span class="tooltip-icon" title="Quantidade total de peças/bonés faturados nas vendas">ℹ</span></div><div class="kpi-value">{total_qtd_vendida} un</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        col_d_venda = "data" if "data" in df_vendas.columns else ("data_venda" if "data_venda" in df_vendas.columns else None)
        meses_disponiveis = ["TODOS"]
        if not df_vendas.empty and col_d_venda:
            df_vendas["mes_ano"] = pd.to_datetime(df_vendas[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
            meses_disponiveis.extend(sorted(df_vendas["mes_ano"].dropna().unique().tolist()))
        
        mes_sel = st.selectbox("📅 Selecionar Período / Mês (Aba 1):", list(set(meses_disponiveis)))
        
        df_vendas_fil = df_vendas.copy()
        if mes_sel != "TODOS" and not df_vendas_fil.empty and col_d_venda:
            df_vendas_fil["mes_temp"] = pd.to_datetime(df_vendas_fil[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
            df_vendas_fil = df_vendas_fil[df_vendas_fil["mes_temp"] == mes_sel]
            
        g1, g2 = st.columns(2)
        with g1:
            st.markdown("#### 🟢 Faturamento vs. 🔴 CMV")
            if not df_vendas_fil.empty and col_d_venda and col_v_val:
                df_vendas_fil["mes"] = pd.to_datetime(df_vendas_fil[col_d_venda].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m")
                y_cols = [col_v_val]
                if "custo" in df_vendas_fil.columns:
                    y_cols.append("custo")
                agrup = df_vendas_fil.groupby("mes")[y_cols].sum().reset_index()
                fig1 = px.bar(agrup, x="mes", y=y_cols, barmode="group",
                              color_discrete_sequence=["#10b981", "#ef4444"], template="plotly_white")
                st.plotly_chart(fig1, use_container_width=True)
            else:
                st.info("Sem dados suficientes para gerar o gráfico.")

        with g2:
            st.markdown("#### 🎨 Cores / Modelos Mais Vendidos (Ordem Alfabética)")
            c_v_col = "codigo_bone" if "codigo_bone" in df_vendas_fil.columns else ("codigo" if "codigo" in df_vendas_fil.columns else "codigo_produto")
            if not df_vendas_fil.empty and c_v_col in df_vendas_fil.columns and not df_produtos.empty:
                df_m = df_vendas_fil.merge(df_produtos, left_on=c_v_col, right_on="codigo", how="left")
                cor_col = "cor" if "cor" in df_m.columns else "cor_x"
                if cor_col in df_m.columns:
                    qtd_col = "qtd_x" if "qtd_x" in df_m.columns else ("qtd" if "qtd" in df_m.columns else "qtd_y")
                    agrup_cor = df_m.groupby(cor_col)[qtd_col].sum().reset_index()
                    agrup_cor = agrup_cor.sort_values(by=cor_col, ascending=True)
                    fig2 = px.pie(agrup_cor, names=cor_col, values=qtd_col, hole=0.45, color_discrete_sequence=px.colors.qualitative.Pastel)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("Sem informação de cor cadastrada.")
            else:
                st.info("Nenhuma venda registrada.")

    # --- ABA 2: Lucratividade por Peça ---
    with tab_d2:
        st.markdown("#### 💎 Lucratividade Detalhada por Venda e Peça")
        
        df_lucro = pd.DataFrame()
        if not df_vendas.empty:
            df_l_base = normalizar_df_vendas(df_vendas).copy()
            df_cm_ref = get_df_compra_mercadorias()
            c_v_col = "codigo_bone" if "codigo_bone" in df_l_base.columns else ("codigo" if "codigo" in df_l_base.columns else "codigo_produto")
            
            if not df_cm_ref.empty and c_v_col in df_l_base.columns:
                df_l_cruzado = df_l_base.merge(df_cm_ref, left_on=c_v_col, right_on="Código", how="left")
                df_l_cruzado["preco_base_un"] = df_l_cruzado["preco_num"].fillna(0.0)
                df_l_cruzado["estampa_extra_un"] = df_l_cruzado["estampa_extra_num"].fillna(0.0)
                df_l_cruzado["matriz_bordado_un"] = df_l_cruzado["matriz_num"].fillna(0.0)
                df_l_cruzado["cmv_unitario"] = df_l_cruzado["preco_base_un"] + df_l_cruzado["estampa_extra_un"] + df_l_cruzado["matriz_bordado_un"]
                
                qtd_col_l = "qtd" if "qtd" in df_l_cruzado.columns else 1
                df_l_cruzado["qtd_num"] = get_numeric_series(df_l_cruzado, qtd_col_l, 1.0)
                df_l_cruzado["cmv_total"] = df_l_cruzado["cmv_unitario"] * df_l_cruzado["qtd_num"]
                
                df_l_cruzado["lucro_liquido_total"] = df_l_cruzado["liquido_recebido_calc"] - df_l_cruzado["cmv_total"]
                df_l_cruzado["lucro_unitario"] = df_l_cruzado["lucro_liquido_total"] / df_l_cruzado["qtd_num"].replace(0, 1)
                
                df_lucro = df_l_cruzado
            else:
                df_lucro = df_l_base
                df_lucro["cmv_total"] = 0.0
                df_lucro["lucro_liquido_total"] = df_lucro["liquido_recebido_calc"]
                df_lucro["lucro_unitario"] = df_lucro["liquido_recebido_calc"]
                df_lucro["Arte Estampada"] = "Peça Geral"

        margem_media_global = 0.0
        lucro_liquido_total_val = 0.0
        if not df_lucro.empty:
            lucro_liquido_total_val = float(df_lucro["lucro_liquido_total"].sum())
            faturamento_total_lucro = float(df_lucro["valor_bruto_calc"].sum())
            if faturamento_total_lucro > 0:
                margem_media_global = (lucro_liquido_total_val / faturamento_total_lucro) * 100.0

        lk1, lk2 = st.columns(2)
        with lk1:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Margem de Lucro Média Global</div><div class="kpi-value">{margem_media_global:.2f}%</div></div>', unsafe_allow_html=True)
        with lk2:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Lucro Líquido Total</div><div class="kpi-value">R$ {lucro_liquido_total_val:,.2f}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        if not df_lucro.empty:
            lg1, lg2 = st.columns(2)
            with lg1:
                st.markdown("#### 🏆 Itens / Artes Mais Lucrativos")
                col_arte_l = "Arte Estampada" if "Arte Estampada" in df_lucro.columns else "cliente"
                agrup_arte = df_lucro.groupby(col_arte_l)["lucro_liquido_total"].sum().reset_index().sort_values(by="lucro_liquido_total", ascending=False).head(8)
                fig_lucro_bar = px.bar(agrup_arte, x=col_arte_l, y="lucro_liquido_total", text_auto=".2f",
                                       color="lucro_liquido_total", color_continuous_scale="greens", template="plotly_white")
                st.plotly_chart(fig_lucro_bar, use_container_width=True)

            with lg2:
                st.markdown("#### 📋 Tabela Detalhada de Lucratividade por Venda")
                df_tabela_lucro = pd.DataFrame({
                    "ID": df_lucro.get("id"),
                    "Cliente": df_lucro.get("cliente"),
                    "Código": df_lucro.get("codigo_bone") if "codigo_bone" in df_lucro.columns else df_lucro.get("codigo"),
                    "Valor Bruto": df_lucro.get("valor_bruto_calc", 0).apply(lambda x: f"R$ {x:,.2f}"),
                    "CMV Total": df_lucro.get("cmv_total", 0).apply(lambda x: f"R$ {x:,.2f}"),
                    "Tarifas": df_lucro.get("tarifa_calc", 0).apply(lambda x: f"R$ {x:,.2f}"),
                    "Lucro Líquido": df_lucro.get("lucro_liquido_total", 0).apply(lambda x: f"R$ {x:,.2f}")
                })
                st.dataframe(df_tabela_lucro, use_container_width=True, hide_index=True)
        else:
            st.info("Sem dados de vendas suficientes para calcular a lucratividade.")

    # --- ABA 3: Giro de Estoque & Ruptura ---
    with tab_d3:
        st.markdown("#### 📦 Giro de Estoque, Baixas e Alerta de Ruptura")
        
        df_cm_estoque_tab3 = get_df_compra_mercadorias()
        qtd_total_est_aba3 = 0
        itens_ruptura = []
        
        if not df_cm_estoque_tab3.empty:
            df_est_tab3 = df_cm_estoque_tab3.copy()
            if not df_produtos.empty and "codigo" in df_produtos.columns:
                col_q_p3 = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
                df_est_tab3 = df_est_tab3.merge(df_produtos[["codigo", col_q_p3]], left_on="Código", right_on="codigo", how="left")
                df_est_tab3["Estoque_Atual"] = pd.to_numeric(df_est_tab3[col_q_p3], errors="coerce").fillna(1).astype(int)
            else:
                df_est_tab3["Estoque_Atual"] = 1
                
            qtd_total_est_aba3 = int(df_est_tab3[df_est_tab3["Estoque_Atual"] > 0]["Estoque_Atual"].sum())
            itens_ruptura = df_est_tab3[(df_est_tab3["Estoque_Atual"] <= 2) & (df_est_tab3["Estoque_Atual"] > 0)].to_dict(orient="records")

        ek1, ek2 = st.columns(2)
        with ek1:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #3b82f6;"><div class="kpi-title">Quantidade Total em Estoque</div><div class="kpi-value">{qtd_total_est_aba3} un</div></div>', unsafe_allow_html=True)
        with ek2:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">Itens com Estoque Baixo ($\le 2$ un)</div><div class="kpi-value">{len(itens_ruptura)} itens</div></div>', unsafe_allow_html=True)

        if itens_ruptura:
            st.warning("⚠ **Alerta de Ruptura / Estoque Baixo:** Os seguintes itens estão com 2 unidades ou menos em estoque:")
            df_ruptura_exib = pd.DataFrame(itens_ruptura)[["Código", "Cor do Boné", "Arte Estampada", "Estoque_Atual"]]
            st.dataframe(df_ruptura_exib, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.markdown("##### 🔻 Resumo Integrado de Baixas de Estoque (Perda, Avaria, Brinde)")
        df_baixas_tab3 = fetch_data("baixas_estoque")
        if not df_baixas_tab3.empty:
            st.dataframe(df_baixas_tab3, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma baixa de estoque registrada com motivos de perda, avaria ou brinde.")

        st.markdown("---")
        st.markdown("##### 📊 Tabela de Rastreio de Giro (Frequência de Saída)")
        if not df_vendas.empty and not df_cm_estoque_tab3.empty:
            c_v_col = "codigo_bone" if "codigo_bone" in df_vendas.columns else ("codigo" if "codigo" in df_vendas.columns else "codigo_produto")
            col_q_v = "qtd" if "qtd" in df_vendas.columns else "quantidade"
            df_giro = df_vendas.groupby(c_v_col)[col_q_v].sum().reset_index().rename(columns={col_q_v: "Qtd_Saidas_Vendas", c_v_col: "Código"})
            df_giro_completo = df_cm_estoque_tab3.merge(df_giro, on="Código", how="left").fillna({"Qtd_Saidas_Vendas": 0})
            st.dataframe(df_giro_completo[["Código", "Cor do Boné", "Arte Estampada", "Produto", "Qtd_Saidas_Vendas"]], use_container_width=True, hide_index=True)
        else:
            st.info("Dados insuficientes para calcular o giro de vendas.")

    # --- ABA 4: Feiras & Eventos (Ex: Feirarte) ---
    with tab_d4:
        st.markdown("#### 🎪 Feiras & Eventos (Análise de ROI / Feirarte)")
        
        df_custos_ev = fetch_data("custos_avulsos")
        feiras_disponiveis = ["TODAS"]
        if not df_custos_ev.empty:
            subcat_c = df_custos_ev.get("subcategoria", pd.Series([""] * len(df_custos_ev))).fillna("").astype(str)
            df_feiras_raw = df_custos_ev[subcat_c.str.contains("feira", case=False, na=False)]
            if not df_feiras_raw.empty and "desc" in df_feiras_raw.columns:
                nomes_f = df_feiras_raw["desc"].astype(str).apply(lambda x: x.split(" - ")[0].replace("Feira: ", "").strip() if "Feira: " in x else "Geral")
                feiras_disponiveis.extend(sorted(nomes_f.unique().tolist()))

        feira_sel = st.selectbox("🎪 Selecionar Feira / Evento:", list(set(feiras_disponiveis)))

        total_despesas_feira = 0.0
        df_despesas_feira_filtrada = pd.DataFrame()
        
        if not df_custos_ev.empty:
            subcat_c = df_custos_ev.get("subcategoria", pd.Series([""] * len(df_custos_ev))).fillna("").astype(str)
            df_f_filtro = df_custos_ev[subcat_c.str.contains("feira", case=False, na=False)].copy()
            if feira_sel != "TODAS":
                df_f_filtro = df_f_filtro[df_f_filtro["desc"].astype(str).str.contains(feira_sel, case=False, na=False)]
            
            total_despesas_feira = float(df_f_filtro["valor"].apply(parse_money).sum())
            df_despesas_feira_filtrada = df_f_filtro

        total_faturado_feira = 0.0
        if not df_vendas.empty and "cliente" in df_vendas.columns:
            df_vendas_norm_f = normalizar_df_vendas(df_vendas)
            if feira_sel != "TODAS":
                df_vendas_feira = df_vendas_norm_f[df_vendas_norm_f["cliente"].astype(str).str.strip().str.lower() == feira_sel.strip().lower()]
            else:
                df_vendas_feira = df_vendas_norm_f
            total_faturado_feira = float(df_vendas_feira["valor_bruto_calc"].sum())

        roi_feira = total_faturado_feira - total_despesas_feira

        fk1, fk2, fk3 = st.columns(3)
        with fk1:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #10b981;"><div class="kpi-title">Total Faturado no Período</div><div class="kpi-value">R$ {total_faturado_feira:,.2f}</div></div>', unsafe_allow_html=True)
        with fk2:
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: #ef4444;"><div class="kpi-title">Total Despesas Operacionais</div><div class="kpi-value">R$ {total_despesas_feira:,.2f}</div></div>', unsafe_allow_html=True)
        with fk3:
            cor_roi = "#10b981" if roi_feira >= 0 else "#ef4444"
            st.markdown(f'<div class="kpi-card-advanced" style="border-top-color: {cor_roi};"><div class="kpi-title">Saldo / ROI do Evento</div><div class="kpi-value">R$ {roi_feira:,.2f}</div></div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        fg1, fg2 = st.columns(2)
        with fg1:
            st.markdown("#### 🥧 Peso de Cada Tipo de Despesa da Feira")
            if not df_despesas_feira_filtrada.empty:
                df_pie_feira = df_despesas_feira_filtrada.groupby("tipo")["valor"].sum().reset_index()
                fig_feira_pie = px.pie(df_pie_feira, names="tipo", values="valor", hole=0.4, color_discrete_sequence=px.colors.qualitative.Set3)
                st.plotly_chart(fig_feira_pie, use_container_width=True)
            else:
                st.info("Sem despesas cadastradas para esta feira.")

        with fg2:
            st.markdown("#### 📋 Lançamentos de Despesas da Feira")
            if not df_despesas_feira_filtrada.empty:
                st.dataframe(df_despesas_feira_filtrada[["data", "tipo", "desc", "valor"]], use_container_width=True, hide_index=True)
            else:
                st.info("Nenhum lançamento encontrado.")

elif "Compra de Mercadorias" in menu:
    st.subheader("🛍 Relatório de Compra de Mercadorias")
    
    df_cm = get_df_compra_mercadorias()

    if df_cm.empty:
        st.info("Nenhum pedido entregue disponível para o relatório de compra de mercadorias.")
    else:
        df_cm["Mes_Ano"] = pd.to_datetime(df_cm["Data_Raw"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
        
        meses_unicos_cm = df_cm["Mes_Ano"].unique()
        for mes in sorted(meses_unicos_cm, reverse=True):
            df_mes_cm = df_cm[df_cm["Mes_Ano"] == mes].copy()
            
            with st.expander(f"📅 Período / Mês: {mes} ({len(df_mes_cm)} itens)", expanded=True):
                df_relatorio = pd.DataFrame({
                    "Data": df_mes_cm["Data"],
                    "Código": df_mes_cm["Código"],
                    "Cor do Boné": df_mes_cm["Cor do Boné"],
                    "Arte Estampada": df_mes_cm["Arte Estampada"],
                    "Cor da Estampa": df_mes_cm["Cor da Estampa"],
                    "Produto": df_mes_cm["Produto"],
                    "Preço Base": df_mes_cm["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Estampa Extra": df_mes_cm["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Matriz Bordado": df_mes_cm["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}"),
                    "Total Item": df_mes_cm["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                })

                st.dataframe(df_relatorio, use_container_width=True, hide_index=True)

elif "Pedidos" in menu:
    st.subheader("📦 Gerenciamento de Pedidos e Encomendas")

    df_todos_pedidos = carregar_dataframe("SELECT * FROM pedidos ORDER BY id ASC")

    with st.expander("➕ Cadastrar Novo Item no Pedido (Manual)", expanded=False):
        opcoes_itens = ["➕ [NOVO] Cadastrar Novo Item"]
        if not df_todos_pedidos.empty:
            for _, r in df_todos_pedidos.iterrows():
                id_p = r.get("id")
                lote_p = r.get("lote_id", "")
                cor_p = r.get("cor_bone", "")
                arte_p = r.get("frase_arte", "")
                opcoes_itens.append(f"✏ [ID #{id_p}] Pedido: {lote_p} | {cor_p} - {arte_p}")

        item_ped_sel = st.selectbox(
            "📌 Selecione uma opção para Cadastrar Novo ou Editar/Excluir um Item Existente:",
            opcoes_itens,
            key="sel_man_ped_item"
        )

        dados_p_edit = {}
        is_edit_ped = False
        id_ped_edit = None

        if item_ped_sel and not item_ped_sel.startswith("➕"):
            is_edit_ped = True
            try:
                id_ped_edit = int(item_ped_sel.split("]")[0].replace("✏ [ID #", "").strip())
                match_p = df_todos_pedidos[df_todos_pedidos["id"] == id_ped_edit]
                if not match_p.empty:
                    dados_p_edit = match_p.iloc[0].to_dict()
            except Exception:
                pass

        with st.form("form_novo_pedido_manual"):
            c_p1, c_p2, c_p3 = st.columns(3)
            with c_p1:
                lote_m = st.text_input("Identificador / Lote do Pedido *", value=str(dados_p_edit.get("lote_id", "Pedido #3.10-2026")))
                cor_b_m = st.text_input("Cor do Boné *", value=str(dados_p_edit.get("cor_bone", "")))
            with c_p2:
                arte_m = st.text_input("Arte Estampada *", value=str(dados_p_edit.get("frase_arte", "")))
                cor_e_m = st.text_input("Cor da Estampa", value=str(dados_p_edit.get("cor_linha", "")))
            with c_p3:
                prod_opts = ["Básico", "Kids", "Outro", "Premium"]
                prod_cur = str(dados_p_edit.get("tipo", "Básico"))
                idx_prod = prod_opts.index(prod_cur) if prod_cur in prod_opts else 0
                prod_m = st.selectbox("Produto *", prod_opts, index=idx_prod)
                preco_m = st.number_input("Preço Base (R$) *", min_value=0.0, value=float(dados_p_edit.get("preco", 29.0)), format="%.2f")

            c_ex1, c_ex2, c_ex3 = st.columns(3)
            with c_ex1:
                v_extra_m = st.number_input("Estampa Extra (R$)", min_value=0.0, value=float(dados_p_edit.get("valor_estampa_extra", 0.0)), format="%.2f")
            with c_ex2:
                v_matriz_m = st.number_input("Matriz Bordado (R$)", min_value=0.0, value=float(dados_p_edit.get("valor_matriz", 0.0)), format="%.2f")
            with c_ex3:
                dt_init_val = datetime.date.today()
                if is_edit_ped and dados_p_edit.get("data_criacao"):
                    try:
                        dt_init_val = pd.to_datetime(parse_date_str(dados_p_edit.get("data_criacao"))).date()
                    except Exception:
                        pass
                dt_p_m = st.date_input("Data da Criação *", dt_init_val, format="YYYY/MM/DD")

            obs_p_m = st.text_area("Observações do Pedido", value=str(dados_p_edit.get("observacoes", "")))

            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                btn_cadastrar_p = st.form_submit_button("💾 Cadastrar Item", use_container_width=True, type="primary")
            with col_b2:
                btn_atualizar_p = st.form_submit_button("✏ Atualizar Item", use_container_width=True)
            with col_b3:
                btn_excluir_p = st.form_submit_button("🗑 Excluir Item", use_container_width=True)

            if btn_cadastrar_p:
                if not lote_m.strip() or not cor_b_m.strip() or not arte_m.strip():
                    st.error("Preencha os campos obrigatórios (Lote, Cor e Arte)!")
                else:
                    dt_p_str = parse_date_str(dt_p_m)
                    payload_pedido = {
                        "lote_id": lote_m.strip(),
                        "data_criacao": dt_p_str,
                        "cor_bone": cor_b_m.strip(),
                        "frase_arte": arte_m.strip(),
                        "cor_linha": cor_e_m.strip(),
                        "tipo": prod_m,
                        "preco": preco_m,
                        "observacoes": obs_p_m.strip(),
                        "status": "Em Produção",
                        "valor_estampa_extra": v_extra_m,
                        "valor_matriz": v_matriz_m,
                        "total_item": round(preco_m + v_extra_m + v_matriz_m, 2)
                    }
                    safe_insert("pedidos", payload_pedido)
                    st.session_state["flash_success"] = f"🎉 Item cadastrado no lote '{lote_m.strip()}' com sucesso!"
                    st.rerun()

            if btn_atualizar_p:
                if not is_edit_ped or not id_ped_edit:
                    st.error("Selecione um item existente para atualizar!")
                elif not lote_m.strip() or not cor_b_m.strip() or not arte_m.strip():
                    st.error("Preencha os campos obrigatórios (Lote, Cor e Arte)!")
                else:
                    dt_p_str = parse_date_str(dt_p_m)
                    payload_upd_p = {
                        "lote_id": lote_m.strip(),
                        "data_criacao": dt_p_str,
                        "cor_bone": cor_b_m.strip(),
                        "frase_arte": arte_m.strip(),
                        "cor_linha": cor_e_m.strip(),
                        "tipo": prod_m,
                        "preco": preco_m,
                        "observacoes": obs_p_m.strip(),
                        "valor_estampa_extra": v_extra_m,
                        "valor_matriz": v_matriz_m,
                        "total_item": round(preco_m + v_extra_m + v_matriz_m, 2)
                    }
                    sqlite_update_record("pedidos", id_ped_edit, payload_upd_p)
                    if supabase:
                        try:
                            supabase.table("pedidos").update(payload_upd_p).eq("id", id_ped_edit).execute()
                        except Exception:
                            pass

                    st.session_state["flash_success"] = f"🎉 Item ID #{id_ped_edit} atualizado com sucesso!"
                    st.rerun()

            if btn_excluir_p:
                if not is_edit_ped or not id_ped_edit:
                    st.error("Selecione um item existente para excluir!")
                else:
                    sqlite_delete_record("pedidos", id_ped_edit)
                    if supabase:
                        try:
                            supabase.table("pedidos").delete().eq("id", id_ped_edit).execute()
                        except Exception:
                            pass

                    st.session_state["flash_success"] = f"🗑 Item ID #{id_ped_edit} excluído com sucesso!"
                    st.rerun()

    st.markdown("---")

    with st.expander("📥 Importar Pedido via Planilha Excel (.xlsx / .csv)", expanded=False):
        st.markdown("**Colunas reconhecidas:** `Cor do Boné`, `Arte Estampada`, `Cor da Estampa`, `Produto`, `Preço Base`, `Estampa Extra`, `Matriz Bordado`, `Total Item`, `Status`, `Observações` e `Data`.")
        st.caption("O lote informado abaixo será aplicado a todas as linhas importadas. Se a coluna `Lote` também existir no arquivo, ela terá prioridade linha a linha.")

        c_imp1, c_imp2 = st.columns([2, 1])
        with c_imp1:
            lote_importacao = st.text_input(
                "Identificador / Lote do Pedido *",
                value="",
                placeholder="Ex.: Pedido #06.10-2026",
                key="lote_importacao_pedidos"
            )
        with c_imp2:
            st.write("")
            st.write("")
            st.caption("Formato de data aceito: YYYY/MM/DD ou DD/MM/YYYY.")

        modelo_pedido = pd.DataFrame([{
            "Cor do Boné": "Preta",
            "Arte Estampada": "Exemplo",
            "Cor da Estampa": "Off White",
            "Produto": "Básico",
            "Preço Base": 29.00,
            "Estampa Extra": 0.00,
            "Matriz Bordado": 0.00,
            "Total Item": 29.00,
            "Status": "Em Produção",
            "Observações": "Nenhuma",
            "Data": "2026/10/06"
        }])
        st.dataframe(modelo_pedido, use_container_width=True, hide_index=True)

        output_p = io.BytesIO()
        with pd.ExcelWriter(output_p, engine="openpyxl") as writer:
            modelo_pedido.to_excel(writer, index=False, sheet_name="Modelo_Pedidos")
        st.download_button(
            "📥 Baixar Modelo de Importação de Pedidos (.xlsx)",
            data=output_p.getvalue(),
            file_name="Modelo_Importacao_Pedidos_R2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        uploaded_p_file = st.file_uploader(
            "Enviar arquivo de pedidos (.xlsx ou .csv)",
            type=["xlsx", "csv"],
            key="uploader_pedidos_final"
        )

        if uploaded_p_file is not None:
            try:
                if uploaded_p_file.name.lower().endswith(".csv"):
                    df_imp_p = pd.read_csv(uploaded_p_file, dtype=str, sep=None, engine="python")
                else:
                    df_imp_p = pd.read_excel(uploaded_p_file, dtype=str)

                df_imp_p.columns = [str(col).strip() for col in df_imp_p.columns]
                aliases_pedidos = {
                    "Cor do Boné": ["Cor do Boné", "Cor do Bone", "cor_bone", "Cor"],
                    "Arte Estampada": ["Arte Estampada", "frase_arte", "Arte", "Frase"],
                    "Cor da Estampa": ["Cor da Estampa", "cor_linha", "Cor Estampa"],
                    "Produto": ["Produto", "tipo", "Categoria"],
                    "Preço Base": ["Preço Base", "Preco Base", "preco", "Preço", "Valor"],
                    "Estampa Extra": ["Estampa Extra", "estampa_extra", "valor_estampa_extra"],
                    "Matriz Bordado": ["Matriz Bordado", "matriz_bordado", "valor_matriz", "Matriz"],
                    "Total Item": ["Total Item", "total_item", "Total", "Valor Total"],
                    "Status": ["status", "Status"],
                    "Observações": ["Observações", "Observacoes", "observacoes", "Obs"],
                    "Data": ["Data", "data", "Data da Criação", "data_criacao"]
                }

                mapa_colunas_p = {}
                for destino, aliases in aliases_pedidos.items():
                    for alias in aliases:
                        if alias in df_imp_p.columns:
                            mapa_colunas_p[destino] = alias
                            break

                obrigatorias_p = ["Cor do Boné", "Arte Estampada", "Produto", "Preço Base", "Total Item", "Data"]
                faltantes_p = [col for col in obrigatorias_p if col not in mapa_colunas_p]

                if faltantes_p:
                    st.error("Colunas obrigatórias ausentes: " + ", ".join(faltantes_p))
                else:
                    df_preview_p = pd.DataFrame()
                    for destino, origem in mapa_colunas_p.items():
                        df_preview_p[destino] = df_imp_p[origem]
                    if "Cor da Estampa" not in df_preview_p.columns:
                        df_preview_p["Cor da Estampa"] = ""
                    if "Lote" in df_imp_p.columns:
                        df_preview_p["Lote"] = df_imp_p["Lote"]
                    elif "lote_id" in df_imp_p.columns:
                        df_preview_p["Lote"] = df_imp_p["lote_id"]

                    st.markdown("##### 🔍 Pré-visualização dos Pedidos a Importar:")
                    st.dataframe(df_preview_p, use_container_width=True, hide_index=True)

                    if st.button("🚀 Confirmar Importação dos Pedidos", type="primary", use_container_width=True, key="btn_confirmar_importacao_pedidos"):
                        lote_padrao = lote_importacao.strip() or os.path.splitext(uploaded_p_file.name)[0]
                        count_p_imp = 0
                        erros_p_imp = []

                        def get_row_val(r, keys, default=""):
                            for k in keys:
                                if k in r and pd.notna(r[k]):
                                    val = str(r[k]).strip()
                                    if val.lower() not in {"nan", "none", "null", ""}:
                                        return val
                            return default

                        for idx, row in df_imp_p.iterrows():
                            try:
                                cor_bone_imp = get_row_val(row, [mapa_colunas_p.get("Cor do Boné", "Cor do Boné"), "Cor do Boné", "cor_bone", "Cor"])
                                arte_imp = get_row_val(row, [mapa_colunas_p.get("Arte Estampada", "Arte Estampada"), "Arte Estampada", "frase_arte", "Arte"])
                                cor_estampa_imp = get_row_val(row, [mapa_colunas_p.get("Cor da Estampa", "Cor da Estampa"), "Cor da Estampa", "cor_linha"], "")
                                produto_imp = get_row_val(row, [mapa_colunas_p.get("Produto", "Produto"), "Produto", "tipo"], "Básico")
                                
                                preco_imp = parse_money(row.get(mapa_colunas_p.get("Preço Base", "Preço Base"), row.get("Preço Base", 29.0)))
                                estampa_extra_imp = parse_money(row.get(mapa_colunas_p.get("Estampa Extra", "Estampa Extra"), row.get("Estampa Extra", 0.0)))
                                matriz_bordado_imp = parse_money(row.get(mapa_colunas_p.get("Matriz Bordado", "Matriz Bordado"), row.get("Matriz Bordado", 0.0)))
                                total_calc_imp = preco_imp + estampa_extra_imp + matriz_bordado_imp
                                total_imp = parse_money(row.get(mapa_colunas_p.get("Total Item", "Total Item"), row.get("Total Item", total_calc_imp)))
                                if total_imp <= 0:
                                    total_imp = total_calc_imp

                                status_imp = get_row_val(row, [mapa_colunas_p.get("Status", "Status"), "Status", "status"], "Em Produção")
                                obs_imp = get_row_val(row, [mapa_colunas_p.get("Observações", "Observações"), "Observações", "Observacoes", "observacoes"], "")
                                data_raw = get_row_val(row, [mapa_colunas_p.get("Data", "Data"), "Data", "data", "Data da Criação"], datetime.date.today().strftime("%Y/%m/%d"))
                                data_imp = parse_date_str(data_raw)

                                if not cor_bone_imp or not arte_imp:
                                    raise ValueError("Cor do Boné e Arte Estampada são obrigatórios")

                                lote_linha = lote_padrao
                                col_lote_origem = "Lote" if "Lote" in df_imp_p.columns else ("lote_id" if "lote_id" in df_imp_p.columns else None)
                                if col_lote_origem:
                                    valor_lote_linha = str(row.get(col_lote_origem, "")).strip()
                                    if valor_lote_linha and valor_lote_linha.lower() not in {"nan", "none", "null"}:
                                        lote_linha = valor_lote_linha

                                payload_imp_p = {
                                    "lote_id": lote_linha,
                                    "data_criacao": data_imp,
                                    "cor_bone": cor_bone_imp,
                                    "frase_arte": arte_imp,
                                    "cor_linha": cor_estampa_imp,
                                    "tipo": produto_imp,
                                    "preco": preco_imp,
                                    "valor_estampa_extra": estampa_extra_imp,
                                    "valor_matriz": matriz_bordado_imp,
                                    "total_item": total_imp,
                                    "observacoes": obs_imp,
                                    "status": status_imp
                                }

                                if safe_insert("pedidos", payload_imp_p):
                                    count_p_imp += 1
                                else:
                                    erros_p_imp.append(f"Linha {idx + 2}: não foi possível salvar")
                            except Exception as exc:
                                erros_p_imp.append(f"Linha {idx + 2}: {exc}")

                        if erros_p_imp:
                            st.warning(f"{count_p_imp} item(ns) importado(s). Algumas linhas não foram salvas.")
                            st.dataframe(pd.DataFrame({"Ocorrências": erros_p_imp}), use_container_width=True, hide_index=True)
                        elif count_p_imp:
                            st.session_state["flash_success"] = f"🎉 {count_p_imp} item(ns) importado(s) com sucesso no lote '{lote_padrao}'!"
                            st.rerun()
                        else:
                            st.warning("Nenhum item válido foi encontrado para importação.")
            except Exception as ex_p:
                st.error(f"Erro ao processar planilha de pedidos: {ex_p}")

    st.markdown("---")

    df_ped = carregar_dataframe("SELECT id, lote_id, data_criacao, cor_bone, frase_arte, cor_linha, tipo, preco, valor_estampa_extra, valor_matriz, total_item, status, observacoes, codigo_produto FROM pedidos ORDER BY id ASC")

    if df_ped.empty:
        st.info("Nenhum pedido cadastrado no momento.")
    else:
        df_ped['lote_id'] = df_ped['lote_id'].fillna('Sem Lote Definido')
        df_ped['total_item_calc'] = df_ped['preco'] + df_ped['valor_estampa_extra'].fillna(0) + df_ped['valor_matriz'].fillna(0)
        df_ped['total_item'] = pd.to_numeric(df_ped['total_item'], errors='coerce')
        df_ped['total_item'] = df_ped['total_item'].where(df_ped['total_item'].notna(), df_ped['total_item_calc'])
        df_ped["Mes_Ano"] = pd.to_datetime(df_ped["data_criacao"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")

        meses_pedidos = sorted(df_ped["Mes_Ano"].unique(), reverse=True)
        for mes in meses_pedidos:
            df_ped_mes = df_ped[df_ped["Mes_Ano"] == mes]
            st.markdown(f"#### 📅 Mês: {mes}")
            
            lotes_unicos = df_ped_mes['lote_id'].unique()

            for lote in lotes_unicos:
                df_lote = df_ped_mes[df_ped_mes['lote_id'] == lote].copy()
                total_qtd = len(df_lote)
                total_valor = df_lote['total_item'].sum()
                
                data_lote_raw = df_lote['data_criacao'].iloc[0] if not df_lote.empty else ""
                data_lote_fmt = format_data_br(data_lote_raw)
                
                titulo_expander = f"📅 Data: {data_lote_fmt} | 📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})" if data_lote_fmt else f"📦 Pedido: {lote} — ({total_qtd} bonés | Total: R$ {total_valor:.2f})"

                with st.expander(titulo_expander, expanded=False):
                    df_lote["Preço Base"] = df_lote["preco"].apply(lambda x: f"R$ {x:.2f}")
                    df_lote["Total Item"] = df_lote["total_item"].apply(lambda x: f"R$ {x:.2f}")
                    
                    cols_lote = ["cor_bone", "frase_arte"]
                    if df_lote["cor_linha"].dropna().astype(str).str.strip().ne("").any():
                        cols_lote.append("cor_linha")
                    cols_lote.append("tipo")
                    cols_lote.append("Preço Base")
                    
                    if (df_lote["valor_estampa_extra"] > 0).any():
                        df_lote["Estampa Extra"] = df_lote["valor_estampa_extra"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                        cols_lote.append("Estampa Extra")
                    if (df_lote["valor_matriz"] > 0).any():
                        df_lote["Matriz Bordado"] = df_lote["valor_matriz"].apply(lambda x: f"R$ {x:.2f}" if x > 0 else "-")
                        cols_lote.append("Matriz Bordado")
                        
                    cols_lote.append("Total Item")
                    
                    if df_lote["observacoes"].dropna().astype(str).str.strip().ne("").any():
                        cols_lote.append("observacoes")

                    df_exibicao_lote = df_lote[cols_lote].rename(columns={
                        "cor_bone": "Cor do Boné",
                        "frase_arte": "Arte Estampada",
                        "cor_linha": "Cor da Estampa",
                        "tipo": "Produto",
                        "observacoes": "Observações"
                    })
                    
                    st.dataframe(df_exibicao_lote, use_container_width=True, hide_index=True)

                    st.markdown("##### 🚚 Ações do Pedido (Entregas e Acompanhamento)")
                    
                    col_e1, col_e2, col_e3, col_e4 = st.columns([3, 2, 1.5, 1.5])
                    with col_e1:
                        dict_itens_ped = {row["id"]: f"ID #{row['id']} | {row['cor_bone']} - {row['frase_arte']} (Status: {row['status']})" for _, row in df_lote.iterrows()}
                        ids_itens_acao = st.multiselect(
                            "Selecione um ou mais itens para alterar o status:", 
                            options=list(dict_itens_ped.keys()), 
                            format_func=lambda x: dict_itens_ped[x], 
                            key=f"msel_entregue_{lote}_{mes}"
                        )

                    with col_e2:
                        dt_entrega_manual = st.text_input(
                            "Data da Entrega / Aquisição (opcional)",
                            value="",
                            placeholder="YYYY/MM/DD",
                            key=f"dt_entrega_{lote}_{mes}",
                            help="Se ficar em branco, será usada automaticamente a data atual no formato YYYY/MM/DD."
                        )
                    
                    with col_e3:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("🚚 Entregue", key=f"btn_entregue_{lote}_{mes}", use_container_width=True, type="primary"):
                            if not ids_itens_acao:
                                st.warning("Selecione ao menos um item!")
                            else:
                                codigo_base_atual = get_ultimo_codigo_config()
                                codigos_gerados = []
                                
                                conn = sqlite3.connect(DB_NAME, timeout=30.0)
                                c = conn.cursor()

                                try:
                                    for item_id in ids_itens_acao:
                                        row_alvo = df_lote[df_lote["id"] == item_id].iloc[0]
                                        codigo_base_atual = gerar_proximo_codigo(codigo_base_atual)
                                        codigos_gerados.append(codigo_base_atual)

                                        dt_aquisicao_item = parse_date_str(dt_entrega_manual) if str(dt_entrega_manual).strip() else datetime.date.today().strftime("%Y/%m/%d")

                                        novo_prod = {
                                            "codigo": codigo_base_atual,
                                            "cor": str(row_alvo.get("cor_bone", "")).strip(),
                                            "frase": str(row_alvo.get("frase_arte", "")).strip(),
                                            "cor_estampa": str(row_alvo.get("cor_linha", "")).strip(),
                                            "categoria": str(row_alvo.get("tipo", "Básico")).strip(),
                                            "custo": float(row_alvo.get("preco", 29.0)),
                                            "estampa_extra": float(row_alvo.get("valor_estampa_extra", 0.0)),
                                            "matriz_bordado": float(row_alvo.get("valor_matriz", 0.0)),
                                            "qtd_estoque": 1,
                                            "qtd_comprada": 1,
                                            "data_aquisicao": dt_aquisicao_item
                                        }

                                        # Inserção segura via REPLACE para evitar conflitos de UNIQUE constraint no codigo
                                        sqlite_insert_record("produtos", novo_prod, replace=True)
                                        if supabase:
                                            try:
                                                supabase.table("produtos").upsert(novo_prod, on_conflict="codigo").execute()
                                            except Exception:
                                                pass

                                        c.execute("UPDATE pedidos SET status = 'Entregue / Retirado', codigo_produto = ? WHERE id = ?", (codigo_base_atual, item_id))
                                        if supabase:
                                            try:
                                                supabase.table("pedidos").update({"status": "Entregue / Retirado", "codigo_produto": codigo_base_atual}).eq("id", item_id).execute()
                                            except Exception:
                                                pass

                                    conn.commit()
                                except Exception as err_lote:
                                    st.error(f"Erro ao processar lote: {err_lote}")
                                finally:
                                    conn.close()
                                
                                set_ultimo_codigo_config(codigo_base_atual)

                                st.session_state["flash_success"] = f"🎉 {len(codigos_gerados)} item(ns) entregue(s) com sucesso em {dt_aquisicao_item} e cadastrado(s) no estoque (Códigos: {', '.join(codigos_gerados)})!"
                                st.rerun()

                    with col_e4:
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("❌ Cancelar", key=f"btn_cancelar_{lote}_{mes}", use_container_width=True, type="secondary"):
                            if not ids_itens_acao:
                                st.warning("Selecione ao menos um item!")
                            else:
                                conn = sqlite3.connect(DB_NAME, timeout=30.0)
                                c = conn.cursor()
                                try:
                                    for item_id in ids_itens_acao:
                                        row_alvo = df_lote[df_lote["id"] == item_id].iloc[0]
                                        cod_prod = row_alvo.get("codigo_produto")
                                        if cod_prod and str(cod_prod).strip() != "" and str(cod_prod).strip().lower() != "none":
                                            estornar_estoque(cod_prod, 1)

                                        c.execute("DELETE FROM pedidos WHERE id = ?", (item_id,))
                                        if supabase:
                                            try:
                                                supabase.table("pedidos").delete().eq("id", item_id).execute()
                                            except Exception:
                                                pass
                                    conn.commit()
                                except Exception as exc_del:
                                    st.error(f"Erro ao cancelar itens: {exc_del}")
                                finally:
                                    conn.close()

                                st.session_state["flash_success"] = f"🗑 {len(ids_itens_acao)} item(ns) cancelado(s) e excluído(s) com sucesso!"
                                st.rerun()

elif "Estoque" in menu:
    st.subheader("📦 Estoque Atual")
    
    df_cm = get_df_compra_mercadorias()
    
    if not df_cm.empty:
        df_est = df_cm.copy()
        
        if not df_produtos.empty and "codigo" in df_produtos.columns:
            col_qtd_p = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
            df_est = df_est.merge(df_produtos[["codigo", col_qtd_p]], left_on="Código", right_on="codigo", how="left")
            df_est["Estoque"] = pd.to_numeric(df_est[col_qtd_p], errors="coerce").fillna(1).astype(int)
        else:
            df_est["Estoque"] = 1
            
        df_est = df_est[df_est["Estoque"] > 0].copy()
        df_est["custo_total_num"] = df_est["total_item_calc"]

        qtd_total_estoque = int(df_est["Estoque"].sum())
        st.markdown(f"#### 📊 **Quantidade Total em Estoque:** `{qtd_total_estoque} un`")

        with st.expander("🔻 Registrar Baixa no Estoque (Perda / Avaria / Brinde)", expanded=False):
            with st.form("form_baixa_estoque"):
                cb_c1, cb_c2, cb_c3 = st.columns(3)
                with cb_c1:
                    cods_disponiveis = df_est[df_est["Estoque"] > 0]["Código"].tolist()
                    cod_baixa = st.selectbox("Selecione a Mercadoria *", cods_disponiveis if cods_disponiveis else ["Sem itens"])
                with cb_c2:
                    motivo_baixa = st.selectbox("Motivo da Baixa *", ["Perda", "Avaria", "Brinde", "Outro"])
                    dt_baixa = st.date_input("Data da Baixa *", datetime.date.today(), format="YYYY/MM/DD")
                with cb_c3:
                    obs_baixa = st.text_input("Observação / Justificativa")
                
                btn_confirmar_baixa = st.form_submit_button("🔻 Confirmar Baixa no Estoque", type="primary", use_container_width=True)
                if btn_confirmar_baixa:
                    if cod_baixa != "Sem itens":
                        payload_baixa = {
                            "codigo": cod_baixa,
                            "motivo": motivo_baixa,
                            "observacao": obs_baixa.strip(),
                            "data_baixa": parse_date_str(dt_baixa)
                        }
                        safe_insert("baixas_estoque", payload_baixa)
                        dar_baixa_estoque_venda(cod_baixa, 1)
                        st.session_state["flash_success"] = f"🔻 Baixa do item '{cod_baixa}' por '{motivo_baixa}' realizada com sucesso!"
                        st.rerun()

        with st.expander("🔍 Consultar e Pesquisar no Estoque", expanded=True):
            c_f1, c_f2, c_f3 = st.columns(3)
            with c_f1:
                busca_texto = st.text_input("Pesquisar por Código ou Arte:")
            with c_f2:
                cat_unicas = ["Todas"] + sorted(list(df_est["Produto"].dropna().unique()))
                filtro_cat = st.selectbox("Filtrar por Produto/Categoria:", cat_unicas)
            with c_f3:
                cor_unicas = ["Todas"] + sorted(list(df_est["Cor do Boné"].dropna().unique()))
                filtro_cor = st.selectbox("Filtrar por Cor do Boné:", cor_unicas)

            df_est_filtrado = df_est.copy()
            if busca_texto:
                df_est_filtrado = df_est_filtrado[
                    df_est_filtrado["Código"].astype(str).str.contains(busca_texto, case=False, na=False) |
                    df_est_filtrado["Arte Estampada"].astype(str).str.contains(busca_texto, case=False, na=False)
                ]
            if filtro_cat != "Todas":
                df_est_filtrado = df_est_filtrado[df_est_filtrado["Produto"] == filtro_cat]
            if filtro_cor != "Todas":
                df_est_filtrado = df_est_filtrado[df_est_filtrado["Cor do Boné"] == filtro_cor]

        df_est_filtrado["Custo Base"] = df_est_filtrado["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Estampa Extra"] = df_est_filtrado["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Matriz Bordado"] = df_est_filtrado["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}")
        df_est_filtrado["Custo Total"] = df_est_filtrado["custo_total_num"].apply(lambda v: f"R$ {float(v):,.2f}")

        cols_est = [
            "Código", "Cor do Boné", "Arte Estampada", "Cor da Estampa", 
            "Produto", "Estoque", "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Total"
        ]

        st.dataframe(df_est_filtrado[cols_est], use_container_width=True, hide_index=True)
    else:
        st.info("Estoque vazio no momento.")

elif "Vendas" in menu:
    st.subheader("🛒 Lançar Nova Venda")
    
    df_cm_estoque = get_df_compra_mercadorias()
    map_estoque_disponivel = {}
    
    if not df_cm_estoque.empty:
        df_cm_estoque = df_cm_estoque[~df_cm_estoque["Código"].isin(CODIGOS_REMOVER)]
        
        if not df_produtos.empty and "codigo" in df_produtos.columns:
            col_q = "qtd_estoque" if "qtd_estoque" in df_produtos.columns else ("qtd" if "qtd" in df_produtos.columns else "estoque")
            df_cm_estoque = df_cm_estoque.merge(df_produtos[["codigo", col_q]], left_on="Código", right_on="codigo", how="left")
            df_cm_estoque["qtd_disp"] = pd.to_numeric(df_cm_estoque[col_q], errors="coerce").fillna(1).astype(int)
        else:
            df_cm_estoque["qtd_disp"] = 0

        df_cm_estoque["qtd_disp"] = pd.to_numeric(
            df_cm_estoque["qtd_disp"], errors="coerce"
        ).fillna(0).astype(int)
        df_cm_disponivel = df_cm_estoque[df_cm_estoque["qtd_disp"] > 0].copy()
        
        opts = []
        for _, r in df_cm_disponivel.iterrows():
            cod_item = r['Código']
            q_disp = int(r['qtd_disp'])
            map_estoque_disponivel[cod_item] = q_disp
            opts.append(f"[{cod_item}] \"{r.get('Arte Estampada','')}\" - Cor: {r.get('Cor do Boné','')} (Disponível: {q_disp} un)")
    else:
        df_cm_disponivel = pd.DataFrame()
        opts = []

    if not opts:
        st.warning("⚠ Nenhum boné disponível em estoque para venda no momento.")
        prod_sel = None
        codigo_sel = ""
    else:
        prod_sel = st.selectbox(
            "🔍 Selecione/Pesquise o Boné no Estoque:",
            opts,
            index=0,
            help="Mostra apenas itens com estoque disponível."
        )
        codigo_sel = prod_sel.split("]")[0].replace("[", "").strip() if prod_sel else ""

    max_qtd_permitida = map_estoque_disponivel.get(codigo_sel, 1) if codigo_sel else 1

    c1, c2, c3 = st.columns(3)
    with c1:
        qtd_venda = st.number_input(
            "Quantidade *", 
            min_value=1, 
            max_value=max_qtd_permitida, 
            value=1, 
            step=1,
            help=f"Estoque limite atual: {max_qtd_permitida} un"
        )
        cliente = st.text_input("Nome do Cliente *")
    with c2:
        valor_venda = st.number_input("Valor de Venda Bruto (R$) *", min_value=0.0, value=0.0, step=5.0, format="%.2f")
        tarifa_venda = st.number_input("Tarifa / Taxa Bancária (R$)", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    with c3:
        forma_pagto = st.selectbox("Forma Pagto *", ["PIX", "Cartão", "Dinheiro", "Brinde"])
        st.write("")
        st.caption("ℹ️ A data da venda é preenchida automaticamente com a data atual (YYYY/MM/DD).")

    valor_liquido_calc = max(0.0, float(valor_venda) - float(tarifa_venda))
    st.markdown(f"👉 **Valor Bruto:** `R$ {float(valor_venda):,.2f}` | 🏷 **Tarifa:** `R$ {float(tarifa_venda):,.2f}` | 💵 **Valor Líquido:** `R$ {valor_liquido_calc:,.2f}`")

    if st.button("🚀 Finalizar Venda Individual", type="primary", use_container_width=True):
        if not cliente.strip():
            st.error("Informe o nome do cliente!")
        elif not codigo_sel.strip():
            st.error("Selecione um produto com estoque válido!")
        else:
            custo_total_cm = 0.0
            if not df_cm_estoque.empty and codigo_sel in df_cm_estoque["Código"].values:
                p_info = df_cm_estoque[df_cm_estoque["Código"] == codigo_sel].iloc[0]
                custo_total_cm = float(p_info.get("total_item_calc", 0.0))
            
            data_atual_str = datetime.date.today().strftime("%Y/%m/%d")
            val_bruto_fmt = round(float(valor_venda), 2)
            tarifa_fmt = round(float(tarifa_venda), 2)
            val_liquido_fmt = round(valor_liquido_calc, 2)

            payload_venda = {
                "codigo_bone": codigo_sel.strip(),
                "codigo": codigo_sel.strip(),
                "cliente": cliente.strip(),
                "qtd": int(qtd_venda),
                "valor_venda": val_bruto_fmt,
                "tarifa": tarifa_fmt,
                "tarifa_bancaria": tarifa_fmt,
                "tarifa_cartao": tarifa_fmt,
                "valor_recebido": val_liquido_fmt,
                "forma_pagto": forma_pagto,
                "data": data_atual_str,
                "data_venda": data_atual_str,
                "data_recebimento": None,
                "custo": custo_total_cm,
                "custo_unitario": custo_total_cm
            }

            if safe_insert("vendas", payload_venda):
                dar_baixa_estoque_venda(codigo_sel.strip(), int(qtd_venda))
                st.session_state["flash_success"] = f"🎉 Venda salva e encaminhada para 'Contas a Receber'! Líquido estimado: R$ {val_liquido_fmt:,.2f}"
                st.rerun()

    st.markdown("---")
    with st.expander("📥 Importar Vendas via Planilha (.xlsx / .csv)", expanded=False):
        st.markdown("##### 📌 Modelo de Planilha de Vendas:")
        df_modelo_vendas = pd.DataFrame([{
            "Código": "BL-0005",
            "Quantidade": 1,
            "Valor Bruto": 80.00,
            "Tarifa": 3.50,
            "Nome do Cliente": "João Silva",
            "Forma de Pagto": "Cartão"
        }])
        st.dataframe(df_modelo_vendas, use_container_width=True, hide_index=True)
        
        output_v = io.BytesIO()
        with pd.ExcelWriter(output_v, engine='openpyxl') as writer:
            df_modelo_vendas.to_excel(writer, index=False, sheet_name="Modelo_Vendas")
        
        st.download_button(
            "📥 Baixar Modelo de Planilha de Vendas (.xlsx)",
            data=output_v.getvalue(),
            file_name="Modelo_Importacao_Vendas_R2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        uploaded_v_file = st.file_uploader("Enviar arquivo de vendas (.xlsx ou .csv)", type=["xlsx", "csv"], key="uploader_vendas_final")
        if uploaded_v_file is not None:
            try:
                df_imp_v = pd.read_csv(uploaded_v_file, dtype=str) if uploaded_v_file.name.endswith(".csv") else pd.read_excel(uploaded_v_file, dtype=str)
                st.markdown("##### 🔍 Pré-visualização das Vendas a Importar:")
                st.dataframe(df_imp_v, use_container_width=True)
                
                if st.button("🚀 Confirmar Importação de Vendas", type="primary", use_container_width=True):
                    count_v_imp = 0
                    data_atual_str = datetime.date.today().strftime("%Y/%m/%d")
                    for _, row in df_imp_v.iterrows():
                        cod_v = str(row.get('Código', row.get('codigo', ''))).strip()
                        qtd_v = int(pd.to_numeric(row.get('Quantidade', row.get('qtd', 1)), errors='coerce') or 1)
                        val_v = parse_money(row.get('Valor Bruto', row.get('valor_venda', row.get('valor', 0.0))))
                        tarifa_v = parse_money(row.get('Tarifa', row.get('tarifa', row.get('tarifa_bancaria', row.get('tarifa_cartao', 0.0)))))
                        val_liq_v = max(0.0, val_v - tarifa_v)
                        
                        cli_v = str(row.get('Nome do Cliente', row.get('cliente', ''))).strip()
                        pag_v = str(row.get('Forma de Pagto', row.get('forma_pagto', 'PIX'))).strip()
                        
                        payload_imp_v = {
                            "codigo_bone": cod_v,
                            "codigo": cod_v,
                            "cliente": cli_v,
                            "qtd": qtd_v,
                            "valor_venda": val_v,
                            "tarifa": tarifa_v,
                            "tarifa_bancaria": tarifa_v,
                            "tarifa_cartao": tarifa_v,
                            "valor_recebido": val_liq_v,
                            "forma_pagto": pag_v,
                            "data": data_atual_str,
                            "data_venda": data_atual_str,
                            "data_recebimento": None,
                            "custo": val_v,
                            "custo_unitario": val_v
                        }

                        safe_insert("vendas", payload_imp_v)
                        dar_baixa_estoque_venda(cod_v, qtd_v)
                        count_v_imp += 1

                    st.session_state["flash_success"] = f"🎉 {count_v_imp} vendas importadas para Contas a Receber com sucesso!"
                    st.rerun()
            except Exception as ex_v:
                st.error(f"Erro ao processar planilha de vendas: {ex_v}")

    st.markdown("---")
    st.subheader("📋 Histórico Detalhado de Vendas")
    st.caption("As vendas são agrupadas por mês. Exibe a coluna dinâmica com Valor Bruto, Tarifa e Líquido Recebido. Use ✏️ para editar ou 🗑 para cancelar.")

    df_historico_vendas = fetch_data("vendas")

    if not df_historico_vendas.empty:
        df_historico_vendas = normalizar_df_vendas(df_historico_vendas)
        col_data_hist = "data_venda" if "data_venda" in df_historico_vendas.columns else ("data" if "data" in df_historico_vendas.columns else None)
        col_codigo_hist = "codigo_bone" if "codigo_bone" in df_historico_vendas.columns else ("codigo" if "codigo" in df_historico_vendas.columns else "codigo_produto")
        if col_data_hist:
            df_historico_vendas["_data_hist"] = df_historico_vendas[col_data_hist].apply(parse_date_str)
            df_historico_vendas["_mes_hist"] = pd.to_datetime(df_historico_vendas["_data_hist"], format="%Y/%m/%d", errors="coerce").dt.strftime("%Y-%m")
        else:
            df_historico_vendas["_data_hist"] = datetime.date.today().strftime("%Y/%m/%d")
            df_historico_vendas["_mes_hist"] = datetime.date.today().strftime("%Y-%m")

        with st.expander("🛠 Seleção e Exclusão em Lote de Vendas", expanded=False):
            ids_vendas_disp = df_historico_vendas["id"].tolist()
            vendas_selecionadas_lote = st.multiselect(
                "Selecione as vendas para exclusão em lote:",
                options=ids_vendas_disp,
                format_func=lambda x: f"Venda ID #{x} - Cliente: {df_historico_vendas[df_historico_vendas['id'] == x]['cliente'].values[0] if not df_historico_vendas[df_historico_vendas['id'] == x].empty else ''}"
            )
            if st.button("🗑 Excluir Vendas Selecionadas em Lote", type="primary"):
                if not vendas_selecionadas_lote:
                    st.warning("Nenhuma venda selecionada.")
                else:
                    count_del = 0
                    for v_id_del in vendas_selecionadas_lote:
                        row_del = df_historico_vendas[df_historico_vendas["id"] == v_id_del]
                        if not row_del.empty:
                            r_d_dict = row_del.iloc[0].to_dict()
                            cod_est = str(r_d_dict.get(col_codigo_hist, ""))
                            qtd_est = int(pd.to_numeric(r_d_dict.get("qtd", 1), errors="coerce") or 1)
                            estornar_estoque(cod_est, qtd_est)
                            if safe_delete_venda(v_id_del):
                                atualizar_caixa_da_venda(r_d_dict, excluir=True)
                                count_del += 1
                    st.session_state["flash_success"] = f"🗑 {count_del} venda(s) excluída(s) em lote com sucesso e itens estornados ao estoque!"
                    st.rerun()

        meses_hist = [m for m in sorted(df_historico_vendas["_mes_hist"].dropna().unique().tolist(), reverse=True)]
        if not meses_hist:
            meses_hist = [datetime.date.today().strftime("%Y-%m")]

        id_edicao = st.session_state.get("editar_venda_id")
        if id_edicao is not None:
            linha_edicao = df_historico_vendas[df_historico_vendas["id"].astype(str) == str(id_edicao)]
            if not linha_edicao.empty:
                venda_edit = linha_edicao.iloc[0].to_dict()
                st.markdown("### ✏️ Editar Venda")
                with st.container(border=True):
                    c_ed1, c_ed2, c_ed3, c_ed4 = st.columns(4)
                    cliente_atual = str(venda_edit.get("cliente", "") or "")
                    bruto_atual = parse_money(venda_edit.get("valor_venda", venda_edit.get("valor", 0.0)))
                    
                    tarifa_atual = 0.0
                    for t_c in ["tarifa", "tarifa_bancaria", "tarifa_cartao"]:
                        if t_c in venda_edit and pd.notna(venda_edit[t_c]):
                            val_t_cand = parse_money(venda_edit[t_c])
                            if val_t_cand > 0:
                                tarifa_atual = val_t_cand
                                break

                    forma_atual = str(venda_edit.get("forma_pagto", "PIX") or "PIX")
                    formas_pagto = ["PIX", "Cartão", "Dinheiro", "Brinde"]
                    if forma_atual and forma_atual not in formas_pagto:
                        formas_pagto.append(forma_atual)

                    with c_ed1:
                        cliente_editado = st.text_input("Cliente *", value=cliente_atual, key=f"cliente_edit_{id_edicao}")
                    with c_ed2:
                        bruto_editado = st.number_input("Valor Bruto (R$) *", min_value=0.0, value=float(bruto_atual), step=5.0, format="%.2f", key=f"bruto_edit_{id_edicao}")
                    with c_ed3:
                        tarifa_editada = st.number_input("Tarifa / Taxa (R$)", min_value=0.0, value=float(tarifa_atual), step=1.0, format="%.2f", key=f"tarifa_edit_{id_edicao}")
                    with c_ed4:
                        forma_editada = st.selectbox("Forma de Pagamento *", formas_pagto, index=formas_pagto.index(forma_atual), key=f"forma_edit_{id_edicao}")

                    liq_editado_calc = max(0.0, float(bruto_editado) - float(tarifa_editada))
                    st.write(f"💵 **Líquido recalculado:** `R$ {liq_editado_calc:,.2f}`")

                    ce1, ce2, ce3 = st.columns([1, 1, 3])
                    with ce1:
                        salvar_edicao = st.button("💾 Salvar Alterações", type="primary", use_container_width=True, key=f"salvar_edicao_{id_edicao}")
                    with ce2:
                        cancelar_edicao = st.button("↩ Cancelar", use_container_width=True, key=f"cancelar_edicao_{id_edicao}")

                    if cancelar_edicao:
                        st.session_state.pop("editar_venda_id", None)
                        st.rerun()

                    if salvar_edicao:
                        if not cliente_editado.strip():
                            st.error("Informe o nome do cliente.")
                        else:
                            payload_edicao = {
                                "cliente": cliente_editado.strip(),
                                "valor_venda": round(float(bruto_editado), 2),
                                "tarifa": round(float(tarifa_editada), 2),
                                "tarifa_bancaria": round(float(tarifa_editada), 2),
                                "tarifa_cartao": round(float(tarifa_editada), 2),
                                "valor_recebido": round(liq_editado_calc, 2),
                                "forma_pagto": forma_editada
                            }
                            if safe_update_venda(id_edicao, payload_edicao):
                                venda_nova_caixa = venda_edit.copy()
                                venda_nova_caixa.update(payload_edicao)
                                atualizar_caixa_da_venda(venda_edit, venda_nova_caixa, excluir=False)
                                st.session_state.pop("editar_venda_id", None)
                                st.session_state["flash_success"] = f"✏️ Venda #{id_edicao} atualizada com sucesso!"
                                st.rerun()
            else:
                st.session_state.pop("editar_venda_id", None)

        for mes_hist in meses_hist:
            df_mes_hist = df_historico_vendas[df_historico_vendas["_mes_hist"] == mes_hist].copy()
            if df_mes_hist.empty:
                continue
            st.markdown(f"#### 📅 Mês: {mes_hist.replace('-', '/')}")
            df_mes_hist = df_mes_hist.sort_values(by="_data_hist", ascending=False)

            h1, h2, h3, h4, h5, h6, h7, h8 = st.columns([1.1, 0.9, 1.6, 0.6, 4.2, 0.8, 0.5, 0.5], vertical_alignment="center")
            with h1: st.markdown("**Data**")
            with h2: st.markdown("**Código**")
            with h3: st.markdown("**Cliente**")
            with h4: st.markdown("**Qtd**")
            with h5: st.markdown("**Resumo Financeiro**")
            with h6: st.markdown("**Pagto**")
            with h7: st.markdown("**Edit**")
            with h8: st.markdown("**Del**")
            st.divider()

            for _, venda_row in df_mes_hist.iterrows():
                venda_id = venda_row.get("id")
                codigo = str(venda_row.get(col_codigo_hist, "") or "").strip()
                cliente = str(venda_row.get("cliente", "") or "").strip()
                qtd = int(pd.to_numeric(venda_row.get("qtd", 1), errors="coerce") or 1)
                valor_bruto = parse_money(venda_row.get("valor_venda", venda_row.get("valor", 0.0)))
                
                tarifa_val = float(venda_row.get("tarifa_calc", 0.0))
                valor_liquido = max(0.0, valor_bruto - tarifa_val)
                forma = str(venda_row.get("forma_pagto", "") or "")
                data_hist = str(venda_row.get("_data_hist", ""))

                resumo_financeiro_str = f"👉 Valor Bruto: R$ {valor_bruto:,.2f} | 🏷 Tarifa: R$ {tarifa_val:,.2f} | 💵 Valor Líquido: R$ {valor_liquido:,.2f}"

                r1, r2, r3, r4, r5, r6, r7, r8 = st.columns([1.1, 0.9, 1.6, 0.6, 4.2, 0.8, 0.5, 0.5], vertical_alignment="center")
                with r1:
                    st.write(f"**{data_hist}**")
                with r2:
                    st.write(f"`{codigo}`")
                with r3:
                    st.write(f"{cliente or 'Sem cliente'}")
                with r4:
                    st.write(f"{qtd}un")
                with r5:
                    st.markdown(resumo_financeiro_str)
                with r6:
                    st.write(f"{forma or '-'}")
                with r7:
                    if st.button("✏️", key=f"editar_venda_{venda_id}", help="Editar venda"):
                        st.session_state["editar_venda_id"] = venda_id
                        st.rerun()
                with r8:
                    if st.button("🗑", key=f"excluir_venda_{venda_id}", help="Excluir / Cancelar venda"):
                        qtd_estorno = max(1, qtd)
                        if estornar_estoque(codigo, qtd_estorno):
                            if safe_delete_venda(venda_id):
                                atualizar_caixa_da_venda(venda_row.to_dict(), excluir=True)
                                st.session_state["flash_success"] = f"🗑 Venda #{venda_id} cancelada com sucesso. {qtd_estorno} un devolvida(s) ao estoque."
                                st.rerun()
                        else:
                            st.error("Não foi possível estornar a quantidade para o estoque. A venda não foi excluída.")
                st.divider()
    else:
        st.info("Nenhuma venda registrada até o momento.")

elif "Contas a Receber" in menu:
    st.subheader("💰 Contas a Receber")
    st.markdown("Gerencie as vendas realizadas que aguardam confirmação de recebimento. Ao confirmar o recebimento, o valor líquido correspondente será lançado automaticamente no Fluxo de Caixa.")

    df_cr = fetch_data("vendas")

    with st.expander("📥 Importar Contas a Receber via Planilha (.xlsx / .csv)", expanded=False):
        st.markdown("**Colunas reconhecidas:** `Código do Boné`, `Nome do Cliente`, `Quantidade`, `Valor Bruto`, `Tarifa`, `Data da Venda`, `Data de Vencimento`, `Forma de Pagto`.")
        st.caption("Permite importar novas contas a receber em lote validando os campos e salvando automaticamente.")

        modelo_cr = pd.DataFrame([{
            "Código do Boné": "BL-0001",
            "Nome do Cliente": "Maria Oliveira",
            "Quantidade": 1,
            "Valor Bruto": 90.00,
            "Tarifa": 3.00,
            "Data da Venda": "2026/10/01",
            "Data de Vencimento": "2026/10/10",
            "Forma de Pagto": "Cartão"
        }])
        st.dataframe(modelo_cr, use_container_width=True, hide_index=True)

        output_cr_mod = io.BytesIO()
        with pd.ExcelWriter(output_cr_mod, engine="openpyxl") as writer:
            modelo_cr.to_excel(writer, index=False, sheet_name="Modelo_Contas_Receber")
        st.download_button(
            "📥 Baixar Modelo de Planilha de Contas a Receber (.xlsx)",
            data=output_cr_mod.getvalue(),
            file_name="Modelo_Importacao_Contas_a_Receber_R2.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

        uploaded_cr_file = st.file_uploader(
            "Enviar arquivo de contas a receber (.xlsx ou .csv)",
            type=["xlsx", "csv"],
            key="uploader_contas_receber_final"
        )

        if uploaded_cr_file is not None:
            try:
                if uploaded_cr_file.name.lower().endswith(".csv"):
                    df_imp_cr = pd.read_csv(uploaded_cr_file, dtype=str, sep=None, engine="python")
                else:
                    df_imp_cr = pd.read_excel(uploaded_cr_file, dtype=str)

                df_imp_cr.columns = [str(col).strip() for col in df_imp_cr.columns]
                
                aliases_cr = {
                    "Código do Boné": ["Código do Boné", "Codigo do Bone", "Código", "codigo", "codigo_bone"],
                    "Nome do Cliente": ["Nome do Cliente", "Cliente", "cliente", "Nome"],
                    "Quantidade": ["Quantidade", "qtd", "Qtd"],
                    "Valor Bruto": ["Valor Bruto", "valor_venda", "valor", "Valor"],
                    "Tarifa": ["Tarifa", "tarifa", "tarifa_bancaria", "tarifa_cartao"],
                    "Data da Venda": ["Data da Venda", "data_venda", "data", "Data"],
                    "Data de Vencimento": ["Data de Vencimento", "data_vencimento", "vencimento"],
                    "Forma de Pagto": ["Forma de Pagto", "forma_pagto", "Forma de Pagamento", "Pagamento"]
                }

                mapa_colunas_cr = {}
                for destino, aliases in aliases_cr.items():
                    for alias in aliases:
                        if alias in df_imp_cr.columns:
                            mapa_colunas_cr[destino] = alias
                            break

                obrigatorias_cr = ["Nome do Cliente", "Valor Bruto"]
                faltantes_cr = [col for col in obrigatorias_cr if col not in mapa_colunas_cr]

                if faltantes_cr:
                    st.error("Colunas obrigatórias ausentes na planilha: " + ", ".join(faltantes_cr))
                else:
                    df_preview_cr = pd.DataFrame()
                    for destino, origem in mapa_colunas_cr.items():
                        df_preview_cr[destino] = df_imp_cr[origem]

                    st.markdown("##### 🔍 Pré-visualização dos Dados de Contas a Receber:")
                    st.dataframe(df_preview_cr, use_container_width=True, hide_index=True)

                    if st.button("🚀 Confirmar Importação de Contas a Receber", type="primary", use_container_width=True, key="btn_confirmar_importacao_cr"):
                        count_cr_imp = 0
                        erros_cr_imp = []

                        def get_cr_val(r, keys, default=""):
                            for k in keys:
                                if k in r and pd.notna(r[k]):
                                    val = str(r[k]).strip()
                                    if val.lower() not in {"nan", "none", "null", ""}:
                                        return val
                            return default

                        for idx, row in df_imp_cr.iterrows():
                            try:
                                cli_cr = get_cr_val(row, [mapa_colunas_cr.get("Nome do Cliente", "Nome do Cliente"), "Nome do Cliente", "cliente", "Cliente"])
                                if not cli_cr:
                                    raise ValueError("Nome do Cliente é obrigatório")

                                cod_cr = get_cr_val(row, [mapa_colunas_cr.get("Código do Boné", "Código do Boné"), "Código do Boné", "codigo", "codigo_bone"], "BL-GERAL")
                                qtd_cr = int(pd.to_numeric(row.get(mapa_colunas_cr.get("Quantidade", "Quantidade"), row.get("Quantidade", 1)), errors="coerce") or 1)
                                bruto_cr = parse_money(row.get(mapa_colunas_cr.get("Valor Bruto", "Valor Bruto"), row.get("Valor Bruto", 0.0)))
                                tarifa_cr = parse_money(row.get(mapa_colunas_cr.get("Tarifa", "Tarifa"), row.get("Tarifa", 0.0)))
                                liquido_cr = max(0.0, bruto_cr - tarifa_cr)

                                data_venda_raw = get_cr_val(row, [mapa_colunas_cr.get("Data da Venda", "Data da Venda"), "Data da Venda", "data", "data_venda"], datetime.date.today().strftime("%Y/%m/%d"))
                                data_venda_str = parse_date_str(data_venda_raw)

                                forma_pagto_cr = get_cr_val(row, [mapa_colunas_cr.get("Forma de Pagto", "Forma de Pagto"), "Forma de Pagto", "forma_pagto"], "PIX")

                                payload_imp_cr = {
                                    "codigo_bone": cod_cr,
                                    "codigo": cod_cr,
                                    "cliente": cli_cr,
                                    "qtd": qtd_cr,
                                    "valor_venda": bruto_cr,
                                    "tarifa": tarifa_cr,
                                    "tarifa_bancaria": tarifa_cr,
                                    "tarifa_cartao": tarifa_cr,
                                    "valor_recebido": liquido_cr,
                                    "forma_pagto": forma_pagto_cr,
                                    "data": data_venda_str,
                                    "data_venda": data_venda_str,
                                    "data_recebimento": None,
                                    "custo": bruto_cr,
                                    "custo_unitario": bruto_cr
                                }

                                if safe_insert("vendas", payload_imp_cr):
                                    count_cr_imp += 1
                                else:
                                    erros_cr_imp.append(f"Linha {idx + 2}: falha ao salvar no banco")
                            except Exception as exc_cr:
                                erros_cr_imp.append(f"Linha {idx + 2}: {exc_cr}")

                        if erros_cr_imp:
                            st.warning(f"{count_cr_imp} registro(s) importado(s). Algumas linhas apresentaram erros.")
                            st.dataframe(pd.DataFrame({"Erros": erros_cr_imp}), use_container_width=True, hide_index=True)
                        elif count_cr_imp:
                            st.session_state["flash_success"] = f"🎉 {count_cr_imp} contas a receber importadas com sucesso!"
                            st.rerun()
                        else:
                            st.warning("Nenhum registro válido encontrado para importação.")
            except Exception as ex_file_cr:
                st.error(f"Erro ao processar arquivo de contas a receber: {ex_file_cr}")

    st.markdown("---")

    if not df_cr.empty:
        df_cr = normalizar_df_vendas(df_cr)
        col_dt_rec_cr = "data_recebimento" if "data_recebimento" in df_cr.columns else None
        
        if col_dt_rec_cr:
            df_pendentes = df_cr[df_cr[col_dt_rec_cr].isna() | df_cr[col_dt_rec_cr].astype(str).str.strip().isin(["", "None", "nan", "NaT"])].copy()
        else:
            df_pendentes = df_cr.copy()

        if not df_pendentes.empty:
            st.markdown(f"#### 📌 Vendas Pendentes de Recebimento ({len(df_pendentes)} itens)")
            
            for _, r in df_pendentes.iterrows():
                v_id = r.get("id")
                v_data = format_data_br(r.get("data_venda") or r.get("data"))
                v_cod = str(r.get("codigo_bone") or r.get("codigo") or "")
                v_cli = str(r.get("cliente") or "")
                v_qtd = int(pd.to_numeric(r.get("qtd", 1), errors="coerce") or 1)
                v_bruto = parse_money(r.get("valor_venda", r.get("valor", 0.0)))
                v_tarifa = float(r.get("tarifa_calc", 0.0))
                v_liq = float(r.get("liquido_recebido_calc", v_bruto - v_tarifa))
                v_pagto = str(r.get("forma_pagto", ""))

                resumo_cr_str = f"👉 Valor Bruto: R$ {v_bruto:,.2f} | 🏷 Tarifa: R$ {v_tarifa:,.2f} | 💵 Valor Líquido: R$ {v_liq:,.2f}"

                with st.container(border=True):
                    rc1, rc2, rc3 = st.columns([3, 4, 2])
                    with rc1:
                        st.markdown(f"**Venda ID #{v_id}** | Data: `{v_data}`")
                        st.write(f"Código: `{v_cod}` | Cliente: **{v_cli}** ({v_qtd}un)")
                        st.write(f"Pagamento: {v_pagto}")
                    with rc2:
                        st.markdown(resumo_cr_str)
                    with rc3:
                        key_input_rec = f"dt_rec_cr_{v_id}"
                        dt_receb_input = st.date_input("Data de Recebimento", datetime.date.today(), format="YYYY/MM/DD", key=key_input_rec)
                        if st.button("✅ Confirmar Recebimento", key=f"btn_rec_cr_{v_id}", use_container_width=True, type="primary"):
                            dt_rec_str = parse_date_str(dt_receb_input)
                            payload_upd = {
                                "data_recebimento": dt_rec_str,
                                "valor_recebido": round(v_liq, 2)
                            }
                            if safe_update_venda(v_id, payload_upd):
                                safe_insert("caixa", {
                                    "data": dt_rec_str,
                                    "desc": f"Venda {v_cod} ({v_qtd}un) - {v_cli}",
                                    "tipo": "Venda",
                                    "valor": round(v_liq, 2)
                                })
                                st.session_state["flash_success"] = f"🎉 Recebimento da Venda ID #{v_id} confirmado com sucesso! R$ {v_liq:,.2f} lançado no Fluxo de Caixa."
                                st.rerun()
        else:
            st.info("🎉 Nenhuma venda pendente de recebimento no momento!")

        st.markdown("---")
        st.markdown("#### ✅ Vendas Já Recebidas")
        if col_dt_rec_cr:
            df_recebidas = df_cr[df_cr[col_dt_rec_cr].notna() & df_cr[col_dt_rec_cr].astype(str).str.strip().ne("") & df_cr[col_dt_rec_cr].astype(str).str.lower().ne("none")].copy()
            if not df_recebidas.empty:
                lista_rec_exib = []
                for _, r in df_recebidas.iterrows():
                    v_bruto_r = parse_money(r.get('valor_venda', 0))
                    v_tarifa_r = float(r.get('tarifa_calc', 0.0))
                    v_liq_r = float(r.get('liquido_recebido_calc', 0))
                    resumo_rec_str = f"👉 Valor Bruto: R$ {v_bruto_r:,.2f} | 🏷 Tarifa: R$ {v_tarifa_r:,.2f} | 💵 Valor Líquido: R$ {v_liq_r:,.2f}"
                    lista_rec_exib.append({
                        "ID": r.get("id"),
                        "Data Venda": format_data_br(r.get("data_venda") or r.get("data")),
                        "Data Recebimento": format_data_br(r.get("data_recebimento")),
                        "Código": str(r.get("codigo_bone") or r.get("codigo") or ""),
                        "Cliente": str(r.get("cliente") or ""),
                        "Resumo Financeiro": resumo_rec_str
                    })
                st.dataframe(pd.DataFrame(lista_rec_exib), use_container_width=True, hide_index=True)
            else:
                st.info("Nenhuma venda recebida registrada ainda.")
    else:
        st.info("Nenhuma venda registrada no sistema.")

elif "Custos" in menu:
    st.subheader("💵 Gerenciamento de Custos e Despesas")
    sub_tab = st.radio("Sub-abas de Custos:", ["📦 Mercadorias", "🏷 Custos / Despesas", "🎪 Feiras"], horizontal=True)

    if "Mercadorias" in sub_tab:
        df_cm = get_df_compra_mercadorias()

        if not df_cm.empty:
            df_m = df_cm.copy()
            df_m["qtd_num"] = 1
            df_m["Mes_Ano"] = pd.to_datetime(df_m["Data_Raw"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")

            meses_custos_m = sorted(df_m["Mes_Ano"].unique(), reverse=True)
            for mes in meses_custos_m:
                df_m_mes = df_m[df_m["Mes_Ano"] == mes]
                total_mes_merc = df_m_mes["total_item_calc"].sum()
                
                with st.expander(f"📅 Mês: {mes.replace('-', '/')} — Custo Total: R$ {total_mes_merc:,.2f}", expanded=False):
                    agrup_data = df_m_mes.groupby("Data").agg({
                        "qtd_num": "sum",
                        "total_item_calc": "sum"
                    }).reset_index().rename(columns={"Data": "Data da Aquisição", "qtd_num": "Quantidade Comprada"})

                    agrup_data["Custo Total"] = agrup_data["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                    st.dataframe(agrup_data[["Data da Aquisição", "Quantidade Comprada", "Custo Total"]], use_container_width=True, hide_index=True)

                    with st.expander("🔍 Visualizar Registros Individuais de Compras", expanded=False):
                        df_m_mes["Custo Base"] = df_m_mes["preco_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                        df_m_mes["Estampa Extra"] = df_m_mes["estampa_extra_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                        df_m_mes["Matriz Bordado"] = df_m_mes["matriz_num"].apply(lambda v: f"R$ {float(v):,.2f}")
                        df_m_mes["Custo Unit. Total"] = df_m_mes["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                        df_m_mes["Custo Total"] = df_m_mes["total_item_calc"].apply(lambda v: f"R$ {float(v):,.2f}")
                        
                        cols_ind = ["Código", "Produto", "Custo Base", "Estampa Extra", "Matriz Bordado", "Custo Unit. Total", "Custo Total", "Data"]
                        st.dataframe(df_m_mes[cols_ind], use_container_width=True, hide_index=True)
        else:
            st.info("Nenhuma aquisição de mercadoria registrada no momento.")

    elif "Custos / Despesas" in sub_tab:
        with st.form("form_cv"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cv = st.date_input("Data *", datetime.date.today(), format="YYYY/MM/DD")
                desc_cv = st.text_input("Descrição *")
            with c2:
                tipos_despesa_sorted = sorted(["Embalagem", "Impostos", "Infraestrutura", "Materiais de Consumo", "Unboxing"])
                tipo_cv = st.selectbox("Tipo de Despesa *", tipos_despesa_sorted)
            with c3:
                val_cv = st.number_input("Valor (R$) *", min_value=0.01, value=10.0, format="%.2f")

            if st.form_submit_button("Adicionar Custo / Despesa", use_container_width=True):
                val_cv_fmt = round(float(val_cv), 2)
                dt_cv_str = parse_date_str(dt_cv)
                
                payload_cv = {
                    "subcategoria": "Custos / Despesas",
                    "data": dt_cv_str,
                    "desc": desc_cv.strip(),
                    "tipo": tipo_cv,
                    "valor": val_cv_fmt
                }
                
                safe_insert("custos_avulsos", payload_cv)
                safe_insert("caixa", {
                    "data": dt_cv_str, 
                    "desc": f"[Custos / Despesas] {desc_cv.strip()}", 
                    "tipo": tipo_cv, 
                    "valor": val_cv_fmt
                })
                st.session_state["flash_success"] = "Custo / Despesa registrado com sucesso!"
                st.rerun()

        st.markdown("---")
        st.markdown("##### 📋 Demonstrativo de Custos / Despesas Lançados")
        
        df_custos_atualizado = fetch_data("custos_avulsos")
        if not df_custos_atualizado.empty:
            subcat_col = df_custos_atualizado.get("subcategoria", pd.Series([""] * len(df_custos_atualizado))).fillna("").astype(str)
            df_cv_exib = df_custos_atualizado[subcat_col.str.contains("Custos / Despesas", case=False, na=False)].copy()
            
            if not df_cv_exib.empty:
                df_cv_exib["Mes_Ano"] = pd.to_datetime(df_cv_exib["data"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
                meses_cv = sorted(df_cv_exib["Mes_Ano"].unique(), reverse=True)
                
                for mes in meses_cv:
                    df_cv_mes = df_cv_exib[df_cv_exib["Mes_Ano"] == mes]
                    total_mes_cv = df_cv_mes["valor"].apply(parse_money).sum()
                    
                    with st.expander(f"📅 Mês: {mes.replace('-', '/')} — Custo Total: R$ {total_mes_cv:,.2f}", expanded=False):
                        for idx, row in df_cv_mes.iterrows():
                            c_id = row.get("id")
                            c_dt = format_data_br(row.get("data"))
                            c_tp = row.get("tipo", "")
                            c_desc = row.get("desc") or row.get("descricao") or ""
                            c_vl = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)

                            col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                            with col1:
                                st.write(f"**Data:** {c_dt}")
                            with col2:
                                st.write(f"**Tipo:** {c_tp}")
                            with col3:
                                st.write(f"**Descrição:** {c_desc}")
                            with col4:
                                st.write(f"**Valor:** R$ {c_vl:,.2f}")
                            with col5:
                                if st.button("🗑 Excluir", key=f"del_cv_{c_id}_{mes}", use_container_width=True):
                                    sqlite_delete_record("custos_avulsos", c_id)
                                    if supabase:
                                        try:
                                            supabase.table("custos_avulsos").delete().eq("id", c_id).execute()
                                        except Exception:
                                            pass
                                    st.session_state["flash_success"] = "Custo / Despesa excluído!"
                                    st.rerun()
                            st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Nenhum custo ou despesa registrado até o momento.")
        else:
            st.info("Nenhum custo registrado.")

    elif "Feiras" in sub_tab:
        with st.form("form_cf"):
            c1, c2, c3 = st.columns(3)
            with c1:
                dt_cf = st.date_input("Data *", datetime.date.today(), format="YYYY/MM/DD")
                feira_cf = st.text_input("Nome da Feira *")
            with c2:
                desc_cf = st.text_input("Descrição *")
                tipos_feiras_sorted = sorted(["Alimentação", "Decoração", "Instalação", "Taxa de Inscrição", "Transporte"])
                tipo_cf = st.selectbox("Tipo de Despesa *", tipos_feiras_sorted)
            with c3:
                val_cf = st.number_input("Valor (R$) *", min_value=0.01, value=50.0, format="%.2f")

            if st.form_submit_button("Adicionar Custo de Feira", use_container_width=True):
                val_cf_fmt = round(float(val_cf), 2)
                dt_cf_str = parse_date_str(dt_cf)
                
                payload_cf = {
                    "subcategoria": "Feiras",
                    "data": dt_cf_str,
                    "desc": f"Feira: {feira_cf.strip()} - {desc_cf.strip()}",
                    "tipo": tipo_cf,
                    "valor": val_cf_fmt
                }
                
                safe_insert("custos_avulsos", payload_cf)
                safe_insert("caixa", {
                    "data": dt_cf_str, 
                    "desc": f"[Feira: {feira_cf.strip()}] {desc_cf.strip()}", 
                    "tipo": tipo_cf, 
                    "valor": val_cf_fmt
                })
                st.session_state["flash_success"] = "Custo de Feira registrado com sucesso!"
                st.rerun()

        st.markdown("---")
        st.markdown("##### 📋 Demonstrativo de Custos de Feiras Lançados")
        
        df_custos_atualizado = fetch_data("custos_avulsos")
        if not df_custos_atualizado.empty:
            subcat_col = df_custos_atualizado.get("subcategoria", pd.Series([""] * len(df_custos_atualizado))).fillna("").astype(str)
            df_cf_exib = df_custos_atualizado[subcat_col.str.contains("feira", case=False, na=False)].copy()
            
            if not df_cf_exib.empty:
                df_cf_exib["Mes_Ano"] = pd.to_datetime(df_cf_exib["data"].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
                meses_cf = sorted(df_cf_exib["Mes_Ano"].unique(), reverse=True)
                
                for mes in meses_cf:
                    df_cf_mes = df_cf_exib[df_cf_exib["Mes_Ano"] == mes]
                    total_mes_cf = df_cf_mes["valor"].apply(parse_money).sum()
                    
                    with st.expander(f"📅 Mês: {mes.replace('-', '/')} — Custo Total: R$ {total_mes_cf:,.2f}", expanded=False):
                        for idx, row in df_cf_mes.iterrows():
                            f_id = row.get("id")
                            f_dt = format_data_br(row.get("data"))
                            f_tp = row.get("tipo", "")
                            f_desc = row.get("desc") or row.get("descricao") or ""
                            f_vl = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)

                            col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 2, 1])
                            with col1:
                                st.write(f"**Data:** {f_dt}")
                            with col2:
                                st.write(f"**Tipo:** {f_tp}")
                            with col3:
                                st.write(f"**Descrição:** {f_desc}")
                            with col4:
                                st.write(f"**Valor:** R$ {f_vl:,.2f}")
                            with col5:
                                if st.button("🗑 Excluir", key=f"del_cf_{f_id}_{mes}", use_container_width=True):
                                    sqlite_delete_record("custos_avulsos", f_id)
                                    if supabase:
                                        try:
                                            supabase.table("custos_avulsos").delete().eq("id", f_id).execute()
                                        except Exception:
                                            pass
                                    st.session_state["flash_success"] = "Custo de feira excluído!"
                                    st.rerun()
                            st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
            else:
                st.info("Nenhum custo de feira registrado até o momento.")
        else:
            st.info("Nenhum custo registrado.")

elif "Caixa" in menu or "Fluxo" in menu:
    st.subheader("💰 Extrato Consolidado de Fluxo de Caixa")
    st.markdown("As entradas de vendas aparecem exclusivamente após a confirmação do recebimento no módulo **Contas a Receber**. Cada mês é exibido em um componente expansivo (accordion/collapse).")
    
    lista_movimentos = []

    # 1. Compras do Módulo Compra de Mercadorias
    df_cm = get_df_compra_mercadorias()
    if not df_cm.empty:
        df_cm["data_str"] = df_cm["Data_Raw"].apply(parse_date_str)
        
        agrup_cm = df_cm.groupby("data_str").agg(
            total_custo=("total_item_calc", "sum"),
            total_qtd=("id", "count")
        ).reset_index()
        
        for _, r in agrup_cm.iterrows():
            dt_c = r["data_str"]
            tot_c = float(r["total_custo"])
            tot_qtd = int(r["total_qtd"])
            if tot_c > 0:
                lista_movimentos.append({
                    "Data_Val": dt_c,
                    "Data": format_data_br(dt_c),
                    "Origem": "🛍 Compra de Mercadorias",
                    "Descrição": f"Compra Agrupada ({tot_qtd} itens adquiridos)",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -tot_c
                })

    # 2. Recebimentos Líquidos das Vendas
    if not df_vendas.empty:
        df_v_norm = normalizar_df_vendas(df_vendas)
        col_dt_rec = "data_recebimento" if "data_recebimento" in df_v_norm.columns else None
        if col_dt_rec:
            df_v_recebidas = df_v_norm[df_v_norm[col_dt_rec].notna() & df_v_norm[col_dt_rec].astype(str).str.strip().ne("") & df_v_norm[col_dt_rec].astype(str).str.lower().ne("none")].copy()
            for _, r in df_v_recebidas.iterrows():
                dt_rec_val = r.get(col_dt_rec)
                val_v_calc = float(r.get("liquido_recebido_calc", 0.0))
                cli = r.get("cliente") or ""
                cod = r.get("codigo_bone") or r.get("codigo") or ""
                if val_v_calc > 0:
                    dt_rec_str = parse_date_str(dt_rec_val)
                    lista_movimentos.append({
                        "Data_Val": dt_rec_str,
                        "Data": format_data_br(dt_rec_str),
                        "Origem": "🛒 Recebimento de Vendas (Líquido)",
                        "Descrição": f"Venda {cod} - Cliente: {cli}",
                        "Tipo": "Entrada 🟢",
                        "Valor_Num": val_v_calc
                    })

    # 3. Custos Avulsos e Feiras
    if not df_custos.empty:
        for _, r in df_custos.iterrows():
            val_c = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            sub_c = str(r.get("subcategoria", "Custos"))
            desc_c = r.get("desc") or r.get("descricao") or "Despesa Avulsa"
            origem_tag = "🏷 Custos / Despesas" if "custos" in sub_c.lower() or "venda" in sub_c.lower() else ("🎪 Custos de Feiras" if "feira" in sub_c.lower() else f"💵 Custos ({sub_c})")
            if val_c > 0:
                dt_c_str = parse_date_str(r.get("data"))
                lista_movimentos.append({
                    "Data_Val": dt_c_str,
                    "Data": format_data_br(dt_c_str),
                    "Origem": origem_tag,
                    "Descrição": desc_c,
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -val_c
                })

    # 4. Aporte e Devoluções de Sócios
    if not df_aportes.empty:
        for _, r in df_aportes.iterrows():
            val_ap = float(pd.to_numeric(r.get("valor", 0.0), errors="coerce") or 0.0)
            tipo_ap = str(r.get("tipo", ""))
            socio = r.get("socio", "")
            
            dt_ap_raw = r.get("data") or r.get("data_aporte") or r.get("created_at")
            dt_ap_str = parse_date_str(dt_ap_raw) if dt_ap_raw else datetime.date.today().strftime("%Y-%m-%d")
            
            if val_ap != 0:
                is_devolucao = "devoluc" in tipo_ap.lower() or val_ap < 0
                nome_op = "Devolução" if is_devolucao else "Aporte"
                
                lista_movimentos.append({
                    "Data_Val": dt_ap_str,
                    "Data": format_data_br(dt_ap_str),
                    "Origem": "🤝 Aporte dos Sócios",
                    "Descrição": f"{nome_op} ({socio})",
                    "Tipo": "Saída 🔴" if is_devolucao else "Entrada 🟢",
                    "Valor_Num": -abs(val_ap) if is_devolucao else abs(val_ap)
                })

    # 5. Devoluções de Vendas como Saída
    if not df_devolucoes.empty:
        for _, r in df_devolucoes.iterrows():
            val_dev = float(pd.to_numeric(r.get("valor_devolvido", 0.0), errors="coerce") or 0.0)
            cod_dev = r.get("codigo", "")
            cli_dev = r.get("cliente", "")
            dt_dev_raw = r.get("data_devolucao")
            dt_dev_str = parse_date_str(dt_dev_raw) if dt_dev_raw else datetime.date.today().strftime("%Y-%m-%d")
            if val_dev > 0:
                lista_movimentos.append({
                    "Data_Val": dt_dev_str,
                    "Data": format_data_br(dt_dev_str),
                    "Origem": "🔄 Devolução de Venda",
                    "Descrição": f"Devolução Venda {cod_dev} - Cliente: {cli_dev}",
                    "Tipo": "Saída 🔴",
                    "Valor_Num": -val_dev
                })

    if lista_movimentos:
        df_extrato = pd.DataFrame(lista_movimentos)
        
        df_extrato["Data_Raw"] = pd.to_datetime(df_extrato["Data_Val"].apply(parse_date_str), errors="coerce")
        df_extrato["Data_Raw"] = df_extrato["Data_Raw"].fillna(pd.Timestamp.now())
        df_extrato["Mes_Ano"] = df_extrato["Data_Raw"].dt.strftime("%Y-%m").fillna("Outros")
        
        df_extrato = df_extrato.sort_values(by="Data_Raw", ascending=True).reset_index(drop=True)
        df_extrato["Saldo_Acumulado"] = df_extrato["Valor_Num"].cumsum()
        
        meses_caixa = sorted(df_extrato["Mes_Ano"].unique(), reverse=False)
        saldo_acumulado_anterior = 0.0

        for mes in meses_caixa:
            df_cx_mes = df_extrato[df_extrato["Mes_Ano"] == mes].copy()
            
            running_mes_calc = saldo_acumulado_anterior
            for _, r_m in df_cx_mes.iterrows():
                running_mes_calc += r_m["Valor_Num"]
            saldo_final_mes_val = running_mes_calc

            titulo_accordion = f"📅 Mês: {mes.replace('-', '/')} — Saldo Final: R$ {saldo_final_mes_val:,.2f}"
            
            with st.expander(titulo_accordion, expanded=False):
                linhas_mes_exib = []
                if saldo_acumulado_anterior != 0.0:
                    linhas_mes_exib.append({
                        "Data": f"{mes}/01",
                        "Origem": "🟢 SALDO INICIAL",
                        "Descrição": f"Saldo transportado do mês anterior",
                        "Tipo": "Saldo 💵",
                        "Valor (R$)": f"R$ {saldo_acumulado_anterior:,.2f}",
                        "Saldo Acumulado (R$)": f"R$ {saldo_acumulado_anterior:,.2f}"
                    })
                
                running_mes = saldo_acumulado_anterior
                for _, r_m in df_cx_mes.iterrows():
                    running_mes += r_m["Valor_Num"]
                    linhas_mes_exib.append({
                        "Data": r_m["Data"],
                        "Origem": r_m["Origem"],
                        "Descrição": r_m["Descrição"],
                        "Tipo": r_m["Tipo"],
                        "Valor (R$)": f"R$ {r_m['Valor_Num']:,.2f}",
                        "Saldo Acumulado (R$)": f"R$ {running_mes:,.2f}"
                    })
                
                saldo_final_mes = running_mes
                saldo_acumulado_anterior = saldo_final_mes
                
                try:
                    ano_m, mes_m = map(int, mes.split("-"))
                    ultimo_dia_num = calendar.monthrange(ano_m, mes_m)[1]
                    data_ultimo_dia_mes = f"{mes}/{ultimo_dia_num:02d}"
                except Exception:
                    data_ultimo_dia_mes = f"{mes}/30"

                linhas_mes_exib.append({
                    "Data": data_ultimo_dia_mes,
                    "Origem": "🏁 SALDO FINAL",
                    "Descrição": f"Saldo Acumulado Final do Período ({mes})",
                    "Tipo": "Saldo 💵",
                    "Valor (R$)": f"R$ {saldo_final_mes:,.2f}",
                    "Saldo Acumulado (R$)": f"R$ {saldo_final_mes:,.2f}"
                })
                
                df_cx_mes_exib = pd.DataFrame(linhas_mes_exib)
                st.dataframe(df_cx_mes_exib, use_container_width=True, hide_index=True)
        
            saldo_acumulado_anterior = saldo_final_mes_val
    else:
        st.info("Nenhuma movimentação registrada no fluxo de caixa.")

elif "Aportes" in menu:
    st.subheader("🤝 Registro de Aportes e Devoluções")
    c1, c2, c3 = st.columns(3)
    with c1:
        dt_ap = st.date_input("Data *", datetime.date.today(), format="YYYY/MM/DD")
    with c2:
        socio_ap = st.selectbox("Sócio *", ["", "Renan", "Ronald"], index=0)
    with c3:
        val_ap = st.number_input("Valor (R$) *", min_value=0.0, value=0.0, format="%.2f")

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🤝 Registrar Aporte", use_container_width=True, type="primary"):
            if not socio_ap:
                st.error("Selecione o Sócio antes de continuar!")
            elif val_ap <= 0:
                st.error("Informe um valor positivo para o Aporte!")
            else:
                val_ap_fmt = round(float(val_ap), 2)
                dt_ap_str = parse_date_str(dt_ap)
                payload_ap = {
                    "data": dt_ap_str,
                    "data_aporte": dt_ap_str,
                    "socio": socio_ap,
                    "valor": val_ap_fmt,
                    "tipo": "Aporte"
                }
                safe_insert("aportes", payload_ap)
                safe_insert("caixa", {
                    "data": dt_ap_str,
                    "desc": f"Aporte ({socio_ap})",
                    "tipo": "Aporte de Sócio",
                    "valor": val_ap_fmt
                })
                st.session_state["flash_success"] = f"Aporte de R$ {val_ap_fmt:,.2f} registrado com sucesso!"
                st.rerun()

    with col_btn2:
        if st.button("🔄 Devolução de Aporte", use_container_width=True):
            if not socio_ap:
                st.error("Selecione o Sócio antes de continuar!")
            elif val_ap <= 0:
                st.error("Informe um valor positivo para a Devolução!")
            else:
                val_ap_fmt = round(float(val_ap), 2)
                dt_ap_str = parse_date_str(dt_ap)
                payload_dev = {
                    "data": dt_ap_str,
                    "data_aporte": dt_ap_str,
                    "socio": socio_ap,
                    "valor": -val_ap_fmt,
                    "tipo": "Devolução"
                }
                safe_insert("aportes", payload_dev)
                safe_insert("caixa", {
                    "data": dt_ap_str,
                    "desc": f"Devolução ({socio_ap})",
                    "tipo": "Devolução de Aporte",
                    "valor": -val_ap_fmt
                })
                st.session_state["flash_success"] = f"Devolução de R$ {val_ap_fmt:,.2f} registrada com sucesso!"
                st.rerun()

    st.markdown("---")
    st.subheader("📊 Resumo Consolidado por Sócio")
    
    if not df_aportes.empty:
        df_ap_calc = df_aportes.copy()
        
        if "tipo" not in df_ap_calc.columns:
            if "operacao" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["operacao"]
            elif "forma" in df_ap_calc.columns:
                df_ap_calc["tipo"] = df_ap_calc["forma"]
            else:
                df_ap_calc["tipo"] = "Aporte"
                
        if "socio" not in df_ap_calc.columns:
            df_ap_calc["socio"] = "Não informado"

        df_ap_calc["valor_num"] = get_numeric_series(df_ap_calc, "valor")
        
        resumo_socios = []
        for s in ["Renan", "Ronald"]:
            df_s = df_ap_calc[df_ap_calc["socio"].astype(str).str.lower() == s.lower()]
            
            ent = df_s[df_s["valor_num"] > 0]["valor_num"].sum()
            sai = abs(df_s[df_s["valor_num"] < 0]["valor_num"].sum())
            
            saldo_dev = ent - sai
            
            resumo_socios.append({
                "Sócio": s,
                "Total Aportado (R$)": f"R$ {ent:,.2f}",
                "Total Devolvido (R$)": f"R$ {sai:,.2f}",
                "Saldo a Devolver (R$)": f"R$ {saldo_dev:,.2f}"
            })
            
        st.dataframe(pd.DataFrame(resumo_socios), use_container_width=True, hide_index=True)

        st.markdown("##### 📋 Relatório Detalhado de Movimentações de Aportes")
        
        if "editing_aporte_id" not in st.session_state:
            st.session_state["editing_aporte_id"] = None

        col_dt_ap = "data" if "data" in df_aportes.columns else ("data_aporte" if "data_aporte" in df_aportes.columns else ("created_at" if "created_at" in df_aportes.columns else None))
        
        if col_dt_ap and not df_aportes.empty:
            df_aportes["Mes_Ano"] = pd.to_datetime(df_aportes[col_dt_ap].apply(parse_date_str), errors="coerce").dt.strftime("%Y-%m").fillna("Outros")
            
            meses_aportes = sorted(df_aportes["Mes_Ano"].unique(), reverse=True)
            for mes in meses_aportes:
                df_ap_mes = df_aportes[df_aportes["Mes_Ano"] == mes].copy()
                
                df_ap_mes["val_num"] = get_numeric_series(df_ap_mes, "valor")
                aporte_mes_total = df_ap_mes[df_ap_mes["val_num"] > 0]["val_num"].sum()
                devolucao_mes_total = abs(df_ap_mes[df_ap_mes["val_num"] < 0]["val_num"].sum())
                dif_mes = aporte_mes_total - devolucao_mes_total
                
                with st.expander(f"📅 Mês: {mes.replace('-', '/')} — Diferença Líquida (Aportes - Devoluções): R$ {dif_mes:,.2f}", expanded=False):
                    for idx, row in df_ap_mes.iterrows():
                        ap_id = row.get("id")
                        ap_dt = format_data_br(row.get(col_dt_ap))
                        ap_socio = row.get("socio", "")
                        
                        ap_val = float(pd.to_numeric(row.get("valor", 0), errors="coerce") or 0.0)
                        
                        tipo_raw = str(row.get("tipo", ""))
                        if "devoluc" in tipo_raw.lower() or ap_val < 0:
                            ap_tipo_exib = "Devolução"
                        else:
                            ap_tipo_exib = "Aporte"

                        c1, c2, c3, c4, c5, c6 = st.columns([2, 2, 2, 2, 1, 1])
                        with c1:
                            st.write(f"**Data:** {ap_dt}")
                        with c2:
                            st.write(f"**Sócio:** {ap_socio}")
                        with c3:
                            st.write(f"**Operação:** {ap_tipo_exib}")
                        with c4:
                            st.write(f"**Valor:** R$ {abs(ap_val):,.2f}")
                        with c5:
                            if st.button("✏️", key=f"edit_ap_{ap_id}_{mes}", use_container_width=True):
                                st.session_state["editing_aporte_id"] = ap_id
                                st.rerun()
                        with c6:
                            if st.button("🗑", key=f"del_ap_{ap_id}_{mes}", use_container_width=True):
                                sqlite_delete_record("aportes", ap_id)
                                if supabase:
                                    try:
                                        supabase.table("aportes").delete().eq("id", ap_id).execute()
                                    except Exception:
                                        pass
                                st.session_state["flash_success"] = f"Registro ID #{ap_id} excluído com sucesso!"
                                st.rerun()

                        if st.session_state.get("editing_aporte_id") == ap_id:
                            with st.form(key=f"form_edit_ap_{ap_id}_{mes}"):
                                st.markdown(f"##### ✏ Editar Registro ID #{ap_id}")
                                e_col1, e_col2, e_col3 = st.columns(3)
                                with e_col1:
                                    idx_s = 0 if ap_socio == "Renan" else 1
                                    novo_socio = st.selectbox("Sócio", ["Renan", "Ronald"], index=idx_s)
                                with e_col2:
                                    idx_t = 0 if ap_tipo_exib == "Aporte" else 1
                                    novo_tipo = st.selectbox("Tipo", ["Aporte", "Devolução"], index=idx_t)
                                with e_col3:
                                    novo_val = st.number_input("Valor (R$)", min_value=1.0, value=abs(ap_val), format="%.2f")

                                btn_s_ap, btn_c_ap = st.columns(2)
                                with btn_s_ap:
                                    if st.form_submit_button("💾 Salvar Alterações", use_container_width=True, type="primary"):
                                        val_final = float(novo_val) if novo_tipo == "Aporte" else -float(novo_val)
                                        payload_upd_ap = {
                                            "socio": novo_socio,
                                            "tipo": novo_tipo,
                                            "valor": val_final
                                        }
                                        sqlite_update_record("aportes", ap_id, payload_upd_ap)
                                        if supabase:
                                            try:
                                                supabase.table("aportes").update(payload_upd_ap).eq("id", ap_id).execute()
                                            except Exception:
                                                pass
                                        st.session_state["editing_aporte_id"] = None
                                        st.session_state["flash_success"] = "Registro atualizado com sucesso!"
                                        st.rerun()
                                with btn_c_ap:
                                    if st.form_submit_button("❌ Cancelar", use_container_width=True):
                                        st.session_state["editing_aporte_id"] = None
                                        st.rerun()
                        st.markdown("<hr style='margin:2px 0;'>", unsafe_allow_html=True)
        else:
            st.info("Nenhum aporte registrado com data válida até o momento.")
    else:
        st.info("Nenhum aporte ou devolução registrado no momento.")

elif "Gestão" in menu or "Dados" in menu:
    st.subheader("💾 Gestão de Dados & Backup")
    st.markdown("Gerencie o banco de dados, faça downloads de segurança e restaure backups do sistema.")

    col_status, col_export = st.columns(2)

    with col_status:
        st.markdown("#### 📌 Status da Conexão")
        if supabase is not None:
            try:
                supabase.table("produtos").select("id").limit(1).execute()
                st.success("🟢 Conectado ao Supabase (PostgreSQL Nuvem)")
                st.caption("Seus dados estão gravados na nuvem e imunes a reinícios do servidor.")
            except Exception as e:
                st.error("🔴 Falha ao conectar com o Supabase")
                st.caption(f"Erro na verificação: {e}")
        else:
            st.error("🔴 Supabase não configurado ou credenciais inválidas")
            st.caption("Verifique as chaves SUPABASE_URL e SUPABASE_KEY em seus secrets.")

    with col_export:
        st.markdown("#### 📥 Exportar Backup Geral em Excel")
        
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df_produtos.to_excel(writer, sheet_name='Produtos_Estoque', index=False)
            df_vendas.to_excel(writer, sheet_name='Vendas', index=False)
            df_caixa.to_excel(writer, sheet_name='Caixa', index=False)
            df_aportes.to_excel(writer, sheet_name='Aportes', index=False)
            df_custos.to_excel(writer, sheet_name='Custos_Avulsos', index=False)
        excel_data = output.getvalue()

        st.download_button(
            label="📥 Baixar Backup Geral (.xlsx)",
            data=excel_data,
            file_name=f"Backup_Geral_R2_Bones_{datetime.date.today().strftime('%Y_%m_%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

    st.markdown("---")
    st.markdown("#### ⚙ Operações de Banco Supabase")
    st.info("Seu banco de dados está sincronizado diretamente na nuvem do Supabase. Todos os cadastros e edições são mantidos permanentemente.")

    with st.expander("🔄 Restaurar / Recuperar Dados via Backup Planilha (.xlsx)"):
        st.warning("⚠️ O envio de uma planilha de restauração substituirá ou atualizará os registros existentes correspondentes aos códigos e IDs.")
        uploaded_backup = st.file_uploader("Carregar Arquivo de Backup para Restauração (.xlsx)", type=["xlsx"])
        
        if uploaded_backup is not None:
            if st.button("🚀 Confirmar Restauração do Banco de Dados", type="primary", use_container_width=True):
                try:
                    xls = pd.ExcelFile(uploaded_backup)
                    
                    if "Produtos_Estoque" in xls.sheet_names and supabase:
                        df_p_rec = pd.read_excel(xls, sheet_name="Produtos_Estoque")
                        if not df_p_rec.empty:
                            supabase.table("produtos").upsert(df_p_rec.to_dict(orient="records"), on_conflict="codigo").execute()
                    
                    if "Vendas" in xls.sheet_names and supabase:
                        df_v_rec = pd.read_excel(xls, sheet_name="Vendas")
                        if not df_v_rec.empty:
                            supabase.table("vendas").upsert(df_v_rec.to_dict(orient="records")).execute()
                            
                    st.success("🎉 Dados restaurados com sucesso a partir do arquivo de backup!")
                    st.rerun()
                except Exception as ex:
                    st.error(f"Erro durante a restauração do backup: {ex}")

elif "Configuração" in menu or "Configuracao" in menu:
    st.subheader("⚙ Configurações Gerais do Sistema")
    st.markdown("Gerencie variáveis de sistema, sequenciais de código e parâmetros operacionais.")

    ult_cod = get_ultimo_codigo_config()

    st.markdown("#### 🏷 Sequencial do Código do Boné")
    st.info("Esta configuração determina qual foi o último código de boné registrado e serve de base para a criação automática de novos códigos quando um pedido for marcado como **Entregue**.")

    c_cfg1, c_cfg2 = st.columns(2)
    with c_cfg1:
        novo_cod_input = st.text_input(
            "Último Item Cadastrado no Estoque *", 
            value=ult_cod, 
            help="Campo alfanumérico com o formato do último produto (exemplo: BL-0001)"
        )
    
    with c_cfg2:
        prox_sugerido = gerar_proximo_codigo(novo_cod_input.strip())
        st.markdown("<br>", unsafe_allow_html=True)
        st.write(f"👉 **Próximo Código Gerado Automaticamente:** `{prox_sugerido}`")

    if st.button("💾 Salvar Parâmetros de Configuração", type="primary", use_container_width=True):
        if not novo_cod_input.strip():
            st.error("Informe um código alfanumérico válido!")
        else:
            set_ultimo_codigo_config(novo_cod_input.strip())
            st.session_state["flash_success"] = f"🎉 Configuração atualizada! O 'Último Item Cadastrado no Estoque' é '{novo_cod_input.strip()}'."
            st.rerun()
