---
name: ship-release
description: Cut a tagged GitHub release from the default branch. Trigger when the user says "ship a release", "cut a release", "tag a release", or invokes the skill explicitly. Auto-sizes the semver bump from conventional-commit prefixes in the commit range since the last tag — patch / minor / major — and respects an explicit size hint (`patch|minor|major`) or exact version (`vX.Y.Z`). Writes CHANGELOG.md, tags, pushes, creates the GitHub release. Aborts if the tree is dirty, the default branch isn't pushed, or the tag already exists.
---

You are running the `ship-release` skill. Full canonical spec: `harness/skills/ship-release.md` in the agentic-harness repo. The summary below is the operational version.

## Preconditions (check first, abort if not met)

1. `gh auth status` — authenticated.
2. Current branch is the default branch (`gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
3. Working tree clean: `git status --porcelain` empty.
4. Local is pushed: `git fetch && [ -z "$(git log origin/HEAD..HEAD --oneline)" ]`.
5. At least one commit since the last tag. If `git describe --tags HEAD` equals the last tag exactly, abort with "nothing to ship".

## Input handling

The user may pass:
- **No argument** → auto-size from commits.
- **`patch` / `minor` / `major`** → force that size.
- **`vX.Y.Z`** → use verbatim, skip auto-sizing.
- **`--dry-run`** → compute + print, don't tag.
- **`--draft`** → create as draft release.

## Workflow

### 1. Classify commits in the range

```bash
PREV=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
RANGE="${PREV:+${PREV}..}HEAD"
git log "$RANGE" --pretty=format:'%s%n%b%n---COMMIT---'
```

Classification rules:
- `feat!:`, `fix!:`, any `!:` subject, or body contains `BREAKING CHANGE:` → **major**
- `feat:` or `feat(scope):` → **minor**
- `fix:`, `perf:`, `refactor:` → **patch**
- `docs:`, `chore:`, `test:`, `ci:`, `build:` → **no-bump**
- Anything else → **patch**

Take the max across all commits. Respect the user's size hint if it's *larger*; warn + confirm if it's *smaller*.

### 2. Compute next version

Parse `PREV` as `vMAJOR.MINOR.PATCH`. Bump per the resolved size. If no prior tag, propose `v0.1.0`.

### 3. Draft release notes

Group commits by section (Added / Changed / Fixed / Breaking / Internal), newest first. Show the draft to the user for edit before tagging. Sections with no commits are omitted.

### 4. Update CHANGELOG.md

Prepend a new section to `CHANGELOG.md` at repo root (create if missing, with a Keep-a-Changelog-style header). Commit it with message `chore(release): vX.Y.Z`. Show the diff and confirm before committing.

### 5. Tag + push + release

```bash
git tag -a "vX.Y.Z" -m "Release vX.Y.Z — <title>"
git push origin HEAD
git push origin "vX.Y.Z"
gh release create "vX.Y.Z" \
  --title "vX.Y.Z — <title>" \
  --notes-file .release-notes.md \
  --verify-tag
```

If any step fails, delete the local tag (`git tag -d vX.Y.Z`) before exiting.

### 6. Print the release URL

`gh release view vX.Y.Z --json url -q .url`.

## Guardrails

- Never push to a non-default branch.
- Never overwrite or move existing tags.
- Never include uncommitted changes.
- Never amend the release commit after tagging.

## Output contract

On success:

```
ship-release: cut vX.Y.Z
  commits:   N (maj/min/patch classification)
  notes:     CHANGELOG.md updated + pushed
  release:   https://github.com/<owner>/<repo>/releases/tag/vX.Y.Z
```

On abort, one line: what failed and what the user should do next.
