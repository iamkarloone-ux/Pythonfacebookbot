import json
import os

base_dir = os.path.dirname(__file__)
locales = {}

# Load locales dynamically
for lang in ["en", "tl"]:
    file_path = os.path.join(base_dir, "locales", f"{lang}.json")
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            locales[lang] = json.load(f)
    else:
        print(f"⚠️ Warning: Locale file not found at {file_path}")

def get_text(key: str, lang_code: str = "en") -> str:
    lang_dict = locales.get(lang_code) or locales.get("en", {})
    return lang_dict.get(key, locales.get("en", {}).get(key, key))
