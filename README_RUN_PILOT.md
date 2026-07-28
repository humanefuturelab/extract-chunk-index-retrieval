# README_RUN_PILOT.md

Purpose
- A short, actionable runbook to execute a 100-sample pilot of the Mode B pipeline contained in this repo. Follows the scaffolded scripts and records the metrics you need to estimate costs and tune prompts.

Prerequisites
- Clone the repo and create a Python 3.9+ venv:
  python -m venv .venv && source .venv/bin/activate
- Install dependencies:
  pip install -r requirements.txt
- System tools (install if you plan to use them): ffmpeg, tesseract (optional)
- Environment variables (set in your shell; do NOT commit keys):
  export CHIPP_API_URL="https://api.chipp.ai"
  export CHIPP_API_KEY="<your_chipp_api_key>"
  export OPENAI_API_KEY="<your_openai_api_key>"  # optional fallback
  export PROVIDER_PRIORITY="chipp,openai"

Directory layout (what the pilot expects)
- content/sources/        # put source files here, one folder per source_id
  - content/sources/src-0001/original.pdf
  - content/sources/src-0002/original.jpg
- data/manifest.json      # produced by src/manifest.py
- data/extracted.jsonl    # produced by src/extract.py
- content/raw-responses/  # provider raw responses stored here
- content/pages/          # generated Markdown pages appear here
- data/pages_meta.sqlite  # page metadata written by generator_worker
- data/jobs/              # simple job queue (embed-page, score-page, human-review)

Pilot dataset (100 samples)
- Prepare a representative sample of 100 files (mix of images and short docs). Put them under content/sources/ as subfolders or into a single directory and run the manifest generator.

Step-by-step pilot commands
1) Generate manifest (discover files)
   python src/manifest.py --src content/sources --out data/manifest.json

2) Extract text
   python src/extract.py --manifest data/manifest.json --out data/extracted.jsonl
   - Inspect the output (first record):
     head -n 1 data/extracted.jsonl | jq '.'

3) Run generator (create pages)
   # Do a limited run (limit=100) to avoid large API spend during pilot
   python src/generator_worker.py \
     --extracted data/extracted.jsonl \
     --prompt prompt_templates/generator_v1.yaml \
     --limit 100 \
     --max-tokens 1200 \
     --temperature 0.2

   What to check after generation:
   - content/raw-responses/*.json (raw provider responses)
   - content/pages/*.md (generated pages)
   - data/jobs/ contains embed-page and score-page jobs for each generated page
   - data/pages_meta.sqlite includes metadata keys for generated pages

4) Run scorer (produce sub_scores & normalized score)
   python src/score_worker.py --db data/pages_meta.sqlite --prompt prompt_templates/scorer_v1.yaml --limit 100

   What to check after scoring:
   - data/pages_meta.sqlite entries have `sub_scores` and `score` fields

5) (Optional) Embed pages and build index
   - Build a pages.jsonl from data/pages_meta.sqlite (script or manual). Then run:
     python src/embed_index.py --chunks pages.jsonl --index-dir data/index
   - Or run a dedicated embed_pages.py if you've added one.

Pilot metrics (record these)
- Total generated pages: N (expect ~100)
- Validation failures: count of human-review jobs in data/jobs/ (job type human-review)
- Average generation latency per page (wall time) — record from console logs or timestamps
- Average tokens per generation (from provider usage in content/raw-responses/*.json or provider dashboard)
- Average scoring latency per page
- Embedding time per page (if embedding run)
- Number of pages above high-score threshold (>= 85) — used to estimate video generation volume
- Disk usage for generated pages and raw responses

How to extract metrics quickly
- Count generated pages:
  ls content/pages | wc -l
- Count validation failures (human-review jobs):
  ls data/jobs | jq -s '.[] | select(.type=="human-review")' | wc -l
- Example: read a sample raw response to see token usage:
  jq '.' content/raw-responses/src-0001.json

Troubleshooting
- Missing frontmatter or validation errors:
  - Inspect content/raw-responses/<source_id>.json to see provider output.
  - Fix prompt_templates/generator_v1.yaml to provide clearer output constraints / add more few-shot examples.
  - Re-run generator for that source: python src/generator_worker.py --source-id src-0001 --extracted data/extracted.jsonl --prompt prompt_templates/generator_v1.yaml

- Provider errors (timeouts / 5xx):
  - The worker falls back to next provider in PROVIDER_PRIORITY. Check logs and raw response files for provider error messages.
  - Inspect CHIPP_API_KEY / OPENAI_API_KEY rate limits and quotas.

- FAISS install issues on pip (faiss-cpu):
  - Use conda to install faiss-cpu or switch to Chroma for easy pip install.

Security & governance checks (pilot)
- Ensure API keys are set as environment variables and never committed.
- Do not publish generated pages until you run license checks and PII detection. Use the human-review queue for pages flagged by the system.

Next steps after pilot
- I can:
  - Analyze pilot outputs you share (one sample page and the corresponding raw response) and tune generator_v1 prompt to reduce validation failures.
  - Scaffold embed_pages.py and cluster_pages.py so you can run clustering on the 100 pages and inspect clusters.
  - Scaffold a minimal generate_video.py that demonstrates script → ElevenLabs TTS → ffmpeg assembly for one high-score page.

If you want me to proceed: run the pilot and paste one sample generated page (content/pages/<page_id>.md) and its raw response (content/raw-responses/<source_id>.json), plus the metric counts above. I will analyze and propose prompt tuning and next infra steps.
