import os
from config import STOPWORDS_PATH

def load_stopwords() -> list[str]:
    if not os.path.exists(STOPWORDS_PATH):
        return []
    with open(STOPWORDS_PATH, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def save_stopwords(words: list[str]):
    with open(STOPWORDS_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(sorted(set(words))))

# Глобальная коллекция для быстрых проверок
STOP_WORDS = load_stopwords()
