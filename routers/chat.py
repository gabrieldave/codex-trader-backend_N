"""
Router para endpoints de chat y sesiones de conversación.
"""
import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.responses import StreamingResponse

from lib.dependencies import get_user, supabase_client
from lib.token_service import token_service
from lib.rag_service import rag_service
from lib.llm_service import llm_service
from lib.vision_service import analyze_image
from routers.models import QueryInput, CreateChatSessionInput

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


def persist_chat_background_task(
    user_id: str,
    query_payload: dict,
    stream_state: dict,
    tokens_restantes: int,
    chat_model: str,
    response_mode: str,
    conversation_id: Optional[str],
):
    """
    Guarda los mensajes y actualiza los tokens después de finalizar el streaming.
    Se ejecuta en background para no bloquear la respuesta al usuario.
    """
    try:
        if stream_state.get("error"):
            logger.warning(f"[BG] Stream finalizó con error, no se guardará historial: {stream_state['error']}")
            return
        
        respuesta_texto = (stream_state.get("full_response") or "").strip()
        if not respuesta_texto:
            logger.warning("[BG] No hay respuesta para guardar en historial.")
            return
        
        prompt_text = stream_state.get("prompt_text") or query_payload.get("query") or ""
        input_tokens = stream_state.get("input_tokens") or 0
        output_tokens = stream_state.get("output_tokens") or 0
        total_tokens_usados = stream_state.get("total_tokens") or 0
        
        if total_tokens_usados == 0:
            input_tokens = len(prompt_text) // 4
            output_tokens = len(respuesta_texto) // 4
            total_tokens_usados = max(100 if respuesta_texto else 0, input_tokens + output_tokens)
        
        # Usar token_service para descontar tokens y manejar uso justo
        nuevos_tokens = token_service.deduct_tokens(
            user_id=user_id,
            tokens_used=total_tokens_usados,
            tokens_restantes=tokens_restantes,
            chat_model=chat_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            query_preview=prompt_text,
            response_mode=response_mode
        )
        
        user_query = query_payload.get("query") or ""
        
        try:
            if not conversation_id:
                session_response = supabase_client.table("chat_sessions").insert({
                    "user_id": user_id,
                    "title": user_query[:50] if len(user_query) > 50 else user_query
                }).execute()
                
                if session_response.data and len(session_response.data) > 0:
                    conversation_id = session_response.data[0]["id"]
                    print(f"[BG] Nueva sesión de chat creada: {conversation_id}")
                else:
                    print(f"[BG] [WARN] No se pudo crear sesión de chat, continuando sin guardar historial")
            else:
                try:
                    session_check = supabase_client.table("chat_sessions").select("id").eq("id", conversation_id).eq("user_id", user_id).execute()
                    if not session_check.data:
                        print(f"[BG] [WARN] Sesión {conversation_id} no encontrada o no pertenece al usuario, creando nueva sesión")
                        session_response = supabase_client.table("chat_sessions").insert({
                            "user_id": user_id,
                            "title": user_query[:50] if len(user_query) > 50 else user_query
                        }).execute()
                        if session_response.data and len(session_response.data) > 0:
                            conversation_id = session_response.data[0]["id"]
                except Exception as e:
                    print(f"[BG] [WARN] Error verificando sesión: {e}, creando nueva sesión")
                    session_response = supabase_client.table("chat_sessions").insert({
                        "user_id": user_id,
                        "title": user_query[:50] if len(user_query) > 50 else user_query
                    }).execute()
                    if session_response.data and len(session_response.data) > 0:
                        conversation_id = session_response.data[0]["id"]
        except Exception as e:
            print(f"[BG] [WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
            import traceback
            traceback.print_exc()
        
        if conversation_id:
            try:
                supabase_client.table("conversations").insert({
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_role": "user",
                    "message_content": user_query,
                    "tokens_used": 0
                }).execute()
                
                supabase_client.table("conversations").insert({
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_role": "assistant",
                    "message_content": respuesta_texto,
                    "tokens_used": total_tokens_usados
                }).execute()
                
                supabase_client.table("chat_sessions").update({
                    "updated_at": "now()"
                }).eq("id", conversation_id).execute()
            except Exception as e:
                print(f"[BG] [WARN] No se pudo guardar historial (puede que la tabla no exista aún): {str(e)}")
                import traceback
                traceback.print_exc()
    except Exception as bg_error:
        logger.error(f"[BG] Error inesperado en tarea de guardado: {bg_error}", exc_info=True)

@chat_router.post("/chat")
@chat_router.post("/chat-simple")
async def chat(query_input: QueryInput, background_tasks: BackgroundTasks, user = Depends(get_user)):
    """
    Endpoint para hacer consultas sobre los documentos indexados.
    
    Requiere autenticación mediante token JWT de Supabase.
    Verifica tokens disponibles, ejecuta la consulta con LiteLLM (Deepseek por defecto),
    y descuenta los tokens usados del perfil del usuario.
    """
    user_id = user.id
    
    # Paso 1: Verificar saldo de tokens
    tokens_restantes = token_service.verify_token_balance(user_id)
    
    # Paso 2: Detectar si es saludo simple
    is_greeting = is_simple_greeting(query_input.query)
    
    # Paso 3: Realizar búsqueda RAG (si no es saludo)
    context_text = ""
    citation_list = ""
    retrieved_chunks = []
    
    if not is_greeting:
        context_text, citation_list, retrieved_chunks = await rag_service.perform_rag_search(
            query=query_input.query,
            category=query_input.category,
            response_mode=query_input.response_mode or 'fast'
        )
    
    # Paso 4: Si no hay chunks y no es saludo, retornar mensaje de error
    if not retrieved_chunks and not is_greeting:
        logger.warning("⚠️ No se encontraron chunks en RAG. Respondiendo sin contexto específico.")
        respuesta_texto = "Lo siento, no pude encontrar información específica en la biblioteca para responder tu pregunta. Por favor, reformula tu consulta o intenta con términos más generales relacionados con trading."
        tokens_usados = 0
        nuevos_tokens = tokens_restantes
        conversation_id = query_input.conversation_id
        
        # Guardar en background
        background_tasks.add_task(
            persist_chat_background_task,
            str(user_id),
            query_input.dict(),
            {
                "full_response": respuesta_texto,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "prompt_text": query_input.query,
                "error": None,
                "conversation_id": conversation_id
            },
            tokens_restantes,
            llm_service.get_chat_model(),
            query_input.response_mode or 'fast',
            conversation_id
        )
        
        return {"response": respuesta_texto, "tokens_used": 0}
    
    # Paso 5: Crear o verificar sesión de chat
    conversation_id = query_input.conversation_id
    if not conversation_id:
        try:
            session_response = supabase_client.table("chat_sessions").insert({
                "user_id": user_id,
                "title": query_input.query[:50] if len(query_input.query) > 50 else query_input.query
            }).execute()
            if session_response.data and len(session_response.data) > 0:
                conversation_id = session_response.data[0]["id"]
                logger.info(f"[INFO] Nueva sesión de chat creada: {conversation_id}")
        except Exception as session_error:
            logger.warning(f"[WARN] No se pudo crear sesión: {session_error}")
    
    # Paso 6: Preparar estado del stream
    response_mode = query_input.response_mode or 'fast'
    stream_state = {
        "full_response": "",
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "prompt_text": query_input.query,
        "error": None,
        "conversation_id": conversation_id
    }
    
    # Paso 7: Generar stream de respuesta
    async def stream_generator():
        async for chunk in llm_service.generate_stream(
            query=query_input.query,
            context=context_text,
            citation_list=citation_list,
            is_greeting=is_greeting,
            response_mode=response_mode,
            stream_state=stream_state
        ):
            yield chunk
    
    # Paso 8: Programar tarea en background para guardar mensajes y descontar tokens
    background_tasks.add_task(
        persist_chat_background_task,
        str(user_id),
        query_input.dict(),
        stream_state,
        tokens_restantes,
        llm_service.get_chat_model(),
        response_mode,
        conversation_id
    )
    
    # Paso 9: Retornar respuesta streaming
    headers = {
        "Cache-Control": "no-cache, no-transform",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    }
    if conversation_id:
        headers["X-Conversation-Id"] = str(conversation_id)
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/plain; charset=utf-8",
        headers=headers
    )


