from pydantic import BaseModel


class CreateConversationRequest(BaseModel):
    merchant_id: str


class CreateConversationResponse(BaseModel):
    session_id: str
    merchant_id: str


class AddMessageRequest(BaseModel):
    role: str
    content: str