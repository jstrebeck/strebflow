"""Multi-provider LLM client for OpenAI-compatible APIs."""
from __future__ import annotations
import asyncio
import json
from typing import Any
import httpx
from attractor.config import ProviderConfig

def parse_model_string(model: str) -> tuple[str, str]:
    """Parse 'provider/model' into (provider_name, model_id)."""
    parts = model.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid model string '{model}': expected 'provider/model'")
    return parts[0], parts[1]

class LLMClient:
    """Async LLM client that routes to multiple OpenAI-compatible providers."""

    def __init__(self, providers: dict[str, ProviderConfig]) -> None:
        self._providers = providers
        self._clients: dict[str, httpx.AsyncClient] = {}
        for name, config in providers.items():
            self._clients[name] = httpx.AsyncClient(
                base_url=config.base_url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json",
                },
                timeout=httpx.Timeout(120.0, connect=10.0),
            )

    def _get_client(self, provider: str) -> httpx.AsyncClient:
        client = self._clients.get(provider)
        if client is None:
            raise ValueError(
                f"Provider '{provider}' not configured. "
                f"Available: {list(self._clients.keys())}"
            )
        return client

    async def complete(self, messages: list[dict], system: str = "", model: str | None = None, tools: list | None = None) -> dict:
        if model is None:
            raise ValueError("model is required")
        provider, model_id = parse_model_string(model)
        client = self._get_client(provider)
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        body: dict[str, Any] = {"model": model_id, "messages": full_messages}
        if tools:
            body["tools"] = tools
        return await self._request_with_retry(client, body)

    async def complete_structured(self, messages: list[dict], system: str, response_schema: dict, model: str | None = None) -> dict:
        if model is None:
            raise ValueError("model is required")
        provider, model_id = parse_model_string(model)
        client = self._get_client(provider)
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)
        body: dict[str, Any] = {
            "model": model_id,
            "messages": full_messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "response", "schema": response_schema},
            },
        }
        return await self._request_with_retry(client, body)

    async def _request_with_retry(self, client: httpx.AsyncClient, body: dict, max_retries: int = 3) -> dict:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await client.post("/chat/completions", json=body)
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPStatusError, httpx.TransportError) as e:
                last_error = e
                if attempt < max_retries - 1:
                    delay = 2 ** attempt
                    await asyncio.sleep(delay)
        raise last_error

    async def close(self) -> None:
        for client in self._clients.values():
            await client.aclose()
