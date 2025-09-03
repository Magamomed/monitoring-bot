import os
from config import RULES_PATH

def load_rules() -> str:
    if not os.path.exists(RULES_PATH):
        return "Правила чата ещё не установлены."
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return f.read()

def save_rules(text: str):
    with open(RULES_PATH, "w", encoding="utf-8") as f:
        f.write(text.strip())
