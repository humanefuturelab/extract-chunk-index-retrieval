"""Utility helpers for workers"""
import re
import yaml
import os
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def parse_frontmatter(text):
    m = FRONTMATTER_RE.match(text)
    if not m:
        return None, text
    try:
        fm = yaml.safe_load(m.group(1))
    except Exception:
        fm = None
    body = text[m.end():]
    return fm, body


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)

