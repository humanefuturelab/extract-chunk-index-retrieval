#!/usr/bin/env python3
"""
Extract text from PDFs (per-page) and read MD files.
Outputs a jsonl file with records:
{ doc_id, path, pages: [{page_num, text}], metadata }
"""
import json, argparse
import pdfplumber
from pathlib import Path
from tqdm import tqdm

def extract_pdf(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page_num": i, "text": text})
    return pages

def extract_md(path):
    with open(path, "r", encoding="utf8") as f:
        text = f.read()
    # treat entire file as one "page"
    return [{"page_num": 1, "text": text}]

def run(manifest_path, out_path):
    with open(manifest_path, "r", encoding="utf8") as f:
        entries = json.load(f)
    with open(out_path, "w", encoding="utf8") as out:
        for e in tqdm(entries):
            p = Path(e["path"])
            try:
                if p.suffix.lower() == ".pdf":
                    pages = extract_pdf(p)
                else:
                    pages = extract_md(p)
                out_rec = {
                    "doc_id": e["id"],
                    "path": e["path"],
                    "name": e["name"],
                    "pages": pages,
                    "metadata": {
                        "sha256": e["sha256"],
                        "modified": e["modified"],
                        "size": e["size"]
                    }
                }
                out.write(json.dumps(out_rec, ensure_ascii=False) + "\n")
            except Exception as exc:
                print(f"ERROR extracting {p}: {exc}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(args.manifest, args.out)
