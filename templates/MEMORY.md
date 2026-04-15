# MEMORY.md - Long-term Memory

*Last updated: YYYY-MM-DD*

<!-- compact:start -->
**L0** Agent:(your-agent-name) | Human:(your-name) | Lang:en | TZ:UTC+0
**L1_RECENT** (5-7 headline bullets kept in sync by hand, or harvested from Events Timeline below by `scripts/compact-update.py`)
- YYYY-MM-DD short summary of a recent notable event
<!-- compact:end -->

> This block is lifted by `scripts/compact-update.py` into
> `MEMORY_COMPACT.md` (the ~200-token wake-up context that every session
> reads). Keep it small. Everything else below is free-form.

## Events Timeline [P0]
<!-- Keep the current month inline. `scripts/memory-compress.py` folds
     months older than 90 days down to one summary line. -->

### YYYY-MM
- **DD** Event description | Another event

## User Profile [P0]
- Language | Location | Timezone | Primary channel

## User Preferences [P0]
- Communication style preferences
- Tool / workflow preferences
- Default model choice

## Infrastructure [P0]
<!-- Your servers, services, connections. Keep it operational (how to
     reach it), not marketing copy. -->
- **Server:** IP, SSH port
- **Services:** list with ports

## Agent Patterns [P0]
<!-- Behavioral patterns the agent has learned. Promote from
     `.learnings/LEARNINGS.md` when `recurring_count ≥ 3` AND the
     correction is about *how the agent acts*.
     See AGENTS.md § Correction Routing. -->
- Pattern descriptions here

## Learnings [P0]
<!-- Factual knowledge promoted from `.learnings/LEARNINGS.md` type=
     `correction` / `knowledge_gap` / `best_practice`. "This API is
     deprecated", "we use tool X not Y", "rate limit is N/hour". -->
- Knowledge item descriptions here

## Cases [P0]
<!-- Recurring bugs, env regressions, incident post-mortems. Promoted
     from `.learnings/ERRORS.md` when `recurring_count ≥ 3`. Each case
     should name the symptom, the root cause, and the fix. -->
- Case descriptions here
