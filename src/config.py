from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

# Load .env file for local development
from dotenv import load_dotenv
load_dotenv()

class Settings(BaseSettings):
    # Trino Connection
    TRINO_HOST: str = Field(validation_alias="TRINO_HOST")
    TRINO_PORT: int = Field(default=8080, validation_alias="TRINO_PORT")
    TRINO_USER: str = Field(default="trino", validation_alias="TRINO_USER")
    TRINO_CATALOG: str = Field(default="tpch", validation_alias="TRINO_CATALOG")
    TRINO_SCHEMA: str = Field(default="sf1", validation_alias="TRINO_SCHEMA")
    
    # Service Configuration
    API_KEY: str = Field(validation_alias="API_KEY")
    LOG_LEVEL: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    
    # SmolAgent Configuration
    AGENT_MAX_RETRIES: int = Field(default=2, validation_alias="AGENT_MAX_RETRIES")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Instantiate settings object for easy import
settings = Settings()

# --- Example LLM Client Setup (adjust based on smol-agent/provider) ---
# This part might live elsewhere or be handled directly by smol-agent's backend config

def get_llm_client(model_name: str):
    """Placeholder factory for getting an LLM client instance."""
    if settings.LLM_PROVIDER == "openai":
        import openai
        if not settings.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY must be set in environment/config")
        # Note: SmolAgent might handle client initialization differently.
        # This is just a conceptual placeholder.
        # You might configure smol-agent's LLMBackend directly.
        # return openai.OpenAI(api_key=settings.OPENAI_API_KEY) # Example
        print(f"INFO: Would initialize OpenAI client for model {model_name}")
        # Actual SmolAgent setup will require more integration
        return None # Replace with actual LLM client/backend setup
    else:
        raise NotImplementedError(f"LLM Provider '{settings.LLM_PROVIDER}' not supported yet.") 