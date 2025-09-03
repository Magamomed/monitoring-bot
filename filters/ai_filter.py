import requests
from config import (
    AZURE_OPENAI_ENDPOINT,
    AZURE_DEPLOYMENT_NAME,
    AZURE_API_VERSION,
    HEADERS,
    AI_ENABLED,
)

SYSTEM_PROMPT = (
    "You are a strict content moderation AI for a group chat.\n"
    "Reply YES only if the message includes any of the following:\n"
    "1. Hate speech, threats, or explicit insults (especially involving family).\n"
    "2. Spam or scam content, such as:\n"
    "- Messages about fast income, like '7500₽ в день', 'доход без вложений', 'работа 18+', 'заработай легко', etc.\n"
    "- Messages asking to contact a user like '@karina_mladcha' for earnings or jobs.\n"
    "- Investment promises, crypto scams, or work-from-phone offers.\n"
    "- Anything that promises fast money or effortless work.\n"
    "Always be cautious of messages with numbers and currency (e.g. '5000₽', '1000 руб') and contact requests.\n"
    "Ignore harmless slang, memes, jokes, and emotional expressions.\n"
    "Reply ONLY with YES or NO."
)

def _build_url() -> str:
    return f"{AZURE_OPENAI_ENDPOINT}/openai/deployments/{AZURE_DEPLOYMENT_NAME}/chat/completions?api-version={AZURE_API_VERSION}"

async def is_bad_content(text: str) -> bool:
    if not AI_ENABLED[0]:
        return False
    try:
        data = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            "temperature": 0.3,
            "max_tokens": 1,
        }
        resp = requests.post(_build_url(), headers=HEADERS, json=data, timeout=10)
        resp.raise_for_status()
        answer = resp.json()["choices"][0]["message"]["content"].strip().lower()
        return answer.startswith("yes")
    except Exception:
        # в случае ошибки модерацию не блокируем
        return False
