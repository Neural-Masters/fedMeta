"""API tool executor.

Converts registered API endpoints into Agno-compatible tool functions,
handles JSON Schema validation, HTTP calls, and result formatting.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

try:
    import httpx
    from jsonschema import validate, ValidationError as JSONSchemaValidationError
    _HAS_DEPS = True
except ImportError:
    _HAS_DEPS = False

from fedMeta.tools.api_tool_registry import APIEndpoint

logger = logging.getLogger(__name__)


@dataclass
class ToolExecutionResult:
    """Result of executing an API tool.

    Attributes:
        success: Whether the execution succeeded.
        data: The response data (parsed JSON or raw text).
        status_code: HTTP status code.
        error: Error message if execution failed.
    """

    success: bool
    data: Any = None
    status_code: Optional[int] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert result to a dictionary."""
        return {
            "success": self.success,
            "data": self.data,
            "status_code": self.status_code,
            "error": self.error,
        }


class APIToolExecutor:
    """Executes API endpoint tools with validation and error handling.

    Each registered API endpoint is wrapped into a callable that Agno
    agents can use as a tool.  Input parameters are validated against
    the endpoint's input_schema before the HTTP call is made.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    def execute(
        self,
        endpoint: APIEndpoint,
        params: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute an API endpoint with validated parameters.

        Args:
            endpoint: The APIEndpoint to execute.
            params: Input parameters for the call.

        Returns:
            ToolExecutionResult with the outcome.
        """
        params = params or {}

        # Validate input against schema
        if endpoint.input_schema:
            try:
                validate(instance=params, schema=endpoint.input_schema)
            except JSONSchemaValidationError as e:
                logger.warning(
                    "Input validation failed for tool %s: %s", endpoint.name, e.message
                )
                return ToolExecutionResult(
                    success=False,
                    error=f"Input validation failed: {e.message}",
                )

        # Make HTTP request
        try:
            response = self._make_request(endpoint, params)
            response.raise_for_status()

            # Try to parse as JSON, fallback to text
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError):
                data = response.text

            logger.info(
                "Tool %s executed successfully (status=%d)",
                endpoint.name,
                response.status_code,
            )
            return ToolExecutionResult(
                success=True,
                data=data,
                status_code=response.status_code,
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "Tool %s returned HTTP error: %s", endpoint.name, e.response.status_code
            )
            return ToolExecutionResult(
                success=False,
                status_code=e.response.status_code,
                error=f"HTTP {e.response.status_code}: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            logger.error("Tool %s request failed: %s", endpoint.name, str(e))
            return ToolExecutionResult(
                success=False,
                error=f"Request failed: {str(e)}",
            )
        except Exception as e:
            logger.exception("Tool %s unexpected error", endpoint.name)
            return ToolExecutionResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    def create_tool_function(
        self,
        endpoint: APIEndpoint,
    ) -> Any:
        """Create an Agno Function backed by a real Python endpoint callable.

        The endpoint's JSON Schema is supplied directly to Agno, while the
        Python entrypoint performs schema validation and the HTTP request.

        Args:
            endpoint: The APIEndpoint to wrap.

        Returns:
            An Agno ``Function`` exposing the endpoint schema and Python entrypoint.
        """
        from agno.tools.function import Function

        agno_name = re.sub(r"[^A-Za-z0-9_-]", "_", endpoint.name).strip("_")[:64]
        if not agno_name:
            agno_name = "api_tool"
        if agno_name[0].isdigit():
            agno_name = f"tool_{agno_name}"

        def tool_function(**kwargs: Any) -> str:
            """Execute the registered API endpoint using its JSON input schema.

            Args:
                **kwargs: Named arguments defined by the endpoint's JSON Schema.

            Returns:
                JSON string of the execution result.
            """
            result = self.execute(endpoint, kwargs)
            return json.dumps(result.to_dict(), default=str, indent=2)

        # Set function metadata for Agno discovery
        tool_function.__name__ = agno_name
        tool_function.__doc__ = endpoint.description or (
            f"Call the {endpoint.method.upper()} API endpoint {endpoint.name}. "
            "Arguments are the fields in this tool's input schema."
        )

        # `**kwargs` is useful for a dynamic Python wrapper, but its inferred
        # schema is empty. Give Agno the endpoint's explicit schema so the LLM
        # can see required inputs such as `query` and produce valid tool calls.
        schema = dict(endpoint.input_schema or {})
        schema.pop("$schema", None)
        schema.pop("$id", None)
        schema.pop("title", None)
        schema.setdefault("type", "object")
        if not isinstance(schema.get("properties"), dict):
            schema["properties"] = {}
        schema.setdefault("additionalProperties", False)
        required = schema.get("required") or []
        schema["required"] = [
            key for key in required
            if key in schema["properties"]
        ]

        return Function(
            name=agno_name,
            description=(endpoint.description or f"Call {endpoint.name}")
            + f" HTTP {endpoint.method.upper()} endpoint.",
            parameters=schema,
            entrypoint=tool_function,
            skip_entrypoint_processing=True,
        )

    def create_tool_functions(
        self,
        endpoints: List[APIEndpoint],
    ) -> List[Any]:
        """Create tool functions for multiple endpoints.

        Args:
            endpoints: List of APIEndpoint objects.

        Returns:
            List of callable tool functions.
        """
        return [self.create_tool_function(ep) for ep in endpoints]

    def _make_request(
        self,
        endpoint: APIEndpoint,
        params: Dict[str, Any],
    ) -> httpx.Response:
        """Make the actual HTTP request with retry logic."""
        method = endpoint.method.upper()
        headers = self._resolve_headers(endpoint.headers)

        last_error: Optional[Exception] = None

        for attempt in range(self.max_retries):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    if method == "GET":
                        response = client.get(
                            endpoint.url,
                            params=params,
                            headers=headers,
                        )
                    elif method == "POST":
                        response = client.post(
                            endpoint.url,
                            json=params,
                            headers=headers,
                        )
                    elif method == "PUT":
                        response = client.put(
                            endpoint.url,
                            json=params,
                            headers=headers,
                        )
                    elif method == "PATCH":
                        response = client.patch(
                            endpoint.url,
                            json=params,
                            headers=headers,
                        )
                    elif method == "DELETE":
                        response = client.delete(
                            endpoint.url,
                            params=params,
                            headers=headers,
                        )
                    else:
                        raise ValueError(f"Unsupported HTTP method: {method}")

                    return response

            except httpx.RequestError as e:
                last_error = e
                logger.warning(
                    "Attempt %d/%d for tool %s failed: %s",
                    attempt + 1,
                    self.max_retries,
                    endpoint.name,
                    str(e),
                )

        # All retries exhausted
        assert last_error is not None
        raise last_error

    @staticmethod
    def _resolve_headers(headers: Dict[str, str]) -> Dict[str, str]:
        """Expand `${ENV_VAR}` placeholders without storing API secrets in DB."""
        resolved: Dict[str, str] = {}
        placeholder = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
        for header_name, header_value in headers.items():
            def replace(match: re.Match[str]) -> str:
                variable = match.group(1)
                value = os.getenv(variable)
                if not value:
                    raise ValueError(f"Required tool credential environment variable {variable} is not set")
                return value

            resolved[header_name] = placeholder.sub(replace, str(header_value))
        return resolved
