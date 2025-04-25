import os
from jinja2 import Environment, FileSystemLoader
from typing import Optional, Dict, Any, Tuple, List

from smol_agent import SmolAgent # Assuming SmolAgent is importable

from src.config import settings, get_llm_client
from src.execution.trino_client import TrinoExecutor, get_trino_executor
from src.caching.cache import RedisCache, get_cache_client
from src.logging.logger import get_logger

logger = get_logger(__name__)

# Setup Jinja2 environment
prompt_dir = os.path.join(os.path.dirname(__file__), 'prompts')
jinja_env = Environment(loader=FileSystemLoader(prompt_dir), autoescape=True)

class OrchestrationError(Exception):
    """Custom exception for orchestration failures."""
    pass


class MasterOrchestrator:
    """Orchestrates the NLQ-to-SQL process using specialized agents."""

    def __init__(self, trino_executor: TrinoExecutor, cache_client: Optional[RedisCache]):
        self.trino = trino_executor
        self.cache = cache_client
        # TODO: Initialize LLM client/backend properly based on smol-agent setup
        # This is highly dependent on how SmolAgent handles LLM backends.
        # You might pass backend configurations or pre-initialized clients.
        # self.llm_backend_generation = get_llm_client(settings.OPENAI_MODEL_GENERATION)
        # self.llm_backend_analysis = get_llm_client(settings.OPENAI_MODEL_ANALYSIS)
        # ... etc for other models

        logger.info("Master Orchestrator initialized.")

    def _load_prompt(self, template_name: str, context: Dict[str, Any]) -> str:
        """Loads and renders a Jinja2 prompt template."""
        try:
            template = jinja_env.get_template(template_name)
            return template.render(context)
        except Exception as e:
            logger.error(f"Failed to load or render prompt template {template_name}: {e}")
            raise OrchestrationError(f"Prompt generation failed for {template_name}") from e

    def _run_agent_task(self, agent_name: str, prompt: str, model_name: str) -> str:
        """
        Runs a specific task using SmolAgent with the specified LLM model.
        """
        logger.info(f"Running {agent_name} task with model {model_name}...")
        
        try:
            # Initialize SmolAgent with the appropriate LLM client
            agent = SmolAgent(
                llm_backend=get_llm_client(model_name),
                system_prompt=f"You are a {agent_name} specialized in SQL generation and analysis."
            )
            
            # Execute the task and get the response
            response = agent.execute(prompt)
            
            # Clean up response (remove markdown backticks if present)
            response = response.replace("```sql", "").replace("```", "").strip()
            
            logger.debug(f"{agent_name} response: {response}")
            return response
            
        except Exception as e:
            logger.error(f"Error in {agent_name} task: {str(e)}")
            raise OrchestrationError(f"Failed to execute {agent_name} task: {str(e)}") from e

    def _analyze_query(self, nlq: str) -> str:
        """Uses Query Analyzer Agent."""
        prompt = self._load_prompt("query_analyzer.j2", {"nlq": nlq})
        analysis = self._run_agent_task(
            "Query Analyzer",
            prompt,
            settings.OPENAI_MODEL_ANALYSIS
        )
        return analysis

    def _retrieve_schema(self, analysis_hints: Optional[str] = None) -> str:
        """
        Uses Schema Retrieval Agent logic (cache check + Trino call).
        'analysis_hints' could potentially be used to fetch a subset of the schema in future.
        """
        cache_key = f"schema:{settings.TRINO_CATALOG}:{settings.TRINO_SCHEMA}"
        cached_schema = self.cache.get(cache_key) if self.cache else None

        if cached_schema:
            logger.info("Schema retrieved from cache.")
            return cached_schema

        logger.info("Schema not in cache, fetching from Trino...")
        schema_str, error = self.trino.get_schema_info(
            target_catalog=settings.TRINO_CATALOG,
            target_schema=settings.TRINO_SCHEMA
        )
        if error:
            logger.error(f"Failed to retrieve schema: {error}")
            raise OrchestrationError(f"Schema retrieval failed: {error}") from error
        if schema_str is None:
             raise OrchestrationError("Schema retrieval returned None unexpectedly.")


        if self.cache:
            self.cache.set(cache_key, schema_str, ttl=settings.SCHEMA_CACHE_TTL)

        return schema_str

    def _generate_sql(self, nlq: str, schema_info: str, analysis_hints: str) -> str:
        """Uses SQL Generation Agent."""
        prompt = self._load_prompt("sql_generator.j2", {
            "nlq": nlq,
            "schema_info": schema_info,
            "analysis_hints": analysis_hints
        })
        sql_draft = self._run_agent_task(
            "SQL Generator",
            prompt,
            settings.OPENAI_MODEL_GENERATION
        )
        if not sql_draft or not sql_draft.upper().startswith("SELECT"):
            logger.error(f"SQL Generator produced invalid output: {sql_draft}")
            raise OrchestrationError("SQL Generation failed to produce valid SQL structure.")
        return sql_draft

    def _validate_sql(self, sql_draft: str, schema_info: str) -> Tuple[bool, Optional[str]]:
        """
        Uses SQL Validation Agent (LLM-based semantic check + Trino execution check).
        Returns (is_valid, error_message)
        """
        # 1. LLM-based check (optional, faster check)
        # prompt = self._load_prompt("sql_validator.j2", {"sql_draft": sql_draft, "schema_info": schema_info})
        # validation_result = self._run_agent_task(
        #     "SQL Validator",
        #     prompt,
        #     settings.OPENAI_MODEL_ANALYSIS # Cheaper model maybe ok for validation
        # )
        # if "VALID" not in validation_result.upper():
        #     logger.warning(f"LLM Validator found potential issues: {validation_result}")
        #     # Decide if this is a hard fail or just a warning
        #     # return False, f"LLM Validation Failed: {validation_result}"

        # 2. Trino execution check (Syntax check via LIMIT 0 or EXPLAIN)
        logger.info("Performing Trino-based SQL validation...")
        validation_error = self.trino.execute_validation(sql_draft)
        if validation_error:
            logger.warning(f"Trino validation failed: {validation_error}")
            # Format error nicely for the correction agent
            error_msg = f"Trino Validation Error: {type(validation_error).__name__} - {str(validation_error)}"
            return False, error_msg
        else:
            logger.info("Trino validation successful.")
            return True, None


    def _correct_sql(self, nlq: str, schema_info: str, sql_draft: str, error_message: str) -> str:
        """Uses SQL Correction Agent."""
        prompt = self._load_prompt("sql_corrector.j2", {
            "nlq": nlq,
            "schema_info": schema_info,
            "sql_draft": sql_draft,
            "error_message": error_message
        })
        corrected_sql = self._run_agent_task(
            "SQL Corrector",
            prompt,
            settings.OPENAI_MODEL_CORRECTION # Powerful model needed
        )
        if not corrected_sql or not corrected_sql.upper().startswith("SELECT"):
             logger.error(f"SQL Corrector produced invalid output: {corrected_sql}")
             raise OrchestrationError("SQL Correction failed to produce valid SQL structure.")
        return corrected_sql

    def _execute_sql(self, final_sql: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Uses SQL Execution Agent logic (calls TrinoExecutor).
        Returns (results, error_message)
        """
        logger.info(f"Executing final SQL: {final_sql[:100]}...")
        results, error = self.trino.execute_query(final_sql)
        if error:
            logger.error(f"Final SQL execution failed: {error}")
            error_msg = f"Trino Execution Error: {type(error).__name__} - {str(error)}"
            return [], error_msg # Return empty list and error message
        else:
            logger.info(f"Final SQL execution successful, {len(results)} rows returned.")
            return results, None

    def _explain_sql(self, final_sql: str) -> str:
        """Uses SQL Explanation Agent."""
        prompt = self._load_prompt("sql_explainer.j2", {"final_sql": final_sql})
        explanation = self._run_agent_task(
            "SQL Explainer",
            prompt,
            settings.OPENAI_MODEL_EXPLANATION
        )
        return explanation

    def process_nlq(self, nlq: str) -> Dict[str, Any]:
        """
        Main orchestration flow based on the Mermaid diagram.
        Returns a dictionary containing results, SQL, explanation, status, etc.
        """
        logger.info(f"Starting orchestration for NLQ: '{nlq}'")
        output = {
            "status": "FAILED",
            "nlq": nlq,
            "analysis_hints": None,
            "schema_info": None,
            "sql_generated": None,
            "sql_final": None,
            "validation_error": None,
            "execution_error": None,
            "explanation": None,
            "results": None,
            "error_message": None,
        }

        try:
            # 1. Analyze Query (Optional but helpful)
            # output["analysis_hints"] = self._analyze_query(nlq)
            # logger.info(f"Analysis hints: {output['analysis_hints']}")

            # 2. Retrieve Schema
            output["schema_info"] = self._retrieve_schema() # Pass hints if analyzer used
            if not output["schema_info"]:
                 raise OrchestrationError("Failed to retrieve a valid schema.")

            # 3. Initial SQL Generation
            current_sql = self._generate_sql(nlq, output["schema_info"], output["analysis_hints"])
            output["sql_generated"] = current_sql
            logger.info(f"Initial SQL generated: {current_sql[:150]}...")

            # 4. Validation and Correction Loop
            is_valid = False
            for attempt in range(settings.AGENT_MAX_RETRIES + 1):
                logger.info(f"Validation attempt {attempt + 1}/{settings.AGENT_MAX_RETRIES + 1}")
                is_valid, validation_error = self._validate_sql(current_sql, output["schema_info"])
                output["validation_error"] = validation_error # Store last validation error

                if is_valid:
                    logger.info("SQL validation successful.")
                    output["sql_final"] = current_sql
                    break # Exit loop on success
                else:
                    logger.warning(f"SQL invalid: {validation_error}")
                    if attempt < settings.AGENT_MAX_RETRIES:
                        logger.info("Attempting SQL correction...")
                        current_sql = self._correct_sql(nlq, output["schema_info"], current_sql, validation_error)
                        logger.info(f"Corrected SQL (attempt {attempt+1}): {current_sql[:150]}...")
                        output["sql_generated"] = current_sql # Update with the latest attempt
                    else:
                        logger.error("Max correction retries reached. Failing orchestration.")
                        raise OrchestrationError(f"SQL could not be validated after {settings.AGENT_MAX_RETRIES + 1} attempts. Last error: {validation_error}")

            # 5. Execute Final SQL (if valid)
            if output["sql_final"]:
                results, execution_error = self._execute_sql(output["sql_final"])
                output["results"] = results
                output["execution_error"] = execution_error
                if execution_error:
                    logger.error(f"Execution failed for validated SQL: {execution_error}")
                    output["error_message"] = f"Execution Failed: {execution_error}"
                    # Don't set status to SUCCESS if execution fails
                else:
                    logger.info("SQL executed successfully.")
                    output["status"] = "SUCCESS"

                    # 6. Explain SQL (Optional)
                    try:
                        output["explanation"] = self._explain_sql(output["sql_final"])
                        logger.info("SQL explanation generated.")
                    except Exception as explain_err:
                        logger.warning(f"Failed to generate SQL explanation: {explain_err}")
                        output["explanation"] = "(Explanation generation failed)"

            else:
                 # Should be caught by loop exhaustion, but as safeguard:
                 output["error_message"] = f"SQL validation failed: {output['validation_error']}"


        except OrchestrationError as e:
            logger.error(f"Orchestration failed: {e}")
            output["error_message"] = str(e)
        except Exception as e:
            logger.exception(f"An unexpected error occurred during orchestration: {e}")
            output["error_message"] = f"Unexpected server error: {type(e).__name__}"

        logger.info(f"Orchestration finished with status: {output['status']}")
        return output 