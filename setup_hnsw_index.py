#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para crear índice HNSW en Supabase de forma segura y monitoreada.
Ejecuta el flujo completo: verificación, limpieza, creación y validación.
"""

import os
import sys
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
import re

# Configurar codificación UTF-8 para Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Cargar variables de entorno
load_dotenv()

# ============================================================================
# FASE 1: VERIFICAR/CONFIGURAR CONEXIÓN
# ============================================================================

def get_db_url():
    """Obtiene SUPABASE_DB_URL desde .env o lo solicita al usuario"""
    db_url = os.getenv("SUPABASE_DB_URL")
    
    if not db_url:
        print("⚠️  SUPABASE_DB_URL no encontrado en .env")
        db_url = input("Pega tu SUPABASE_DB_URL (postgresql://...): ").strip()
        
        if not db_url:
            print("❌ Error: URL de base de datos requerida")
            sys.exit(1)
    
    return db_url

def connect_to_db(db_url):
    """Conecta a Supabase con autocommit=True"""
    try:
        print("🔌 Conectando a Supabase...")
        conn = psycopg2.connect(db_url, connect_timeout=10)
        conn.autocommit = True
        print("✅ Conexión establecida\n")
        return conn
    except Exception as e:
        print(f"❌ Error conectando a la base de datos: {e}")
        sys.exit(1)

# ============================================================================
# FASE 2: LIMPIEZA (si existe índice corrupto)
# ============================================================================

def cleanup_indexes(conn):
    """Elimina índices existentes si existen"""
    cur = conn.cursor()
    
    print("🧹 Limpiando índices existentes...")
    
    try:
        cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_m32_ef64")
        print("   ✓ Eliminado: knowledge_vec_idx_hnsw_m32_ef64")
    except Exception as e:
        print(f"   ⚠️  Error eliminando knowledge_vec_idx_hnsw_m32_ef64: {e}")
    
    try:
        cur.execute("DROP INDEX IF EXISTS vecs.knowledge_vec_idx_hnsw_safe")
        print("   ✓ Eliminado: knowledge_vec_idx_hnsw_safe")
    except Exception as e:
        print(f"   ⚠️  Error eliminando knowledge_vec_idx_hnsw_safe: {e}")
    
    cur.close()
    print("✅ Limpieza completada\n")

# ============================================================================
# FASE 3: CREAR ÍNDICE SEGURO CON MONITOREO
# ============================================================================

def format_size(bytes_size):
    """Formatea el tamaño en bytes a formato legible"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"

