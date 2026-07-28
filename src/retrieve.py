#!/usr/bin/env python3
"""
Simple retrieval demo:
- load FAISS index + metadata
- embed query with same model
- return top-k chunks and metadata
"""
import argparse, os, faiss, numpy as np, json
from sentence_transformers import SentenceTransformer
from sqlitedict import SqliteDict

MODEL_NAME = "all-MiniLM-L6-v2"

def run(index_dir, query, topk=5):
    model = SentenceTransformer(MODEL_NAME)
    q_emb = model.encode([query], convert_to_numpy=True)
    faiss.normalize_L2(q_emb)
    index = faiss.read_index(os.path.join(index_dir, "faiss.index"))
    D, I = index.search(q_emb, topk)
    with SqliteDict(os.path.join(index_dir, "metadata.sqlite")) as db:
        texts = db["__texts__"]
        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            meta = db[str(idx)]
            text = texts[idx]
            results.append((float(score), meta, text[:1000]))
    print("Top results:")
    for s, m, snippet in results:
        print(f"\nSCORE: {s:.4f} | chunk {m['chunk_id']} (doc:{m['doc_id']} pages {m['start_page']}-{m['end_page']})")
        print("--- snippet ---")
        print(snippet)
    # Stub: show how to synthesize this into a final answer:
    print("\n---\nTo synthesize an answer from these chunks, pass the top chunks into your generator_worker/RAG model with strict citation instructions.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-dir", required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--topk", type=int, default=5)
    args = parser.parse_args()
    run(args.index_dir, args.query, args.topk)
