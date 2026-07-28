# Mode B pipeline — Generate-first, cluster-after (complete doc)

Purpose
- Mode B: generate structured Markdown pages from individual sources first, then deduplicate/cluster/merge the generated pages.  
- Support multi-user submissions, local-first storage, score-driven ranking, high-score triggers for video production with two canonical voices, automated social posting, and a “top scored pages” site.

Overview (one‑line)
- For each source (image or short doc) generate a single structured ~800-word Markdown doc (with YAML frontmatter and numeric score). Persist source → generated doc mapping. After many generated docs, compute embeddings, cluster/merge duplicates, and surface top pages for video generation and publishing.

High-level stages
1. Submission & manifest
2. Source extraction (OCR, captioning, doc extraction)
3. Generate MD (structured prompt + self or external scoring)
4. Persist generated docs + metadata
5. Compute embeddings for generated docs
6. Post-generation dedupe & clustering (merge canonical pages)
7. Enrichment (tags/topics, KG links)
8. Ranking & top-index
9. High-score triggers → Video generation pipeline
10. Social posting (queue + connectors)
11. Top-pages site & admin UI
12. Monitoring, governance, and backups

Detailed design

1) Submission & manifest
- Purpose: capture files and uploader metadata deterministically.
- Inputs: local files (images, short docs) uploaded by users or agents.
- Action:
  - Copy or reference file into canonical local storage path.
  - Create Source manifest entry:
    - schema: { source_id, uploader_id, path, filename, sha256, size, mime, created_at, original_path, license, privacy_flags }
- Jobs:
  - enqueue job: extract-source -> job payload { source_id }

2) Source extraction
- Images:
  - OCR (Tesseract or better) → extracted_text (may be empty)
  - Image captioning / scene detection (BLIP/BLIP2, CLIP prompts, or multimodal LLM) → caption_text, tags, objects, persons_found (face count), nsfw_score
  - Save image metadata: { width, height, exif, color_profile }
- Short docs (MD/TXT/small PDF):
  - Text extraction (pdfmd/markitdown) → text
  - Normalize whitespace, remove boilerplate headers/footers.
- Persist: Extraction record for source_id with extracted_text, caption, and extraction_pipeline_version.
- Cache key: source_id + sha256.

3) Generate MD
- Worker: generator_worker (task type: generate-md)
- Input: { source_id, extracted_text, caption, prompt_template_version, user_id, context_params }
- Output: file content = YAML frontmatter + Markdown body + score block
- Frontmatter fields (required):
  - id: page-<uuid>
  - title: <generated title>
  - sources: [source_id,...]
  - generated_by: user_id
  - generated_at: ISO timestamp
  - score: 0-100 (normalized)
  - sub_scores: { relevance, factuality, structure, readability, originality }
  - tags: []
  - embedding_id (filled later)
  - version: generator_prompt_version
- Markdown body: explicit headings structure (see Suggested prompt template).
- Implementation notes:
  - Use deterministic prompt + few-shot examples to get consistent output structure.
  - Set low temperature for structural consistency; allow higher temperature for creativity in an optional mode.
  - If generator can self-score reliably, include the scoring step in generation; otherwise run a separate scoring job.

Suggested prompt template (concept)
- Provide: instructions, structure, few-shot examples (2), explicit "Output must be:" rules, and scoring rubric example.
- Enforce output format: YAML frontmatter only, then Markdown. Example first lines:
  ---
  title: ...
  sources: [...]
  score: 82
  sub_scores: { relevance: 30, factuality: 20, structure: 18, readability: 8, originality: 6 }
  ---
  # Title
  ## Summary
  ...
- Keep the canonical template stored as an agent-skill (agent-skills) with versioning.

4) Persist generated docs + metadata
- Save doc file to: content/pages/<page_id>.md (plus canonical copy in Git or local blob store).
- Save metadata record in DB (SQLite/Postgres): pages table (see DB schema section).
- Save mapping: source_id → page_id(s). A source can map to multiple pages if desired (e.g., one page per image + one per doc).
- Ensure generated artifacts are immutable: keep versions when re-generation occurs.

