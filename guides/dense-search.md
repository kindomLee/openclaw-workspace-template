# Dense search (optional)

`scripts/memory-search-hybrid.py` is BM25 (jieba) × recency × hall boost out of
the box. When a local embedding server is running for the workspace, it also
fuses in a semantic ranking, and can rerank the top 10 with a cross-encoder.
Nothing else changes: same CLI, same scores range, same hook thresholds.

```
query ─▶ BM25 ranking ──┐
                        ├─ weighted RRF (dense ×3) ─▶ optional cross-encoder rerank of top 10 ─▶ results
query ─▶ embed-server ──┘   (reorders only)            (1:1 RRF with the fused order)
```

`mode=` in the output tells you what ran: `BM25+jieba`, `BM25+jieba+dense`, or
`BM25+jieba+dense+rerank`.

## When it is worth it

- Questions phrased differently from how the notes were written ("how do I get
  into the home network" vs a note titled "WireGuard tunnel").
- Mixed-language corpora.

It costs disk and RAM, so skip it on small workspaces or machines without
spare memory. Measured on the author's Mac:

| Piece | Size |
|---|---|
| venv with torch + sentence-transformers | ~0.9 GB |
| `google/embeddinggemma-2` (Apache-2.0, not gated) | ~2.8 GB on disk |
| `BAAI/bge-reranker-v2-m3` (only with `EMBED_RERANK=1`) | ~2.1 GB on disk, +1–2 GB RAM, +~1.5 s per search |

A query takes ~40–110 ms when the server is up; the first index build embeds
every file in `memory/` + `notes/` (minutes on MPS, longer on CPU), later
refreshes only re-embed changed files.

## Install (macOS)

```bash
cd <your-workspace>
python3 -m venv ~/.local/share/oracle-embed/venv
~/.local/share/oracle-embed/venv/bin/pip install -r scripts/requirements-dense.txt

# try it in the foreground first; it listens once the index is built
~/.local/share/oracle-embed/venv/bin/python -u scripts/embed-server.py
curl -s 127.0.0.1:8766/health          # {"chunks": …, "root": "<your-workspace>", "rerank": false}
python3 scripts/memory-search-hybrid.py "some question" --top 3   # mode=BM25+jieba+dense
```

Run it as a launchd service (kept alive, restarted on crash). The plist lives
in `cron/optional/`, which `cron/install-mac.sh` does **not** install:

```bash
sed -e "s|__PROJECT_DIR__|$PWD|g" -e "s|__HOME__|$HOME|g" \
    cron/optional/org.mklee.embed-server.plist > ~/Library/LaunchAgents/org.mklee.embed-server.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/org.mklee.embed-server.plist
tail -f cron/logs/embed-server.log     # wait for "[ready] …"
```

Reranker: add `<key>EMBED_RERANK</key><string>1</string>` to the plist's
`EnvironmentVariables`, then `launchctl bootout gui/$(id -u)/org.mklee.embed-server`
and bootstrap again.

Linux: `install-linux.sh` only writes crontab lines and can't express a
long-running service. Run `scripts/embed-server.py` under a systemd user unit
or similar (not shipped); `EMBED_DEVICE=cpu` is picked automatically when MPS
is absent.

## Several workspaces on one machine

Each server indexes one workspace and reports it as `root` in every `/search`
reply. The search script ignores a server whose `root` isn't its own
workspace, so a second workspace never mixes in another corpus — it just runs
BM25-only until it has its own server:

```bash
EMBED_PORT=8767 ~/.local/share/oracle-embed/venv/bin/python -u scripts/embed-server.py   # in workspace B
export EMBED_URL=http://127.0.0.1:8767                                                    # where B's searches run
```

Give a second launchd copy its own `Label` and set `EMBED_PORT` +
`EMBED_STATE` (index directory) in its `EnvironmentVariables`.

## Turning it off

`--no-dense` / `--no-rerank` per query (useful for comparing), or stop the
service: `launchctl bootout gui/$(id -u)/org.mklee.embed-server`. With no
server the search is plain BM25 and connection-refused costs nothing.

## Time budget

The recall hook (`.claude/hooks/memory-search-trigger.py`) kills the search
after 6 s and passes `--budget 5`; the rerank only runs with the time left
(≥ 1 s), so a slow rerank degrades to the fused order instead of a hook
timeout.

## Env reference

| Variable | Side | Default | Meaning |
|---|---|---|---|
| `EMBED_URL` | search | `http://127.0.0.1:8766` | server to ask |
| `EMBED_PORT` | server | `8766` | listen port |
| `EMBED_ROOT` | server | the workspace containing the script | corpus root (needs a non-default port) |
| `EMBED_STATE` | server | `~/.local/share/oracle-embed` (or `$EMBED_ROOT/state`) | index directory |
| `EMBED_DEVICE` | server | `mps` if available, else `cpu` | torch device |
| `EMBED_RERANK` | server | unset | `1` loads the cross-encoder |
