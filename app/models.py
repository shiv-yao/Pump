from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list = Field(default_factory=list)


class CommandRequest(BaseModel):
    command: str
    session_id: str = "default"


class InstallPluginRequest(BaseModel):
    name: str
    url: Optional[str] = None
    manifest: Optional[dict] = None


class PluginManualCreate(BaseModel):
    name: str
    description: str
    tools: list[dict]
    handler_code: Optional[str] = None
    category: Optional[str] = "utility"
    price: Optional[float] = 0
