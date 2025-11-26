"""
Modelos Pydantic compartidos para los routers.
"""
from pydantic import BaseModel
from typing import Optional


class QueryInput(BaseModel):
    query: str
    conversation_id: Optional[str] = None
    response_mode: Optional[str] = 'fast'
    category: Optional[str] = None


class NewConversationInput(BaseModel):
    title: Optional[str] = None


class TokenReloadInput(BaseModel):
    cantidad: int


class CreateChatSessionInput(BaseModel):
    title: Optional[str] = None


class CheckoutSessionInput(BaseModel):
    planCode: str


class TestEmailInput(BaseModel):
    to: str
    subject: str
    html: str


class NotifyRegistrationInput(BaseModel):
    token_hash: Optional[str] = None
    user_id: Optional[str] = None
    triggered_by: Optional[str] = None
    password: Optional[str] = None  # Contraseña del usuario para incluir en email de bienvenida
    force_resend: Optional[bool] = False  # Forzar reenvío incluso si ya se envió antes


