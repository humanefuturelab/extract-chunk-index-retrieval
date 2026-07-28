#!/usr/bin/env python3
"""
Walk a source directory and produce manifest.json with files to ingest.
"""
import os, json, hashlib, argparse
from pathlib import Path
from datetime import datetime

def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(8192)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def build_manifest(src_dir, out_path):
    src = Path(src_dir)
    entries = []
    for p in sorted(src.rglob("*")):
        if p.is_file() and p.suffix.lower() in [".pdf", ".md", ".markdown", ".txt"]:
            st = p.stat()
            entries.append({
                "id": f"src-{len(entries)+1}",
                "path": str(p.resolve()),
                "name": p.name,
                "suffix": p.suffix.lower(),
                "size": st.st_size,
                "modified": datetime.utcfromtimestamp(st.st_mtime).isoformat()+"Z",
                "sha256": file_hash(p)
            })
    with open(out_path, "w", encoding="utf8") as f:
        json.dump(entries, f, indent=2)
    print(f"Wrote manifest with {len(entries)} entries to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    build_manifest(args.src, args.out)
