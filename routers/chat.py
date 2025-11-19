"""
Router para endpoints de chat y sesiones de conversación.
"""
import os
import re
import logging
import threading
import json
import time
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from lib.dependencies import get_user, supabase_client
from lib.config_shared import (
    modelo_por_defecto, local_embedder, RAG_AVAILABLE,
    DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    GOOGLE_API_KEY, COHERE_API_KEY
)
from routers.models import QueryInput, CreateChatSessionInput
import config
import litellm

logger = logging.getLogger(__name__)

# Crear router
chat_router = APIRouter(tags=["chat"])


def is_simple_greeting(message: str) -> bool:
    """
    Detecta si el mensaje es solo un saludo simple sin contenido de trading.
    Retorna True si es solo un saludo, False si contiene contenido de trading.
    """
    # Normalizar el mensaje: minúsculas, sin espacios extra, sin emojis
    normalized = re.sub(r'[^\w\s]', '', message.lower().strip())
    words = normalized.split()
    
    # Si el mensaje es muy largo, probablemente no es solo un saludo
    if len(words) > 5:
        return False
    
    # Lista de saludos simples (español e inglés)
    simple_greetings = [
        'hola', 'hi', 'hello', 'hey',
        'buenas', 'buen', 'día', 'day',
        'qué', 'tal', 'what', 'up',
        'saludos', 'greetings',
        'buenos', 'días', 'mornings', 'afternoon', 'evening',
        'good', 'morning', 'afternoon', 'evening',
        'there', 'hola qué tal', 'hi there', 'hello there', 'hey there'
    ]
    
    # Verificar si todas las palabras son saludos simples
    all_greetings = all(word in simple_greetings for word in words if word)
    
    # Palabras relacionadas con trading que indican que NO es solo un saludo
    trading_keywords = [
        'trading', 'trader', 'mercado', 'market', 'operar', 'trade',
        'estrategia', 'strategy', 'riesgo', 'risk', 'capital', 'money',
        'análisis', 'analysis', 'gráfico', 'chart', 'indicador', 'indicator',
        'soporte', 'support', 'resistencia', 'resistance', 'tendencia', 'trend',
        'compra', 'venta', 'buy', 'sell', 'precio', 'price', 'acción', 'stock',
        'forex', 'crypto', 'bitcoin', 'cripto', 'divisa', 'currency',
        'psicología', 'psychology', 'emociones', 'emotions', 'disciplina', 'discipline',
        'swing', 'scalping', 'intradía', 'intraday', 'day trading', 'daytrading',
        'explicar', 'explain', 'qué es', 'what is', 'cómo', 'how', 'cuál', 'which'
    ]
    
    # Si contiene palabras de trading, NO es solo un saludo
    has_trading_content = any(keyword in normalized for keyword in trading_keywords)
    
    # Es solo un saludo si: todas las palabras son saludos Y no hay contenido de trading
    return all_greetings and not has_trading_content and len(words) > 0


