---
name: telegram-html-reply
description: Generate rich HTML file replies for Telegram when the response contains tables, comparison matrices, or structured data that Telegram's limited markdown cannot render well. Trigger when replying with tables (|---|), multi-column comparisons, dashboards, or when user explicitly asks for HTML output. NOT for simple text, bullet lists, or small tables (≤2 cols, ≤3 rows).
---

# Telegram HTML Reply

When a reply contains **tables, comparison matrices, or complex structured data**, generate an HTML file and send it via Telegram instead of plain text. Telegram markdown does not support tables.

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
2. Generate HTML file at `/tmp/<descriptive-name>.html` using the template style
3. Send via message tool: `action=send, channel=telegram, target=925735798, filePath=/tmp/<name>.html, caption=<one-line description>`
4. The text reply + file send together form the complete response

## HTML Style Guide

Use `assets/base-style.css` as inline `<style>` in every generated HTML. Key rules:

- Dark theme (`#0f0f17` background, `#e0e0e0` text)
- Mobile-first, max-width 680px
- Tables: dark header (`#2d2d44`), hover rows, clean borders
- Tags/badges: colored inline blocks for categories
- Cards: rounded corners, subtle borders, for item listings
- Images: use base64 data URIs (external URLs get blocked by hotlink protection)
- Language: match user's language (Traditional Chinese default)
- `<meta name="viewport" content="width=device-width, initial-scale=1.0">`

## After Sending

End your text reply with `NO_REPLY` if the HTML file IS the complete reply and you used `message` tool to send both caption and file. Otherwise reply normally with a brief summary referencing the file.

## Example

User asks for a comparison of 5 coffee grinders:

1. Generate `/tmp/grinder-comparison.html` with styled table
2. `message(action=send, target=925735798, filePath=/tmp/grinder-comparison.html, caption="磨豆機比較表")`
3. Reply: brief 2-line summary + mention file sent
