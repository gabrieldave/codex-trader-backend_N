"""
⚙️ CONFIGURACIÓN REUTILIZABLE
==============================

Clase de configuración centralizada para el pipeline RAG
"""

from dataclasses import dataclass
from typing import Optional

@dataclass
class RAGConfig:
    """Configuración del pipeline RAG"""
    
    # Directorios y archivos
    data_directory: str
    
    # Supabase
    supabase_url: str
    supabase_password: str
    collection_name: str = "knowledge"
    
    # OpenAI
    openai_api_key: str
    embedding_model: str = "text-embedding-3-small"
    
    # Chunking
    chunk_size: int = 1024
    chunk_overlap: int = 200
    
    # Procesamiento
    embedding_batch_size: int = 30
    max_workers: int = 15
    
    # Rate limiting
    target_rpm: int = 3500
    target_tpm: int = 3500000
    
    # Calidad
    min_chunks_per_file: int = 5
    
    # Monitor
    monitor_update_interval: int = 5
    max_problematic_files_detail: int = 20
    
    # Otros
    force_reindex: bool = False
    
    def get_postgres_connection_string(self) -> str:
        """Genera string de conexión a PostgreSQL"""
        from urllib.parse import quote_plus
        project_ref = self.supabase_url.replace("https://", "").replace(".supabase.co", "")
        encoded_password = quote_plus(self.supabase_password)
        return f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"



















