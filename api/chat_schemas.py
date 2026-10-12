from pydantic import BaseModel


class ChatRequest(BaseModel):
    merchant_id: str
    session_id: str
    message: str


class ChatResponse(BaseModel):
    response: str