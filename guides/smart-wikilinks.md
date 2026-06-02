# Smart wikilinks (optional)

The template ships with a **deterministic** broken-wikilink detector
(`scripts/check-broken-wikilinks.py` + `scripts/cron-broken-links-check.sh`).
It is pure regex, has no external dependencies, and catches the case you
actually lose sleep over: stale `[[links]]` whose targets no longer exist.

Separately, you may want **proactive wikilink suggestions** — "when I open
note X, offer 4 related notes I should link to."

## Shipped: zero-LLM version (`cron/bin/smart-wikilinks-bare.sh`)

The template now ships a **deterministic, zero-LLM** proactive suggester that
needs no embedding model and no API quota — it reuses the existing
`scripts/memory-search-hybrid.py` (BM25 + jieba) for relatedness.

- `cron/runner.sh smart-wikilinks` auto-prefers `cron/bin/smart-wikilinks-bare.sh`
  over the `claude -p` prompt (the prompt is kept only as a fallback — delete
  the bare script to revert). This "`bin/<job>-bare.sh` beats `prompts/<job>.md`"
  escape hatch is generic: any cron job can be converted to zero-LLM the same way.
- For notes **without** a `## Related` section it appends one automatically,
  guarded against spurious matches (a candidate filename's kebab-case words must
  actually appear in the note body).
- For notes that **already have** `## Related` it does not edit inline; it writes
  suggestions to `cron/state/wikilink-suggestions.md` for human review.
- Runs in ~1s instead of the prompt version's minutes, and sends a Telegram
  summary if `TG_BOT_TOKEN` / `TG_CHAT_ID` are set in `cron/config.env`.

The embedding-based recipe below remains an **optional quality upgrade** when
BM25 relatedness isn't good enough for your corpus (e.g. heavily multilingual or
synonym-rich notes where lexical overlap misses semantic neighbours).

## When you want this

- Your `notes/` has grown past ~50 files and you keep forgetting that
  related notes exist.
- You want a daily or weekly cron job to update a `## Related` section at
  the end of each active note.
- You are willing to call an embedding API (Gemini, OpenAI, Voyage, local
  model via `sentence-transformers`, etc.) and cache the results.

## Recipe

The implementation is ~300 lines of Python; rather than ship it, here is
the shape so you can adapt it to your embedding provider of choice.

1. **Index stage** (`scripts/build-note-embeddings.py`, you write):
   - Walk `notes/`, strip frontmatter + any existing `## Related` section.
   - For each file, compute `sha256(content)` and compare with an on-disk
     cache keyed by relative path. Only re-embed when the hash changes.
   - Store as `.notes-embedding-index.json`:
     ```json
     {
       "02-Areas/Tech/foo.md": {
         "hash": "<sha256>",
         "embedding": [0.123, ...]
       }
     }
     ```
   - Rate-limit API calls (e.g. `time.sleep(1.5)` for Gemini's free tier).

2. **Suggest stage** (`scripts/smart-wikilinks.py`, you write):
   - Load the index, compute cosine similarity between the target note and
     every other indexed note.
   - Filter: drop archived notes, drop anything below `MIN_SIMILARITY`
     (0.35-0.4 is a reasonable floor), dedupe by simplified filename stem.
   - Take the top K (4-5).
   - Replace the target file's `## Related` section with new `[[links]]`.

3. **Schedule stage** — pick whichever matches your cron runner:

   **Claude Code mode** (add a plist under `cron/launchd/`, then
   re-run `bash cron/install-mac.sh`):
   ```xml
   <key>StartCalendarInterval</key>
   <dict>
     <key>Hour</key><integer>4</integer>
     <key>Minute</key><integer>30</integer>
   </dict>
   ```
   The runner already handles network-wait, timeout, and logging — the
   plist just points at `runner.sh smart-wikilinks-embed` and you put
   the build + suggest logic in a prompt under `cron/prompts/`, or in a
   shell wrapper that calls your Python scripts.

   **OpenClaw mode** (edit `templates/crontab.example`):
   ```
   # daily: embed any new/changed notes, then suggest related links for
   # notes touched in the last 24h
   30 4 * * *  cd $OPENCLAW_WORKSPACE && python3 scripts/build-note-embeddings.py
   45 4 * * *  cd $OPENCLAW_WORKSPACE && python3 scripts/smart-wikilinks.py --recent 1d
   ```

## Why this isn't shipped

- Embedding providers and auth are wildly different; any default we pick
  would be wrong for half the users.
- Cache corruption on first run can burn the whole free-tier quota if the
  user isn't careful.
- The deterministic broken-link checker already handles the highest-value
  case (stale links are a bug; missing suggestions are a nice-to-have).

If you build this, consider contributing it back as a separate repo and
linking it from this guide.
