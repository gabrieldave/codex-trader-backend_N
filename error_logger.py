"""
🔴 LOGGING PROFESIONAL DE ERRORES EN SUPABASE
==============================================

Registra errores de ingesta en una tabla dedicada de Supabase
para análisis y diagnóstico posterior.
"""

import os
import sys
import traceback
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Dict, Any
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

load_dotenv()

def get_env(key):
    value = os.getenv(key, "")
    if not value:
        for env_key in os.environ.keys():
            if env_key.strip().lstrip('\ufeff') == key:
                value = os.environ[env_key]
                break
    return value.strip('"').strip("'").strip()

SUPABASE_URL = get_env("SUPABASE_URL")
SUPABASE_DB_PASSWORD = get_env("SUPABASE_DB_PASSWORD")

if not SUPABASE_URL or not SUPABASE_DB_PASSWORD:
    raise ValueError("Faltan variables de entorno necesarias")

project_ref = SUPABASE_URL.replace("https://", "").replace(".supabase.co", "")
encoded_password = quote_plus(SUPABASE_DB_PASSWORD)
postgres_connection_string = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# ============================================================================
# CREACIÓN DE TABLA DE ERRORES
# ============================================================================

def ensure_errors_table():
    """Asegura que la tabla ingestion_errors existe en Supabase"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Crear tabla ingestion_errors si no existe
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ingestion_errors (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                doc_id TEXT,
                filename TEXT NOT NULL,
                error_type TEXT NOT NULL,
                error_message TEXT NOT NULL,
                traceback TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Crear índices para búsquedas rápidas
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_doc_id 
            ON ingestion_errors(doc_id)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_filename 
            ON ingestion_errors(filename)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_error_type 
            ON ingestion_errors(error_type)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_errors_created_at 
            ON ingestion_errors(created_at)
        """)
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Error creando tabla ingestion_errors: {e}")
        return False

# ============================================================================
# TIPOS DE ERRORES
# ============================================================================

class ErrorType:
    """Tipos de errores estándar"""
    PDF_PARSE_ERROR = "PDF_PARSE_ERROR"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
    CHUNKING_ERROR = "CHUNKING_ERROR"
    OPENAI_ERROR = "OPENAI_ERROR"
    RATE_LIMIT_ERROR = "RATE_LIMIT_ERROR"
    SUPABASE_ERROR = "SUPABASE_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    HASH_ERROR = "HASH_ERROR"
    METADATA_ERROR = "METADATA_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

# ============================================================================
# REGISTRO DE ERRORES
# ============================================================================

def log_error(
    filename: str,
    error_type: str,
    error_message: str,
    doc_id: Optional[str] = None,
    traceback_text: Optional[str] = None,
    exception: Optional[Exception] = None
) -> bool:
    """
    Registra un error en la tabla ingestion_errors
    
    Args:
        filename: Nombre del archivo que causó el error
        error_type: Tipo de error (usar ErrorType)
        error_message: Mensaje descriptivo del error
        doc_id: ID del documento (opcional)
        traceback_text: Traceback completo (opcional)
        exception: Excepción capturada (opcional, se usará para generar traceback)
        
    Returns:
        True si se registró exitosamente, False en caso contrario
    """
    try:
        # Generar traceback si se proporcionó una excepción
        if exception and not traceback_text:
            traceback_text = ''.join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            ))
        
        # Limitar tamaño del traceback (máximo 10,000 caracteres)
        if traceback_text and len(traceback_text) > 10000:
            traceback_text = traceback_text[:10000] + "\n... (truncado)"
        
        # Limitar tamaño del mensaje (máximo 5,000 caracteres)
        if len(error_message) > 5000:
            error_message = error_message[:5000] + "... (truncado)"
        
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO ingestion_errors (doc_id, filename, error_type, error_message, traceback, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
        """, (doc_id, filename, error_type, error_message, traceback_text))
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        # Si falla el logging, al menos imprimir en consola
        print(f"⚠️  Error al registrar error en Supabase: {e}")
        print(f"   Archivo: {filename}")
        print(f"   Tipo: {error_type}")
        print(f"   Mensaje: {error_message}")
        return False

# ============================================================================
# CONSULTAS DE ERRORES
# ============================================================================

def get_error_summary() -> Dict[str, Any]:
    """
    Obtiene un resumen de errores de ingesta
    
    Returns:
        Dict con estadísticas de errores
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Total de errores
        cur.execute("SELECT COUNT(*) as total FROM ingestion_errors")
        total_errors = cur.fetchone()['total']
        
        # Archivos afectados (únicos)
        cur.execute("SELECT COUNT(DISTINCT filename) as unique_files FROM ingestion_errors")
        unique_files = cur.fetchone()['unique_files']
        
        # Conteo por tipo de error
        cur.execute("""
            SELECT error_type, COUNT(*) as count
            FROM ingestion_errors
            GROUP BY error_type
            ORDER BY count DESC
        """)
        errors_by_type = {row['error_type']: row['count'] for row in cur.fetchall()}
        
        cur.close()
        conn.close()
        
        return {
            'total_errors': total_errors,
            'unique_files_affected': unique_files,
            'errors_by_type': errors_by_type
        }
    except Exception as e:
        print(f"⚠️  Error obteniendo resumen de errores: {e}")
        return {
            'total_errors': 0,
            'unique_files_affected': 0,
            'errors_by_type': {}
        }

def get_recent_errors(limit: int = 20) -> list:
    """
    Obtiene los errores más recientes
    
    Args:
        limit: Número máximo de errores a devolver
        
    Returns:
        Lista de dicts con información de errores
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT doc_id, filename, error_type, error_message, created_at
            FROM ingestion_errors
            ORDER BY created_at DESC
            LIMIT %s
        """, (limit,))
        
        errors = [dict(row) for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return errors
    except Exception as e:
        print(f"⚠️  Error obteniendo errores recientes: {e}")
        return []

















