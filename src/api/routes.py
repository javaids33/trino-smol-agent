import time
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from typing import Optional, Annotated, Dict, Any

from src.api.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ResponseMessage,
    Choice,
    Usage
)
from src.orchestration.agent_manager import MasterOrchestrator, OrchestrationError
from src.execution.trino_client import get_trino_executor, TrinoExecutor
from src.caching.cache import get_cache_client, RedisCache
from src.config import settings
from src.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# --- Dependency Injection ---

def get_orchestrator(
    trino: TrinoExecutor = Depends(get_trino_executor),
    cache: Optional[RedisCache] = Depends(get_cache_client)
) -> MasterOrchestrator:
    """Dependency injector for the MasterOrchestrator."""
    # Potentially cache the orchestrator instance if initialization is expensive,
    # but ensure thread safety if it holds state.
    return MasterOrchestrator(trino_executor=trino, cache_client=cache)

# --- Authentication (Placeholder) ---

async def verify_api_key(x_api_key: Annotated[str | None, Header()] = None):
    """Placeholder for API Key authentication."""
    if settings.API_KEY and x_api_key == settings.API_KEY:
        return True
    # In a real app, use a more secure comparison (e.g., timing-attack resistant)
    # and proper key management.
    logger.warning("API Key verification failed.")
    raise HTTPException(status_code=401, detail="Invalid API Key")

# --- Routes ---

@router.post(
    "/v1/chat/completions",
    response_model=ChatCompletionResponse,
    # dependencies=[Depends(verify_api_key)] # Uncomment to enable auth
)
async def chat_completions(
    request: ChatCompletionRequest,
    orchestrator: MasterOrchestrator = Depends(get_orchestrator)
):
    """
    Handles NLQ requests, orchestrates SQL generation and execution,
    and returns results in an OpenAI-compatible format.
    """
    request_id = f"chatcmpl-{uuid.uuid4()}"
    created_time = int(time.time())

    # Extract the last user message as the NLQ
    # TODO: Handle conversation history if needed for multi-turn queries
    last_user_message = next((msg for msg in reversed(request.messages) if msg.role == 'user'), None)

    if not last_user_message or not last_user_message.content:
        logger.error("No user message found in the request.")
        raise HTTPException(status_code=400, detail="No user message provided.")

    nlq = last_user_message.content
    logger.info(f"Received NLQ request (ID: {request_id}): '{nlq[:100]}...'")

    try:
        # Run the orchestration process
        orchestration_result = await run_orchestration_async(orchestrator, nlq)

        # Format the response based on the orchestration outcome
        response_content = format_response_content(orchestration_result)
        finish_reason = "stop" if orchestration_result.get("status") == "SUCCESS" else "error"

        if orchestration_result.get("status") != "SUCCESS" and not response_content:
             response_content = f"Processing failed. Error: {orchestration_result.get('error_message', 'Unknown error')}"


        response_message = ResponseMessage(content=response_content)
        choice = Choice(message=response_message, finish_reason=finish_reason)

        # TODO: Implement token counting if needed for Usage field
        usage_data = Usage()

        return ChatCompletionResponse(
            id=request_id,
            created=created_time,
            model=request.model, # Echo back requested model
            choices=[choice],
            usage=usage_data
            # Add custom fields here if needed (e.g., _sql_query)
            # _sql_query=orchestration_result.get("sql_final")
        )

    except HTTPException:
        # Re-raise HTTPExceptions (like auth errors)
        raise
    except OrchestrationError as e:
        logger.error(f"Orchestration failed for request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Orchestration Error: {e}")
    except Exception as e:
        logger.exception(f"Unexpected error processing request {request_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {type(e).__name__}")


async def run_orchestration_async(orchestrator: MasterOrchestrator, nlq: str) -> Dict[str, Any]:
    """
    Runs the potentially blocking orchestration logic in a thread pool
    to avoid blocking the main async event loop.
    FastAPI handles this automatically for standard 'def' route functions,
    but explicitly using run_in_executor is safer if agents involve I/O.
    """
    # For simplicity here, we call it directly. If agent calls are truly blocking I/O,
    # consider using asyncio.to_thread (Python 3.9+) or starlette.concurrency.run_in_threadpool
    # loop = asyncio.get_running_loop()
    # result = await loop.run_in_executor(None, orchestrator.process_nlq, nlq)
    # return result
    return orchestrator.process_nlq(nlq) # Assuming agent calls are async or handled internally


def format_response_content(result: Dict[str, Any]) -> str:
    """
    Formats the final content string for the API response based on success/failure
    and the presence of results, SQL, and explanation.
    """
    if result.get("status") == "SUCCESS":
        content_parts = []
        if result.get("explanation"):
            content_parts.append(f"Explanation:\n{result.get('explanation')}\n")
        if result.get("sql_final"):
             content_parts.append(f"Generated SQL:\n```sql\n{result.get('sql_final')}\n```\n")
        if result.get("results") is not None:
             # TODO: Implement better formatting/summarization for large results
             results_str = "\n".join(str(row) for row in result["results"][:10]) # Preview first 10 rows
             if len(result["results"]) > 10:
                 results_str += f"\n... ({len(result['results'])} total rows)"
             content_parts.append(f"Results Preview:\n{results_str}")

        return "\n".join(content_parts).strip() if content_parts else "Query processed successfully, but no specific output generated."
    else:
        # Failed request
        error_msg = result.get('error_message', 'An unknown error occurred.')
        content = f"Failed to process the query.\nError: {error_msg}"
        # Optionally include the last attempted SQL if available
        last_sql = result.get('sql_generated') or result.get('sql_final')
        if last_sql:
            content += f"\n\nLast Attempted SQL:\n```sql\n{last_sql}\n```"
        return content


# Include other potential endpoints like /v1/completions if needed,
# adapting the logic similarly. 