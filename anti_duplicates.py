"""
🔒 SISTEMA ANTI-DUPLICADOS PARA INGESTA RAG
===========================================

Sistema robusto de detección y prevención de duplicados basado en:
- Hash SHA256 del contenido del archivo
- Tabla de documentos en Supabase
- Chunk IDs determinísticos
"""

import os
import sys
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from typing import Optional, Tuple, Dict
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
# CONFIGURACIÓN
# ============================================================================

# Flag para forzar reindexación (configurable mediante variable de entorno)
FORCE_REINDEX = os.getenv("FORCE_REINDEX", "false").lower() == "true"

# ============================================================================
# CREACIÓN DE TABLA DE DOCUMENTOS
# ============================================================================

def ensure_documents_table():
    """Asegura que la tabla documents existe en Supabase"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Crear tabla documents si no existe (con metadatos ricos)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                doc_id TEXT PRIMARY KEY,
                filename TEXT NOT NULL,
                file_path TEXT,
                title TEXT,
                author TEXT,
                language TEXT DEFAULT 'unknown',
                category TEXT DEFAULT 'general',
                published_year INTEGER,
                hash_method TEXT DEFAULT 'sha256',
                total_chunks INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        
        # Agregar columnas nuevas si no existen (para migración de tablas existentes)
        try:
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS author TEXT")
        except:
            pass
        
        try:
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS language TEXT DEFAULT 'unknown'")
        except:
            pass
        
        try:
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general'")
        except:
            pass
        
        try:
            cur.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS published_year INTEGER")
        except:
            pass
        
        # Crear índices para búsquedas rápidas
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_filename 
            ON documents(filename)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_created_at 
            ON documents(created_at)
        """)
        
        # Índices para filtros de búsqueda
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_language 
            ON documents(language)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_category 
            ON documents(category)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_author 
            ON documents(author)
        """)
        
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_documents_published_year 
            ON documents(published_year)
        """)
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Error creando tabla documents: {e}")
        return False

# ============================================================================
# FUNCIONES DE HASH
# ============================================================================

def calculate_file_hash(file_path: str) -> str:
    """
    Calcula hash SHA256 del archivo
    
    Args:
        file_path: Ruta del archivo
        
    Returns:
        Hash SHA256 en hexadecimal
    """
    sha256_hash = hashlib.sha256()
    
    try:
        with open(file_path, "rb") as f:
            # Leer archivo en chunks para archivos grandes
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        raise Exception(f"Error calculando hash del archivo: {e}")

def calculate_content_hash(content: str) -> str:
    """
    Calcula hash SHA256 del contenido de texto normalizado
    
    Args:
        content: Contenido de texto
        
    Returns:
        Hash SHA256 en hexadecimal
    """
    # Normalizar: eliminar espacios extra, convertir a minúsculas
    normalized = " ".join(content.split()).lower().strip()
    return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

def calculate_doc_id(file_path: str, use_content_hash: bool = False, content: Optional[str] = None) -> str:
    """
    Calcula doc_id único para un documento
    
    Por defecto usa hash del archivo (más rápido).
    Si use_content_hash=True, usa hash del contenido (más robusto para detectar contenido duplicado).
    
    Args:
        file_path: Ruta del archivo
        use_content_hash: Si True, usa hash del contenido en lugar del archivo
        content: Contenido de texto (requerido si use_content_hash=True)
        
    Returns:
        doc_id único
    """
    if use_content_hash and content:
        return calculate_content_hash(content)
    else:
        return calculate_file_hash(file_path)

def calculate_chunk_id(doc_id: str, chunk_index: int, chunk_content: str) -> str:
    """
    Calcula chunk_id determinístico para un chunk
    
    Args:
        doc_id: ID del documento
        chunk_index: Índice del chunk
        chunk_content: Contenido del chunk (normalizado)
        
    Returns:
        chunk_id único
    """
    # Normalizar contenido del chunk
    normalized_content = " ".join(chunk_content.split()).lower().strip()
    
    # Combinar: doc_id + índice + contenido
    combined = f"{doc_id}:{chunk_index}:{normalized_content}"
    
    return hashlib.sha256(combined.encode('utf-8')).hexdigest()

# ============================================================================
# VERIFICACIÓN DE DUPLICADOS
# ============================================================================

