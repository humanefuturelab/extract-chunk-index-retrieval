#!/usr/bin/env python3
"""
Chunk extracted documents. Produces chunks.jsonl
Each chunk:
{ chunk_id, doc_id, start_page, end_page, text, char_len, token_est }
"""
import json, argparse
from tqdm import tqdm
from pathlib import Path
import math

# simple char-based chunking parameters (proxy for tokens)
CHUNK_SIZE_CHARS = 3000
CHUNK_OVERLAP = 500

def chunk_text(text, size=CHUNK_SIZE_CHARS, overlap=CHUNK_OVERLAP):
    chunks = []
    start = 0
    L = len(text)
    while start < L:
        end = min(L, start + size)
        chunks.append(text[start:end])
        if end == L:
            break
        start = max(0, end - overlap)
    return chunks

def run(in_path, out_path):
    cnt = 0
    with open(in_path, "r", encoding="utf8") as inp, open(out_path, "w", encoding="utf8") as out:
        for line in tqdm(inp):
            doc = json.loads(line)
            doc_id = doc["doc_id"]
            pages = doc["pages"]
            # join pages but keep page ranges for each chunk
            full_text = "\n\n".join([p["text"] or "" for p in pages])
            # chunk
            chunks = chunk_text(full_text)
            # approximate page numbers by char offsets (simple mapping)
            page_breaks = []
            cum = 0
            for p in pages:
                page_breaks.append(cum)
                cum += len(p["text"] or "")
            for i, chunk in enumerate(chunks):
                cnt += 1
                # naive mapping: start_page = closest page_break index
                start_pos = full_text.find(chunk)
                # find page index for start and end
                def page_for_pos(pos):
                    idx = 0
                    s = 0
                    for pi, p in enumerate(pages):
                        if s + len(p["text"] or "") >= pos:
                            return p["page_num"]
                        s += len(p["text"] or "")
                    return pages[-1]["page_num"]
                start_page = page_for_pos(start_pos)
                end_page = page_for_pos(start_pos + len(chunk))
                rec = {
                    "chunk_id": f"{doc_id}-chunk-{i+1}",
                    "doc_id": doc_id,
                    "doc_path": doc["path"],
                    "start_page": start_page,
                    "end_page": end_page,
                    "text": chunk,
                    "char_len": len(chunk)
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"Wrote chunks to {out_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="in_path", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(args.in_path, args.out)
