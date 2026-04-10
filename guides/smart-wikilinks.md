# Smart wikilinks (optional)

The template ships with a **deterministic** broken-wikilink detector
(`scripts/check-broken-wikilinks.py` + `scripts/cron-broken-links-check.sh`).
It is pure regex, has no external dependencies, and catches the case you
actually lose sleep over: stale `[[links]]` whose targets no longer exist.

Separately, you may want **proactive wikilink suggestions** — "when I open
note X, offer 4 related notes I should link to." This is genuinely useful
but requires an embedding model, so the template treats it as an optional
recipe rather than a built-in.

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

3. **Schedule stage** (crontab, you add):
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
