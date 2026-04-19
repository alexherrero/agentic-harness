# Known migrations

Per-project recipes for packages that have caused dependabot breakage before. Consulted first by the `dependabot-fixer` skill — if a bump matches a recipe here, the skill tries the recipe before diagnosing from logs.

## Format

```
## <package-name>
### <version-range>          # e.g. v1 → v2, or 0.x → 1.0
- <step 1: what to change>
- <step 2>
Common breakage: <symptom from CI logs> → <fix>
```

## Examples (delete when adding real entries)

## express
### v4 → v5
- `req.param()` is removed — use `req.params`, `req.query`, or `req.body` explicitly.
- `app.del()` removed — use `app.delete()`.
Common breakage: `TypeError: req.param is not a function` → call-site replacement.

## go.uber.org/zap
### v1.x patch bumps
- API stable; bumps almost always green. If red, suspect transitive dep change in `go.sum`.
Common breakage: `go.sum` checksum mismatch → `go mod tidy && go mod verify`.

---

(Add your own entries below. The skill does not auto-update this file — generalizing a fix into a recipe is a human call.)