5) Embeddings for generated docs
- After generation, enqueue job: embed-page
- Compute embedding (choice of model):
  - Lightweight: sentence-transformers/all-MiniLM-L6-v2 for scale
  - High quality: mpnet/paraphrase or LL-based embeddings
- Store embedding vector in vector store (FAISS/Chroma/Milvus) and persist embedding id in pages table.
- Store also a cached text summary and length.

6) Deduplication & clustering (post-generation)
- Run periodically (e.g., daily or when N new pages generated) a clustering pipeline:
  - Step A (coarse): cluster document-level embeddings to get candidate groups (HDBSCAN or k-means depending on scale).
  - Step B (fine dedupe): within cluster, compute chunk-level or embedding similarity for exact dedupe (cosine similarity threshold).
  - Merge rules:
    - If pages are near-identical (above threshold) mark as duplicate and optionally candidate for canonical merge.
    - For similar but complementary pages, propose aggregated canonical page (automated merge script or editor-assisted merge).
- Persistence:
  - cluster table: { cluster_id, centroid_vector, label, confidence, rep_page_id }
  - canonicalization table: map canonical_page_id -> member_page_ids
- Admin action: UI to inspect clusters, merge, set canonical page, or reject auto-merge.

7) Enrichment: tags, topics & KG links
- Tagging:
  - Use LLM or lightweight keyphrase extractor to propose tags; present for review or auto-add with threshold.
- Topics:
  - Use clustering labels or topic-modeling (BERTopic) to assign topic IDs.
- KG enrichment:
  - Extract named entities, methods, parameter values, and references (citations) using NER tools + LLM entity extraction.
  - Upsert triples into brainapi2 with provenance links to chunk/page.
- Use these enrichments to improve retrieval, drill-downs, and video templating.

8) Ranking & top-index
- Normalize scores: if generator produces sub-scores, combine using weighted sum.
- Example weights (default):
  - relevance 30%, factuality 25%, structure 20%, readability 15%, originality 10%
- Store normalized_score = round(sum(weights * sub_scores)/100)
- Maintain index/table view: top_pages (sorted by normalized_score, recency, cluster novelty)
- Expose endpoints: GET /top-pages?limit=50&topic=..

9) High-score triggers → Video generation
- Condition: page.normalized_score >= threshold (configurable; default 85) AND no existing video OR video outdated
- Job: generate-video { page_id, template_id, voices: [voiceA, voiceB], length_target }
- Video pipeline components:
  - Script generation: transform page into short script (e.g., 60-90 sec). Use templating for CI design (intro, bullet highlights, call-to-action).
  - TTS: use deterministic voice presets (voice-pro, VoxCPM, Confucius4-TTS). Voice assets must be versioned and immutable.
  - Visuals: slides generated from key headings + images from source (licensed) + B-roll rules.
  - Assembly: OpenMontage / ViMax / moviepy to assemble slides, TTS audio, transitions, captions.
- Output: content/videos/<page_id>.mp4 and metadata (duration, voice_preset, storyboard)
- Persist video link in pages table.

10) Social posting & scheduling
- Job: schedule-post { page_id, video_id, platforms, caption_template, schedule_time }
- Use connectors:
  - YouTube: youtube-automation-agent
  - X/Twitter: XActions / twitter-automation-ai
  - Reddit: RedditVideoMakerBot
- Ensure per-account auth, quotas, and retry policies.
- When posting, add metadata with post_id, platform, status, posted_at.

11) Top-pages site & admin UI
- Site features:
  - Landing: top scored pages (by score & topic)
  - Page detail: show MD, source list, score & sub-scores, link to video, play video, show clusters and related pages.
  - Admin: merge clusters, re-score, re-generate, trigger video generation, manage voice presets.
- Implementation choices:
  - Static site (next export) fed from DB/index, or dynamic Next.js app using API endpoints.
  - Ghost is an option if you want CMS features; alternatively a small Next.js service with auth.

