#!/usr/bin/env python3
"""Generator worker: reads extracted.jsonl and generates pages by calling model providers via adapters.

Usage examples:
  python src/generator_worker.py --extracted data/extracted.jsonl --prompt prompt_templates/generator_v1.yaml --out content/pages
  python src/generator_worker.py --source-id src-123 --extracted data/extracted.jsonl --prompt prompt_templates/generator_v1.yaml

Environment variables expected:
  CHIPP_API_URL, CHIPP_API_KEY, OPENAI_API_KEY
  PROVIDER_PRIORITY (comma separated, default: chipp,openai)

This is a light-weight, pluggable scaffold. It validates YAML frontmatter and enqueues simple job files for embedding and scoring.
"""
import os
import json
import argparse
import time
import uuid
from pathlib import Path
from sqlitedict import SqliteDict
from importlib import import_module
from src.utils import parse_frontmatter, ensure_dir
import yaml

# Provider adapters import paths
ADAPTERS = {
    "chipp": "src.adapters.chipp_adapter",
    "openai": "src.adapters.openai_adapter"
}

DEFAULT_PROVIDERS = os.environ.get("PROVIDER_PRIORITY", "chipp,openai").split(",")

JOBS_DIR = Path("data/jobs")
PAGES_DIR = Path("content/pages")
RAW_DIR = Path("content/raw-responses")
META_DB = Path("data/pages_meta.sqlite")

ensure_dir(JOBS_DIR)
ensure_dir(PAGES_DIR)
ensure_dir(RAW_DIR)


def load_prompt_template(path):
    with open(path, "r", encoding="utf8") as f:
        return yaml.safe_load(f)


def build_prompt(template, source_snippet, extra={}):
    # Simple templating: replace {{source_text}} and other keys if present
    instr = template.get("instruction", "")
    instr = instr.replace("{{source_text}}", source_snippet)
    for k, v in extra.items():
        instr = instr.replace("{{%s}}" % k, str(v))
    return instr


def call_providers(prompt, providers=DEFAULT_PROVIDERS, max_tokens=1200, temperature=0.2):
    last_exc = None
    for p in providers:
        p = p.strip()
        if p not in ADAPTERS:
            continue
        mod = import_module(ADAPTERS[p])
        try:
            res = mod.call_model(prompt=prompt, max_tokens=max_tokens, temperature=temperature)
            # Expect res dict with keys: text, usage, model
            if res and isinstance(res, dict) and res.get("text"):
                return p, res
        except Exception as exc:
            last_exc = exc
            print(f"Provider {p} failed: {exc}")
    raise RuntimeError(f"All providers failed. Last error: {last_exc}")