@chat_router.post("/chat")
@chat_router.post("/chat-simple")
async def chat(query_input: QueryInput, user = Depends(get_user)):
    """
    Endpoint para hacer consultas sobre los documentos indexados.
    
    Requiere autenticación mediante token JWT de Supabase.
    Verifica tokens disponibles, ejecuta la consulta con LiteLLM (Deepseek por defecto),
    y descuenta los tokens usados del perfil del usuario.
    """
    
    try:
        # Obtener el ID del usuario
        user_id = user.id
        
        # Paso A: Verificar tokens disponibles
        profile_response = supabase_client.table("profiles").select("tokens_restantes").eq("id", user_id).execute()
        
        if not profile_response.data:
            raise HTTPException(
                status_code=404,
                detail="Perfil de usuario no encontrado"
            )
        
        tokens_restantes = profile_response.data[0]["tokens_restantes"]
        
        if tokens_restantes <= 0:
            # IMPORTANTE: Enviar email al usuario cuando los tokens se agoten (solo una vez)
            try:
                from lib.email import send_email
                
                # Verificar si ya se envió el email de tokens agotados (usar un flag en el perfil)
                profile_check = supabase_client.table("profiles").select("email, tokens_exhausted_email_sent").eq("id", user_id).execute()
                user_email = profile_check.data[0].get("email") if profile_check.data else None
                email_already_sent = profile_check.data[0].get("tokens_exhausted_email_sent", False) if profile_check.data else False
                
                if user_email and not email_already_sent:
                    def send_tokens_exhausted_email():
                        try:
                            user_name = user_email.split('@')[0] if '@' in user_email else 'usuario'
                            # Construir URL de billing antes del f-string
                            frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                            billing_url = f"{frontend_url.rstrip('/')}/billing"
                            
                            user_html = f"""
                            <html>
                            <body style="font-family: Arial, sans-serif; line-height: 1.8; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 30px; text-align: center; border-radius: 10px 10px 0 0;">
                                    <h1 style="color: white; margin: 0; font-size: 28px;">⚠️ Tus Tokens se Han Agotado</h1>
                                </div>
                                
                                <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                    <p style="font-size: 16px; margin-bottom: 20px;">
                                        Hola <strong>{user_name}</strong>,
                                    </p>
                                    
                                    <p style="font-size: 16px; margin-bottom: 20px;">
                                        Te informamos que tus tokens se han agotado. Para continuar usando Codex Trader, necesitas recargar tokens.
                                    </p>
                                    
                                    <div style="background: #fee2e2; padding: 20px; border-radius: 8px; border-left: 4px solid #ef4444; margin: 20px 0;">
                                        <p style="margin: 0; color: #991b1b; font-weight: bold; font-size: 18px;">
                                            Tokens restantes: 0
                                        </p>
                                    </div>
                                    
                                    <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #10b981;">
                                        <h3 style="color: #059669; margin-top: 0; font-size: 18px;">💡 Opciones para continuar:</h3>
                                        <ul style="margin: 10px 0; padding-left: 20px; color: #333;">
                                            <li style="margin-bottom: 10px;">Recargar tokens desde tu panel de cuenta</li>
                                            <li style="margin-bottom: 10px;">Actualizar a un plan con más tokens mensuales</li>
                                            <li style="margin-bottom: 0;">Contactarnos si necesitas ayuda</li>
                                        </ul>
                                    </div>
                                    
                                    <div style="text-align: center; margin: 30px 0;">
                                        <a href="{billing_url}" style="display: inline-block; background: #10b981; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px;">
                                            💰 Recargar Tokens
                                        </a>
                                    </div>
                                    
                                    <p style="font-size: 12px; margin-top: 30px; color: #666; text-align: center; border-top: 1px solid #e5e7eb; padding-top: 20px; line-height: 1.6;">
                                        Si tienes alguna pregunta, no dudes en contactarnos respondiendo a este correo.
                                    </p>
                                </div>
                            </body>
                            </html>
                            """
                            send_email(
                                to=user_email,
                                subject="⚠️ Tus tokens se han agotado - Codex Trader",
                                html=user_html
                            )
                            
                            # Marcar que el email fue enviado
                            supabase_client.table("profiles").update({
                                "tokens_exhausted_email_sent": True
                            }).eq("id", user_id).execute()
                            
                            print(f"✅ Email de tokens agotados enviado a {user_email}")
                        except Exception as e:
                            print(f"⚠️ Error al enviar email de tokens agotados: {e}")
                    
                    email_thread = threading.Thread(target=send_tokens_exhausted_email, daemon=True)
                    email_thread.start()
            except Exception as email_error:
                print(f"⚠️ Error al preparar email de tokens agotados: {email_error}")
            
            raise HTTPException(
                status_code=402,
                detail="Tokens agotados. Por favor, recarga."
            )
        
        # Verificar si es solo un saludo simple (evitar búsqueda RAG para acelerar respuesta)
        is_greeting = is_simple_greeting(query_input.query)
        
        # Inicializar variables para fuentes y SYSTEM_PROMPT
        context_text = ""
        sources_text = ""
        SYSTEM_PROMPT = None
        citation_list = ""
        source_list = []
        retrieved_chunks = []
        respuesta_texto = ""  # Inicializar aquí para evitar errores si falla LiteLLM
        tokens_usados = 0  # Inicializar aquí para evitar errores si falla LiteLLM
        nuevos_tokens = tokens_restantes  # Inicializar con tokens actuales para evitar errores
        conversation_id = query_input.conversation_id  # Inicializar aquí para evitar errores
        
        if is_greeting:
            # Para saludos simples, saltarse RAG completamente (contexto vacío)
            logger.info("ℹ️  Saludo simple detectado - RAG omitido (respuesta rápida sin contexto)")
            contexto = ""
        elif not RAG_AVAILABLE or local_embedder is None:
            # Si RAG no está disponible, usar contexto vacío
            if not RAG_AVAILABLE:
                logger.warning("RAG no disponible: SUPABASE_DB_URL no configurada. Respondiendo sin contexto de documentos.")
            elif local_embedder is None:
                logger.warning("RAG no disponible: Embedder local no inicializado. Respondiendo sin contexto de documentos.")
            contexto = ""
        else:
            # Obtener contexto usando embeddings locales + RPC en Supabase (sin OpenAI)
            start_time = time.time()
            logger.info("=" * 80)
            logger.info("🔍 CONSULTANDO RAG - Metodología propia (checksums, sin índices OpenAI)")
            logger.info(f"📝 Consulta: {query_input.query[:100]}{'...' if len(query_input.query) > 100 else ''}")
            logger.info("─" * 80)
            try:
                if local_embedder is None:
                    raise RuntimeError("Embedder local MiniLM no inicializado")
                # Generar embedding local (384d) con SentenceTransformer
                logger.info("⚙️  Generando embedding con all-MiniLM-L6-v2 (384 dimensiones)...")
                query_vec = local_embedder.encode([query_input.query], show_progress_bar=False)[0]
                query_embedding = query_vec.tolist()
                
                # Determinar match_count según el modo de respuesta
                # Modo Estudio Profundo: más chunks para más contexto
                # Modo Rápido: menos chunks para respuestas más rápidas
                is_deep_mode = query_input.response_mode and (
                    query_input.response_mode.lower() == 'deep' or 
                    query_input.response_mode.lower() == 'estudio profundo' or
                    query_input.response_mode.lower() == 'profundo'
                )
                
                if is_deep_mode:
                    # Modo Estudio Profundo: 15 chunks para máximo contexto
                    match_count = 15
                    logger.info(f"📚 Modo Estudio Profundo: usando {match_count} chunks para contexto amplio")
                else:
                    # Modo Rápido: 5 chunks para respuestas rápidas
                    match_count = 5
                    logger.info(f"⚡ Modo Rápido: usando {match_count} chunks para respuesta rápida")
                
                logger.info(f"🔎 Buscando en book_chunks usando match_documents_384 (top {match_count})...")
                payload = {"query_embedding": query_embedding, "match_count": match_count}
                # Agregar category_filter si se proporciona una categoría
                if query_input.category:
                    payload["category_filter"] = query_input.category
                    logger.info(f"📂 Filtro de categoría aplicado: {query_input.category}")
                rpc = supabase_client.rpc("match_documents_384", payload).execute()
                rows = rpc.data or []
                context_chunks = rows
                retrieved_chunks = rows  # Variable para verificar si hay chunks recuperados
                logger.info(f"🔍 [DEBUG] retrieved_chunks asignado: {len(retrieved_chunks) if retrieved_chunks else 0} chunks")
                logger.info(f"🔍 [DEBUG] retrieved_chunks es truthy: {bool(retrieved_chunks)}")
                
                # Extraer doc_id únicos de los chunks para buscar los nombres de archivo
                doc_ids = set()
                for row in rows:
                    metadata = row.get("metadata", {})
                    if isinstance(metadata, dict):
                        doc_id = metadata.get("doc_id")
                        if doc_id:
                            doc_ids.add(doc_id)
                
                # Consultar la tabla documents para obtener los filename asociados
                doc_id_to_filename = {}
                if doc_ids:
                    try:
                        docs_response = supabase_client.table("documents").select("doc_id, filename").in_("doc_id", list(doc_ids)).execute()
                        if docs_response.data:
                            for doc in docs_response.data:
                                doc_id_to_filename[doc.get("doc_id")] = doc.get("filename", "Documento desconocido")
                        logger.info(f"📚 Fuentes encontradas: {len(doc_id_to_filename)} documentos únicos")
                    except Exception as e:
                        logger.warning(f"⚠️ Error al obtener nombres de archivo: {str(e)[:100]}")
                
                # Construcción condicional de contexto y citación basada en response_mode
                # is_deep_mode ya está definido arriba, reutilizamos la variable
                if is_deep_mode:
                    # Lógica de Citación (Para modo detallado/Estudio Profundo)
                    context_components = []
                    unique_sources = {}
                    source_index = 1
                    
                    for chunk in rows:
                        # Extraer doc_id y content
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
                    
                    contexto = "\n---\n".join(context_components)
                    logger.info(f"🔍 [DEBUG] contexto construido (Estudio Profundo): {len(contexto)} caracteres, context_components={len(context_components)}")
                    logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {contexto[:200] if contexto else 'VACÍO'}")
                    
                    # Crear la lista final de fuentes para el LLM
                    citation_list = "\n".join([
                        f"[{index}]: {filename}" 
                        for filename, index in sorted(unique_sources.items(), key=lambda x: x[1])
                    ])
                    
                    sources_text = citation_list
                    logger.info(f"📚 Modo Estudio Profundo: {len(unique_sources)} fuentes únicas con citación")
                else:
                    # Lógica Rápida (Para modo veloz, sin citación)
                    context_content = [chunk.get("content", "") for chunk in rows if chunk.get("content")]
                    contexto = "\n---\n".join(context_content)
                    logger.info(f"🔍 [DEBUG] contexto construido (Modo Rápido): {len(contexto)} caracteres, context_content={len(context_content)}")
                    logger.info(f"🔍 [DEBUG] Primeros 200 caracteres de contexto: {contexto[:200] if contexto else 'VACÍO'}")
                    sources_text = ""
                    citation_list = ""
                    logger.info("⚡ Modo rápido: sin citación de fuentes")
                
                duration = time.time() - start_time
                logger.info("─" * 80)
                logger.info(f"✅ RAG EXITOSO: {len(context_chunks)} chunks recuperados en {duration:.2f}s")
                logger.info(f"📊 Contexto generado: {len(contexto)} caracteres")
                logger.info(f"📚 Fuentes utilizadas: {len(unique_sources) if is_deep_mode else 0} documentos")
                logger.info("=" * 80)
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
                contexto = ""
                context_text = ""
                sources_text = ""
                citation_list = ""
                source_list = []
                retrieved_chunks = []
        
        # DEBUG: Verificar valores antes de decidir si llamar a LiteLLM
        logger.info(f"🔍 [DEBUG] ANTES DE DECISIÓN LLM:")
        logger.info(f"🔍 [DEBUG] - contexto: {len(contexto) if contexto else 0} caracteres (vacío: {not contexto or contexto.strip() == ''})")
        logger.info(f"🔍 [DEBUG] - retrieved_chunks: {len(retrieved_chunks) if retrieved_chunks else 0} chunks")
        logger.info(f"🔍 [DEBUG] - is_greeting: {is_greeting}")
        logger.info(f"🔍 [DEBUG] - context_text: {len(context_text) if context_text else 0} caracteres")
        if contexto and len(contexto) > 0:
            logger.info(f"🔍 [DEBUG] - contexto NO está vacío, debería proceder con RAG")
        else:
            logger.warning(f"🔍 [DEBUG] - ⚠️ contexto ESTÁ VACÍO, podría entrar en fallback")
        
        # Crear el prompt con contexto y pregunta
        # Si es un saludo, usar un prompt más simple sin contexto RAG
        if is_greeting:
            # Para saludos, el prompt es simplemente el mensaje del usuario
            prompt = query_input.query
            SYSTEM_PROMPT = None
        else:
            # Determinar si es modo "Estudio Profundo" (deep) o modo rápido
            is_deep_mode = query_input.response_mode and (
                query_input.response_mode.lower() == 'deep' or 
                query_input.response_mode.lower() == 'estudio profundo' or
                query_input.response_mode.lower() == 'profundo'
            )
            
            if is_deep_mode and sources_text:
                # Prompt que pide Citaciones (Modo Estudio Profundo)
                SYSTEM_PROMPT = f"""Eres Codex Trader, un experto financiero y asistente de RAG. Tu tarea es responder a la pregunta del usuario ÚNICAMENTE basándote en el contexto proporcionado.

Sigue estrictamente estas reglas:

1. Proporciona un resumen conciso y detallado.

2. POR CADA HECHO que utilices, debes **citar inmediatamente la fuente** usando el formato [Fuente X] al final de la frase.

3. Al final de la respuesta, bajo el encabezado 'Fuentes Utilizadas:', lista todas las fuentes citadas.

Contexto Recuperado:

---

{contexto}

---

Fuentes a Listar:

---

{sources_text}

---

"""
                prompt = query_input.query
            else:
                # Lógica Rápida (Para modo veloz, sin citación)
                SYSTEM_PROMPT = f"""Eres Codex Trader, un experto financiero. Responde a la pregunta basándote ÚNICAMENTE en el contexto. Sé extremadamente conciso (3-4 párrafos máximo).

Contexto:

---

{contexto}

---

"""
                prompt = query_input.query
        
        # Verificar si hay chunks recuperados antes de llamar a LiteLLM
        # Los saludos no necesitan chunks, así que se procesan normalmente
        logger.info(f"🔍 Verificando chunks: retrieved_chunks={len(retrieved_chunks) if retrieved_chunks else 0}, is_greeting={is_greeting}")
        logger.info(f"🔍 [DEBUG] CONDICIÓN: retrieved_chunks={bool(retrieved_chunks)}, is_greeting={is_greeting}, resultado={bool(retrieved_chunks) or is_greeting}")
        if retrieved_chunks or is_greeting:
            logger.info("✅ Procediendo con llamada a LiteLLM")
            logger.info(f"🔍 [DEBUG] contexto que se usará en prompt: {len(contexto) if contexto else 0} caracteres")
            # Ejecutar la consulta usando LiteLLM con Deepseek
            # Usar el modelo configurado al inicio (ya tiene prioridad: CHAT_MODEL > Deepseek > OpenAI)
            chat_model = modelo_por_defecto
            if not chat_model:
                # Fallback de seguridad (no debería llegar aquí)
                if DEEPSEEK_API_KEY:
                    chat_model = "deepseek/deepseek-chat"  # Formato correcto para LiteLLM
                else:
                    chat_model = "gpt-3.5-turbo"
            
            # REGLA CRÍTICA SOBRE SALUDOS (máxima prioridad, se aplica antes de RAG y modo de respuesta)
            greetings_instruction = """

REGLA CRÍTICA SOBRE SALUDOS (OBEDECE ESTO SIEMPRE):

1. Si el mensaje del usuario es SOLO un saludo o algo social muy corto,

   por ejemplo en español:
   - "hola"
   - "buenas"
   - "buen día"
   - "qué tal"
   - "hey"
   - "saludos"
   - "hola, qué tal"
   - o variaciones similares con o sin emojis,

   o en inglés:
   - "hi"
   - "hello"
   - "hey"
   - "good morning"
   - "good afternoon"
   - "good evening"
   - "what's up"
   - "hi there"
   - "hello there"
   - "hey there"
   - "good day"
   - o variaciones similares con o sin emojis,

   Y NO contiene ninguna palabra relacionada con trading, mercados, dinero, estrategia, gestión de riesgo, análisis, etc.,

   ENTONCES:

   - NO uses el contexto de RAG.
   - NO generes una explicación larga.
   - NO uses encabezados, ni listas, ni markdown complejo.

   En esos casos, responde SOLO con:

   - 1 o 2 frases muy cortas:

     *Primero*, un saludo amable.

     *Segundo*, una frase diciendo en qué puedes ayudar (trading, gestión de riesgo, psicología, estrategias).

     Y termina con una pregunta breve invitando a que el usuario formule su duda.

   Ejemplo de estilo:

     Usuario: "hola"

     Asistente: "¡Hola! Soy Codex Trader, tu asistente de IA especializado en trading. 

     Puedo ayudarte con gestión de riesgo, análisis técnico, psicología del trader y diseño de estrategias. 

     ¿Sobre qué tema de trading te gustaría que empecemos?"

2. Si el mensaje del usuario incluye ya alguna pregunta o tema de trading

   (por ejemplo: "hola, explícame gestión de riesgo" o "hola, qué es el day trading"),

   ENTONCES:

   - Trátalo como una pregunta normal de trading.

   - Aplica el modo de respuesta (Rápida o Estudio profundo) según corresponda.
"""
        
            # Construir instrucción de modo de respuesta según el modo seleccionado
            response_mode = query_input.response_mode or 'fast'
            if response_mode == 'fast':
                mode_instruction = """

═══════════════════════════════════════════════════════════════
MODO: RESPUESTA RÁPIDA (OBLIGATORIO - RESPETA ESTO ESTRICTAMENTE)
═══════════════════════════════════════════════════════════════

RESPUESTA MÁXIMA: 1-2 PÁRRAFOS CORTOS. NADA MÁS.

REGLAS ESTRICTAS:
- Máximo 1-2 párrafos cortos (3-5 oraciones cada uno)
- Ve directo al punto, sin introducciones largas
- NO uses encabezados (##, ###)
- NO uses listas de viñetas extensas
- NO des ejemplos detallados
- NO expliques conceptos secundarios
- Si la pregunta es amplia, menciona solo las ideas principales
- Al final, puedes mencionar brevemente que el usuario puede pedir más detalles si lo desea

EJEMPLO DE LONGITUD CORRECTA:
"La gestión de riesgo es fundamental en trading. Consiste en limitar las pérdidas potenciales usando stop loss y calculando el tamaño de posición según tu capital disponible. Nunca arriesgues más del 1-2% de tu cuenta por operación."

Si excedes 2 párrafos, estás violando el modo Rápida.
"""
            else:  # 'deep'
                mode_instruction = """

═══════════════════════════════════════════════════════════════
MODO: ESTUDIO PROFUNDO (OBLIGATORIO - RESPETA ESTO ESTRICTAMENTE)
═══════════════════════════════════════════════════════════════

RESPUESTA MÍNIMA: 5+ PÁRRAFOS O MÁS. DESARROLLA COMPLETAMENTE.

REGLAS ESTRICTAS:
- Mínimo 5 párrafos, preferiblemente más
- Primero: RESUMEN en 3-5 viñetas con las ideas clave
- Después: DESARROLLO COMPLETO con secciones y subtítulos (usa ##, ###)
- Incluye ejemplos prácticos y casos de uso
- Explica conceptos relacionados y contexto
- Estructura con: Introducción → Desarrollo → Ejemplos → Conclusiones
- Sé exhaustivo pero claro
- Usa markdown para organizar: encabezados, listas, negritas

EJEMPLO DE ESTRUCTURA:
## Resumen de Ideas Clave
- Idea 1
- Idea 2
- Idea 3

## Desarrollo Completo

### Subtema 1
[Párrafo 1: Explicación detallada...]
[Párrafo 2: Ejemplos y casos...]

### Subtema 2
[Párrafo 3: Más detalles...]
[Párrafo 4: Aplicaciones prácticas...]

### Subtema 3
[Párrafo 5: Conclusiones y recomendaciones...]

Si tienes menos de 5 párrafos, estás violando el modo Estudio Profundo.
"""
            
            # Construir el system_prompt según si es saludo o no
            # Si SYSTEM_PROMPT ya está definido (modo Estudio Profundo con citación), usarlo directamente
            if SYSTEM_PROMPT:
                system_prompt = SYSTEM_PROMPT
                # Ajustar max_tokens para modo Estudio Profundo
                max_tokens = 4000  # Más tokens para respuestas largas con citación
            elif is_greeting:
                # Para saludos: system prompt simple y directo, SIN modo de respuesta
                system_prompt = """Eres CODEX TRADER, un asistente de IA especializado en trading.

INSTRUCCIONES PARA SALUDOS:
- Responde SOLO con 1-2 frases muy cortas
- Saluda amablemente
- Menciona brevemente en qué puedes ayudar (trading, gestión de riesgo, psicología, estrategias)
- Termina con una pregunta breve invitando al usuario a formular su duda
- NO uses encabezados, ni listas, ni markdown
- NO des explicaciones largas

Ejemplo: "¡Hola! Soy Codex Trader, tu asistente de IA especializado en trading. Puedo ayudarte con gestión de riesgo, análisis técnico, psicología del trader y diseño de estrategias. ¿Sobre qué tema de trading te gustaría que empecemos?"

Responde siempre en español."""
                # Para saludos, limitar tokens a 100 para forzar respuestas cortas
                max_tokens = 100
            else:
                # Para preguntas normales: system prompt completo con modo de respuesta
                system_prompt = config.ASSISTANT_DESCRIPTION + '\n\n' + greetings_instruction + '\n\n' + mode_instruction
                # Ajustar max_tokens según el modo
                if response_mode == 'fast':
                    max_tokens = 300  # Limitar tokens para forzar respuestas cortas (1-2 párrafos)
                else:  # 'deep'
                    max_tokens = 4000  # Más tokens para respuestas largas (5+ párrafos)
            
            # Preparar parámetros para LiteLLM
            litellm_params = {
                "model": chat_model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": config.MODEL_TEMPERATURE,
                "max_tokens": max_tokens
            }
            
            # Configurar la API key según el modelo ANTES de hacer la llamada
            # Esto asegura que LiteLLM tenga la key correcta
            
            # Configurar la API key según el modelo
            # LiteLLM detecta automáticamente las API keys desde variables de entorno,
            # pero podemos configurarlas explícitamente si es necesario
            if chat_model.startswith("deepseek") or "deepseek" in chat_model.lower():
                if DEEPSEEK_API_KEY:
                    litellm_params["api_key"] = DEEPSEEK_API_KEY
                    print(f"✓ API Key de Deepseek configurada")
                else:
                    raise HTTPException(
                        status_code=500,
                        detail="DEEPSEEK_API_KEY no está configurada pero se intentó usar Deepseek"
                    )
            elif chat_model.startswith("claude") or "anthropic" in chat_model.lower():
                if ANTHROPIC_API_KEY:
                    litellm_params["api_key"] = ANTHROPIC_API_KEY
                    print(f"✓ API Key de Anthropic (Claude) configurada")
                # LiteLLM también puede usar ANTHROPIC_API_KEY desde variables de entorno
            elif chat_model.startswith("gemini") or "google" in chat_model.lower():
                if GOOGLE_API_KEY:
                    litellm_params["api_key"] = GOOGLE_API_KEY
                    print(f"✓ API Key de Google (Gemini) configurada")
                # LiteLLM también puede usar GOOGLE_API_KEY desde variables de entorno
            elif chat_model.startswith("command") or "cohere" in chat_model.lower():
                if COHERE_API_KEY:
                    litellm_params["api_key"] = COHERE_API_KEY
                    print(f"✓ API Key de Cohere configurada")
                # LiteLLM también puede usar COHERE_API_KEY desde variables de entorno
            elif chat_model.startswith("gpt") or "openai" in chat_model.lower():
                if not OPENAI_API_KEY:
                    raise HTTPException(
                        status_code=500,
                        detail="OPENAI_API_KEY no está configurada pero se intentó usar OpenAI/ChatGPT"
                    )
                # Asegurar que la API key esté en las variables de entorno
                os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
                # También pasarla explícitamente en los parámetros
                litellm_params["api_key"] = OPENAI_API_KEY
                print(f"✓ API Key de OpenAI configurada para {chat_model}")
            # Para otros modelos, LiteLLM intentará detectar la API key automáticamente
            
            # Log para debugging (solo mostrar primeros caracteres de la query)
            logger.info(f"📤 Enviando consulta a {chat_model} (query: {query_input.query[:50]}...)")
            
            try:
                response = litellm.completion(**litellm_params)
                logger.info(f"✓ Respuesta recibida de {chat_model}")
            except Exception as e:
                logger.error(f"❌ Error en llamada a LiteLLM: {str(e)}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Error al generar respuesta con LiteLLM: {str(e)}"
                )
            
            # Obtener la respuesta y los tokens usados
            if not response or not response.choices or len(response.choices) == 0:
                logger.error("❌ Respuesta de LiteLLM vacía o sin choices")
                respuesta_texto = "Lo siento, hubo un error al generar la respuesta. Por favor, intenta nuevamente."
            else:
                respuesta_texto = response.choices[0].message.content
                if not respuesta_texto or respuesta_texto.strip() == "":
                    logger.warning("⚠️ Respuesta de LiteLLM está vacía")
                    respuesta_texto = "Lo siento, no pude generar una respuesta. Por favor, intenta reformular tu pregunta."
                else:
                    logger.info(f"✅ Respuesta generada: {len(respuesta_texto)} caracteres")
                    
                    # Añadir la lista de fuentes al final de la respuesta si es modo "Estudio Profundo"
                    is_deep_mode = query_input.response_mode and (
                        query_input.response_mode.lower() == 'deep' or 
                        query_input.response_mode.lower() == 'estudio profundo' or
                        query_input.response_mode.lower() == 'profundo'
                    )
                    
                    if is_deep_mode and citation_list:
                        respuesta_texto += "\n\n---\n**FUENTES DETALLADAS**:\n" + citation_list
                        logger.info(f"📚 Lista de fuentes añadida a la respuesta: {len(citation_list)} caracteres")
            
            # Extraer información detallada de uso de tokens de LiteLLM
            usage = response.usage if hasattr(response, 'usage') else None
            
            # Inicializar variables de tokens
            input_tokens = 0
            output_tokens = 0
            total_tokens_usados = 0
            
            if usage:
                # LiteLLM puede devolver usage como objeto o dict
                if isinstance(usage, dict):
                    # Si es un diccionario
                    input_tokens = usage.get('prompt_tokens', usage.get('input_tokens', 0))
                    output_tokens = usage.get('completion_tokens', usage.get('output_tokens', 0))
                    total_tokens_usados = usage.get('total_tokens', 0)
                else:
                    # Si es un objeto
                    if hasattr(usage, 'prompt_tokens'):
                        input_tokens = usage.prompt_tokens
                    elif hasattr(usage, 'input_tokens'):
                        input_tokens = usage.input_tokens
                    
                    if hasattr(usage, 'completion_tokens'):
                        output_tokens = usage.completion_tokens
                    elif hasattr(usage, 'output_tokens'):
                        output_tokens = usage.output_tokens
                    
                    if hasattr(usage, 'total_tokens'):
                        total_tokens_usados = usage.total_tokens
                
                # Si total_tokens_usados es 0 pero tenemos input y output, calcularlo
                if total_tokens_usados == 0 and (input_tokens > 0 or output_tokens > 0):
                    total_tokens_usados = input_tokens + output_tokens
            
            # Si no se pudieron obtener los tokens, usar un estimado basado en la longitud
            if total_tokens_usados == 0:
                # Estimación aproximada: 1 token ≈ 4 caracteres
                input_tokens = len(prompt) // 4
                output_tokens = len(respuesta_texto) // 4
                total_tokens_usados = max(100, input_tokens + output_tokens)
                print(f"⚠ No se pudo obtener usage de LiteLLM, usando estimación")
            
            # IMPORTANTE: Registrar uso del modelo para monitoreo de costos
            # Esta llamada es no-bloqueante y no afecta el flujo principal si falla
            try:
                from lib.model_usage import log_model_usage_from_response
                log_model_usage_from_response(
                    user_id=str(user_id),
                    model=chat_model,
                    tokens_input=input_tokens,
                    tokens_output=output_tokens
                )
            except Exception as e:
                # No es crítico si falla el logging, solo registrar el error
                print(f"WARNING: Error al registrar uso de modelo (no critico): {e}")
            
            # Loggear información detallada de tokens y costos
            print("=" * 60)
            print(f"[INFO] Consulta procesada:")
            print(f"  Modelo: {chat_model}")
            print(f"  Input tokens: {input_tokens}")
            print(f"  Output tokens: {output_tokens}")
            print(f"  Total tokens: {total_tokens_usados}")
            print(f"  Tokens restantes antes: {tokens_restantes}")
            print("=" * 60)
            
            # Usar total_tokens_usados para el descuento (mantener compatibilidad)
            tokens_usados = total_tokens_usados
            
            # Paso B: Calcular nuevos tokens antes de guardar el log
            nuevos_tokens = tokens_restantes - tokens_usados
        
            # Guardar log de tokens en archivo para consulta posterior
            try:
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "user_id": str(user_id),
                    "model": chat_model,
                    "query_preview": query_input.query[:50] + "..." if len(query_input.query) > 50 else query_input.query,
                    "response_mode": response_mode,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": total_tokens_usados,
                    "tokens_antes": tokens_restantes,
                    "tokens_despues": nuevos_tokens
                }
                
                # Guardar en archivo JSON (append)
                log_file = "tokens_log.json"
                log_data = []
                
                # Leer logs existentes si el archivo existe
                if os.path.exists(log_file):
                    try:
                        with open(log_file, 'r', encoding='utf-8') as f:
                            log_data = json.load(f)
                    except:
                        log_data = []
                
                # Agregar nuevo log (mantener solo los últimos 100)
                log_data.append(log_entry)
                if len(log_data) > 100:
                    log_data = log_data[-100:]
                
                # Guardar
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(log_data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                # Si falla el logging, no es crítico, solo imprimir error
                print(f"⚠ No se pudo guardar log de tokens: {e}")
            
            # Paso C: Descontar tokens de la base de datos y verificar uso justo
        
            # IMPORTANTE: Lógica de uso justo (Fair Use)
            # Obtener información del perfil para calcular porcentaje de uso
            # Manejar el caso cuando las columnas no existen (compatibilidad con esquemas antiguos)
            update_data = {
                "tokens_restantes": nuevos_tokens
            }
            
            try:
                profile_fair_use = supabase_client.table("profiles").select(
                    "tokens_monthly_limit, fair_use_warning_shown, fair_use_discount_eligible, fair_use_discount_used"
                ).eq("id", user_id).execute()
                
                if profile_fair_use.data:
                    profile = profile_fair_use.data[0]
                    tokens_monthly_limit = profile.get("tokens_monthly_limit") or 0
                    
                    if tokens_monthly_limit > 0:
                        # Calcular porcentaje de uso
                        tokens_usados_total = tokens_monthly_limit - nuevos_tokens
                        usage_percent = (tokens_usados_total / tokens_monthly_limit) * 100
                        
                        # Aviso suave al 80% de uso
                        if usage_percent >= 80 and not profile.get("fair_use_warning_shown", False):
                            update_data["fair_use_warning_shown"] = True
                            print(f"WARNING: Usuario {user_id} alcanzo 80% de uso ({usage_percent:.1f}%)")
                            
                            # Enviar email al admin cuando se alcanza el 80%
                            try:
                                from lib.email import send_admin_email
                                
                                # Obtener email del usuario
                                user_email_response = supabase_client.table("profiles").select("email, current_plan").eq("id", user_id).execute()
                                user_email = user_email_response.data[0].get("email") if user_email_response.data else None
                                current_plan = user_email_response.data[0].get("current_plan", "N/A") if user_email_response.data else "N/A"
                                
                                def send_admin_80_percent_email():
                                    try:
                                        admin_html = f"""
                                        <html>
                                        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                            <div style="background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                                <h2 style="color: white; margin: 0; font-size: 24px;">⚠️ Alerta: Usuario alcanzó 80% de límite</h2>
                                            </div>
                                            
                                            <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                                <p style="font-size: 16px; margin-bottom: 20px;">
                                                    Un usuario ha alcanzado el <strong>80% de su límite mensual de tokens</strong>.
                                                </p>
                                                
                                                <div style="background: #fef3c7; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #f59e0b;">
                                                    <ul style="list-style: none; padding: 0; margin: 0;">
                                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                            <strong style="color: #92400e;">Email del usuario:</strong> 
                                                            <span style="color: #333;">{user_email or 'N/A'}</span>
                                                        </li>
                                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                            <strong style="color: #92400e;">ID de usuario:</strong> 
                                                            <span style="color: #333; font-family: monospace; font-size: 12px;">{user_id}</span>
                                                        </li>
                                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                            <strong style="color: #92400e;">Plan actual:</strong> 
                                                            <span style="color: #333;">{current_plan}</span>
                                                        </li>
                                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                            <strong style="color: #92400e;">Límite mensual:</strong> 
                                                            <span style="color: #333;">{tokens_monthly_limit:,} tokens</span>
                                                        </li>
                                                        <li style="margin-bottom: 12px; padding-bottom: 12px; border-bottom: 1px solid #e5e7eb;">
                                                            <strong style="color: #92400e;">Tokens restantes:</strong> 
                                                            <span style="color: #333;">{nuevos_tokens:,} tokens</span>
                                                        </li>
                                                        <li style="margin-bottom: 0;">
                                                            <strong style="color: #92400e;">Porcentaje usado:</strong> 
                                                            <span style="color: #d97706; font-weight: bold; font-size: 18px;">{usage_percent:.1f}%</span>
                                                        </li>
                                                    </ul>
                                                </div>
                                                
                                                <p style="font-size: 14px; color: #666; margin-top: 20px;">
                                                    <strong>Nota:</strong> El usuario recibirá un aviso suave. Si alcanza el 90%, será elegible para un descuento del 20%.
                                                </p>
                                                
                                                <p style="font-size: 12px; color: #666; margin-top: 20px; text-align: center;">
                                                    Fecha: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                                                </p>
                                            </div>
                                        </body>
                                        </html>
                                        """
                                        send_admin_email("⚠️ Alerta: Usuario alcanzó 80% de límite de tokens", admin_html)
                                    except Exception as e:
                                        print(f"⚠️ Error al enviar email al admin por 80% de uso: {e}")
                                
                                admin_thread = threading.Thread(target=send_admin_80_percent_email, daemon=True)
                                admin_thread.start()
                            except Exception as e:
                                print(f"⚠️ Error al preparar email al admin por 80% de uso: {e}")
                        
                        # Elegibilidad para descuento al 90% de uso
                        if usage_percent >= 90 and not profile.get("fair_use_discount_eligible", False):
                            update_data["fair_use_discount_eligible"] = True
                            update_data["fair_use_discount_eligible_at"] = datetime.utcnow().isoformat()
                            print(f"🔔 Usuario {user_id} alcanzó 90% de uso ({usage_percent:.1f}%) - Elegible para descuento del 20%")
                            
                            # Enviar email de alerta al 90% (solo una vez)
                            if not profile.get("fair_use_email_sent", False):
                                try:
                                    # Obtener email del usuario
                                    user_email_response = supabase_client.table("profiles").select("email").eq("id", user_id).execute()
                                    user_email = user_email_response.data[0].get("email") if user_email_response.data else None
                                    
                                    if user_email:
                                        # Obtener información del plan
                                        plan_name = "tu plan actual"
                                        current_plan_code_for_email = None
                                        if profile_fair_use.data:
                                            current_plan_code_for_email = profile_fair_use.data[0].get("current_plan")
                                            if current_plan_code_for_email:
                                                from plans import get_plan_by_code
                                                plan_info = get_plan_by_code(current_plan_code_for_email)
                                                if plan_info:
                                                    plan_name = plan_info.name
                                        
                                        # Guardar variables para usar en el thread
                                        plan_code_for_thread = current_plan_code_for_email
                                        plan_name_for_thread = plan_name
                                        
                                        # Enviar email en background (no bloquea)
                                        def send_90_percent_email_background():
                                            try:
                                                from lib.email import send_email
                                                from plans import get_plan_by_code, CODEX_PLANS
                                                
                                                # Construir URL de planes antes del f-string
                                                frontend_url = os.getenv("FRONTEND_URL", "https://www.codextrader.tech").strip('"').strip("'").strip()
                                                planes_url = f"{frontend_url.rstrip('/')}/planes"
                                                
                                                # Determinar plan sugerido
                                                suggested_plan_code = "trader"
                                                if plan_code_for_thread:
                                                    current_plan_index = next((i for i, p in enumerate(CODEX_PLANS) if p.code == plan_code_for_thread), -1)
                                                    if current_plan_index >= 0 and current_plan_index < len(CODEX_PLANS) - 1:
                                                        suggested_plan_code = CODEX_PLANS[current_plan_index + 1].code
                                                
                                                suggested_plan = get_plan_by_code(suggested_plan_code)
                                                suggested_plan_name = suggested_plan.name if suggested_plan else "Trader"
                                                
                                                # Template de email atractivo (simplificado para ahorrar espacio)
                                                email_html = f"""
                                                <html>
                                                <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); padding: 30px; text-align: center; border-radius: 12px;">
                                                        <h1 style="color: white; margin: 0;">🚨 Alerta de Uso</h1>
                                                    </div>
                                                    <div style="background: white; padding: 30px; border-radius: 8px; margin-top: 20px;">
                                                        <p>Has alcanzado el <strong>90% de tu límite</strong> en tu plan <strong>{plan_name_for_thread}</strong>.</p>
                                                        <div style="background: #f0fdf4; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                                            <p><strong>📊 Tu uso actual:</strong></p>
                                                            <p>Tokens restantes: <strong>{nuevos_tokens:,}</strong> de <strong>{tokens_monthly_limit:,}</strong></p>
                                                            <p>Porcentaje usado: <strong>{usage_percent:.1f}%</strong></p>
                                                        </div>
                                                        <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 25px; border-radius: 10px; text-align: center; margin: 25px 0;">
                                                            <h2 style="margin: 0 0 10px 0;">🎁 ¡Descuento Especial del 20%!</h2>
                                                            <p>Te ofrecemos un <strong>20% de descuento</strong> para actualizar tu plan.</p>
                                                            <div style="background: white; color: #f5576c; padding: 15px 30px; border-radius: 8px; font-size: 24px; font-weight: bold; margin: 15px 0; display: inline-block;">CUPON20</div>
                                                        </div>
                                                        <div style="text-align: center; margin: 30px 0;">
                                                            <a href="{planes_url}" style="display: inline-block; background: #667eea; color: white; padding: 15px 40px; text-decoration: none; border-radius: 8px; font-weight: bold;">Ver Planes y Aprovechar Descuento</a>
                                                        </div>
                                                    </div>
                                                </body>
                                                </html>
                                                """
                                                
                                                send_email(
                                                    to=user_email,
                                                    subject=f"🚨 Has alcanzado el 90% de tu límite - Descuento del 20% disponible",
                                                    html=email_html
                                                )
                                                
                                                # Marcar que el email fue enviado
                                                supabase_client.table("profiles").update({
                                                    "fair_use_email_sent": True
                                                }).eq("id", user_id).execute()
                                                
                                                print(f"✅ Email de alerta al 90% enviado a {user_email}")
                                                
                                                # IMPORTANTE: También enviar email al admin cuando se alcanza el 90%
                                                try:
                                                    from lib.email import send_admin_email
                                                    
                                                    admin_html_90 = f"""
                                                    <html>
                                                    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
                                                        <div style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); padding: 20px; text-align: center; border-radius: 10px 10px 0 0;">
                                                            <h2 style="color: white; margin: 0; font-size: 24px;">🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite</h2>
                                                        </div>
                                                        
                                                        <div style="background: #ffffff; padding: 30px; border-radius: 0 0 10px 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                                                            <p>Un usuario ha alcanzado el <strong>90% de su límite mensual de tokens</strong>.</p>
                                                            <div style="background: #fee2e2; padding: 20px; border-radius: 8px; margin: 20px 0;">
                                                                <p><strong>Email:</strong> {user_email}</p>
                                                                <p><strong>ID:</strong> {user_id}</p>
                                                                <p><strong>Plan:</strong> {plan_name_for_thread}</p>
                                                                <p><strong>Uso:</strong> {usage_percent:.1f}%</p>
                                                            </div>
                                                        </div>
                                                    </body>
                                                    </html>
                                                    """
                                                    send_admin_email("🚨 ALERTA CRÍTICA: Usuario alcanzó 90% de límite de tokens", admin_html_90)
                                                    print(f"✅ Email de alerta al admin enviado por 90% de uso de usuario {user_id}")
                                                except Exception as admin_error:
                                                    print(f"⚠️ Error al enviar email al admin por 90% de uso: {admin_error}")
                                            except Exception as e:
                                                print(f"⚠️ Error al enviar email de alerta al 90%: {e}")
                                        
                                        email_thread = threading.Thread(target=send_90_percent_email_background, daemon=True)
                                        email_thread.start()
                                except Exception as e:
                                    print(f"⚠️ Error al preparar envío de email al 90%: {e}")
            except Exception as e:
                # Si las columnas no existen, continuar sin la lógica de uso justo
                # Verificar si es un error de columna no existente (código 42703) o tabla no encontrada (PGRST205)
                error_str = str(e)
                if "42703" in error_str or "PGRST205" in error_str or "does not exist" in error_str.lower():
                    # Solo mostrar warning en modo debug, no en producción
                    pass
                else:
                    # Para otros errores, mostrar el warning
                    logger.warning(f"Columnas de uso justo no disponibles (puede que no estén creadas): {e}")
                # Continuar sin actualizar campos de uso justo
            
            try:
                supabase_client.table("profiles").update(update_data).eq("id", user_id).execute()
                print(f"[INFO] Tokens descontados: {tokens_usados} tokens")
                print(f"[INFO] Tokens restantes después: {nuevos_tokens} tokens")
            except Exception as e:
                # Si falla la actualización, aún devolvemos la respuesta pero registramos el error
                print(f"ERROR: Error al actualizar tokens: {str(e)}")
            
            # Paso C: Crear o usar sesión de chat y guardar mensajes
            # conversation_id ya está inicializado al inicio de la función
            try:
                # Si no hay conversation_id, crear una nueva sesión
                if not conversation_id:
                    # Crear nueva sesión de chat
                    session_response = supabase_client.table("chat_sessions").insert({
                        "user_id": user_id,
                        "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                    }).execute()
                    
                    if session_response.data and len(session_response.data) > 0:
                        conversation_id = session_response.data[0]["id"]
                        print(f"[INFO] Nueva sesión de chat creada: {conversation_id}")
                    else:
                        print(f"[WARN] No se pudo crear sesión de chat, continuando sin guardar historial")
                else:
                    # Si hay conversation_id, verificar que existe y pertenece al usuario
                    try:
                        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
                        if not session_check.data:
                            # La sesión no existe o no pertenece al usuario, crear una nueva
                            print(f"[WARN] Sesión {conversation_id} no encontrada o no pertenece al usuario, creando nueva sesión")
                            session_response = supabase_client.table("chat_sessions").insert({
                                "user_id": user_id,
                                "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                            }).execute()
                            if session_response.data and len(session_response.data) > 0:
                                conversation_id = session_response.data[0]["id"]
                    except Exception as e:
                        print(f"[WARN] Error verificando sesión: {e}, creando nueva sesión")
                        session_response = supabase_client.table("chat_sessions").insert({
                            "user_id": user_id,
                            "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
                        }).execute()
                        if session_response.data and len(session_response.data) > 0:
                            conversation_id = session_response.data[0]["id"]
            except Exception as e:
                # Si la tabla no existe o hay error, continuar sin guardar historial
                print(f"[WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
                import traceback
                traceback.print_exc()
            
            # Guardar mensajes si tenemos conversation_id
            if conversation_id:
                try:
                    # Guardar mensaje del usuario
                    supabase_client.table("conversations").insert({
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "message_role": "user",
                        "message_content": query_input.query,
                        "tokens_used": 0
                    }).execute()
                    
                    # Guardar respuesta del asistente
                    supabase_client.table("conversations").insert({
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "message_role": "assistant",
                        "message_content": respuesta_texto,
                        "tokens_used": tokens_usados
                    }).execute()
                    
                    # Actualizar updated_at de la sesión (se hace automáticamente con el trigger, pero lo hacemos explícitamente también)
                    supabase_client.table("chat_sessions").update({
                        "updated_at": "now()"
                    }).eq("id", conversation_id).execute()
                except Exception as e:
                    # Si la tabla no existe o hay error, continuar sin guardar historial
                    print(f"[WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
                    import traceback
                    traceback.print_exc()
            
                # Devolver la respuesta inmediatamente después de procesar exitosamente LiteLLM
                # Esto evita que el bloque else del fallback sobrescriba la respuesta
                logger.info(f"📤 Devolviendo respuesta exitosa: {len(respuesta_texto) if respuesta_texto else 0} caracteres, tokens_usados={tokens_usados}, conversation_id={conversation_id}")
                # NOTA: El return aquí termina la función, evitando que el else se ejecute
                return {
                    "response": respuesta_texto,
                    "tokens_usados": tokens_usados,
                    "tokens_restantes": nuevos_tokens,
                    "conversation_id": conversation_id
                }
        else:
            # Si no hay chunks recuperados y no es saludo, usar un prompt genérico
            logger.warning("⚠️ No se encontraron chunks en RAG. Respondiendo sin contexto específico.")
            respuesta_texto = "Lo siento, no pude encontrar información específica en la biblioteca para responder tu pregunta. Por favor, reformula tu consulta o intenta con términos más generales relacionados con trading."
            tokens_usados = 0
            nuevos_tokens = tokens_restantes
            # conversation_id ya está inicializado al inicio de la función
            logger.info(f"📤 Respuesta preparada (sin chunks): {len(respuesta_texto)} caracteres")
            
            # Devolver la respuesta con información de tokens y conversation_id
            logger.info(f"📤 Devolviendo respuesta: {len(respuesta_texto) if respuesta_texto else 0} caracteres, tokens_usados={tokens_usados}, conversation_id={conversation_id}")
            return {
                "response": respuesta_texto,
                "tokens_usados": tokens_usados,
                "tokens_restantes": nuevos_tokens,
                "conversation_id": conversation_id
            }
    
    except HTTPException:
        # Re-lanzar excepciones HTTP (como tokens agotados)
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error al procesar consulta: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # En lugar de devolver error 500, devolver una respuesta de error amigable
        return {
            "response": f"Lo siento, hubo un error al procesar tu consulta. Por favor, intenta nuevamente. Error: {error_msg[:100]}",
            "tokens_usados": 0,
            "tokens_restantes": 0,
            "conversation_id": None,
            "error": True
        }


@chat_router.get("/chat-sessions")
async def get_chat_sessions(user = Depends(get_user), limit: int = 50):
    """
    Endpoint para obtener la lista de sesiones de chat del usuario autenticado.
    Devuelve las sesiones ordenadas por fecha de actualización (más recientes primero).
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Obteniendo sesiones de chat para usuario: {user_id}")
        
        # Usar el cliente global con SERVICE_KEY (las políticas RLS permiten service_role)
        try:
            # Obtener sesiones de chat ordenadas por fecha de actualización (más recientes primero)
            sessions_response = supabase_client.table("chat_sessions").select(
                "id, title, created_at, updated_at"
            ).eq("user_id", user_id).order("updated_at", desc=True).limit(limit).execute()
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al consultar tabla 'chat_sessions': {error_msg}")
            # Si la tabla no existe, retornar lista vacía en lugar de error
            if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
                logger.warning("⚠️ La tabla 'chat_sessions' no existe. Retornando lista vacía.")
                return {
                    "sessions": [],
                    "total": 0
                }
            raise
        
        if not sessions_response.data:
            logger.info(f"ℹ️ No hay sesiones para usuario: {user_id}")
            return {
                "sessions": [],
                "total": 0
            }
        
        logger.info(f"✅ Sesiones obtenidas: {len(sessions_response.data)} para usuario: {user_id}")
        
        return {
            "sessions": sessions_response.data,
            "total": len(sessions_response.data)
        }
    except HTTPException as http_ex:
        # Si es un error de autenticación (401), re-lanzarlo
        if http_ex.status_code == 401:
            raise
        # Para otros errores HTTP, retornar lista vacía
        logger.warning(f"⚠️ Error HTTP {http_ex.status_code} en /chat-sessions: {http_ex.detail}")
        return {
            "sessions": [],
            "total": 0
        }
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error en /chat-sessions: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # Si es un error de conexión a Supabase, dar mensaje más claro
        if "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            logger.warning("⚠️ Error de conexión con Supabase. Retornando lista vacía.")
            return {
                "sessions": [],
                "total": 0
            }
        # Si la tabla no existe, retornar lista vacía en lugar de error
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            logger.warning("⚠️ La tabla 'chat_sessions' no existe. Retornando lista vacía.")
            return {
                "sessions": [],
                "total": 0
            }
        # En lugar de devolver error 500, retornar lista vacía
        logger.warning("⚠️ Retornando lista vacía debido a error")
        return {
            "sessions": [],
            "total": 0
        }


@chat_router.get("/chat-sessions/{conversation_id}/messages")
async def get_conversation_messages(conversation_id: str, user = Depends(get_user), limit: int = 100):
    """
    Endpoint para obtener los mensajes de una conversación específica.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Obtener mensajes de la conversación ordenados por fecha de creación
        messages_response = supabase_client.table("conversations").select(
            "id, message_role, message_content, tokens_used, created_at"
        ).eq("conversation_id", conversation_id).eq("user_id", user_id).order("created_at", desc=False).limit(limit).execute()
        
        if not messages_response.data:
            return {
                "messages": [],
                "total": 0
            }
        
        return {
            "messages": messages_response.data,
            "total": len(messages_response.data)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al obtener mensajes: {str(e)}"
        )


@chat_router.post("/chat-sessions")
async def create_chat_session(create_input: Optional[CreateChatSessionInput] = None, user = Depends(get_user)):
    """
    Endpoint para crear una nueva sesión de chat.
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Creando nueva sesión de chat para usuario: {user_id}")
        
        try:
            # Crear nueva sesión de chat
            new_session = supabase_client.table("chat_sessions").insert({
                "user_id": user_id,
                "title": create_input.title if create_input and create_input.title else "Nueva conversación"
            }).execute()
            
            if not new_session.data:
                logger.warning("⚠️ No se recibieron datos al crear sesión")
                # Retornar una sesión temporal en lugar de error
                import uuid
                return {
                    "session": {
                        "id": str(uuid.uuid4()),
                        "user_id": str(user_id),
                        "title": create_input.title if create_input and create_input.title else "Nueva conversación",
                        "created_at": None,
                        "updated_at": None
                    },
                    "message": "Sesión creada (temporal)"
                }
            
            logger.info(f"✅ Sesión creada exitosamente: {new_session.data[0]['id']}")
            return {
                "session": new_session.data[0],
                "message": "Conversación creada exitosamente"
            }
        except Exception as db_error:
            error_msg = str(db_error)
            logger.error(f"❌ Error al crear sesión en BD: {error_msg}")
            logger.error(f"❌ Traceback completo: {str(db_error)}", exc_info=True)
            # Retornar una sesión temporal en lugar de error 500
            import uuid
            return {
                "session": {
                    "id": str(uuid.uuid4()),
                    "user_id": str(user_id),
                    "title": create_input.title if create_input and create_input.title else "Nueva conversación",
                    "created_at": None,
                    "updated_at": None
                },
                "message": "Sesión creada (temporal debido a error en BD)"
            }
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        logger.error(f"❌ Error general al crear conversación: {error_msg}")
        logger.error(f"❌ Traceback completo: {str(e)}", exc_info=True)
        # Retornar una sesión temporal en lugar de error 500
        import uuid
        return {
            "session": {
                "id": str(uuid.uuid4()),
                "user_id": str(user.id) if hasattr(user, 'id') else None,
                "title": "Nueva conversación",
                "created_at": None,
                "updated_at": None
            },
            "message": "Sesión creada (temporal debido a error)"
        }


@chat_router.delete("/chat-sessions/{conversation_id}")
async def delete_chat_session(conversation_id: str, user = Depends(get_user)):
    """
    Endpoint para eliminar una sesión de chat y todos sus mensajes.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Eliminar la sesión (los mensajes se eliminarán automáticamente por CASCADE)
        supabase_client.table("chat_sessions").delete().eq("id", conversation_id).execute()
        
        return {
            "message": "Conversación eliminada exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al eliminar conversación: {str(e)}"
        )


@chat_router.patch("/chat-sessions/{conversation_id}")
async def update_chat_session(conversation_id: str, title: str, user = Depends(get_user)):
    """
    Endpoint para actualizar el título de una sesión de chat.
    """
    try:
        user_id = user.id
        
        # Verificar que la conversación pertenezca al usuario
        session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
        if not session_check.data:
            raise HTTPException(
                status_code=404,
                detail="Conversación no encontrada o no pertenece al usuario"
            )
        
        # Actualizar el título
        updated_session = supabase_client.table("chat_sessions").update({
            "title": title,
            "updated_at": "now()"
        }).eq("id", conversation_id).execute()
        
        if not updated_session.data:
            raise HTTPException(
                status_code=500,
                detail="Error al actualizar conversación"
            )
        
        return {
            "session": updated_session.data[0],
            "message": "Título actualizado exitosamente"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error al actualizar conversación: {str(e)}"
        )