12) Monitoring, telemetry & governance
- Metrics to collect:
  - generator throughput (pages/hour), fail rate, avg tokens per generation
  - embedding time, index latency, retrieval latency
  - video generation time, post success/fail, social clicks (via UTM)
  - storage: pages count, embeddings stored, video storage
- Alerts:
  - Generation worker crashes, repeated hallucination flags, PII/PII detection hits.
- Governance:
  - PII detection & quarantine workflows
  - License checks (copyright) on source
  - Per-user quotas & spending controls for LLM APIs if hybrid cloud usage
  - Audit logs for edits & publishing

Integration points: map to existing repos (quick)
- Orchestration & queue: mission-control (use as canonical job dispatcher) or deer-flow for skill-based harness.
- Extraction:
  - pdfmd, markitdown — doc extraction
  - OCR wrapper needed (Tesseract) — create microservice
  - image-caption wrapper needed (BLIP/vision-LM) — create microservice and host on ODS/ollama/jcode
- Generation:
  - agent-skills stores canonical prompt templates
  - generator_worker: new repo/service (stub initially)
  - model runtime: ODS / ollama / jcode / colibri (host LLM)
- Embeddings & vector store:
  - embed_index prototype uses FAISS; for production add vector-adapter repo to support Chroma/Milvus/Weaviate
  - embeddings runtime: sentence-transformers or local LLM embedding via ODS
- KG & enrichment:
  - brainapi2 for KG upserts
  - graph-engineering / Understand-Anything for visualization
- Scoring & verification:
  - iFixAi (re-purpose rules) for scoring harness and factuality checks
- Video:
  - OpenMontage, ViMax, Toonflow-app, OpenCut for pipelines
  - voice-pro / VoxCPM / Confucius4-TTS for voice assets
- Social:
  - youtube-automation-agent, XActions, RedditVideoMakerBot

Data model (DB tables — minimal)
- sources: source_id PK, uploader_id, path, sha256, mime, license, created_at, metadata_json
- pages: page_id PK, title, path_to_md, generated_by, generated_at, score, sub_scores_json, embedding_id, canonical_flag, video_id, tags, topics, version
- embeddings: embedding_id PK, item_type (page/source/chunk), item_id, vector_meta (link to vector store)
- clusters: cluster_id PK, centroid_meta, label, rep_page_id, member_page_ids_json
- videos: video_id PK, page_id, path, duration, voices, generated_at, status
- posts: post_id PK, platform, video_id, page_id, scheduled_at, posted_at, status, response_json

Job types (mission-control)
- extract-source { source_id }
- generate-md { source_id, prompt_version, user_id }
- embed-page { page_id }
- cluster-pages { since_ts | list_page_ids }
- score-page { page_id } (if scoring separate)
- generate-video { page_id, template_id, voice_preset }
- post-video { video_id, platform, schedule_time }
- re-generate-page { page_id, reason }

Storage & file layout (recommended)
- content/sources/<source_id>.(pdf|jpg|md)
- content/pages/<page_id>.md
- content/pages/frontmatter/<page_id>.json (quick metadata)
- content/videos/<page_id>/<page_id>.mp4
- db/ (sqlite for prototype, Postgres for production)
- vector-store/ (FAISS folder or pointer to Chroma)
- backups/ (periodic)

Prompt & scoring specifics (practical)
- Prompt rules:
  - Start with "Output MUST be YAML frontmatter followed by Markdown body"
  - Provide two few-shot examples varying in tone/structure
  - Provide exact headings: Title, Summary, Background, Key Findings, Actionable Steps, Sources, Score block
  - Ask model to produce sub_scores and a normalized score 0-100
- Scoring rubric (defaults):
  - relevance 30, factuality 25, structure 20, readability 15, originality 10
  - Sub-scores scale each 0-100; normalized score = round(sum(weights * sub_scores)/100)
