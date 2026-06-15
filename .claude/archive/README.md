# Archive — historical 1.x docs

Kept here for reference and so we can trace why 2.0 chose to drop
certain features. Nothing in this folder is part of the current
project; everything described here is gone from the codebase.

| File | What it is |
|---|---|
| `legacy-CLAUDE-1.x.md` | The pre-2.0 CLAUDE.md. Describes TOON format v3.1, page.json, architecture.txt, mark_important, mark_component_hidden, and the 88-test test suite — all dropped in 2.0. |
| `BOT_MIDDLEWARE_IMPLEMENTATION.md` | Implementation notes from when the bot-detection middleware was added in v0.2.0. The middleware itself shipped and is now in `_flask_adapter.py` + `handlers.py`; this doc is historical. |
| `design-1.x.txt` | Original design notes (87KB) from the 1.x era. |

## Safe to delete

All three of these files are safe-delete candidates. They have no
inbound references from the codebase or the current `CLAUDE.md`. The
2.0 design is captured in:

- `CHANGELOG.md` 2.0.0 section (breaking changes + migration)
- `docs/SKILLS.md` (practical usage guide)
- `.claude/CLAUDE.md` (project conventions for Claude Code)
- Auto memory at `~/.claude/projects/-Users-pip-PycharmProjects-dash-hook-my-ai/memory/project-v2-rescope.md`

If you've made peace with leaving 1.x behind, `rm -rf .claude/archive/`
is fine.
