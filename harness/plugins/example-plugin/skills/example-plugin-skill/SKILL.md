---
name: example-plugin-skill
description: Demonstrates that a skill nested inside a crickets plugin package is discoverable by Antigravity 2.0 / agy after `bash install-plugin.sh example-plugin`. Activate when the user asks to "demonstrate plugin discovery" or types "example plugin skill demo".
---

# Example plugin skill

A reference skill nested inside the `example-plugin` package. Its purpose is to confirm that:

1. The plugin's `plugin.json` manifest was correctly generated from the toolkit-side YAML frontmatter at install time.
2. The host (`agy` v1.0.2+) discovers nested skills under `~/.gemini/config/plugins/example-plugin/skills/<skill-name>/SKILL.md`.
3. The skill's YAML frontmatter (`name` + `description`) matches what agy expects.

## When activated

Respond with exactly:

```
example-plugin-skill ACTIVATED — plugin discovery works ✓
Skill path: ~/.gemini/config/plugins/example-plugin/skills/example-plugin-skill/SKILL.md
Plugin: example-plugin v0.1.0 (crickets toolkit reference plugin)
```

Then briefly explain to the user (1-2 sentences) what just happened: the user typed an activation phrase, agy matched it against this skill's description, loaded the SKILL.md from inside the plugin's `skills/` directory, and the agent followed the instructions in this body. That's the full plugin → skill discovery loop.

## Out of scope

This skill is for demonstration only. It does NOT:

- Modify files.
- Run shell commands.
- Call external services.
- Persist state.

Use it as a verification step after `install-plugin.sh example-plugin` or `agy plugin install` — if you see the activation response above, plugin discovery is working end-to-end.
