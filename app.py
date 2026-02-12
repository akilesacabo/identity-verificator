import streamlit as st
import pandas as pd
import json
import requests
import time
import os
import re
import toml
from fuzzywuzzy import fuzz

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Validador de Cédulas VZLA", page_icon="💎", layout="wide")

# --- CLASES Y LÓGICA DE BACKEND ---
class Token():
    def __init__(self, token, app_id, capacity=200):
        self.capacity = capacity
        self.current_usage = 0
        self.token_id = token
        self.app_id = app_id

    def has_capacity(self):
        return self.current_usage < self.capacity

    def get_credentials(self):
        return {"app_id": self.app_id, "token": self.token_id}

def normalizar_cedula(input_id):
    solo_numeros = re.sub(r'\D', '', str(input_id))
    return solo_numeros

def api_request_and_parse_data(query_params):
    api_url = "https://api.cedula.com.ve/api/v1"
    try:
        response = requests.get(api_url, params=query_params, timeout=10)
        return response.json() if response.status_code == 200 else {}
    except:
        return {}

def parse_api_response(data):
    d = data.get("data", {})
    if not d: return None
    full_name = f"{d.get('primer_nombre', '')} {d.get('segundo_nombre', '')} {d.get('primer_apellido', '')} {d.get('segundo_apellido', '')}"
    return " ".join(full_name.split()).upper()

# --- PERSISTENCIA ---
HISTORIC_PATH = "historic.jsonl"
PENDIENTES_PATH = "pendientes.jsonl"

def inicializar_sistema():
    cache = {}
    if os.path.exists(HISTORIC_PATH):
        with open(HISTORIC_PATH, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    cache[str(item["cedula"])] = item["nombre"]
                except: continue
    return cache

def add_to_historic(cedula, nombre):
    with open(HISTORIC_PATH, "a", encoding="utf-8") as file:
        file.write(json.dumps({"cedula": cedula, "nombre": nombre}) + "\n")

# --- INTERFAZ STREAMLIT ---
st.title("💎 Validador de Identidad API")
st.markdown("Consulta masiva optimizada con gestión de tokens y caché local.")

# Cargar configuración desde Secrets de Streamlit
if 'tokens' not in st.session_state:
    try:
        # En Streamlit Cloud se usa st.secrets, en local busca el .toml
        tokens_data = st.secrets["tokens"]
        st.session_state.tokens = [Token(t["token"], t["app_id"]) for t in tokens_data]
    except:
        st.error("⚠️ No se encontraron los Tokens en los Secretos.")
        st.stop()

if 'cache' not in st.session_state:
    st.session_state.cache = inicializar_sistema()

tab1, tab2 = st.tabs(["🚀 Procesar Lista", "📁 Histórico"])

with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
            modo = st.radio("Modo de trabajo:", ["Solo Consultar", "Comparar con mi lista"])
            
            # --- NUEVA SECCIÓN DE ENTRADA MIXTA ---
            metodo_entrada = st.radio("Método de entrada:", ["Sube un CSV", "Pega las Cédulas"])
            
            raw_ids = []
            nombres_ref = {}

            if metodo_entrada == "Sube un CSV":
                uploaded_file = st.file_uploader("Sube tu archivo", type=["csv"])
                if uploaded_file:
                    df = pd.read_csv(uploaded_file, sep=None, engine='python',encoding = "latin-1")
                    st.success(f"Cargadas {len(df)} filas.")
                    
                    col_id = st.selectbox("Columna de Cédula", df.columns)
                    raw_ids = df[col_id].dropna().astype(str).tolist()
                    
                    if modo == "Comparar con mi lista":
                        col_nom = st.selectbox("Columna de Nombre Completo", df.columns)
                        nombres_ref = dict(zip([normalizar_cedula(c) for c in raw_ids], df[col_nom].astype(str)))
            
            else:
                txt_input = st.text_area("Pega las cédulas (una por línea):", height=200, placeholder="12345678\n87654321")
                if txt_input:
                    raw_ids = txt_input.split('\n')
                    if modo == "Comparar con mi lista":
                        st.warning("⚠️ El modo manual no soporta comparación automática. Usa un CSV para comparar nombres.")

    with col2:
        if st.button("Iniciar Procesamiento"):
            ids_limpios = list(dict.fromkeys([normalizar_cedula(c) for c in raw_ids if normalizar_cedula(c)]))
            resultados_finales = []
            
            progbar = st.progress(0)
            status = st.empty()
            
            token_idx = 0
            
            for i, _id in enumerate(ids_limpios):
                # 1. Check Caché
                if _id in st.session_state.cache:
                    nombre_api = st.session_state.cache[_id]
                    origen = "Caché"
                else:
                    # 2. Check Tokens
                    tokens_disponibles = [t for t in st.session_state.tokens if t.has_capacity()]
                    if not tokens_disponibles:
                        status.error("❌ Tokens agotados. Descarga lo procesado.")
                        break
                    
                    # Rotación
                    while not st.session_state.tokens[token_idx].has_capacity():
                        token_idx = (token_idx + 1) % len(st.session_state.tokens)
                    
                    t = st.session_state.tokens[token_idx]
                    res_api = api_request_and_parse_data({**t.get_credentials(), "cedula": _id, "nacionalidad": "V"})
                    nombre_api = parse_api_response(res_api)
                    
                    if nombre_api:
                        st.session_state.cache[_id] = nombre_api
                        add_to_historic(_id, nombre_api)
                        t.current_usage += 1
                        origen = "API"
                        time.sleep(0.2)
                    else:
                        nombre_api = "NO ENCONTRADO"
                        origen = "Error/No existe"
                    
                    token_idx = (token_idx + 1) % len(st.session_state.tokens)

                # 3. Armar fila
                res_row = {"Cédula": _id, "Nombre API": nombre_api, "Fuente": origen}
                if modo == "Comparar con mi lista":
                    n_usuario = nombres_ref.get(_id, "")
                    score = fuzz.token_sort_ratio(n_usuario.upper(), nombre_api.upper())
                    res_row["Tu Lista"] = n_usuario
                    res_row["Resultado"] = "IGUAL" if score > 90 else "REVISAR" if score > 65 else "DIFERENTE"
                
                resultados_finales.append(res_row)
                progbar.progress((i + 1) / len(ids_limpios))
                status.text(f"Procesando {i+1} de {len(ids_limpios)}...")

            df_final = pd.DataFrame(resultados_finales)
            st.dataframe(df_final, use_container_width=True)
            st.download_button("Descargar Resultados", df_final.to_csv(index=False), "resultados.csv")

with tab2:
    st.header("Base de datos local")
    if st.session_state.cache:
        df_hist = pd.DataFrame([{"Cédula": k, "Nombre": v} for k, v in st.session_state.cache.items()])
        st.write(f"Total registros guardados: {len(df_hist)}")
        st.dataframe(df_hist, use_container_width=True)
    else:
        st.info("El histórico está vacío.")

st.caption("Sistema de protección de tokens activo (Balanceo de carga).")

# --- FOOTER ---
st.divider()
st.caption("Hecho con ❤️ para mi amorcito")