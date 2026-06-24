from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: Optional[str] = "naatomatic"
    messages: List[ChatMessage]
    stream: Optional[bool] = False
    thread_id: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None

class ChatChoiceMessage(BaseModel):
    role: str = "assistant"
    content: str

class ChatChoice(BaseModel):
    index: int = 0
    message: ChatChoiceMessage
    finish_reason: str = "stop"

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str = "naatomatic"
    choices: List[ChatChoice]
