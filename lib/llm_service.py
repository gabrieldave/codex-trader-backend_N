"""
Servicio para llamadas a modelos de IA (LiteLLM): construcción de prompts y streaming.
"""
import os
import logging
from typing import Optional, Dict, Any, AsyncGenerator, Tuple

from fastapi import HTTPException
import litellm

from lib.config_shared import (
    modelo_por_defecto,
    DEEPSEEK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    GOOGLE_API_KEY, COHERE_API_KEY
)
import config

logger = logging.getLogger(__name__)


class LLMService:
    """Servicio para generar respuestas usando modelos de IA."""
    
    def __init__(self):
        self.default_model = modelo_por_defecto
        self.api_keys = {
            "deepseek": DEEPSEEK_API_KEY,
            "openai": OPENAI_API_KEY,
            "anthropic": ANTHROPIC_API_KEY,
            "google": GOOGLE_API_KEY,
            "cohere": COHERE_API_KEY
        }
    
    def get_chat_model(self) -> str:
        """Obtiene el modelo de chat a usar."""
        chat_model = self.default_model
        if not chat_model:
            if DEEPSEEK_API_KEY:
                chat_model = "deepseek/deepseek-chat"
            else:
                chat_model = "gpt-3.5-turbo"
        return chat_model
    
    def _build_system_prompt(
        self,
        context: str,
        citation_list: str,
        is_greeting: bool,
        response_mode: str,
        is_deep_mode: bool
    ) -> Tuple[str, int]:
        """
        Construye el system prompt según el contexto y modo.
        
        Args:
            context: Contexto RAG recuperado
            citation_list: Lista de citaciones (solo en modo deep)
            is_greeting: Si es un saludo simple
            response_mode: Modo de respuesta ('fast' o 'deep')
            is_deep_mode: Si está en modo estudio profundo
            
        Returns:
            Tuple[system_prompt, max_tokens]
        """
        if is_greeting:
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
            return system_prompt, 100
        
        # Construir instrucciones según el modo
        greetings_instruction = self._get_greetings_instruction()
        mode_instruction = self._get_mode_instruction(response_mode)
        
        if is_deep_mode and citation_list:
            # Modo Estudio Profundo con citaciones
            system_prompt = f"""Eres Codex Trader, un experto financiero y asistente de RAG. Tu tarea es responder a la pregunta del usuario basándote en el contexto proporcionado.

Sigue estrictamente estas reglas:

1. **PRIORIDAD 1 - Usar RAG**: Si el contexto recuperado contiene información relevante para responder la pregunta, úsalo como base principal de tu respuesta.

2. **PRIORIDAD 2 - Complementar con conocimiento general**: Si el contexto recuperado es insuficiente o no cubre completamente la pregunta, complementa tu respuesta usando tu conocimiento general sobre trading, pero siempre menciona primero lo que encontraste en el contexto.

3. **PRIORIDAD 3 - Usar solo conocimiento general**: Si el contexto recuperado NO contiene información relevante para la pregunta (por ejemplo, si la pregunta es sobre un tema completamente diferente), entonces:
   - NO digas "no puedo responder" o "el contexto no contiene información"
   - En su lugar, usa tu conocimiento general para dar una respuesta completa y útil
   - Al final, menciona brevemente que esta información proviene de conocimiento general sobre trading

4. POR CADA HECHO del contexto RAG que utilices, debes **citar inmediatamente la fuente** usando el formato [X] al final de la frase, donde X es el número de la fuente.

5. Al final de la respuesta, bajo el encabezado '**Fuentes Utilizadas:**', lista todas las fuentes del RAG citadas en el formato [X] Nombre del libro. Si solo usaste conocimiento general, omite esta sección.

Contexto Recuperado:

---

{context}

---

Fuentes a Listar:

---

{citation_list}

---

"""
            return system_prompt, 4000
        else:
            # Modo Rápido o sin citaciones
            if context:
                # Hay contexto RAG disponible
                context_section = f"""
Contexto Recuperado:

---

{context}

---

INSTRUCCIONES:
- Usa el contexto recuperado como base principal de tu respuesta
- Si el contexto es insuficiente o no cubre completamente la pregunta, complementa con tu conocimiento general sobre trading
- Si el contexto NO es relevante para la pregunta, usa tu conocimiento general para responder completamente
- NO digas "no puedo responder" - siempre proporciona una respuesta útil

"""
            else:
                # No hay contexto RAG - usar conocimiento general
                context_section = """
INSTRUCCIONES:
- No hay contexto RAG disponible para esta pregunta
- Usa tu conocimiento general sobre trading para responder completamente
- Proporciona una respuesta útil y detallada según el modo seleccionado

"""
            base_prompt = config.ASSISTANT_DESCRIPTION + '\n\n' + greetings_instruction + '\n\n' + mode_instruction
            system_prompt = base_prompt + context_section
            max_tokens = 300 if response_mode == 'fast' else 4000
            return system_prompt, max_tokens
    
    def _get_greetings_instruction(self) -> str:
        """Retorna las instrucciones para manejo de saludos."""
        return """

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
    
    def _get_mode_instruction(self, response_mode: str) -> str:
        """Retorna las instrucciones según el modo de respuesta."""
        if response_mode == 'fast':
            return """

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
            return """

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
    
    def _configure_api_key(self, chat_model: str, litellm_params: Dict[str, Any]):
        """Configura la API key según el modelo."""
        if chat_model.startswith("deepseek") or "deepseek" in chat_model.lower():
            if DEEPSEEK_API_KEY:
                litellm_params["api_key"] = DEEPSEEK_API_KEY
                logger.info("✓ API Key de Deepseek configurada")
            else:
                raise HTTPException(
                    status_code=500,
                    detail="DEEPSEEK_API_KEY no está configurada pero se intentó usar Deepseek"
                )
        elif chat_model.startswith("claude") or "anthropic" in chat_model.lower():
            if ANTHROPIC_API_KEY:
                litellm_params["api_key"] = ANTHROPIC_API_KEY
                logger.info("✓ API Key de Anthropic (Claude) configurada")
        elif chat_model.startswith("gemini") or "google" in chat_model.lower():
            if GOOGLE_API_KEY:
                litellm_params["api_key"] = GOOGLE_API_KEY
                logger.info("✓ API Key de Google (Gemini) configurada")
        elif chat_model.startswith("command") or "cohere" in chat_model.lower():
            if COHERE_API_KEY:
                litellm_params["api_key"] = COHERE_API_KEY
                logger.info("✓ API Key de Cohere configurada")
        elif chat_model.startswith("gpt") or "openai" in chat_model.lower():
            if not OPENAI_API_KEY:
                raise HTTPException(
                    status_code=500,
                    detail="OPENAI_API_KEY no está configurada pero se intentó usar OpenAI/ChatGPT"
                )
            os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
            litellm_params["api_key"] = OPENAI_API_KEY
            logger.info(f"✓ API Key de OpenAI configurada para {chat_model}")
    
    async def generate_stream(
        self,
        query: str,
        context: str,
        citation_list: str,
        is_greeting: bool,
        response_mode: str,
        stream_state: Dict[str, Any]
    ) -> AsyncGenerator[str, None]:
        """
        Genera un stream de respuesta del LLM.
        
        Args:
            query: Consulta del usuario
            context: Contexto RAG
            citation_list: Lista de citaciones
            is_greeting: Si es un saludo
            response_mode: Modo de respuesta
            stream_state: Estado del stream (se actualiza durante el streaming)
            
        Yields:
            str: Chunks de texto de la respuesta
        """
        chat_model = self.get_chat_model()
        is_deep_mode = response_mode and (
            response_mode.lower() == 'deep' or 
            response_mode.lower() == 'estudio profundo' or
            response_mode.lower() == 'profundo'
        )
        
        system_prompt, max_tokens = self._build_system_prompt(
            context, citation_list, is_greeting, response_mode, is_deep_mode
        )
        
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
                    "content": query
                }
            ],
            "temperature": config.MODEL_TEMPERATURE,
            "max_tokens": max_tokens,
            "stream": True
        }
        
        # Configurar API key
        self._configure_api_key(chat_model, litellm_params)
        
        logger.info(f"📤 Enviando consulta a {chat_model} (query: {query[:50]}...)")
        
        # Funciones auxiliares para procesar chunks
        def assign_usage_values(usage_obj):
            if not usage_obj:
                return
            try:
                if isinstance(usage_obj, dict):
                    prompt_tokens = usage_obj.get("prompt_tokens", usage_obj.get("input_tokens", 0)) or 0
                    completion_tokens = usage_obj.get("completion_tokens", usage_obj.get("output_tokens", 0)) or 0
                    total_tokens_local = usage_obj.get("total_tokens", 0) or (prompt_tokens + completion_tokens)
                else:
                    prompt_tokens = getattr(usage_obj, "prompt_tokens", getattr(usage_obj, "input_tokens", 0)) or 0
                    completion_tokens = getattr(usage_obj, "completion_tokens", getattr(usage_obj, "output_tokens", 0)) or 0
                    total_tokens_local = getattr(usage_obj, "total_tokens", 0) or (prompt_tokens + completion_tokens)
                if prompt_tokens:
                    stream_state["input_tokens"] = prompt_tokens
                if completion_tokens:
                    stream_state["output_tokens"] = completion_tokens
                if total_tokens_local:
                    stream_state["total_tokens"] = total_tokens_local
            except Exception as usage_error:
                logger.debug(f"[STREAM] No se pudo asignar usage del chunk: {usage_error}")
        
        def extract_delta_text(chunk_obj):
            try:
                choices = getattr(chunk_obj, "choices", None)
                if choices is None and isinstance(chunk_obj, dict):
                    choices = chunk_obj.get("choices")
                if not choices:
                    return ""
                choice = choices[0]
                delta = getattr(choice, "delta", None)
                if delta is None and isinstance(choice, dict):
                    delta = choice.get("delta") or choice.get("message")
                content = None
                if delta is not None:
                    if isinstance(delta, dict):
                        content = delta.get("content")
                    else:
                        content = getattr(delta, "content", None)
                if content is None and isinstance(choice, dict):
                    content = choice.get("text")
                elif content is None:
                    content = getattr(choice, "text", None)
                if isinstance(content, list):
                    content = "".join([c for c in content if isinstance(c, str)])
                return content or ""
            except Exception as parse_error:
                logger.debug(f"[STREAM] Error al extraer delta: {parse_error}")
                return ""
        
        # Generar stream
        response_stream = None
        try:
            response_stream = litellm.completion(**litellm_params)
            chunk_count = 0
            for chunk in response_stream:
                usage_chunk = getattr(chunk, "usage", None)
                if usage_chunk:
                    assign_usage_values(usage_chunk)
                delta_text = extract_delta_text(chunk)
                if delta_text:
                    chunk_count += 1
                    stream_state["full_response"] += delta_text
                    if chunk_count % 10 == 0:
                        logger.debug(f"[STREAM] Chunk {chunk_count} enviado: {len(delta_text)} chars")
                    yield delta_text
            
            # Procesar respuesta final si existe
            final_response = getattr(response_stream, "final_response", None)
            if final_response:
                assign_usage_values(getattr(final_response, "usage", None))
            
            # Agregar citaciones si es modo deep
            if citation_list and is_deep_mode:
                fuentes_chunk = "\n\n---\n**FUENTES DETALLADAS:**\n" + citation_list
                stream_state["full_response"] += fuentes_chunk
                yield fuentes_chunk
                
        except Exception as stream_error:
            logger.error(f"❌ Error durante streaming: {stream_error}")
            stream_state["error"] = str(stream_error)
            fallback_chunk = "\n[Error] Ocurrió un problema al generar la respuesta. Por favor, intenta nuevamente."
            stream_state["full_response"] += fallback_chunk
            yield fallback_chunk
        finally:
            # Calcular tokens estimados si no se obtuvieron
            if stream_state.get("total_tokens", 0) == 0 and stream_state["full_response"]:
                approx_input = len(stream_state.get("prompt_text", query)) // 4
                approx_output = len(stream_state["full_response"]) // 4
                stream_state["input_tokens"] = stream_state.get("input_tokens") or approx_input
                stream_state["output_tokens"] = stream_state.get("output_tokens") or approx_output
                stream_state["total_tokens"] = stream_state["input_tokens"] + stream_state["output_tokens"]


# Instancia global del servicio
llm_service = LLMService()

