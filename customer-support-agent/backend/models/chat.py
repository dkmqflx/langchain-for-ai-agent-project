from pydantic import BaseModel


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    user_id: str = "anonymous"
