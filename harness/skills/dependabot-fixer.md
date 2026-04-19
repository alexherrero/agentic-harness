# Skill: dependabot-fixer

**Purpose:** when a Dependabot PR has red CI, attempt a bounded automated fix — read the failing logs, consult the upstream CHANGELOG, apply call-site updates, push commits, and abort honestly if the change needs human judgment.

**Not for:** green-CI auto-merge (use GitHub's native [Dependabot auto-merge](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/automating-dependabot-with-github-actions) instead — that problem is solved). This skill exists for the *failed-CI* case where a major-version bump broke call sites.

## Preconditions

1. `gh` CLI authenticated for the target repo.
2. `.harness/verify.sh` exists and exits non-zero on broken state. If not, the skill falls back to project-detected commands (`go test ./...`, `npm test`, etc.) but emits a warning.
3. Working tree is clean. Skill refuses to run otherwise.

## Inputs

One of:
- The current branch is `dependabot/*` — operate on that PR.
- A PR number passed explicitly: `/dependabot-fix 42`.
- No argument — list open Dependabot PRs with red CI and ask which one.

## Workflow

### 1. Gather

- `gh pr view <n> --json title,body,headRefName,statusCheckRollup,files`
- Extract: ecosystem (gomod / npm / pip / actions / …), package name, old version, new version, version delta (patch / minor / major).
- `gh run view <latest-failed-run-id> --log-failed` — capture the failing job output.
- Look for upstream changelog:
  - GitHub releases on the package's source repo, filtered to versions in the bump range.
  - `CHANGELOG.md` at the package's source if releases are empty.
- Read `.harness/known-migrations.md` — per-project recipes for known-painful packages. If the bumped package matches an entry, that recipe is the first attempt.

### 2. Diagnose

Produce a short structured diagnosis (kept in scratch, not written to disk yet):
- **Failure category:** type error / removed symbol / signature change / behavior change / lockfile conflict / peer-dep cascade / unknown.
- **Confidence:** high / medium / low. Low → abort to human.
- **Proposed fix:** one or two sentences, plus the file(s) that need editing.

### 3. Bounded fix loop

Default budget: **3 iterations**. Configurable via `DEPENDABOT_FIX_BUDGET` env var.

```
iteration = 0
while iteration < budget:
    apply proposed fix
    run .harness/verify.sh
    if passing: break
    re-read failing output; produce next diagnosis
    iteration += 1
```

If the loop exits without passing → **abort path** (see §5).

### 4. Push and report

On success:
- Commit each iteration as a separate commit on the Dependabot branch with messages like `fix: update call sites for <pkg> v<old>→v<new>`. Co-author the commit per repo convention.
- `git push` to the Dependabot branch.
- Comment on the PR with:
  - Summary of what changed and why (linked to the relevant CHANGELOG entry).
  - Files touched.
  - **Residual risks** the human should review before merging (always include this — never claim "fully verified").
- Append a one-line entry to `.harness/progress.md`: `dependabot-fixer: <pkg> v<old>→v<new> fixed in N iterations`.
- **Do not merge.** The human merges. (Mirrors the `/release` principle: never auto-push/merge/tag.)

### 5. Honest abort

Trigger when:
- Fix budget exhausted.
- Diagnosis confidence is low.
- Fix would require modifying tests (forbidden by AGENTS.md rule 5).
- Fix would touch more than `DEPENDABOT_FIX_MAX_FILES` (default 10) — too broad for an automated update.
- The change is semantically ambiguous (behavior change, not just API rename).

On abort, the skill must:
- Comment on the PR with: the diagnosis, what was tried, what's blocking, and a concrete next step for the human.
- Push any partial fixes only if they leave the tree in a valid state and pass verification — otherwise discard.
- Append to `.harness/progress.md`: `dependabot-fixer: <pkg> v<old>→v<new> ABORTED — <reason>`.
- Exit non-zero.

## What the skill must never do

- Merge the PR.
- Modify tests to make them pass.
- Disable lint rules or type checks to get past errors.
- Push to the default branch directly.
- Pin a dependency to an older version to dodge the bump (if the bump can't be made to work, abort and let the human decide).
- Claim success without `verify.sh` exiting 0.

## Per-project knowledge: `.harness/known-migrations.md`

A curated list of recipes for packages this project has hit before. Format:

```
## <package-name>
### <version-range>
- <step 1>
- <step 2>
Common breakage: <symptom> → <fix>
```

The skill consults this first. If a fix works, the human can append a new recipe. (The skill itself does not auto-update this file — recipes need human judgment to generalize.)

## Why this skill is scoped tight

The research found that green-CI auto-merge is saturated by mature tools. The remaining gap is the **major-version Dependabot PR with red CI** where call sites need updating. This skill targets exactly that case and abandons cleanly when it hits anything broader.