def validate_and_write(page_text, page_id):
    fm, body = parse_frontmatter(page_text)
    if not fm:
        raise ValueError("Missing or invalid frontmatter")
    required = ["id", "title", "sources", "score", "sub_scores"]
    for r in required:
        if r not in fm:
            raise ValueError(f"Missing required frontmatter field: {r}")
    # write md file
    out_path = PAGES_DIR / f"{page_id}.md"
    with open(out_path, "w", encoding="utf8") as f:
        f.write(page_text)
    # write metadata
    meta = dict(fm)
    meta["path_to_md"] = str(out_path)
    meta["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with SqliteDict(str(META_DB), autocommit=True) as db:
        db[page_id] = meta
    return out_path


def enqueue_job(job_type, payload):
    job_id = f"job-{job_type}-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    path = JOBS_DIR / f"{job_id}.json"
    with open(path, "w", encoding="utf8") as f:
        json.dump({"id": job_id, "type": job_type, "payload": payload, "created_at": time.time()}, f)
    return str(path)


def run_from_extracted(extracted_path, prompt_path, providers, max_tokens, temperature, limit=None):
    template = load_prompt_template(prompt_path)
    count = 0
    with open(extracted_path, "r", encoding="utf8") as inp:
        for line in inp:
            if limit and count >= limit:
                break
            rec = json.loads(line)
            source_id = rec.get("doc_id")
            # build a simple source snippet: first 1000 chars of concatenated pages
            pages = rec.get("pages", [])
            text = "\n\n".join([p.get("text","") for p in pages])
            snippet = text[:3000]
            prompt = build_prompt(template, snippet)
            provider, res = call_providers(prompt, providers=providers, max_tokens=max_tokens, temperature=temperature)
            page_text = res.get("text")
            # save raw response
            raw_path = RAW_DIR / f"{source_id}.json"
            with open(raw_path, "w", encoding="utf8") as f:
                json.dump({"provider": provider, "response": res}, f, indent=2)
            # validate
            try:
                # if template expects id, use generated one or create
                parsed_fm, _ = parse_frontmatter(page_text)
                if parsed_fm and parsed_fm.get("id"):
                    page_id = parsed_fm.get("id")
                else:
                    page_id = f"page-{source_id}"
                    # attach frontmatter id if missing
                    page_text = f"---\nid: {page_id}\n---\n\n" + page_text
                out_path = validate_and_write(page_text, page_id)
            except Exception as exc:
                print(f"Validation failed for source {source_id}: {exc}")
                # enqueue human-review job
                enqueue_job("human-review", {"source_id": source_id, "error": str(exc), "raw_path": str(raw_path)})
                continue
            # enqueue embed and score jobs
            enqueue_job("embed-page", {"page_id": page_id})
            enqueue_job("score-page", {"page_id": page_id})
            print(f"Generated page {page_id} from source {source_id} (provider={provider})")
            count += 1


def run_for_source(source_id, extracted_path, prompt_path, providers, max_tokens, temperature):
    # scan extracted file for record
    found = False
    with open(extracted_path, "r", encoding="utf8") as inp:
        for line in inp:
            rec = json.loads(line)
            if rec.get("doc_id") == source_id:
                found = True
                pages = rec.get("pages", [])
                text = "\n\n".join([p.get("text","") for p in pages])
                snippet = text[:3000]
                template = load_prompt_template(prompt_path)
                prompt = build_prompt(template, snippet)
                provider, res = call_providers(prompt, providers=providers, max_tokens=max_tokens, temperature=temperature)
                page_text = res.get("text")
                raw_path = RAW_DIR / f"{source_id}.json"
                with open(raw_path, "w", encoding="utf8") as f:
                    json.dump({"provider": provider, "response": res}, f, indent=2)
                try:
                    parsed_fm, _ = parse_frontmatter(page_text)
                    if parsed_fm and parsed_fm.get("id"):
                        page_id = parsed_fm.get("id")
                    else:
                        page_id = f"page-{source_id}"
                        page_text = f"---\nid: {page_id}\n---\n\n" + page_text
                    validate_and_write(page_text, page_id)
                except Exception as exc:
                    print(f"Validation failed for source {source_id}: {exc}")
                    enqueue_job("human-review", {"source_id": source_id, "error": str(exc), "raw_path": str(raw_path)})
                    return
                enqueue_job("embed-page", {"page_id": page_id})
                enqueue_job("score-page", {"page_id": page_id})
                print(f"Generated page {page_id} from source {source_id} (provider={provider})")
                return
    if not found:
        print(f"Source {source_id} not found in {extracted_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--extracted", default="data/extracted.jsonl", help="path to extracted jsonl")
    parser.add_argument("--prompt", default="prompt_templates/generator_v1.yaml")
    parser.add_argument("--providers", default=None, help="comma-separated provider list (overrides env)")
    parser.add_argument("--max-tokens", type=int, default=1200)
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--source-id", default=None)
    args = parser.parse_args()
    providers = args.providers.split(",") if args.providers else DEFAULT_PROVIDERS
    if args.source_id:
        run_for_source(args.source_id, args.extracted, args.prompt, providers, args.max_tokens, args.temperature)
    else:
        run_from_extracted(args.extracted, args.prompt, providers, args.max_tokens, args.temperature, limit=args.limit)
