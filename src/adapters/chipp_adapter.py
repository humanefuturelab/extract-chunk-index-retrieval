"""Adapter for chipp.ai - lightweight HTTP wrapper.

Configure via environment:
  CHIPP_API_URL, CHIPP_API_KEY

The exact chipp.ai API may differ; this wrapper uses a generic /v1/generate endpoint. Adjust as needed to match chipp.ai API.
"""
import os
import requests

CHIPP_API_URL = os.environ.get("CHIPP_API_URL", "https://api.chipp.ai")
CHIPP_API_KEY = os.environ.get("CHIPP_API_KEY", "")


def call_model(prompt, max_tokens=1200, temperature=0.2, **kwargs):
    url = CHIPP_API_URL.rstrip("/") + "/v1/generate"
    headers = {"Authorization": f"Bearer {CHIPP_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=120)
    resp.raise_for_status()
    j = resp.json()
    # Expecting structure: { "text": "...", "usage": {...}, "model": "..." }
    # This may need to be adapted to the real chipp.ai response format.
    return {
        "text": j.get("text") or j.get("output") or "",
        "usage": j.get("usage", {}),
        "model": j.get("model", "chipp")
    }
