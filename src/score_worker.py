#!/usr/bin/env python3
"""Score worker: read pages metadata, call scoring prompt to providers, write normalized score back to metadata store.

Usage:
  python src/score_worker.py --prompt prompt_templates/scorer_v1.yaml --db data/pages_meta.sqlite --limit 100

This worker expects pages to be stored in content/pages/<page_id>.md and metadata in data/pages_meta.sqlite (sqlitedict).
"""
import os
import json
import argparse
from sqlitedict import SqliteDict
from importlib import import_module
from src.utils import parse_frontmatter
import yaml

ADAPTERS = {
    "chipp": "src.adapters.chipp_adapter",
    "openai": "src.adapters.openai_adapter"
}
DEFAULT_PROVIDERS = os.environ.get("PROVIDER_PRIORITY", "chipp,openai").split(",")

META_DB = "data/pages_meta.sqlite"


def load_prompt_template(path):
    with open(path, "r", encoding="utf8") as f:
        return yaml.safe_load(f)


def call_providers(prompt, providers=DEFAULT_PROVIDERS, max_tokens=400, temperature=0.0):
    last_exc = None
    for p in providers:
        p = p.strip()
        if p not in ADAPTERS:
            continue
        mod = import_module(ADAPTERS[p])
        try:
            res = mod.call_model(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
            if res and res.get("text"):
                return p, res
        except Exception as exc:
            last_exc = exc
            print(f"Provider {p} failed: {exc}")
    raise RuntimeError(f"All providers failed. Last error: {last_exc}")


def compute_normalized(sub_scores, weights=None):
    # sub_scores: dict of subscore name -> value (0-100)
    if weights is None:
        weights = {"relevance":30, "factuality":25, "structure":20, "readability":15, "originality":10}
    total = 0
    for k, w in weights.items():
        val = sub_scores.get(k, 0)
        total += (w * val)
    norm = round(total / 100)
    return norm


def run(db_path, prompt_path, providers, limit=None):
    template = load_prompt_template(prompt_path)
    with SqliteDict(db_path, autocommit=True) as db:
        keys = list(db.keys())
        count = 0
        for k in keys:
            if k == "__meta__":
                continue
            meta = db[k]
            # skip if already scored
            if meta.get("score") is not None:
                continue
            page_path = meta.get("path_to_md")
            if not page_path or not os.path.exists(page_path):
                print(f"Missing page file for {k}")
                continue
            with open(page_path, "r", encoding="utf8") as f:
                txt = f.read()
            fm, body = parse_frontmatter(txt)
            # build scoring prompt: include page (frontmatter + body) and ask for numeric sub_scores JSON
            prompt = template.get("instruction", "").replace("{{page_text}}", txt)
            provider, res = call_providers(prompt, providers=providers)
            resp_text = res.get("text")
            # Expect JSON in response; try to parse JSON object with sub_scores and score
            sub_scores = {}
            score = None
            try:
                # naive extraction: find first JSON object in resp_text
                import re
                m = re.search(r"\{[\s\S]*\}", resp_text)
                if m:
                    j = json.loads(m.group(0))
                    sub_scores = j.get("sub_scores", {})
                    score = j.get("score")
            except Exception as exc:
                print(f"Failed to parse scorer response for {k}: {exc}")
            if not sub_scores:
                print(f"No sub_scores from scorer for {k}; skipping")
                continue
            if score is None:
                score = compute_normalized(sub_scores)
            meta["sub_scores"] = sub_scores
            meta["score"] = score
            db[k] = meta
            print(f"Scored page {k} -> {score}")
            count += 1
            if limit and count >= limit:
                break

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=META_DB)
    parser.add_argument("--prompt", default="prompt_templates/scorer_v1.yaml")
    parser.add_argument("--providers", default=None)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    providers = args.providers.split(",") if args.providers else DEFAULT_PROVIDERS
    run(args.db, args.prompt, providers, limit=args.limit)
