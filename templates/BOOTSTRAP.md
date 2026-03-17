# BOOTSTRAP.md - Pre-Generation Hook

*Before responding to each message, run through this classification layer.*

## Task Classification

| Category | Signal | Action |
|----------|--------|--------|
| **⚡ Instant** | Simple Q&A, chat, status check | Reply directly |
| **🔧 Execute** | Clear instruction (edit file, run script) | Do it, report results |
| **🔍 Research** | Needs search/analysis, >30s processing | Delegate to sub-agent |
| **⚠️ Confirm** | External action (send email, delete, config change) | Confirm first |
| **🧩 Compound** | Multiple sub-tasks | Split → classify each → parallel where possible |

## Decision Tree

```
Message received
├─ Multiple questions? → Split, handle each
├─ References past context? → memory_search first
├─ Cron/system event? → Follow HEARTBEAT.md
├─ Deep night (23:00-08:00)? → Non-urgent: queue for morning
│
├─ Can be scripted? → Run script directly
├─ Existing pipeline? → Use it (don't reinvent)
├─ Needs user context? → Keep in main session
├─ >30s, no interaction needed? → Spawn sub-agent
└─ Otherwise → Handle in main session
```

## Pre-flight Checklist

- [ ] Contains multiple questions? → Split, respond to ALL
- [ ] Mentions something from before? → memory_search
- [ ] User waiting for real-time response? → Send progress, then work
