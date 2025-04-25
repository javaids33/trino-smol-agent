from fastapi import FastAPI
from src.api import routes as api_routes
from src.config import settings
from src.logging.logger import logger

# Create FastAPI app instance
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API Service to convert Natural Language Queries to SQL using SmolAgents and Trino.",
    # Add other FastAPI configurations like docs_url, redoc_url etc.
)

# Include API routers
app.include_router(api_routes.router, prefix="/v1") # Prefixing with /v1 for OpenAI compatibility

# --- Event Handlers (Optional) ---
@app.on_event("startup")
async def startup_event():
    logger.info(f"Starting up {settings.APP_NAME} v{settings.APP_VERSION}...")
    # Initialize connections or resources if needed here
    # (Trino and Redis connections are lazy/managed in their respective classes)
    logger.info("Application startup complete.")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info(f"Shutting down {settings.APP_NAME}...")
    # Clean up resources if needed (e.g., explicitly close connections)
    # trino_executor = get_trino_executor()
    # if trino_executor.conn:
    #     trino_executor.conn.close()
    # cache_client = get_cache_client()
    # if cache_client:
    #     cache_client.client.close() # Close Redis connection
    logger.info("Application shutdown complete.")

# --- Root Endpoint (Optional) ---
@app.get("/", tags=["Health Check"])
async def read_root():
    return {"message": f"Welcome to {settings.APP_NAME}"}

# --- Run with Uvicorn (for local development) ---
# This block is typically used for running directly with `python src/main.py`
# In production, you'd use `uvicorn src.main:app --host 0.0.0.0 --port 8000`
if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Uvicorn server for local development...")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level=settings.LOG_LEVEL.lower()) 