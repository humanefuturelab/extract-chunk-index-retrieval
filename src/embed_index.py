#!/usr/bin/env python3
"""
Compute embeddings for chunks and build a FAISS index.
Also stores chunk metadata in a small SQLite-backed JSON store (sqlitedict) for demo.
"""
import json, argparse, os
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
from sqlitedict import SqliteDict
from tqdm import tqdm
from pathlib import Path

MODEL_NAME = "all-MiniLM-L6-v2"

def run(chunks_file, index_dir):
    os.makedirs(index_dir, exist_ok=True)
    model = SentenceTransformer(MODEL_NAME)
    texts = []
    metas = []
    for line in open(chunks_file, "r", encoding="utf8"):
        rec = json.loads(line)
        texts.append(rec["text"].strip())
        metas.append({
            "chunk_id": rec["chunk_id"],
            "doc_id": rec["doc_id"],
            "doc_path": rec["doc_path"],
            "start_page": rec["start_page"],
            "end_page": rec["end_page"],
            "char_len": rec["char_len"]
        })
    print(f"Computing embeddings for {len(texts)} chunks...")
    embeddings = model.encode(texts, show_progress_bar=True, convert_to_numpy=True)
    dim = embeddings.shape[1]
    index = faiss.IndexFlatIP(dim)  # inner-product on normalized vectors
    faiss.normalize_L2(embeddings)
    index.add(embeddings)
    faiss.write_index(index, os.path.join(index_dir, "faiss.index"))
    # store metadata and texts
    with SqliteDict(os.path.join(index_dir, "metadata.sqlite"), autocommit=True) as db:
        db["meta_count"] = len(metas)
        for i, m in enumerate(metas):
            db[str(i)] = m
        # store texts separately
        db["__texts__"] = texts
    print(f"Index and metadata stored in {index_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", required=True)
    parser.add_argument("--index-dir", required=True)
    args = parser.parse_args()
    run(args.chunks, args.index_dir)