def get_index_size(conn, index_name):
    """Obtiene el tamaño actual del índice"""
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT pg_relation_size(%s::regclass) as size
        """, (index_name,))
        result = cur.fetchone()
        cur.close()
        return result[0] if result else 0
    except Exception:
        return 0

def create_index_safe(conn):
    """Crea el índice HNSW de forma segura con monitoreo"""
    print("🚀 Creando índice HNSW (m=16)... ESTO TARDA 5-8 MINUTOS")
    print("   (Monitoreando progreso cada 30 segundos...)\n")
    
    index_name = "vecs.knowledge_vec_idx_hnsw_safe"
    
    try:
        # CREATE INDEX CONCURRENTLY se ejecuta de forma asíncrona
        # Necesitamos ejecutarlo y luego monitorear su progreso
        create_query = """
            CREATE INDEX CONCURRENTLY knowledge_vec_idx_hnsw_safe 
            ON vecs.knowledge 
            USING hnsw (vec vector_cosine_ops) 
            WITH (m = 16, ef_construction = 64)
        """
        
        # Ejecutar en un hilo separado para poder monitorear
        import threading
        import queue
        
        error_queue = queue.Queue()
        done_event = threading.Event()
        
        def create_index():
            try:
                cur = conn.cursor()
                # Desactivar timeout para CREATE INDEX CONCURRENTLY
                cur.execute("SET statement_timeout = 0")
                cur.execute(create_query)
                cur.close()
                done_event.set()
            except Exception as e:
                error_queue.put(e)
                done_event.set()
        
        thread = threading.Thread(target=create_index)
        thread.daemon = True
        thread.start()
        
        # Monitorear mientras se crea
        start_time = time.time()
        last_size = 0
        no_change_count = 0
        
        while not done_event.is_set():
            time.sleep(30)  # Esperar 30 segundos entre verificaciones
            
            elapsed = int(time.time() - start_time)
            
            # Verificar si el índice existe y está listo
            try:
                check_cur = conn.cursor()
                check_cur.execute("""
                    SELECT indisready, indisvalid
                    FROM pg_index 
                    WHERE indexrelid = %s::regclass
                """, (index_name,))
                result = check_cur.fetchone()
                check_cur.close()
                
                if result:
                    indisready, indisvalid = result
                    if indisready:  # Índice está listo
                        print(f"   ✓ Índice listo para usar (Tiempo: {elapsed}s)")
                        break
            except Exception:
                # Índice aún no existe, continuar monitoreando tamaño
                pass
            
            # Monitorear tamaño del índice (si existe)
            current_size = get_index_size(conn, index_name)
            
            if current_size > 0:
                print(f"   Progreso: {format_size(current_size)} - Tiempo: {elapsed}s")
                
                # Si el tamaño no cambió, incrementar contador
                if current_size == last_size:
                    no_change_count += 1
                else:
                    no_change_count = 0
                    last_size = current_size
            else:
                print(f"   Iniciando creación... - Tiempo: {elapsed}s")
        
        # Esperar a que termine el hilo (puede tardar un poco más)
        thread.join(timeout=30)
        
        # Verificar errores
        if not error_queue.empty():
            error = error_queue.get()
            raise error
        
        print("\n✅ Índice creado\n")
        
    except Exception as e:
        print(f"\n❌ Error durante la creación del índice: {e}")
        raise

# ============================================================================
# FASE 4: VERIFICACIÓN FINAL
# ============================================================================

def verify_index(conn):
    """Verifica que el índice sea válido y funcional"""
    cur = conn.cursor()
    index_name = "vecs.knowledge_vec_idx_hnsw_safe"
    
    print("🔍 Verificando índice...")
    
    try:
        # Verificar si el índice es válido
        cur.execute("""
            SELECT indisvalid 
            FROM pg_index 
            WHERE indexrelid = %s::regclass
        """, (index_name,))
        
        result = cur.fetchone()
        
        if not result:
            print("❌ Índice no encontrado")
            cur.close()
            return False
        
        is_valid = result[0]
        
        if is_valid:
            print("✅ ÍNDICE VÁLIDO Y FUNCIONAL\n")
            
            # Prueba de velocidad
            print("⚡ Ejecutando prueba de velocidad...")
            
            # Obtener un vector de ejemplo para la prueba
            cur.execute("""
                SELECT vec 
                FROM vecs.knowledge 
                WHERE vec IS NOT NULL 
                LIMIT 1
            """)
            
            example_vec = cur.fetchone()
            
            if example_vec:
                # Ejecutar EXPLAIN ANALYZE con búsqueda vectorial
                cur.execute("""
                    EXPLAIN (ANALYZE, TIMING, BUFFERS) 
                    SELECT id, metadata, 1 - (vec <=> %s::vector) as similarity
                    FROM vecs.knowledge
                    WHERE vec IS NOT NULL
                    ORDER BY vec <=> %s::vector
                    LIMIT 8
                """, (example_vec[0], example_vec[0]))
                
                explain_result = cur.fetchall()
                
                # Buscar el tiempo de ejecución en el resultado
                execution_time = None
                for row in explain_result:
                    row_str = str(row[0])
                    if "Execution Time:" in row_str:
                        # Extraer el tiempo
                        match = re.search(r'Execution Time:\s*([\d.]+)\s*ms', row_str)
                        if match:
                            execution_time = float(match.group(1))
                            break
                
                if execution_time:
                    print(f"   ⚡ Execution Time: {execution_time:.2f} ms")
                else:
                    print("   ⚡ Prueba completada (ver detalles arriba)")
                
                # Mostrar algunos detalles del plan
                print("\n   Plan de ejecución:")
                for row in explain_result[:5]:  # Mostrar primeras 5 líneas
                    print(f"   {row[0]}")
            
            cur.close()
            return True
        else:
            print("❌ ÍNDICE INVÁLIDO - Se requiere intervención manual")
            cur.close()
            return False
            
    except Exception as e:
        print(f"❌ Error verificando índice: {e}")
        cur.close()
        return False

# ============================================================================
# FUNCIÓN PRINCIPAL
# ============================================================================

def main():
    """Ejecuta el flujo completo"""
    print("=" * 60)
    print("🔧 SETUP ÍNDICE HNSW - SUPABASE")
    print("=" * 60)
    print()
    
    # FASE 1: Conexión
    db_url = get_db_url()
    conn = connect_to_db(db_url)
    
    try:
        # FASE 2: Limpieza
        cleanup_indexes(conn)
        
        # FASE 3: Crear índice
        create_index_safe(conn)
        
        # FASE 4: Verificación
        verify_index(conn)
        
        print("\n" + "=" * 60)
        print("✅ PROCESO COMPLETADO")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Proceso interrumpido por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error durante el proceso: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
        print("\n🔌 Conexión cerrada")

if __name__ == "__main__":
    main()

