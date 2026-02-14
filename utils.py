# utils.py
import re
from config import BAD_WORDS

def censor_text(text: str) -> str:
    if not text:
        return text
    censored_text = text
    for word in BAD_WORDS:
        # \b забезпечує пошук цілого слова
        pattern = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
        censored_text = pattern.sub(lambda m: "*" * len(m.group()), censored_text)
    return censored_text