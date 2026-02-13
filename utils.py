import json
import requests
import time
import os 
from fuzzywuzzy import fuzz
import toml
import unicodedata
import re


# --- PERSISTENCIA ---
HISTORIC_PATH = "historic.jsonl"
PENDIENTES_PATH = "pendientes.jsonl"



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


# --- LÓGICA DE BÚSQUEDA Y CACHÉ ---

def inicializar_sistema(historial_path=HISTORIC_PATH):
    cache = {}
    if os.path.exists(historial_path):
        with open(historial_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    cache[str(item["cedula"])] = item["nombre"]
                except: continue
    return cache


def is_id_in_cache(id_list, cache: dict):
    ids_set = set(id_list)
    cache_keys = set(cache.keys())
    cached = ids_set.intersection(cache_keys)
    non_cached = ids_set.difference(cached)
    return list(cached), list(non_cached)


def cargar_configuracion(ruta_toml=".streamlit/secrets.toml"):
    """
    Lee los tokens del archivo TOML y retorna una lista de objetos Token.
    """
    try:
        config = toml.load(ruta_toml)
        tokens_objs = []
        for t in config.get("tokens", []):
            tokens_objs.append(Token(token=t["token"], app_id=t["app_id"]))
        return tokens_objs
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return []
    
# --- LÓGICA DE API Y PROCESAMIENTO ---

def normalizar_cedula(input_id):
    return re.sub(r'\D', '', str(input_id))

def parse_api_response(data):
    d = data.get("data", {})
    if not d: return None
    full_name = f"{d.get('primer_nombre', '')} {d.get('segundo_nombre', '')} {d.get('primer_apellido', '')} {d.get('segundo_apellido', '')}"
    return " ".join(full_name.split()).upper()

def api_request_and_parse_data(query_params, api_url="https://api.cedula.com.ve/api/v1"):
    try:
        response = requests.get(api_url, params=query_params, timeout=10)
        return response.json() if response.status_code == 200 else {}
    except Exception as e:
        print(f"Fallo de conexión: {e}")
        return {}

def manage_api_requests(non_cached_ids, tokens, cache_dict):
    """
    EL MOTOR: Rotación de tokens (Round Robin) y gestión de errores.
    """
    results = []
    token_list = tokens
    token_index = 0
    id_no_procesados = []

    for i, _id in enumerate(non_cached_ids):
        # 1. Verificar capacidad global
        tokens_con_cupo = [t for t in token_list if t.has_capacity()]
        if not tokens_con_cupo:
            id_no_procesados = non_cached_ids[i:]
            guardar_pendientes(id_no_procesados)
            break

        # 2. Rotar hasta encontrar uno con cupo
        while not token_list[token_index].has_capacity():
            token_index = (token_index + 1) % len(token_list)
        
        selected_token = token_list[token_index]
        
        # 3. Petición
        try:
            params = selected_token.get_credentials()
            params["cedula"] = _id
            params["nacionalidad"] = "V"
            
            raw_data = api_request_and_parse_data(params)
            nombre_api = parse_api_response(raw_data)
            
            if nombre_api:
                cache_dict[_id] = nombre_api
                add_to_historic(json.dumps({"cedula": _id, "nombre": nombre_api}))
                selected_token.current_usage += 1
                results.append({"cedula": _id, "nombre": nombre_api, "status": "API"})
            
            token_index = (token_index + 1) % len(token_list)
            time.sleep(0.3) 
            
        except Exception as e:
            id_no_procesados.append(_id)
            print(f"Error en ID {_id}: {e}")

    if not id_no_procesados and os.path.exists(PENDIENTES_PATH):
        os.remove(PENDIENTES_PATH)
        
    return results


# --- PERSISTENCIA ---

def add_to_historic(json_line, historial_path=HISTORIC_PATH):
    with open(historial_path, "a", encoding="utf-8") as file:
        file.write(json_line + "\n")


def guardar_pendientes(lista_pendientes):
    """Guarda las cédulas que no se pudieron procesar por falta de tokens o error."""
    # Usamos 'w' porque cada vez que guardamos, es la lista nueva de lo que quedó fuera
    with open(PENDIENTES_PATH, "w") as file:
        for _id in lista_pendientes:
            file.write(json.dumps({"cedula": _id, "timestamp": time.time()}) + "\n")


def cargar_pendientes():
    """Carga la lista de cédulas que quedaron a medias en la sesión anterior."""
    if not os.path.exists(PENDIENTES_PATH):
        return []
    
    pendientes = []
    with open(PENDIENTES_PATH, "r") as file:
        for line in file:
            item = json.loads(line)
            pendientes.append(item["cedula"])
    return pendientes

def comparar_nombres(nombre_usuario, nombre_api):
    """Lógica: Case Insensitive y contención de palabras."""
    if not nombre_api or nombre_api == "NO ENCONTRADO":
        return "NO ENCONTRADO"
    if not nombre_usuario or str(nombre_usuario).strip() == "nan" or str(nombre_usuario).strip() == "":
        return "SIN NOMBRE EN LISTA"
        
    u_raw = str(nombre_usuario).upper()
    a_raw = str(nombre_api).upper()
    palabras_usuario = u_raw.split()
    
    if not palabras_usuario: return "ERROR INPUT"

    coinciden_todas = all(p in a_raw for p in palabras_usuario)
    return "IGUAL" if coinciden_todas else "REVISAR"


def procesar_cedula_individual(_id, tokens, cache_dict, token_idx, nombres_ref, modo):
    """
    Esta función procesa UNA sola cédula. 
    Retorna: (nueva_fila, nuevo_token_idx, origen)
    """
    origen = ""
    nombre_api = ""
    
    # 1. Caché
    if _id in cache_dict:
        nombre_api = cache_dict[_id]
        origen = "Caché"
    else:
        # 2. API (Rotación de tokens)
        tokens_con_cupo = [t for t in tokens if t.has_capacity()]
        if not tokens_con_cupo:
            return None, token_idx, "Agotado"
            
        while not tokens[token_idx].has_capacity():
            token_idx = (token_idx + 1) % len(tokens)
        
        selected_token = tokens[token_idx]
        params = selected_token.get_credentials()
        params.update({"cedula": _id, "nacionalidad": "V"})
        
        raw_data = api_request_and_parse_data(params)
        nombre_api = parse_api_response(raw_data)
        
        if nombre_api:
            cache_dict[_id] = nombre_api
            add_to_historic(json.dumps({"cedula": _id, "nombre": nombre_api}))
            selected_token.current_usage += 1
            origen = "API"
            time.sleep(0.3)
        else:
            nombre_api = "NO ENCONTRADO"
            origen = "No existe"
            
        token_idx = (token_idx + 1) % len(tokens)

    # 3. Construir Fila
    res_row = {"Cédula": _id, "Nombre API": nombre_api, "Fuente": origen}
    if modo == "Comparar con mi lista" and nombres_ref:
        n_usuario = nombres_ref.get(_id, "")
        res_row["Tu Lista"] = n_usuario
        res_row["Resultado"] = comparar_nombres(n_usuario, nombre_api)
        
    return res_row, token_idx, origen

def process_full_list(id_list, tokens, cache_dict, nombres_ref=None, modo="Solo Consultar"):
    """
    ESTA ES LA FUNCIÓN QUE LLAMA EL FRONT.
    Une Caché, API y Comparación en un solo paso.
    """
    # 1. Separar qué está en caché y qué no
    cached, non_cached = is_id_in_cache(id_list, cache_dict)
    
    final_results = []
    
    # 2. Procesar lo que está en Caché
    for _id in cached:
        nombre_api = cache_dict[_id]
        fila = {"Cédula": _id, "Nombre API": nombre_api, "Fuente": "Caché"}
        
        if modo == "Comparar con mi lista" and nombres_ref:
            nom_usr = nombres_ref.get(_id, "")
            fila["Tu Lista"] = nom_usr
            fila["Resultado"] = comparar_nombres(nom_usr, nombre_api)
        
        final_results.append(fila)
        
    # 3. Procesar lo que NO está en Caché (llamando a la API)
    if non_cached:
        api_data = manage_api_requests(non_cached, tokens, cache_dict)
        for item in api_data:
            nombre_api = item["nombre"]
            fila = {"Cédula": item["cedula"], "Nombre API": nombre_api, "Fuente": "API"}
            
            if modo == "Comparar con mi lista" and nombres_ref:
                nom_usr = nombres_ref.get(item["cedula"], "")
                fila["Tu Lista"] = nom_usr
                fila["Resultado"] = comparar_nombres(nom_usr, nombre_api)
            
            final_results.append(fila)
            
    return final_results

