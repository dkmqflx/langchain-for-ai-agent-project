---
name: commit-each
description: Split the current git changes (working tree + staged) into one commit per logical unit of work. Use when the user asks to commit changes separately by task — phrases like "각각 커밋해줘", "작업별로 커밋", "변경사항 분리해서 커밋", "split commits", "commit by task", "/commit-each".
---

# Commit Each

Group the current changes into logical units and create one commit per unit.

## When to apply

User asks to commit the current diff as several separate commits, one per task / concern.
**Do not apply** when the user wants a single bundled commit, or when there are no changes.

## Process

1. **Survey** — run in parallel:
   - `git status` (untracked + modified)
   - `git diff` (unstaged)
   - `git diff --staged` (staged)
   - `git log --oneline -10` (message style reference)
2. **Group** the changes by logical unit:
   - Different feature / skill / command / module → separate commits.
   - A new file and its tests → usually one commit.
   - Refactor + unrelated bugfix mixed inside one file → flag to user; do **not** auto-split with `git add -p`.
   - Pure formatting-only changes → separate commit at the end.
3. **Confirm grouping** with the user when ambiguous (≥ 3 groups, or any mixed-purpose file). For obvious splits (clearly different directories or unrelated files), proceed without asking.
4. **Commit each group** sequentially:
   - Stage only that group's files by name — never `git add .` / `-A` / `-u`.
   - Match the repo's existing message style (check `git log -10`; current convention here is lowercase imperative).
   - Use HEREDOC for multi-line messages.
   - Always end with `Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>`.
5. **Verify** with a final `git status` — clean, or containing only what the user explicitly excluded.

## Guardrails

- Never stage with `git add .` / `-A` / `-u` — list files explicitly.
- Never commit files that look like secrets (`.env`, `credentials*`, keys). Warn instead.
- Never amend or rewrite existing commits — always create new ones.
- Never bundle unrelated work to "save a commit."
- If a pre-commit hook fails, fix the underlying issue and create a NEW commit — never use `--no-verify`.
