"""
🚀 PIPELINE RAG REUTILIZABLE
============================

Pipeline principal que orquesta todo el proceso de ingesta RAG.
Puede ser usado en cualquier proyecto que necesite indexar documentos.
"""

import os
import sys
from typing import Optional, Dict, Any
from pathlib import Path

# Importar módulos de la infraestructura
from .config import RAGConfig
from .ingestion import IngestionEngine
from .monitor import IngestionMonitor
from .anti_duplicates import AntiDuplicatesManager
from .metadata_extractor import MetadataExtractor
from .error_logger import ErrorLogger

class RAGIngestionPipeline:
    """
    Pipeline principal de ingesta RAG reutilizable
    
    Ejemplo de uso:
        pipeline = RAGIngestionPipeline(
            data_directory="./documents",
            supabase_url="https://xxx.supabase.co",
            supabase_password="password",
            openai_api_key="sk-..."
        )
        pipeline.ingest()
    """
    
    def __init__(
        self,
        data_directory: str,
        supabase_url: str,
        supabase_password: str,
        openai_api_key: str,
        collection_name: str = "knowledge",
        chunk_size: int = 1024,
        chunk_overlap: int = 200,
        embedding_batch_size: int = 30,
        max_workers: int = 15,
        embedding_model: str = "text-embedding-3-small",
        **kwargs
    ):
        """
        Inicializa el pipeline de ingesta
        
        Args:
            data_directory: Directorio con documentos a indexar
            supabase_url: URL de Supabase
            supabase_password: Contraseña de Supabase
            openai_api_key: API key de OpenAI
            collection_name: Nombre de la colección vectorial
            chunk_size: Tamaño de chunks en caracteres
            chunk_overlap: Overlap entre chunks
            embedding_batch_size: Tamaño de batch para embeddings
            max_workers: Número de workers paralelos
            embedding_model: Modelo de embeddings de OpenAI
            **kwargs: Configuraciones adicionales
        """
        # Crear configuración
        self.config = RAGConfig(
            data_directory=data_directory,
            supabase_url=supabase_url,
            supabase_password=supabase_password,
            openai_api_key=openai_api_key,
            collection_name=collection_name,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            embedding_batch_size=embedding_batch_size,
            max_workers=max_workers,
            embedding_model=embedding_model,
            **kwargs
        )
        
        # Inicializar componentes
        self.anti_duplicates = AntiDuplicatesManager(self.config)
        self.metadata_extractor = MetadataExtractor()
        self.error_logger = ErrorLogger(self.config)
        self.monitor = IngestionMonitor(self.config)
        self.ingestion_engine = IngestionEngine(
            config=self.config,
            anti_duplicates=self.anti_duplicates,
            metadata_extractor=self.metadata_extractor,
            error_logger=self.error_logger,
            monitor=self.monitor
        )
    
    def ingest(self, force_reindex: bool = False) -> Dict[str, Any]:
        """
        Ejecuta el pipeline de ingesta completo
        
        Args:
            force_reindex: Si True, reindexa documentos duplicados
            
        Returns:
            Dict con estadísticas del proceso
        """
        try:
            # Inicializar tablas
            self.anti_duplicates.ensure_tables()
            self.error_logger.ensure_tables()
            
            # Ejecutar ingesta
            results = self.ingestion_engine.process_all(force_reindex=force_reindex)
            
            # Generar reporte
            report = self.monitor.generate_report()
            
            return {
                'success': True,
                'results': results,
                'report': report
            }
        except Exception as e:
            self.error_logger.log_error(
                filename="pipeline",
                error_type="PIPELINE_ERROR",
                error_message=f"Error en pipeline: {str(e)}",
                exception=e
            )
            return {
                'success': False,
                'error': str(e)
            }
    
    def search(
        self,
        query: str,
        top_k: int = 10,
        language: Optional[str] = None,
        category: Optional[str] = None,
        author: Optional[str] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None
    ) -> list:
        """
        Realiza búsqueda con filtros
        
        Args:
            query: Texto de búsqueda
            top_k: Número de resultados
            language: Filtrar por idioma
            category: Filtrar por categoría
            author: Filtrar por autor
            year_min: Año mínimo
            year_max: Año máximo
            
        Returns:
            Lista de resultados
        """
        from .rag_search import search_with_filters
        
        return search_with_filters(
            query=query,
            top_k=top_k,
            language=language,
            category=category,
            author=author,
            year_min=year_min,
            year_max=year_max,
            config=self.config
        )























