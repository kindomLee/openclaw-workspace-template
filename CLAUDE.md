# openclaw-workspace-template (source checkout)

This directory is the template source, not a workspace. A workspace is created
from it with `bootstrap.sh` in a separate directory, so `git pull` here stays
clean for upgrades. This file is not copied into workspaces.

## The user wants to set it up

Signals: a greeting such as "hi", "install", "set up", "how do I start", or
anything about personalizing the agent — in any language. Reply in the user's
language.

1. Ask one question: where should the workspace go? Suggest `~/my-workspace`;
   it must be outside this clone.
2. Run `./bootstrap.sh --path <dir> --yes` and report the result. If it stops on
   missing required tools, help install those first and re-run.
3. Tell the user to continue in the new workspace: `cd <dir> && claude`, then
   type `hi`. Its first-run flag walks them through the profile files, search
   dependencies and scheduled jobs — don't do that setup from here.

Don't personalize or edit files in this clone as part of setup.

## The user is working on the template itself

Editing scripts, guides or `templates/`, or reviewing a diff: ignore the
section above.
