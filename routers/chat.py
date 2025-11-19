"""
Router para endpoints de chat y sesiones de conversación.
"""
import re
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse

from lib.dependencies import get_user, supabase_client
from lib.token_service import token_service
from lib.rag_service import rag_service
from lib.llm_service import llm_service
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
