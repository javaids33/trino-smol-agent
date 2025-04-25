from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal

# --- OpenAI Compatible Schemas ---

class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatCompletionRequest(BaseModel):
    model: str # Although we use our own logic, mimic OpenAI structure
    messages: List[ChatMessage]
    # Add other OpenAI parameters if needed (temperature, max_tokens, stream, etc.)
    # stream: bool = False
    max_tokens: Optional[int] = None
    # ... other potential fields

class ResponseMessage(BaseModel):
    role: Literal["assistant"] = "assistant"
    # Content could be SQL, results summary, explanation, or error
    content: str
    # Potentially add structured content if needed beyond simple string
    # tool_calls: Optional[List[Any]] = None

class Choice(BaseModel):
    index: int = 0
    message: ResponseMessage
    finish_reason: Literal["stop", "length", "error"] = "stop" # Adjust reason based on outcome

class Usage(BaseModel):
    # Optional: You might estimate token usage if relevant
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

class ChatCompletionResponse(BaseModel):
    id: str # Generate a unique ID for the request
    object: Literal["chat.completion"] = "chat.completion"
    created: int # Unix timestamp
    model: str # Echo back the requested model or indicate internal model
    choices: List[Choice]
    usage: Optional[Usage] = None
    # Add custom fields for SQL, explanation etc. if needed outside 'content'
    # _sql_query: Optional[str] = None
    # _explanation: Optional[str] = None
    # _results_preview: Optional[List[Dict[str, Any]]] = None

# --- Internal Schemas (Optional) ---

# Could define Pydantic models for internal state if needed,
# but using Dicts within the orchestrator might be simpler for now. 