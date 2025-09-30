# filters/ai_filter.py
import asyncio
import aiohttp
import logging
import re
from typing import Any, Dict

from config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_DEPLOYMENT_NAME,
    AZURE_API_VERSION,
    HEADERS,
    AI_ENABLED,
)

log = logging.getLogger("moderation.ai")

SYSTEM_PROMPT = """You are a strict content moderation AI for a group chat.
Reply YES only if the message includes any of the following:
1. Hate speech, threats, or explicit insults (especially involving family).
2. Spam or scam content, such as:
   - Messages about fast income, like '7500₽ в день', 'доход без вложений', 'работа 18+', 'заработай легко', etc.
   - Messages asking to contact a user like '@karina_mladcha' for earnings or jobs.
   - Investment promises, crypto scams, or work-from-phone offers.
   - Messages offering payment for personal favors, errands, or purchases (e.g., "купить продукты", "занести домой") especially from unknown users, often mentioning money or currency (e.g., '3500₽', '5000 руб').
Always be cautious of messages with numbers and currency and contact requests.
Ignore harmless slang, memes, jokes, and emotional expressions.
Reply ONLY with YES or NO.
"""


# Параметры
_MAX_TOKENS = 3
_TIMEOUT_SECONDS = 8
_RETRY_COUNT = 2
_RETRY_BACKOFF = 1.0  # умножается экспоненциально

_yes_re = re.compile(r'^(yes|да)\b', flags=re.IGNORECASE)

def _build_url() -> str:
    base = AZURE_OPENAI_ENDPOINT.rstrip("/")
    return f"{base}/openai/deployments/{AZURE_DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_API_VERSION}"


async def is_bad_content(text: str) -> bool:
    """
    Асинхронный запрос к Azure OpenAI chat completions.
    Возвращает True если модель отвечает 'YES'/'да' в начале ответа.
    """
    # Простая и понятная проверка флага
    if not bool(AI_ENABLED):
        log.debug("AI moderation disabled: AI_ENABLED=%r", AI_ENABLED)
        return False

    url = _build_url()
    payload: Dict[str, Any] = {
        # "model": AZURE_DEPLOYMENT_NAME,   # 👈 добавляем сюда
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.0,
        "max_tokens": _MAX_TOKENS,
    }

    headers = HEADERS if isinstance(HEADERS, dict) else {}
    log.debug("AI request url=%s payload_preview=%.200s", url, str(payload)[:200])

    timeout = aiohttp.ClientTimeout(total=_TIMEOUT_SECONDS)

    # базовый retry для 429/5xx
    for attempt in range(1, _RETRY_COUNT + 2):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    text_body = await resp.text()
                    status = resp.status

                    log.debug("AI response status=%s attempt=%s", status, attempt)

                    if status == 429:
                        # rate limit — попробуем с backoff
                        log.warning("AI rate-limited (429), attempt=%s body=%.400s", attempt, text_body[:400])
                        if attempt <= _RETRY_COUNT:
                            await asyncio.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
                            continue
                        return False

                    if status >= 500:
                        log.warning("AI server error %s, attempt=%s", status, attempt)
                        if attempt <= _RETRY_COUNT:
                            await asyncio.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
                            continue
                        return False

                    if status >= 400:
                        log.error("AI request failed status=%s body=%.400s", status, text_body[:400])
                        return False

                    # parse JSON
                    try:
                        j = await resp.json()
                    except Exception:
                        log.exception("Failed to parse JSON from AI: %.400s", text_body[:400])
                        return False

                    # try to extract content robustly
                    choice = (j.get("choices") or [None])[0]
                    if not choice:
                        log.warning("No choices in AI response: %s", j)
                        return False

                    # support both shapes: choice.get('message', {}).get('content') or choice.get('text')
                    content = ""
                    if isinstance(choice, dict):
                        msg = choice.get("message") or {}
                        content = msg.get("content") or choice.get("text") or ""
                    else:
                        content = ""

                    ans = (content or "").strip()
                    log.debug("AI raw answer=%r", ans)

                    if _yes_re.match(ans):
                        log.info("AI moderation -> BAD (matched yes) for text: %.80s", text)
                        return True

                    # not flagged
                    return False

        except asyncio.TimeoutError:
            log.warning("AI request timeout (attempt=%s)", attempt)
            if attempt <= _RETRY_COUNT:
                await asyncio.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
                continue
            return False
        except aiohttp.ClientError as e:
            log.exception("AI client error: %s (attempt=%s)", e, attempt)
            if attempt <= _RETRY_COUNT:
                await asyncio.sleep(_RETRY_BACKOFF * (2 ** (attempt - 1)))
                continue
            return False
        except Exception as e:
            log.exception("Unexpected error in is_bad_content: %s", e)
            return False

    return False