- Scoring implementation:
  - Option A: LLM self-score with few-shot examples and explicit criteria (faster).
  - Option B: Separate scoring LLM that receives generated doc + sources and returns numeric sub-scores (more robust).
  - Option C: Hybrid: heuristics (source match fraction, length, presence of sections) + LLM scoring for factuality.

Prototype / MVP plan (4 phases)
- MVP (1–2 weeks)
  - Implement manifest → extract → chunk → embed → retrieve (done: extract-chunk-index scaffold).
  - Add generator_worker stub that calls model runtime with stored prompt (local or remote) and writes MD frontmatter and pages table entry.
  - Add simple scoring: generator self-score + small normalization script.
- Phase 2 (2–3 weeks)
  - Vector-adapter (FAISS + optional Chroma)
  - Clustering/dedupe batch job and small admin UI to inspect clusters.
  - Add OCR + image captioning wrappers (local BLIP/Tesseract).
- Phase 3 (2–4 weeks)
  - Video-template repo + TTS voice presets integration and video assembly pipeline.
  - Social posting connectors and posting scheduler with per-account credentials.
- Phase 4 (2–4 weeks)
  - Productionize: Postgres, scalable vector DB (Milvus/Weaviate), mission-control hardening, CI, backups, monitoring, per-user quotas & billing.

Testing & validation
- Unit tests for extractor, chunker, embedder.
- Integration tests: full pipeline on a small corpus (10 images + 10 docs).
- Evaluation:
  - Sample ground truth: pick 50 sources and compare auto-generated pages with human-written pages for fidelity, factuality, and structure.
  - Track scoring distribution and calibrate scoring weights.
- User feedback loop:
  - thumbs up/down in UI, re-run generator on negative feedback, track improvements.

Security, privacy & governance
- PII redaction & quarantine: detect PII via NER & flag for manual review.
- License & copyright: store license metadata; block publications where license disallows re-publishing.
- Access control: roles (admin/editor/generator/viewer) controlling publishing & merging.
- Backups: daily metadata snapshots + weekly content backups.

Ops & cost controls
- Use headroom to compress large RAG chunks before generation.
- Per-user quotas and job budgets enforced by mission-control (max tokens / daily generation cap).
- Cache results aggressively (extracted text, embeddings); only recompute on file change.

APIs & example endpoints
- POST /api/v1/submit (multipart/form-data) -> returns source_id; enqueues extract-source
- GET /api/v1/pages/top?limit=20 -> list top pages with metadata
- GET /api/v1/page/{page_id} -> returns page MD + metadata + related videos
- POST /api/v1/page/{page_id}/generate-video -> enqueues generate-video
- POST /api/v1/page/{page_id}/post -> enqueues post-video with platform params
- GET /api/v1/clusters/{cluster_id} -> cluster details
- Admin CLI: kimi-cli page:regen page_id, page:merge canonical_page_id member_ids

Operational checklist before production release
- Harden worker autoscaling & retries
- Add per-user authentication & quotas
- Add vector-adapter for chosen production DB
- Prepare voice asset licensing and verifiable storage
- Add CI & scheduled DB backups
- Add monitoring dashboards (Prometheus/Grafana) and alerts

Open tasks (high priority)
- Create OCR wrapper repo (Tesseract + caching)
- Create image-caption wrapper repo (BLIP or multimodal LLM)
- Create generator_worker repo + sample prompt skill in agent-skills
- Build vector-adapter repo (FAISS + Chroma + Milvus connectors)
- Build video-template repo with two versioned voice presets
- Add social posting secrets store & scheduler

Contact points & references
- Prototype repo: https://github.com/humanefuturelab/extract-chunk-index-retrieval
- Relevant internal repos: mission-control, pdfmd, markitdown, agent-skills, ODS, jcode, brainapi2, headroom, OpenMontage, voice-pro, youtube-automation-agent

Appendix: Minimal example of YAML frontmatter
```yaml
---
---
id: page-0001
title: "*

Included is some information about a GitHub repository and its language composition.
repo: humanefuturelab/extract-chunk-index-retrieval
repo ID: 1314894535
