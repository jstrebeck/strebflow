import pytest
import httpx
import respx
import json
from attractor.llm_client import LLMClient, parse_model_string
from attractor.config import ProviderConfig

def test_parse_model_string():
    provider, model = parse_model_string("openrouter/anthropic/claude-sonnet-4-5")
    assert provider == "openrouter"
    assert model == "anthropic/claude-sonnet-4-5"

def test_parse_model_string_single_segment():
    provider, model = parse_model_string("vastai/llama-3.1-70b")
    assert provider == "vastai"
    assert model == "llama-3.1-70b"

@pytest.mark.asyncio
@respx.mock
async def test_complete_routes_to_correct_provider():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}],
        })
    )
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
    })
    result = await client.complete(
        messages=[{"role": "user", "content": "hi"}],
        model="openrouter/anthropic/claude-sonnet-4-5",
    )
    assert route.called
    assert result["choices"][0]["message"]["content"] == "hello"
    await client.close()

@pytest.mark.asyncio
@respx.mock
async def test_complete_structured():
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": '{"plan": "do stuff", "test_command": "pytest"}'}}],
        })
    )
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://openrouter.ai/api/v1", api_key="test-key"),
    })
    result = await client.complete_structured(
        messages=[{"role": "user", "content": "plan this"}],
        system="You are a planner",
        response_schema={"type": "object", "properties": {"plan": {"type": "string"}}},
        model="openrouter/anthropic/claude-sonnet-4-5",
    )
    assert route.called
    request_body = json.loads(route.calls[0].request.content)
    assert "response_format" in request_body
    await client.close()

@pytest.mark.asyncio
async def test_complete_unknown_provider():
    client = LLMClient(providers={
        "openrouter": ProviderConfig(base_url="https://x.com/v1", api_key="k"),
    })
    with pytest.raises(ValueError, match="unknown_provider"):
        await client.complete(
            messages=[{"role": "user", "content": "hi"}],
            model="unknown_provider/some-model",
        )
    await client.close()
