# extract-chunk-index — prototype

Purpose
- Ingest long PDFs and MD files, extract text with provenance (page ranges), chunk deterministically, compute embeddings, index into FAISS, and provide a retrieval demo that returns the top supporting chunks for a natural-language query.

Quick start (local prototype)
1. Create and activate a Python 3.9+ venv:
   python -m venv .venv && source .venv/bin/activate
2. Install dependencies:
   pip install -r requirements.txt
3. Put sample PDFs/MD files in `data/sources/`
4. Run pipeline:
   python src/manifest.py --src data/sources --out data/manifest.json
   python src/extract.py --manifest data/manifest.json --out data/extracted.jsonl
   python src/chunker.py --in data/extracted.jsonl --out data/chunks.jsonl
   python src/embed_index.py --chunks data.chunks.jsonl --index-dir data/index
5. Query (demo):
   python src/retrieve.py --index-dir data/index --query "How to set up X?" --topk 5

Notes
- The prototype uses sentence-transformers (all-MiniLM-L6-v2) for embeddings and FAISS for local vector search.
- Extraction uses pdfplumber for PDFs and plain read for MD.
- The retrieval demo prints top chunks and metadata. You can plug these into your generator worker as sources for RAG synthesis.

---

Data layout
- data/sources/  ← put your PDFs/MDs here
- data/manifest.json
- data/extracted.jsonl
- data/chunks.jsonl
- data/index/  ← FAISS index files + metadata.sqlite

Notes, tradeoffs and suggested improvements
- Embeddings model: prototype uses all-MiniLM-L6-v2 (fast & small). If you want higher quality for scientific docs, switch to sentence-transformers/paraphrase-mpnet-base-v2 or a larger embedding hosted in ODS/jcode.
- Chunking: current chunker is char-based (deterministic). For better semantic chunks, use an NLP sentence tokenizer and chunk by token count (via transformers tokenizer) or use structural headings from pdfmd when available.
- Index persistence: FAISS is local and fast. For production, swap in Chroma/Milvus/Weaviate via a vector-adapter module so distributed services can share the index.
- Provenance: each chunk stores doc_id and page-range; for precise citations, store character offsets and highlight spans.
- Retrieval & answer synthesis: the demo prints supporting chunks. Your generator_worker should call a synthesis LLM with ‘use only these sources’ instructions and include the chunk ids/page numbers in the output frontmatter.
- Integration points: mission-control can schedule ingestion jobs; brainapi2 can receive extracted entities and doc metadata after extraction; headroom can compress long chunks before sending to the LLM during synthesis.

Next steps
- I can add the rest of the scaffolded files (src/manifest.py, src/extract.py, src/chunker.py, src/embed_index.py, src/retrieve.py, requirements.txt) into the repo now, or push the whole scaffold. Tell me if you want the full repo pushed and whether to create it as a new repository or update an existing one.
