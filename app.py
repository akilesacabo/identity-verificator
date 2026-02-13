import streamlit as st
import pandas as pd
from utils import (
    normalizar_cedula, 
    inicializar_sistema, 
    cargar_configuracion,
    procesar_cedula_individual
)

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Validador de Cédulas VZLA", page_icon="💎", layout="wide")


# --- INICIALIZACIÓN DE ESTADO ---
if 'tokens' not in st.session_state:
    # Intentamos cargar desde secrets (Cloud) o localmente
    tokens = cargar_configuracion()
    if not tokens:
        st.error("⚠️ No se encontraron los Tokens. Revisa tu archivo secrets.toml.")
        st.stop()
    st.session_state.tokens = tokens

if 'resultados' not in st.session_state:
    st.session_state.resultados = []
if 'ejecutando' not in st.session_state:
    st.session_state.ejecutando = False
if 'cache' not in st.session_state:
    st.session_state.cache = inicializar_sistema()

# --- INTERFAZ STREAMLIT ---
st.title("💎 Validador de Identidad API")
st.markdown("Consulta masiva optimizada con gestión de tokens y caché local.")

tab1, tab2 = st.tabs(["🚀 Procesar Lista", "📁 Histórico"])

with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Configuración")
        modo = st.radio("Modo de trabajo:", ["Solo Consultar", "Comparar con mi lista"])
        
        # --- NUEVA GUÍA VISUAL (UX) ---
        with st.expander("ℹ️ Ver formato de CSV requerido"):
            if modo == "Solo Consultar":
                st.write("Tu CSV solo necesita una columna con los números de cédula.")
                st.table(pd.DataFrame({"cedula": ["12345678", "87654321"]}))
            else:
                st.write("Tu CSV debe tener al menos dos columnas: Cédula y Nombre.")
                st.table(pd.DataFrame({
                    "cedula": ["12345678", "87654321"],
                    "nombre_lista": ["PEDRO PEREZ", "MARIA GOMEZ"]
                }))
        
        metodo_entrada = st.radio("Método de entrada:", ["Sube un CSV", "Pega las Cédulas"], horizontal=True)
        
        raw_ids = []
        nombres_ref = {}

        if metodo_entrada == "Sube un CSV":
            uploaded_file = st.file_uploader("Sube tu archivo", type=["csv"])
            if uploaded_file:
                try:
                    df = pd.read_csv(uploaded_file, sep=None, engine='python')
                except:
                    uploaded_file.seek(0)
                    df = pd.read_csv(uploaded_file, sep=None, engine='python', encoding="latin-1")
                
                st.success(f"✅ {len(df)} filas cargadas.")
                col_id = st.selectbox("Selecciona columna de Cédula", df.columns)
                raw_ids = df[col_id].dropna().astype(str).tolist()
                
                if modo == "Comparar con mi lista":
                    col_nom = st.selectbox("Selecciona columna de Nombre (Tu Lista)", df.columns)
                    nombres_ref = dict(zip([normalizar_cedula(c) for c in raw_ids], df[col_nom].astype(str)))
        
        else:
            txt_input = st.text_area("Pega las cédulas (una por línea):", height=150, placeholder="12345678\n87654321")
            if txt_input:
                raw_ids = txt_input.split('\n')
                if modo == "Comparar con mi lista":
                    st.warning("⚠️ El modo manual no soporta comparación. Usa un CSV para comparar nombres.")

        # btn_iniciar = st.button("🚀 Iniciar Procesamiento", use_container_width=True)

 # app.py

# ... (imports y carga de tokens/caché)

    with col2:
        st.subheader("Resultados")
        
        # Botones de control
        c1, c2, c3 = st.columns(3)
        with c1:
            # Iniciamos el proceso
            btn_iniciar = st.button("🚀 Iniciar", use_container_width=True)
        with c2:
            # Botón para detener (usa st.stop() para romper la ejecución de Streamlit)
            if st.button("🛑 Detener", use_container_width=True):
                st.session_state.ejecutando = False
                st.rerun()
        with c3:
            if st.button("🗑️ Limpiar", use_container_width=True):
                st.session_state.resultados = []
                st.rerun()

        # Contenedores visuales
        prog_bar = st.progress(0)
        status_txt = st.empty()

        if btn_iniciar and raw_ids:
            st.session_state.resultados = []
            ids_limpios = list(dict.fromkeys([normalizar_cedula(c) for c in raw_ids if normalizar_cedula(c)]))
            
            token_idx = 0
            for i, _id in enumerate(ids_limpios):
                # Llama a la lógica del backend para UNA cédula
                resultado, token_idx, status = procesar_cedula_individual(
                    _id, 
                    st.session_state.tokens, 
                    st.session_state.cache, 
                    token_idx, 
                    nombres_ref, 
                    modo
                )
                
                if status == "Agotado":
                    st.error("⚠️ Tokens agotados. Se detuvo el proceso.")
                    break
                    
                if resultado:
                    st.session_state.resultados.append(resultado)
                
                # ACTUALIZACIÓN DE BARRA DE PROGRESO (Aquí en el front)
                prog_bar.progress((i + 1) / len(ids_limpios))
                status_txt.text(f"Procesando {i+1}/{len(ids_limpios)}...")

        # MUESTRA LA TABLA SIEMPRE QUE HAYA DATOS (Fuera del if del botón)
        if st.session_state.resultados:
            df_final = pd.DataFrame(st.session_state.resultados)
            
            if modo == "Comparar con mi lista":
                # Filtro que ahora sí funciona porque st.session_state persiste
                ver_errores = st.toggle("🔍 Mostrar solo discrepancias", key="toggle_filtro")
                if ver_errores:
                    df_final = df_final[df_final["Resultado"] != "IGUAL"]

            st.dataframe(df_final, use_container_width=True)
with tab2:
    st.header("📁 Base de Datos Local (Caché)")
    
    if st.session_state.cache:
        # Convertimos el dict de caché a DataFrame
        df_hist = pd.DataFrame([
            {"Cédula": k, "Nombre": v} 
            for k, v in st.session_state.cache.items()
        ])
        
        # --- MÉTRICAS Y BUSCADOR ---
        c1, c2 = st.columns([1, 3])
        with c1:
            st.metric("Total en Memoria", len(df_hist))
        with c2:
            search = st.text_input("🔍 Buscar por Cédula o Nombre en el histórico:", placeholder="Ej: 123456 o PEREZ")

        # Aplicar búsqueda si existe
        if search:
            df_hist = df_hist[
                df_hist["Cédula"].str.contains(search) | 
                df_hist["Nombre"].str.contains(search.upper())
            ]

        # --- MOSTRAR TABLA ---
        st.dataframe(df_hist, use_container_width=True, height=400)
        
        # Opción para exportar TODO el histórico acumulado
        csv_hist = df_hist.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Exportar Base de Datos Completa",
            data=csv_hist,
            file_name="historico_total_api.csv",
            mime="text/csv"
        )
    else:
        st.info("El historial está vacío. Comienza a procesar cédulas en la primera pestaña para alimentar la base de datos.")

# --- FOOTER ---
st.divider()
st.caption("Sistema de protección de tokens activo (Balanceo de carga).")
st.caption("Hecho con ❤️ para mi amorcito")