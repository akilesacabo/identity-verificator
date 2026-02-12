from utils import (
    Token, inicializar_sistema, process_full_list, 
    normalizar_cedula, comparar_nombres, cargar_configuracion
)
import os

def run_tests():
    print("--- 1. Probando Normalización ---")
    c_sucio = "V-12.345.678 "
    c_limpio = normalizar_cedula(c_sucio)
    print(f"Input: {c_sucio} -> Output: {c_limpio}")
    assert c_limpio == "12345678"

    print("\n--- 2. Probando Carga de Configuración ---")
    # Asegúrate de tener el archivo .streamlit/secrets.toml creado
    tokens = cargar_configuracion()
    print(f"Tokens cargados: {len(tokens)}")
    for i, t in enumerate(tokens):
        print(f"Token {i+1}: ID={t.app_id} Capacidad={t.capacity}")

    print("\n--- 3. Probando Comparación de Nombres ---")
    n_user = "JUAN PEREZ"
    n_api = "JUAN ALBERTO PEREZ"
    resultado, score = comparar_nombres(n_user, n_api)
    print(f"Comparando '{n_user}' vs '{n_api}': {resultado} ({score}%)")

    print("\n--- 4. Probando Motor Completo (Caché + API) ---")
    # Simulamos un caché inicial
    cache_falso = {"11222333": "PEDRO PEREZ"}
    
    # Lista de prueba: una en caché, una nueva (API), una inválida
    lista_test = ["11222333", "26000000", "V-1"] 
    
    print(f"Procesando lista: {lista_test}")
    # Nota: Esto intentará llamar a la API real para '26000000'
    resultados = process_full_list(lista_test, tokens, cache_falso)
    
    for r in resultados:
        print(f"Resultado: Cedula={r['cedula']}, Nombre={r['nombre']}, Origen={r['status']}")

    print("\n--- 5. Verificando Persistencia ---")
    if os.path.exists("historic.jsonl"):
        print("OK: Se creó/actualizó 'historic.jsonl'")
    if os.path.exists("pendientes.jsonl"):
        print("AVISO: Hay pendientes guardados en 'pendientes.jsonl'")

if __name__ == "__main__":
    # Crea un dummy secrets si no existe para la prueba
    if not os.path.exists(".streamlit/secrets.toml"):
        print("ERROR: Crea .streamlit/secrets.toml antes de testear.")
    else:
        run_tests()