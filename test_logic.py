import pandas as pd
import unicodedata
import re

# --- TU LÓGICA DE CONTENCIÓN ---
def normalizar_sustituir(texto):
    """Limpia tildes, caracteres especiales y vectoriza palabras."""
    if not texto or pd.isna(texto): return set()
    # 1. Quitar tildes
    texto = unicodedata.normalize('NFD', str(texto))
    texto = "".join([c for c in texto if unicodedata.category(c) != 'Mn'])
    # 2. Mayúsculas y limpiar basura
    texto = re.sub(r'[^A-Z0-9\s]', '', texto.upper())
    # 3. Vectorizar (Palabras de más de 2 letras o conectores clave)
    palabras = [p for p in texto.split() if len(p) > 2 or p in ["DE", "LA"]]
    return set(palabras)

def clasificador_contencion(row):
    nombre_usuario = row['Tu Lista']
    nombre_api = row['Nombre API']
    
    if not nombre_api or nombre_api == "NO ENCONTRADO":
        return "NO ENCONTRADO", 0, ""

    tokens_u = normalizar_sustituir(nombre_usuario)
    tokens_a = normalizar_sustituir(nombre_api)
    
    if not tokens_u:
        return "ERROR INPUT", 0, ""

    # Lógica de contención
    encontrados = [p for p in tokens_u if p in tokens_a]
    faltantes = [p for p in tokens_u if p not in tokens_a]
    
    porcentaje = len(encontrados) / len(tokens_u)
    
    # Clasificación
    if porcentaje == 1.0:
        res = "IGUAL"
    elif porcentaje >= 0.5:
        res = "REVISAR"
    else:
        res = "DIFERENTE"
        
    return res, int(porcentaje * 100), ", ".join(faltantes)

# --- EJECUCIÓN DEL TEST ---
def run_test():
    # 1. Cargar tu archivo
    try:
        df = pd.read_csv('resultados.csv')
    except Exception as e:
        print(f"Error: Asegúrate de que 'resultados.csv' esté en la misma carpeta. {e}")
        return

    print(f"Analizando {len(df)} registros con la nueva lógica...\n")

    # 2. Aplicar el clasificador
    df[['Nuevo Resultado', 'Confianza %', 'Faltó en API']] = df.apply(
        lambda row: pd.Series(clasificador_contencion(row)), axis=1
    )

    # 3. Mostrar casos que ANTES fallaban y AHORA son IGUAL
    # (Filtramos donde tu archivo viejo decía REVISAR/DIFERENTE pero el nuevo dice IGUAL)
    mejorados = df[(df['Resultado'] != 'IGUAL') & (df['Nuevo Resultado'] == 'IGUAL')]
    
    print(f"✅ Se corrigieron {len(mejorados)} registros que antes daban error.")
    print("-" * 50)
    
    if not mejorados.empty:
        print(mejorados[['Tu Lista', 'Nombre API', 'Nuevo Resultado']].head(10))
    
    # 4. Guardar para que lo veas
    df.to_csv('test_mejorado.csv', index=False)
    print("\n🚀 Archivo 'test_mejorado.csv' generado para revisión.")

if __name__ == "__main__":
    run_test()