def check_document_exists(doc_id: str) -> Tuple[bool, Optional[Dict]]:
    """
    Verifica si un documento ya existe en la base de datos
    
    Args:
        doc_id: ID del documento a verificar
        
    Returns:
        (exists, document_info) donde document_info es None si no existe
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT doc_id, filename, file_path, title, total_chunks, created_at, updated_at
            FROM documents
            WHERE doc_id = %s
        """, (doc_id,))
        
        result = cur.fetchone()
        cur.close()
        conn.close()
        
        if result:
            return True, dict(result)
        return False, None
        
    except Exception as e:
        print(f"⚠️  Error verificando documento: {e}")
        return False, None

def register_document(
    doc_id: str, 
    filename: str, 
    file_path: str, 
    title: Optional[str] = None,
    author: Optional[str] = None,
    language: Optional[str] = None,
    category: Optional[str] = None,
    published_year: Optional[int] = None,
    total_chunks: int = 0
):
    """
    Registra un nuevo documento en la tabla documents con metadatos ricos
    
    Args:
        doc_id: ID único del documento
        filename: Nombre del archivo
        file_path: Ruta completa del archivo
        title: Título del documento (opcional)
        author: Autor del documento (opcional)
        language: Idioma del documento (opcional)
        category: Categoría/tema del documento (opcional)
        published_year: Año de publicación (opcional)
        total_chunks: Número total de chunks
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO documents (
                doc_id, filename, file_path, title, author, language, category, 
                published_year, total_chunks, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
            ON CONFLICT (doc_id) 
            DO UPDATE SET 
                updated_at = NOW(),
                total_chunks = EXCLUDED.total_chunks,
                title = COALESCE(EXCLUDED.title, documents.title),
                author = COALESCE(EXCLUDED.author, documents.author),
                language = COALESCE(EXCLUDED.language, documents.language),
                category = COALESCE(EXCLUDED.category, documents.category),
                published_year = COALESCE(EXCLUDED.published_year, documents.published_year)
        """, (doc_id, filename, file_path, title, author, language, category, published_year, total_chunks))
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Error registrando documento: {e}")
        return False

def update_document_chunks(doc_id: str, total_chunks: int):
    """Actualiza el número de chunks de un documento"""
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        cur.execute("""
            UPDATE documents
            SET total_chunks = %s, updated_at = NOW()
            WHERE doc_id = %s
        """, (total_chunks, doc_id))
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"⚠️  Error actualizando chunks: {e}")
        return False

def delete_document_chunks(doc_id: str, collection_name: str):
    """
    Elimina todos los chunks de un documento (para reindexación)
    
    Args:
        doc_id: ID del documento
        collection_name: Nombre de la colección de vectores
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        conn.autocommit = True
        cur = conn.cursor()
        
        # Eliminar chunks que pertenecen a este documento
        cur.execute(f"""
            DELETE FROM vecs.{collection_name}
            WHERE metadata->>'doc_id' = %s
        """, (doc_id,))
        
        deleted_count = cur.rowcount
        
        cur.close()
        conn.close()
        return deleted_count
    except Exception as e:
        print(f"⚠️  Error eliminando chunks: {e}")
        return 0

def check_chunk_exists(chunk_id: str, collection_name: str) -> bool:
    """
    Verifica si un chunk ya existe en la base de datos
    
    Args:
        chunk_id: ID del chunk
        collection_name: Nombre de la colección de vectores
        
    Returns:
        True si existe, False si no
    """
    try:
        conn = psycopg2.connect(postgres_connection_string, connect_timeout=10)
        cur = conn.cursor()
        
        cur.execute(f"""
            SELECT COUNT(*) 
            FROM vecs.{collection_name}
            WHERE metadata->>'chunk_id' = %s
        """, (chunk_id,))
        
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        
        return count > 0
    except Exception as e:
        print(f"⚠️  Error verificando chunk: {e}")
        return False

# ============================================================================
# DECISIÓN DE PROCESAMIENTO
# ============================================================================

class DocumentDecision:
    """Resultado de la decisión sobre un documento"""
    SKIP = "skip"           # Saltar (duplicado)
    PROCESS = "process"     # Procesar (nuevo)
    REINDEX = "reindex"      # Reindexar (forzado)

def decide_document_action(doc_id: str, force_reindex: bool = FORCE_REINDEX) -> Tuple[str, Optional[Dict]]:
    """
    Decide qué acción tomar con un documento
    
    Args:
        doc_id: ID del documento
        force_reindex: Si True, fuerza reindexación incluso si existe
        
    Returns:
        (action, document_info) donde action es 'skip', 'process', o 'reindex'
    """
    exists, doc_info = check_document_exists(doc_id)
    
    if not exists:
        return DocumentDecision.PROCESS, None
    
    if force_reindex:
        return DocumentDecision.REINDEX, doc_info
    
    return DocumentDecision.SKIP, doc_info

