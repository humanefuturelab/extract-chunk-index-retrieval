"""Adapter for OpenAI via REST calls (chat completions style).

Set OPENAI_API_KEY in the environment.
"""
import os
import requests
import json

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


def call_model(prompt, max_tokens=1200, temperature=0.2, model="gpt-4o-mini", **kwargs):
    headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a content generation assistant. Output MUST be YAML frontmatter followed by Markdown body."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    resp = requests.post(OPENAI_API_URL, headers=headers, data=json.dumps(payload), timeout=120)
    resp.raise_for_status()
    j = resp.json()
    # extract text from choices
    text = ""
    try:
        text = j["choices"][0]["message"]["content"]
    except Exception:
        text = j.get("choices", [{}])[0].get("text", "")
    usage = j.get("usage", {})
    return {"text": text, "usage": usage, "model": model}
