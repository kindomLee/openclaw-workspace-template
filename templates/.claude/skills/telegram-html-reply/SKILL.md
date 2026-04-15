---
name: telegram-html-reply
description: Generate rich HTML file replies for Telegram when the response contains tables, comparison matrices, or structured data that Telegram's limited markdown cannot render well. Trigger when replying with tables (|---|), multi-column comparisons, dashboards, or when user explicitly asks for HTML output. NOT for simple text, bullet lists, or small tables (≤2 cols, ≤3 rows).
---

# Telegram HTML Reply

When a reply contains **tables, comparison matrices, or complex structured data**, generate an HTML file and send it via Telegram as a document. Telegram's Markdown does not support tables; sending a styled HTML file renders perfectly on both mobile and desktop clients.

## When to Trigger

- Reply contains markdown tables (`| --- |`)
- Multi-column comparisons or matrices
- User explicitly asks for HTML or rich formatting
- Data that benefits from visual layout (cards, timelines, tagged lists)

## When NOT to Trigger

- Simple text replies, bullet lists, or short code blocks
- Replies where a table has ≤2 columns and ≤3 rows (just use text)
- User is in a hurry / quick Q&A context

## Workflow

1. Write the normal reply text to the user (brief summary, no table)
2. Generate HTML file under the workspace-local `tmp/` directory (system `/tmp` is blocked by the workspace-root constraint — see the `write-tmp` skill)
3. Send the file to Telegram as a document (see the Send section below)
4. The text reply + file send together form the complete response

## Send — Claude Code mode (default)

Claude Code has no built-in `message` tool. Send directly via the Telegram Bot API with `curl`:

```bash
# Prereqs: TG_BOT_TOKEN + TG_CHAT_ID in cron/config.env or shell env
source "$CLAUDE_PROJECT_DIR/cron/config.env" 2>/dev/null || true
OUTPUT="$CLAUDE_PROJECT_DIR/tmp/grinder-comparison.html"

curl -s -X POST "https://api.telegram.org/bot${TG_BOT_TOKEN}/sendDocument" \
  -F "chat_id=${TG_CHAT_ID}" \
  -F "document=@${OUTPUT}" \
  -F "caption=磨豆機比較表"
```

Notes:
- Use `sendDocument`, not `sendMessage` — it lets Telegram preview the HTML inline on desktop and offer download on mobile.
- Keep the caption short; long captions get truncated by the Telegram client.
- `curl -s` to suppress the JSON response; add `-v` when debugging delivery.

## Send — OpenClaw mode (alternative)

OpenClaw ships a `message` tool that handles channel routing:

```
message(
  action=send,
  channel=telegram,
  target=$TG_CHAT_ID,
  filePath="$OPENCLAW_WORKSPACE/tmp/grinder-comparison.html",
  caption="磨豆機比較表"
)
```

Use this path only when running inside an OpenClaw agent — on Claude Code the `message` tool does not exist.

## HTML Style Guide

Key rules for the generated HTML:

- Dark theme (`#0f0f17` background, `#e0e0e0` text)
- Mobile-first, `max-width: 680px`
- Tables: dark header (`#2d2d44`), hover rows, clean borders
- Tags/badges: coloured inline blocks for categories
- Cards: rounded corners, subtle borders, for item listings
- Images: base64 data URIs (external URLs get blocked by Telegram hotlink protection)
- Language: match the user's language (Traditional Chinese default for this workspace)
- `<meta name="viewport" content="width=device-width, initial-scale=1.0">` in `<head>`

All styles go inline in a single `<style>` block — Telegram strips external stylesheet references.

## After Sending

End your text reply with `NO_REPLY` if the HTML file **is** the complete reply and you've already delivered it (caption + file) to Telegram. Otherwise write a brief 2-line summary text reply referencing the file you sent.

## Example

User asks for a comparison of 5 coffee grinders:

1. Generate `$CLAUDE_PROJECT_DIR/tmp/grinder-comparison.html` with a styled comparison table
2. `curl sendDocument` with `document=@$CLAUDE_PROJECT_DIR/tmp/grinder-comparison.html` and `caption=磨豆機比較表`
3. Text reply: 2-line summary + "full comparison sent as attachment"
