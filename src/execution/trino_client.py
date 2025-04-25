import time
from typing import List, Dict, Any, Optional, Tuple
from trino.dbapi import connect
from trino.exceptions import TrinoError
from requests.exceptions import ConnectionError as RequestsConnectionError # Alias to avoid name clash

from src.config import settings
from src.logging.logger import get_logger

logger = get_logger(__name__)

class TrinoExecutor:
    """Handles connection and execution of queries against Trino."""

    def __init__(self):
        # Connection pooling is handled by the underlying trino client's session
        # but we might want to manage the connection object itself
        self.conn = None
        self._connect() # Attempt initial connection

    def _connect(self):
        """Establishes connection to Trino."""
        if self.conn:
            try:
                # Simple check if connection is alive (may not be foolproof)
                self.conn.cursor().execute("SELECT 1")
                logger.debug("Trino connection is alive.")
                return # Connection likely still valid
            except (TrinoError, AttributeError, RequestsConnectionError) as e:
                logger.warning(f"Trino connection check failed ({type(e).__name__}), reconnecting. Error: {e}")
                self.conn = None # Force reconnect

        logger.info(f"Connecting to Trino at {settings.TRINO_HTTP_SCHEME}://{settings.TRINO_HOST}:{settings.TRINO_PORT}")
        try:
            self.conn = connect(
                host=settings.TRINO_HOST,
                port=settings.TRINO_PORT,
                user=settings.TRINO_USER,
                catalog=settings.TRINO_CATALOG,
                schema=settings.TRINO_SCHEMA,
                http_scheme=settings.TRINO_HTTP_SCHEME,
                password=settings.TRINO_PASSWORD,
                http_headers={'Trino-User': settings.TRINO_USER}, # Recommended header
                request_timeout=settings.TRINO_CONN_TIMEOUT,
                # Add source or other relevant session properties if needed
                # session_properties={"query_max_run_time": "10m"}
            )
            logger.info("Trino connection established successfully.")
        except (TrinoError, RequestsConnectionError) as e:
            logger.error(f"Failed to connect to Trino: {e}")
            self.conn = None # Ensure conn is None if connection failed
            raise ConnectionError(f"Could not establish connection to Trino: {e}") from e


    def _execute_with_retry(self, sql: str, is_validation: bool = False) -> Tuple[Optional[List[Tuple]], Optional[List[str]], Optional[Exception]]:
        """Internal execution logic with retry for transient errors."""
        last_exception = None
        for attempt in range(settings.TRINO_MAX_RETRIES + 1):
            try:
                if not self.conn:
                    self._connect() # Attempt reconnect if connection is missing
                if not self.conn:
                    raise ConnectionError("Trino connection not available.") # Bail if reconnect failed

                cursor = self.conn.cursor()
                logger.debug(f"Executing SQL (Attempt {attempt+1}/{settings.TRINO_MAX_RETRIES+1}):\n{sql[:500]}{'...' if len(sql) > 500 else ''}")
                cursor.execute(sql)

                if is_validation:
                    # For validation (like LIMIT 0 or EXPLAIN), we don't fetch rows, just check for errors
                    logger.info(f"SQL validation successful for: {sql[:100]}...")
                    return None, None, None # Success (no rows, no columns, no error)
                else:
                    rows = cursor.fetchall()
                    columns = [desc[0] for desc in cursor.description] if cursor.description else []
                    logger.info(f"SQL execution successful. Fetched {len(rows)} rows.")
                    return rows, columns, None # Success

            except (TrinoError, RequestsConnectionError, ConnectionError) as e:
                logger.warning(f"Trino execution error (Attempt {attempt+1}): {type(e).__name__} - {e}")
                last_exception = e
                # Check if error is likely transient (e.g., connection error, timeout)
                # More specific error checking could be added here based on TrinoError subtypes
                is_transient = isinstance(e, (RequestsConnectionError, ConnectionError)) # Add specific Trino transient codes if known

                if is_transient and attempt < settings.TRINO_MAX_RETRIES:
                    wait_time = settings.TRINO_RETRY_DELAY * (2 ** attempt) # Exponential backoff
                    logger.warning(f"Retrying in {wait_time} seconds...")
                    time.sleep(wait_time)
                    # Ensure connection is re-established before next retry
                    if isinstance(e, (RequestsConnectionError, ConnectionError)):
                         self.conn = None # Force reconnect on connection errors
                else:
                    logger.error(f"Non-retryable error or max retries reached for SQL: {sql[:100]}...")
                    return None, None, e # Return the final error

        # Should only be reached if loop finishes due to retries exhausting
        logger.error(f"Failed to execute SQL after {settings.TRINO_MAX_RETRIES + 1} attempts.")
        return None, None, last_exception


    def execute_query(self, sql: str) -> Tuple[List[Dict[str, Any]], Optional[Exception]]:
        """Executes a SQL query and returns results as list of dicts, or an exception."""
        rows, columns, error = self._execute_with_retry(sql, is_validation=False)

        if error:
            return [], error
        if rows is None or columns is None:
             # Should not happen if error is None, but safety check
             return [], ValueError("Execution succeeded but no rows/columns returned unexpectedly.")

        results = [dict(zip(columns, row)) for row in rows]
        return results, None

    def execute_validation(self, sql: str) -> Optional[Exception]:
        """Executes a SQL statement purely for validation (e.g., syntax check). Returns exception if failed."""
        # Example validation: Append LIMIT 0. Alternatively use EXPLAIN.
        # Using EXPLAIN might be better but requires parsing its output.
        # Using LIMIT 0 is simpler but might still fail later on semantic issues EXPLAIN could catch.
        validation_sql = f"SELECT * FROM ({sql}) AS _subquery LIMIT 0"
        # Or: validation_sql = f"EXPLAIN {sql}" # If using EXPLAIN

        logger.info(f"Attempting validation with query: {validation_sql[:100]}...")
        _, _, error = self._execute_with_retry(validation_sql, is_validation=True)
        return error

    def get_schema_info(self, target_catalog: Optional[str] = None, target_schema: Optional[str] = None) -> Tuple[Optional[str], Optional[Exception]]:
        """Fetches schema information (tables and columns) as a formatted string."""
        # TODO: Implement more robust schema fetching, possibly filtering,
        # and formatting it in a way the LLM understands well (e.g., CREATE TABLE statements or simplified JSON).
        # This is a very basic example.

        catalog = target_catalog or settings.TRINO_CATALOG
        schema = target_schema or settings.TRINO_SCHEMA

        if not catalog or not schema:
            return None, ValueError("Catalog and schema must be specified either in config or request to fetch schema.")

        # Use ANSI standard information_schema
        sql = f"""
        SELECT table_name, column_name, data_type
        FROM {catalog}.information_schema.columns
        WHERE table_schema = '{schema}'
        ORDER BY table_name, ordinal_position;
        """
        rows, columns, error = self._execute_with_retry(sql, is_validation=False)

        if error:
            logger.error(f"Failed to fetch schema for {catalog}.{schema}: {error}")
            return None, error
        if not rows:
            logger.warning(f"No tables found in schema: {catalog}.{schema}")
            return "", None # Return empty string if schema exists but is empty

        schema_str = ""
        current_table = None
        for row_tuple in rows:
            # Assuming order is table_name, column_name, data_type
            row = dict(zip(columns, row_tuple))
            if row['table_name'] != current_table:
                if current_table is not None:
                    schema_str += ");\n\n"
                current_table = row['table_name']
                schema_str += f"TABLE {schema}.{current_table} (\n"
            schema_str += f"  {row['column_name']} {row['data_type']},\n"

        if current_table is not None:
             # Remove trailing comma and newline, add closing parenthesis
             schema_str = schema_str.rstrip(',\n') + "\n);"

        logger.info(f"Successfully fetched schema string for {catalog}.{schema}")
        return schema_str, None


# Global instance (or use dependency injection)
trino_executor = TrinoExecutor()

def get_trino_executor() -> TrinoExecutor:
    """Dependency function to get the Trino executor."""
    # Could add logic here to check/refresh connection if needed
    return trino_executor 