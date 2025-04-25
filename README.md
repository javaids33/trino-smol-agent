# Trino-SmolAgent NLQ-to-SQL Service

A service that converts Natural Language Queries (NLQ) to SQL using a multi-agent architecture with SmolAgent and executes them against Trino.

## Overview

This service provides an API that allows users to submit natural language queries about data, which are then:

1. Analyzed to extract key entities and concepts
2. Converted to SQL using LLM agents
3. Validated against the Trino schema
4. Corrected if there are issues
5. Executed against Trino
6. Explained in natural language along with the results

## Features

- 🧠 Multi-agent architecture for NLQ-to-SQL conversion
- 🔄 SQL validation and correction loop
- 🗄️ Caching of schema information for efficiency
- 🔌 OpenAI-compatible API interface
- 📈 Automatic query explanation
- 🔒 Simple API key authentication

## Prerequisites

- Python 3.9+
- Trino server
- Redis (optional, for caching)
- OpenAI API key or other LLM provider
- Docker and Docker Compose (for containerized deployment)

## Installation

### Local Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/trino-smol-agent.git
   cd trino-smol-agent
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment variables by copying and modifying the sample .env file:
   ```bash
   cp .env.sample .env
   # Edit .env with your configuration
   ```

### Docker Deployment

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/trino-smol-agent.git
   cd trino-smol-agent
   ```

2. Configure environment variables for Docker:
   ```bash
   cp .env.docker .env
   # Edit .env with your configuration, especially:
   # - TRINO_HOST (name or IP of your Trino service)
   # - TRINO_NETWORK (Docker network where Trino is running)
   # - OPENAI_API_KEY (your OpenAI API key)
   ```

3. Build and run the Docker containers:
   ```bash
   docker-compose up -d
   ```

4. To connect to an existing Trino instance in another Docker Compose setup:
   - Make sure you've set the correct `TRINO_NETWORK` value in your `.env` file
   - This should match the network name where your Trino instance is running
   - Ensure `TRINO_HOST` matches the service name of your Trino container

   Example:
   ```
   TRINO_HOST=trino-coordinator
   TRINO_NETWORK=my-trino-network
   ```

## Configuration

Edit the `.env` file to configure the service:

```
# Trino Connection
TRINO_HOST=your_trino_host
TRINO_PORT=8080
TRINO_USER=your_trino_user
TRINO_CATALOG=your_catalog  # e.g., tpch
TRINO_SCHEMA=your_schema    # e.g., sf1

# Redis Cache (optional)
REDIS_HOST=your_redis_host
REDIS_PORT=6379

# LLM Provider (default: OpenAI)
LLM_PROVIDER=openai
OPENAI_API_KEY=your_openai_api_key

# Service
API_KEY=your_api_key_for_authentication
```

## Usage

### Running the Service

#### Local Development

Start the service with:

```bash
python src/main.py
```

For production deployment, use:

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

#### Docker Deployment

```bash
docker-compose up -d
```

To view logs:
```bash
docker-compose logs -f
```

To stop the service:
```bash
docker-compose down
```

### API Endpoints

#### Chat Completions (OpenAI Compatible)

```
POST /v1/chat/completions
```

Example request:

```json
{
  "model": "gpt-4",
  "messages": [
    {
      "role": "user",
      "content": "Show me the top 5 customers by total order value"
    }
  ]
}
```

Example response:

```json
{
  "id": "chatcmpl-123abc",
  "object": "chat.completion",
  "created": 1677858242,
  "model": "gpt-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Explanation:\nThis query finds the top 5 customers by their total order value.\n\nGenerated SQL:\n```sql\nSELECT c.name, SUM(o.totalprice) as total_value\nFROM customer c\nJOIN orders o ON c.custkey = o.custkey\nGROUP BY c.name\nORDER BY total_value DESC\nLIMIT 5\n```\n\nResults Preview:\n{'name': 'Customer#000000001', 'total_value': 50000.0}\n{'name': 'Customer#000000002', 'total_value': 48000.0}\n{'name': 'Customer#000000003', 'total_value': 45000.0}\n..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": null,
    "completion_tokens": null,
    "total_tokens": null
  }
}
```

## Troubleshooting Docker Network Connectivity

If you're having trouble connecting to Trino from the Docker container:

1. Verify the network configuration:
   ```bash
   docker network ls
   ```

2. Check if the Trino container is on the expected network:
   ```bash
   docker network inspect <trino_network_name>
   ```

3. Ensure the Trino host is accessible from the NLQ service container:
   ```bash
   docker exec -it nlq-sql-service ping <trino_host>
   ```

4. Check the service logs for connection errors:
   ```bash
   docker-compose logs nlq-sql-service
   ```

5. If needed, you can manually add the container to the Trino network:
   ```bash
   docker network connect <trino_network_name> nlq-sql-service
   ```

## Development

### Project Structure

- `src/` - Main source code
  - `config.py` - Configuration settings
  - `main.py` - Application entry point
  - `api/` - API routes and schemas
  - `caching/` - Redis caching
  - `execution/` - Trino client
  - `orchestration/` - Agent orchestration
    - `prompts/` - Templates for agent prompts
  - `logging/` - Logging utilities

### Adding Custom LLM Providers

To add support for other LLM providers besides OpenAI:

1. Modify `src/config.py` to support new provider settings
2. Update `get_llm_client()` function to initialize the new provider's client
3. Modify `_run_agent_task()` in `src/orchestration/agent_manager.py` to use the new provider

## License

[MIT License](LICENSE)

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.