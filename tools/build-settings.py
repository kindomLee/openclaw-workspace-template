#!/usr/bin/env python3
"""Generate templates/.claude/settings.json from settings.capabilities.toml.

This is a template-authoring tool — it lives under tools/ at the repo root
and is intentionally NOT copied into user workspaces by workspace.spec.

Why generate instead of hand-edit:
  The raw settings.json permissions.allow array is a flat list of
  opaque "Bash(...)" / "Read(*)" / ... strings. Grouping them by
  capability (inspect_git, run_scripts, write_memory, ...) makes it
  possible to tell at a glance what the agent can actually do. The
  TOML source is the authoritative spec; the JSON is a mechanical
  projection of it.

Guarantees:
  * stdlib only (uses tomllib, Python 3.11+).
  * Preserves the existing ``hooks`` block in settings.json verbatim.
  * Preserves ``permissions.deny`` from the TOML spec.
  * Stable ordering: capabilities in TOML file order, entries within a
    capability in the order they appear in the TOML array.
  * Idempotent: running twice produces byte-identical output.
  * JSON output uses 2-space indent and a trailing newline to match
    the current settings.json style.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC_PATH = REPO_ROOT / "templates" / ".claude" / "settings.capabilities.toml"
SETTINGS_PATH = REPO_ROOT / "templates" / ".claude" / "settings.json"


def load_spec(path: Path) -> dict:
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_current_settings(path: Path) -> dict:
    """Read settings.json so we can preserve non-permissions keys (hooks)."""
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def build_allow_list(spec: dict) -> list[str]:
    """Flatten capability buckets into a single allow list.

    Capability order follows the TOML file; entries within each capability
    preserve their in-file order. No deduplication is performed — a
    duplicate in the source is a bug the author should fix, not something
    this script should silently paper over.
    """
    capabilities = spec.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise SystemExit("settings.capabilities.toml: [capabilities] must be a table")

    allow: list[str] = []
    for cap_name, cap_body in capabilities.items():
        if not isinstance(cap_body, dict):
            raise SystemExit(
                f"settings.capabilities.toml: [capabilities.{cap_name}] must be a table"
            )
        entries = cap_body.get("allow", [])
        if not isinstance(entries, list):
            raise SystemExit(
                f"settings.capabilities.toml: [capabilities.{cap_name}].allow must be an array"
            )
        for entry in entries:
            if not isinstance(entry, str):
                raise SystemExit(
                    f"settings.capabilities.toml: [capabilities.{cap_name}].allow entries must be strings"
                )
            allow.append(entry)
    return allow


def main() -> int:
    if not SPEC_PATH.exists():
        print(f"error: spec not found: {SPEC_PATH}", file=sys.stderr)
        return 1

    spec = load_spec(SPEC_PATH)
    allow = build_allow_list(spec)
    deny = spec.get("deny", [])
    if not isinstance(deny, list):
        raise SystemExit("settings.capabilities.toml: top-level `deny` must be an array")

    current = load_current_settings(SETTINGS_PATH)
    hooks = current.get("hooks", {})

    # Rebuild the settings dict from scratch with a stable key order so
    # diff noise is minimized across regenerations.
    new_settings = {
        "permissions": {
            "allow": allow,
            "deny": deny,
        },
        "hooks": hooks,
    }

    rendered = json.dumps(new_settings, indent=2, ensure_ascii=False) + "\n"

    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(rendered, encoding="utf-8")

    print(f"wrote {SETTINGS_PATH.relative_to(REPO_ROOT)}")
    print(
        f"  capabilities: {len(spec.get('capabilities', {}))}, "
        f"allow entries: {len(allow)}, deny entries: {len(deny)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
