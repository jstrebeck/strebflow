"""reviewer node — reviews final diff for quality (post-convergence only)."""
from __future__ import annotations
from typing import Any
from attractor.llm_client import LLMClient

REVIEWER_SYSTEM = """You are a senior code reviewer. The implementation has passed all scenarios. Review the final diff for:
- Code style and readability
- Potential bugs or edge cases
- Maintainability concerns
- Security issues

Produce a concise review report. This is informational — it does NOT block the pipeline."""

_MAX_DIFF_CHARS = 200_000


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    half = limit // 2
    return text[:half] + "\n\n[... truncated ...]\n\n" + text[-half:]


async def reviewer(state: dict[str, Any], llm: LLMClient, model: str) -> dict[str, Any]:
    latest_diff = state.get("latest_diff", "")
    user_content = f"""## Spec
{state['spec']}

## Scenarios
{state['scenarios']}

## Full Diff
{_truncate(latest_diff, _MAX_DIFF_CHARS)}"""
    response = await llm.complete(
        messages=[{"role": "user", "content": user_content}],
        system=REVIEWER_SYSTEM,
        model=model,
    )
    review = response["choices"][0]["message"]["content"]
    return {"review_report": review}
