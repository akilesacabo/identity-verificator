import json
import requests
import time
import os 
from fuzzywuzzy import fuzz
import toml



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

def parse_api_response(data):
    """Convierte el JSON de la API en un nombre completo string."""
    d = data.get("data", {})
    if not d: return None
    full_name = f"{d.get('primer_nombre', '')} {d.get('segundo_nombre', '')} {d.get('primer_apellido', '')} {d.get('segundo_apellido', '')}"
    return " ".join(full_name.split()).upper()

def api_request_and_parse_data(query_params, api_url="https://api.cedula.com.ve/api/v1"):
    """Realiza la llamada HTTP GET a la API."""
    try:
        # Los query_params ya contienen app_id, token, cedula y nacionalidad
        response = requests.get(api_url, params=query_params, timeout=10)
        
        # Si la API responde con error de rate limit (429) o similar
        if response.status_code != 200:
            print(f"Error API: Código {response.status_code}")
            return {}
            
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Fallo de conexión: {e}")
        return {}

def add_to_historic(json_line, historial_path="historic.jsonl"):
    """Escribe una nueva línea en el histórico (Append mode)."""
    # json_line ya viene como string desde manage_api_requests
    with open(historial_path, "a", encoding="utf-8") as file:
        file.write(json_line + "\n")

def normalizar_cedula(input_id):
    """
    Limpia la cédula: quita puntos, espacios y letras.
    Retorna solo los dígitos.
    """
    import re
    # Convertir a string y extraer solo los números
    solo_numeros = re.sub(r'\D', '', str(input_id))
    return solo_numeros


def process_full_list(id_list, tokens, cache_dict):
    """Función principal que une Caché + API."""
    cached, non_cached = is_id_in_cache(id_list, cache_dict)
    
    final_data = []
    
    # Recuperar de Caché
    for _id in cached:
        final_data.append({"cedula": _id, "nombre": cache_dict[_id], "status": "Cache"})
        
    # Recuperar de API
    if non_cached:
        api_results = manage_api_requests(non_cached, tokens, cache_dict)
        final_data.extend(api_results)
        
    return final_data



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

def manage_api_requests(non_cached_ids, tokens, cache_dict):
    results = []
    token_list = tokens
    token_index = 0
    
    # Lista para rastrear qué NO se pudo procesar
    id_no_procesados = []

    for i, _id in enumerate(non_cached_ids):
        # 1. Verificar si todavía hay algún token con capacidad
        tokens_con_cupo = [t for t in token_list if t.has_capacity()]
        
        if not tokens_con_cupo:
            # Si no hay cupo, guardamos el resto de la lista y salimos
            id_no_procesados = non_cached_ids[i:]
            print(f"Capacidad agotada. Guardando {len(id_no_procesados)} pendientes.")
            guardar_pendientes(id_no_procesados)
            break

        # 2. Seleccionar el siguiente token con capacidad (Round Robin)
        while not token_list[token_index].has_capacity():
            token_index = (token_index + 1) % len(token_list)
        
        selected_token = token_list[token_index]
        
        # 3. Petición y Procesamiento
        try:
            params = selected_token.get_credentials()
            params["cedula"] = _id
            params["nacionalidad"] = "V"
            
            raw_data = api_request_and_parse_data(params)
            nombre_api = parse_api_response(raw_data)
            
            if nombre_api:
                # Actualizar caché y disco
                cache_dict[_id] = nombre_api
                add_to_historic(json.dumps({"cedula": _id, "nombre": nombre_api}))
                selected_token.current_usage += 1
                results.append({"cedula": _id, "nombre": nombre_api, "status": "API"})
            
            token_index = (token_index + 1) % len(token_list)
            time.sleep(0.3) # Respetar el servidor
            
        except Exception as e:
            # Si hay un error de red, también lo mandamos a pendientes para no perderlo
            id_no_procesados.append(_id)
            print(f"Error en ID {_id}, se reintentará luego.")

    # Si terminamos la lista completa con éxito, borramos el archivo de pendientes
    if not id_no_procesados and os.path.exists(PENDIENTES_PATH):
        os.remove(PENDIENTES_PATH)
        
    return results


def comparar_nombres(nombre_usuario, nombre_api):
    """
    Compara dos strings y devuelve el nivel de similitud.
    """
    if not nombre_api:
        return "NO ENCONTRADO", 0
        
    # Limpieza básica para mejorar la comparación
    n1 = nombre_usuario.strip().upper()
    n2 = nombre_api.strip().upper()
    
    # token_sort_ratio ignora el orden de las palabras (ej. "Perez Juan" vs "Juan Perez")
    score = fuzz.token_sort_ratio(n1, n2)
    
    if score >= 90:
        return "IGUAL", score
    elif score >= 65:
        return "REVISAR", score
    else:
        return "DIFERENTE", score
    

def inicializar_sistema(historial_path="historic.jsonl"):
    """
    Carga el historial existente en memoria al arrancar.
    """
    cache = {}
    if os.path.exists(historial_path):
        with open(historial_path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    item = json.loads(line)
                    # Mapeamos cedula -> nombre para búsqueda rápida O(1)
                    cache[str(item["cedula"])] = item["nombre"]
                except:
                    continue
    return cache