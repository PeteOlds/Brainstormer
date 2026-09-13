import os
import httpx
from typing import Any


class OllamaError(Exception):
    pass


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

        response = await self._client.post(f"{self.base_url}/api/generate", json=payload)
        response.raise_for_status()
        return response.json()

    async def close(self):
        await self._client.aclose()

    # Sync wrapper for Celery tasks
    def generate_sync(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        format: str = "json",
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> dict[str, Any]:
        import asyncio
        return asyncio.run(self.generate(model, prompt, system, format, False, options, keep_alive))
