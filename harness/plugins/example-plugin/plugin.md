---
name: example-plugin
description: Reference plugin showing how to package crickets skills for distribution into Antigravity 2.0 / agy CLI.
kind: plugin
supported_hosts: [antigravity]
version: 0.1.0
author: Crickets toolkit
repository: https://github.com/alexherrero/crickets
license: Apache-2.0
keywords: [example, reference, agentm]
contents:
  - skill: example-plugin-skill
---

# Example plugin

Reference plugin demonstrating the `kind: plugin` customization shape introduced in crickets v1.2.0 (per [ADR 0011](../../wiki/explanation/decisions/0011-antigravity-2-host-support.md)).

## What this plugin demonstrates

- **The plugin directory layout** — `plugins/<plugin-name>/plugin.md` (toolkit-side YAML manifest) + `plugins/<plugin-name>/skills/<skill-name>/SKILL.md` (nested skill files).
- **The Antigravity-side install path** — when delivered to a user's local `agy` install, the plugin lands at `~/.gemini/config/plugins/<plugin-name>/` with:
  - `plugin.json` (auto-generated JSON manifest from the toolkit-side YAML frontmatter)
  - `skills/<skill-name>/SKILL.md` (nested skills, byte-identical to the source)
- **The author / repository / license / keywords fields** that populate the generated `plugin.json` for marketplace discovery.

## How a user installs this plugin

Two paths:

1. **Via the crickets `install-plugin.sh` script** (Recommended for crickets users):
   ```bash
   bash /path/to/crickets/scripts/install-plugin.sh example-plugin
   ```
   This generates `plugin.json` from the YAML frontmatter, copies the plugin tree to `~/.gemini/config/plugins/example-plugin/`, and prints a verification command.

2. **Via `agy plugin install <git-url>` directly** (for plugins published as standalone git repos OR via marketplace):
   ```bash
   agy plugin install https://github.com/alexherrero/crickets/plugins/example-plugin
   ```
   Note: this path requires the plugin to be in a format `agy` can install — typically as the root of a git repo. Plugins inside the crickets monorepo at `plugins/<name>/` work via the first path.

## After install

```bash
agy plugin list
# Should show: example-plugin (v0.1.0)
```

Start an agy session in any directory + ask: *"Use the example-plugin skill to demonstrate plugin discovery."* The agent loads `example-plugin-skill` and responds per the skill's instructions.
