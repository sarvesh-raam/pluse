import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("pulse.ai_summary")

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


async def summarize_failure(handler: str, error_message: str, log_lines: list[str]) -> str | None:
    """§10 bonus: on a job's final failure (attempts exhausted, moved to
    DLQ), ask Groq for a short root-cause summary an on-call engineer can
    read at a glance. Returns None (never raises) if no API key is
    configured or the request fails — this is a nice-to-have annotation,
    not something that should ever block the failure pipeline itself."""
    settings = get_settings()
    if not settings.groq_api_key:
        return None

    recent_logs = "\n".join(log_lines[-10:]) if log_lines else "(no log lines recorded)"
    prompt = (
        f"A background job handler '{handler}' failed permanently after exhausting all retry "
        f"attempts.\n\nFinal error: {error_message}\n\nRecent log lines:\n{recent_logs}\n\n"
        "In 1-2 concise sentences, state the likely root cause and a suggested fix for an "
        "on-call engineer. No preamble."
    )

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                GROQ_URL,
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": settings.groq_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 200,
                },
            )
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception:
        logger.exception("Groq AI summary request failed")
        return None
