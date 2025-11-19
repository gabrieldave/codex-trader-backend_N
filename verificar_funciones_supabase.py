"""
Script para verificar funciones en Supabase.
Verifica que match_documents_hybrid NO existe y que match_documents_384 SÍ existe.
"""
import os
import sys
from urllib.parse import quote_plus

def get_env(key):
    """Obtiene variable de entorno limpiando comillas"""
    value = os.environ.get(key)
    if value is None:
        return None
    return value.strip('"').strip("'").strip()

# Intentar cargar desde .env si existe
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Obtener variables de entorno
SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    print("ERROR: Faltan variables de entorno SUPABASE_URL o SUPABASE_DB_PASSWORD")
    print("   Asegurate de tener estas variables configuradas en tu entorno")
    print("   o en un archivo .env en el directorio del proyecto")
    sys.exit(1)

# Construir cadena de conexión PostgreSQL
project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

print("=" * 70)
print("VERIFICANDO FUNCIONES EN SUPABASE")
print("=" * 70)
print()

try:
    import psycopg2
    
    # Conectar a la base de datos
    print("Conectando a Supabase...")
    conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
    cur = conn.cursor()
    print("OK: Conexion establecida\n")
    
    # Verificar que match_documents_hybrid NO existe
    print("1. Verificando que match_documents_hybrid NO existe...")
    cur.execute("""
        SELECT proname, pronargs 
        FROM pg_proc 
        WHERE proname = 'match_documents_hybrid'
    """)
    hybrid_result = cur.fetchall()
    
    if len(hybrid_result) == 0:
        print("   OK: match_documents_hybrid NO existe (esta eliminada)")
    else:
        print(f"   ADVERTENCIA: match_documents_hybrid AUN EXISTE ({len(hybrid_result)} version/es)")
        for row in hybrid_result:
            print(f"      - {row[0]} con {row[1]} argumentos")
    print()
    
    # Verificar que match_documents_384 SI existe
    print("2. Verificando que match_documents_384 SI existe...")
    cur.execute("""
        SELECT proname, pronargs 
        FROM pg_proc 
        WHERE proname = 'match_documents_384'
    """)
    semantic_result = cur.fetchall()
    
    if len(semantic_result) > 0:
        print(f"   OK: match_documents_384 existe ({len(semantic_result)} version/es)")
        for row in semantic_result:
            print(f"      - {row[0]} con {row[1]} argumentos")
    else:
        print("   ERROR: match_documents_384 NO existe (necesita ser creada)")
    print()
    
    # Resumen
    print("=" * 70)
    print("RESUMEN:")
    print("=" * 70)
    if len(hybrid_result) == 0 and len(semantic_result) > 0:
        print("TODO CORRECTO:")
        print("   - match_documents_hybrid: Eliminada [OK]")
        print("   - match_documents_384: Existe [OK]")
        print("\nEl sistema esta listo para funcionar correctamente")
    elif len(hybrid_result) > 0:
        print("ACCION REQUERIDA:")
        print("   - match_documents_hybrid: Aun existe (debe eliminarse)")
        print("   - Ejecuta el script ELIMINAR_FUNCION_HIBRIDA.sql en Supabase")
    else:
        print("PROBLEMA DETECTADO:")
        print("   - match_documents_384 no existe")
        print("   - Necesitas crear la funcion match_documents_384")
    
    cur.close()
    conn.close()
    
except ImportError:
    print("ERROR: psycopg2 no esta instalado")
    print("   Instala con: pip install psycopg2-binary")
    sys.exit(1)
except Exception as e:
    print(f"ERROR conectando a Supabase: {e}")
    sys.exit(1)

