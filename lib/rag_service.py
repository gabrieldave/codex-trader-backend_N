"""
Servicio para búsqueda RAG: embeddings y recuperación de documentos desde Supabase.
"""
import logging
import time
from typing import Optional, Tuple, List, Dict, Any

from lib.dependencies import supabase_client
from lib.config_shared import RAG_AVAILABLE, local_embedder

logger = logging.getLogger(__name__)


class RAGService:
    """Servicio para realizar búsquedas RAG en la biblioteca de documentos."""
    
    def __init__(self):
        self.supabase = supabase_client
        self.embedder = local_embedder
        self.rag_available = RAG_AVAILABLE
    
    async def perform_rag_search(
        self,
        query: str,
        category: Optional[str] = None,
        match_count: Optional[int] = None,
        response_mode: str = 'fast'
    ) -> Tuple[str, str, List[Dict[str, Any]]]:
        """
        Realiza una búsqueda RAG y devuelve el contexto y citaciones.
        
        Args:
            query: Consulta del usuario
            category: Categoría opcional para filtrar
            match_count: Número de chunks a recuperar (se calcula automáticamente si es None)
            response_mode: Modo de respuesta ('fast' o 'deep')
            
        Returns:
            Tuple[context_text, citation_list, retrieved_chunks]:
                - context_text: Texto de contexto formateado
                - citation_list: Lista de citaciones (vacía en modo rápido)
                - retrieved_chunks: Lista de chunks recuperados
        """
        # Si RAG no está disponible, retornar vacío
        if not self.rag_available or self.embedder is None:
            if not self.rag_available:
                logger.warning("RAG no disponible: SUPABASE_DB_URL no configurada. Respondiendo sin contexto de documentos.")
            elif self.embedder is None:
                logger.warning("RAG no disponible: Embedder local no inicializado. Respondiendo sin contexto de documentos.")
            return "", "", []
        
        start_time = time.time()
        logger.info("=" * 80)
        logger.info("🔍 CONSULTANDO RAG - Metodología propia (checksums, sin índices OpenAI)")
        logger.info(f"📝 Consulta: {query[:100]}{'...' if len(query) > 100 else ''}")
        logger.info("─" * 80)
        
        try:
            if self.embedder is None:
                raise RuntimeError("Embedder local MiniLM no inicializado")
            
            # Generar embedding local (384d) con SentenceTransformer
            logger.info("⚙️  Generando embedding con all-MiniLM-L6-v2 (384 dimensiones)...")
            query_vec = self.embedder.encode([query], show_progress_bar=False)[0]
            query_embedding = query_vec.tolist()
            
            # Determinar match_count según el modo de respuesta
            is_deep_mode = response_mode and (
                response_mode.lower() == 'deep' or 
                response_mode.lower() == 'estudio profundo' or
                response_mode.lower() == 'profundo'
            )
            
            if match_count is None:
                if is_deep_mode:
                    match_count = 15  # Modo Estudio Profundo: más chunks
                    logger.info(f"📚 Modo Estudio Profundo: usando {match_count} chunks para contexto amplio")
                else:
                    match_count = 5  # Modo Rápido: menos chunks
                    logger.info(f"⚡ Modo Rápido: usando {match_count} chunks para respuesta rápida")
            
            # Realizar búsqueda RPC en Supabase
            logger.info(f"🔎 Buscando en book_chunks usando match_documents_384 (top {match_count})...")
            payload = {"query_embedding": query_embedding, "match_count": match_count}
            
            if category:
                payload["category_filter"] = category
                logger.info(f"📂 Filtro de categoría aplicado: {category}")
            
            rpc = self.supabase.rpc("match_documents_384", payload).execute()
            rows = rpc.data or []
            retrieved_chunks = rows
            
            logger.info(f"🔍 [DEBUG] retrieved_chunks asignado: {len(retrieved_chunks) if retrieved_chunks else 0} chunks")
            
            # Obtener nombres de archivo desde la tabla documents
            doc_id_to_filename = self._get_document_filenames(rows)
            
            # Construir contexto y citaciones según el modo
            if is_deep_mode:
                context_text, citation_list = self._build_deep_mode_context(rows, doc_id_to_filename)
                logger.info(f"📚 Modo Estudio Profundo: {len(doc_id_to_filename)} fuentes únicas con citación")
            else:
                context_text, citation_list = self._build_fast_mode_context(rows)
                logger.info("⚡ Modo rápido: sin citación de fuentes")
            
            duration = time.time() - start_time
            logger.info("─" * 80)
            logger.info(f"✅ RAG EXITOSO: {len(retrieved_chunks)} chunks recuperados en {duration:.2f}s")
            logger.info(f"📊 Contexto generado: {len(context_text)} caracteres")
            logger.info(f"📚 Fuentes utilizadas: {len(doc_id_to_filename) if is_deep_mode else 0} documentos")
            logger.info("=" * 80)
            
            return context_text, citation_list, retrieved_chunks
            
        except Exception as e:
            error_msg = str(e)
            # Si la función RPC no existe, es un error no crítico
            if "function" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning(f"⚠️ La función RPC 'match_documents_384' no existe en Supabase")
                logger.warning("ℹ️ Ejecuta el script SQL 'create_match_documents_384_function.sql' en Supabase SQL Editor")
                logger.warning("ℹ️ Continuando sin contexto RAG para esta consulta")
            elif "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning(f"⚠️ La tabla 'book_chunks' no existe en Supabase")
                logger.warning("ℹ️ Los libros deben ser indexados primero usando ingest_masiva_local.py")
                logger.warning("ℹ️ Continuando sin contexto RAG para esta consulta")
            else:
                logger.error(f"Error en búsqueda RPC RAG: {error_msg[:200]}")
            
            return "", "", []
    
    def _get_document_filenames(self, chunks: List[Dict[str, Any]]) -> Dict[str, str]:
        """
        Obtiene los nombres de archivo asociados a los doc_ids de los chunks.
        
        Args:
            chunks: Lista de chunks recuperados
            
        Returns:
            Dict[doc_id, filename]: Mapeo de doc_id a nombre de archivo
        """
        doc_ids = set()
        for row in chunks:
            # La función retorna doc_id directamente, pero también puede estar en metadata
            doc_id = row.get("doc_id")
            if not doc_id:
                # Fallback: buscar en metadata si no está en el nivel superior
                metadata = row.get("metadata", {})
                if isinstance(metadata, dict):
                    doc_id = metadata.get("doc_id")
            if doc_id:
                doc_ids.add(doc_id)
        
        doc_id_to_filename = {}
        if doc_ids:
            try:
                docs_response = self.supabase.table("documents").select("doc_id, filename").in_("doc_id", list(doc_ids)).execute()
                if docs_response.data:
                    for doc in docs_response.data:
                        doc_id_to_filename[doc.get("doc_id")] = doc.get("filename", "Documento desconocido")
                logger.info(f"📚 Fuentes encontradas: {len(doc_id_to_filename)} documentos únicos")
            except Exception as e:
                logger.warning(f"⚠️ Error al obtener nombres de archivo: {str(e)[:100]}")
        
        return doc_id_to_filename
    
    def _build_deep_mode_context(
        self,
        chunks: List[Dict[str, Any]],
        doc_id_to_filename: Dict[str, str]
    ) -> Tuple[str, str]:
        """
        Construye el contexto y citaciones para modo Estudio Profundo.
        
        Args:
            chunks: Lista de chunks recuperados
            doc_id_to_filename: Mapeo de doc_id a nombre de archivo
            
        Returns:
            Tuple[context_text, citation_list]
        """
        context_components = []
        unique_sources = {}
        source_index = 1
        
        for chunk in chunks:
            metadata = chunk.get("metadata", {})
            if isinstance(metadata, dict):
                doc_id = metadata.get("doc_id")
            else:
                doc_id = None
            
            chunk_content = chunk.get("content", "")
            
            # Obtener filename desde la tabla documents o metadata
            if doc_id and doc_id in doc_id_to_filename:
                source_filename = doc_id_to_filename[doc_id]
            else:
                # Fallback: intentar obtener desde metadata
                if isinstance(metadata, dict):
                    source_filename = metadata.get("source_file") or metadata.get("file_name") or doc_id or "Documento desconocido"
                else:
                    source_filename = "Documento desconocido"
            
            # Crear referencia única por fuente
            if source_filename not in unique_sources:
                unique_sources[source_filename] = source_index
                source_index += 1
            
            source_tag = f"[Fuente {unique_sources[source_filename]}]"
            context_components.append(f"{source_tag} {chunk_content}")
        
        context_text = "\n---\n".join(context_components)
        logger.info(f"🔍 [DEBUG] contexto construido (Estudio Profundo): {len(context_text)} caracteres, context_components={len(context_components)}")
        logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {context_text[:200] if context_text else 'VACÍO'}")
        
        # Crear la lista final de fuentes para el LLM
        citation_list = "\n".join([
            f"[{index}]: {filename}" 
            for filename, index in sorted(unique_sources.items(), key=lambda x: x[1])
        ])
        
        return context_text, citation_list
    
    def _build_fast_mode_context(self, chunks: List[Dict[str, Any]]) -> Tuple[str, str]:
        """
        Construye el contexto para modo Rápido (sin citaciones).
        
        Args:
            chunks: Lista de chunks recuperados
            
        Returns:
            Tuple[context_text, ""]: Contexto sin citaciones
        """
        context_content = [chunk.get("content", "") for chunk in chunks if chunk.get("content")]
        context_text = "\n---\n".join(context_content)
        logger.info(f"🔍 [DEBUG] contexto construido (Modo Rápido): {len(context_text)} caracteres, context_content={len(context_content)}")
        logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {context_text[:200] if context_text else 'VACÍO'}")
        
        return context_text, ""


# Instancia global del servicio
rag_service = RAGService()

