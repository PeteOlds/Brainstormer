import os
import httpx
from typing import Any


class OllamaError(Exception):
    """Ollama API error with response body for diagnosis."""
    def __init__(self, message: str, status_code: int | None = None, response_body: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


class OllamaClient:
    """Client for Ollama API."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def list_models(self) -> list[dict[str, Any]]:
        """List installed models from Ollama."""
        response = await self._client.get(f"{self.base_url}/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])

    def list_models_sync(self) -> list[dict[str, Any]]:
        """List installed models from Ollama (synchronous)."""
        import httpx
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(f"{self.base_url}/api/tags")
            response.raise_for_status()
            data = response.json()
            return data.get("models", [])

    def is_model_available(self, model: str) -> bool:
        """Check if a model is installed in this Ollama instance."""
        models = self.list_models_sync()
        return any(m.get("name") == model for m in models)

    @staticmethod
    def _build_payload(model, prompt, system=None, format="json",
                       stream=False, options=None, keep_alive=None) -> dict[str, Any]:
        payload = {
            "model": model,
            "prompt": prompt,
            "format": format,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options
        if keep_alive:
            payload["keep_alive"] = keep_alive
        return payload

    async def embeddings(
        self, model: str, prompt: str,
    ) -> dict[str, Any]:
        """Embedding lookup via the dedicated embeddings endpoint.

        NOTE: embedding models do NOT support /api/generate (400
        'does not support generate') — always use this method.
        """
        try:
            response = await self._client.post(
                f"{self.base_url}/api/embeddings",
                json={"model": model, "prompt": prompt})
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text if e.response else None
            raise OllamaError(
                f"Ollama API error {e.response.status_code}: {e.response.reason_phrase}",
                status_code=e.response.status_code,
                response_body=body
            ) from e

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str = "json",
        stream: bool = False,
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        """Generate completion from Ollama."""
        payload = self._build_payload(model, prompt, system, format, stream, options, keep_alive)

        try:
            response = await self._client.post(f"{self.base_url}/api/generate", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text if e.response else None
            raise OllamaError(
                f"Ollama API error {e.response.status_code}: {e.response.reason_phrase}",
                status_code=e.response.status_code,
                response_body=body
            ) from e

    async def close(self):
        await self._client.aclose()

    # Sync generate for Celery tasks. Uses a plain sync httpx.Client per
    # call on purpose: sharing one AsyncClient across asyncio.run() calls
    # reuses a pool bound to a closed loop ("Event loop is closed").
    def generate_sync(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str = "json",
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        payload = self._build_payload(model, prompt, system, format, False, options, keep_alive)
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            body = e.response.text if e.response else None
            raise OllamaError(
                f"Ollama API error {e.response.status_code}: {e.response.reason_phrase}",
                status_code=e.response.status_code,
                response_body=body
            ) from e