@chat_router.get("/chat-sessions")
async def get_chat_sessions(user = Depends(get_user), limit: int = 50):
    """
    Endpoint para obtener la lista de sesiones de chat del usuario autenticado.
    Devuelve las sesiones ordenadas por fecha de actualización (más recientes primero).
    Protegido contra llamadas duplicadas simultáneas.
    """
    # PROTECCIÓN CONTRA DUPLICADOS: Verificar si ya se está procesando una solicitud
    import time
    
    cache_key = None  # Inicializar para usar en except
    
    try:
        user_id = user.id
        
        # Crear una clave única para este usuario
        cache_key = f"get_sessions_{user_id}"
        
        # Cache simple en memoria para evitar llamadas duplicadas
        if not hasattr(get_chat_sessions, '_request_cache'):
            get_chat_sessions._request_cache = {}
        
        # Limpiar cache antiguo (más de 2 segundos)
        current_time = time.time()
        get_chat_sessions._request_cache = {
            k: v for k, v in get_chat_sessions._request_cache.items()
            if current_time - v.get('time', 0) < 2  # 2 segundos
        }
        
        # Verificar si ya hay una solicitud en curso
        if cache_key in get_chat_sessions._request_cache:
            cached_data = get_chat_sessions._request_cache[cache_key]
            time_since_request = current_time - cached_data.get('time', 0)
            if time_since_request < 0.5:  # Menos de 500ms - retornar cache
                logger.debug(f"⚠️ Solicitud duplicada detectada para usuario {user_id} (hace {int(time_since_request * 1000)}ms). Retornando cache.")
                return cached_data.get('response', {"sessions": [], "total": 0})
        
        # Marcar solicitud en curso
        get_chat_sessions._request_cache[cache_key] = {
            'time': current_time,
            'response': None
        }
        
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
                response_data = {
                    "sessions": [],
                    "total": 0
                }
                # Limpiar cache en caso de error
                if cache_key in get_chat_sessions._request_cache:
                    del get_chat_sessions._request_cache[cache_key]
                return response_data
            raise
        
        if not sessions_response.data:
            logger.info(f"ℹ️ No hay sesiones para usuario: {user_id}")
            response_data = {
                "sessions": [],
                "total": 0
            }
            # Guardar en cache
            if cache_key in get_chat_sessions._request_cache:
                get_chat_sessions._request_cache[cache_key]['response'] = response_data
            return response_data
        
        logger.info(f"✅ Sesiones obtenidas: {len(sessions_response.data)} para usuario: {user_id}")
        
        response_data = {
            "sessions": sessions_response.data,
            "total": len(sessions_response.data)
        }
        
        # Guardar en cache
        if cache_key in get_chat_sessions._request_cache:
            get_chat_sessions._request_cache[cache_key]['response'] = response_data
        
        return response_data
    except HTTPException as http_ex:
        # Si es un error de autenticación (401), re-lanzarlo
        if http_ex.status_code == 401:
            raise
        # Para otros errores HTTP, retornar lista vacía
        logger.warning(f"⚠️ Error HTTP {http_ex.status_code} en /chat-sessions: {http_ex.detail}")
        response_data = {
            "sessions": [],
            "total": 0
        }
        # Limpiar cache en caso de error
        if cache_key and 'get_chat_sessions' in globals() and hasattr(get_chat_sessions, '_request_cache') and cache_key in get_chat_sessions._request_cache:
            del get_chat_sessions._request_cache[cache_key]
        return response_data
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
        response_data = {
            "sessions": [],
            "total": 0
        }
        # Limpiar cache en caso de error
        if cache_key and cache_key in get_chat_sessions._request_cache:
            del get_chat_sessions._request_cache[cache_key]
        return response_data


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
    Protegido contra llamadas duplicadas simultáneas.
    """
    try:
        user_id = user.id
        logger.info(f"🔍 Creando nueva sesión de chat para usuario: {user_id}")
        
        # PROTECCIÓN CONTRA DUPLICADOS: Verificar si ya se creó una sesión recientemente
        import hashlib
        import time
        
        # Crear una clave única para este usuario en esta sesión
        cache_key = f"create_session_{user_id}"
        
        # Cache simple en memoria (se puede mejorar con Redis en producción)
        if not hasattr(create_chat_session, '_session_cache'):
            create_chat_session._session_cache = {}
        
        # Limpiar cache antiguo (más de 5 segundos)
        current_time = time.time()
        create_chat_session._session_cache = {
            k: v for k, v in create_chat_session._session_cache.items()
            if current_time - v.get('time', 0) < 5  # 5 segundos
        }
        
        # Verificar si ya se creó una sesión en los últimos 2 segundos
        if cache_key in create_chat_session._session_cache:
            cached_data = create_chat_session._session_cache[cache_key]
            time_since_created = current_time - cached_data.get('time', 0)
            if time_since_created < 2:  # 2 segundos
                logger.warning(f"⚠️ Sesión ya creada recientemente para usuario {user_id} (hace {int(time_since_created)} segundos). Retornando sesión existente.")
                return {
                    "session": cached_data.get('session'),
                    "message": "Sesión ya existe (evitando duplicado)"
                }
        
        try:
            # Verificar si hay una sesión reciente (últimos 3 segundos) antes de crear una nueva
            try:
                recent_sessions = supabase_client.table("chat_sessions").select(
                    "id, title, created_at"
                ).eq("user_id", user_id).order("created_at", desc=True).limit(1).execute()
                
                if recent_sessions.data:
                    session = recent_sessions.data[0]
                    from datetime import datetime, timezone
                    created_at_str = session.get("created_at")
                    if created_at_str:
                        # Parsear la fecha y verificar si es muy reciente
                        try:
                            if isinstance(created_at_str, str):
                                created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            else:
                                created_at = created_at_str
                            
                            now = datetime.now(timezone.utc)
                            if isinstance(created_at, datetime):
                                if created_at.tzinfo is None:
                                    created_at = created_at.replace(tzinfo=timezone.utc)
                                time_diff = (now - created_at).total_seconds()
                                
                                if time_diff < 3:  # Menos de 3 segundos
                                    logger.info(f"ℹ️ Usando sesión reciente existente (creada hace {int(time_diff)} segundos)")
                                    # Guardar en cache
                                    create_chat_session._session_cache[cache_key] = {
                                        'session': session,
                                        'time': current_time
                                    }
                                    return {
                                        "session": session,
                                        "message": "Usando sesión reciente existente"
                                    }
                        except Exception as time_check_error:
                            logger.debug(f"⚠️ Error al verificar tiempo de sesión: {time_check_error}")
            except Exception as check_error:
                logger.debug(f"⚠️ Error al verificar sesiones recientes: {check_error}")
            
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
            
            # Guardar en cache para evitar duplicados
            create_chat_session._session_cache[cache_key] = {
                'session': new_session.data[0],
                'time': time.time()
            }
            
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


@chat_router.post("/chat/vision")
async def chat_vision(
    file: UploadFile = File(...),
    query: str = Form(...),
    response_mode: str = Form("Estudio Profundo"),
    conversation_id: Optional[str] = Form(None),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    user = Depends(get_user)
):
    """
    Endpoint para análisis multimodal de imágenes con RAG.
    
    Flujo:
    1. Analiza la imagen con Gemini 1.5 Flash
    2. Combina la descripción visual con la query para buscar en RAG
    3. Genera respuesta usando contexto RAG + análisis visual
    4. Descuenta tokens como "Estudio Profundo" (premium)
    5. Guarda el historial del chat
    
    Requiere autenticación mediante token JWT de Supabase.
    """
    user_id = user.id
    
    # Paso 1: Verificar saldo de tokens
    tokens_restantes = token_service.verify_token_balance(user_id)
    
    # Paso 2: Validar archivo
    if not file.content_type or not file.content_type.startswith('image/'):
        raise HTTPException(
            status_code=400,
            detail="El archivo debe ser una imagen"
        )
    
    try:
        # Paso A: Leer bytes del archivo y analizar imagen
        image_bytes = await file.read()
        logger.info(f"📸 Analizando imagen: {file.filename} ({len(image_bytes)} bytes)")
        
        descripcion_visual = await analyze_image(image_bytes)
        logger.info(f"✅ Análisis visual completado: {len(descripcion_visual)} caracteres")
        
        # Paso B: Combinar query + descripción visual para búsqueda RAG
        query_combinada = f"{query}\n\nAnálisis visual de la imagen:\n{descripcion_visual}"
        
        context_text = ""
        citation_list = ""
        retrieved_chunks = []
        
        # Realizar búsqueda RAG con la query combinada
        context_text, citation_list, retrieved_chunks = await rag_service.perform_rag_search(
            query=query_combinada,
            category=None,
            response_mode=response_mode or 'Estudio Profundo'
        )
        
        # Paso 3: Si no hay chunks, usar solo el análisis visual
        if not retrieved_chunks:
            logger.warning("⚠️ No se encontraron chunks en RAG. Usando solo análisis visual.")
            context_text = ""
        
        # Paso 4: Crear o verificar sesión de chat
        if not conversation_id:
            try:
                session_response = supabase_client.table("chat_sessions").insert({
                    "user_id": user_id,
                    "title": query[:50] if len(query) > 50 else query
                }).execute()
                if session_response.data and len(session_response.data) > 0:
                    conversation_id = session_response.data[0]["id"]
                    logger.info(f"[INFO] Nueva sesión de chat creada: {conversation_id}")
            except Exception as session_error:
                logger.warning(f"[WARN] No se pudo crear sesión: {session_error}")
        
        # Paso C: Construir prompt con contexto RAG + análisis visual + pregunta
        # El prompt se construye automáticamente en llm_service, pero necesitamos
        # incluir el análisis visual en el contexto
        contexto_completo = ""
        if context_text:
            contexto_completo = f"{context_text}\n\n"
        contexto_completo += f"Análisis Visual de la Imagen:\n---\n{descripcion_visual}\n---\n"
        
        # Paso 5: Preparar estado del stream
        # IMPORTANTE: Siempre usar "Estudio Profundo" para el cobro
        response_mode_premium = "Estudio Profundo"
        # Incluir análisis visual en prompt_text para cálculo de tokens más preciso
        prompt_text_completo = f"{query}\n\n[Análisis visual incluido: {len(descripcion_visual)} caracteres]"
        stream_state = {
            "full_response": "",
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "prompt_text": prompt_text_completo,
            "error": None,
            "conversation_id": conversation_id
        }
        
        # Paso D: Generar stream de respuesta
        async def stream_generator():
            async for chunk in llm_service.generate_stream(
                query=query,
                context=contexto_completo,
                citation_list=citation_list,
                is_greeting=False,
                response_mode=response_mode or 'Estudio Profundo',
                stream_state=stream_state
            ):
                yield chunk
        
        # Paso E: Programar tarea en background para guardar mensajes y descontar tokens
        # IMPORTANTE: Siempre cobrar como "Estudio Profundo" debido al doble costo de API
        query_payload = {
            "query": query,
            "response_mode": response_mode_premium,
            "conversation_id": conversation_id,
            "has_image": True,
            "image_filename": file.filename
        }
        
        background_tasks.add_task(
            persist_chat_background_task,
            str(user_id),
            query_payload,
            stream_state,
            tokens_restantes,
            llm_service.get_chat_model(),
            response_mode_premium,  # Siempre cobrar como Estudio Profundo
            conversation_id
        )
        
        # Paso 6: Retornar respuesta streaming
        headers = {
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        }
        if conversation_id:
            headers["X-Conversation-Id"] = str(conversation_id)
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/plain; charset=utf-8",
            headers=headers
        )
        
    except ValueError as ve:
        # Error de configuración (ej: GOOGLE_API_KEY no configurado)
        logger.error(f"❌ Error de configuración en análisis de imagen: {ve}")
        raise HTTPException(
            status_code=500,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"❌ Error en análisis de imagen: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la imagen: {str(e)}"
        )
