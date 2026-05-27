#!/usr/bin/env bash
# install-plugin.sh — install an agentm plugin to Antigravity's user-global
# plugins directory (`~/.gemini/config/plugins/<plugin-name>/`).
#
# Unlike agentm/install.sh which installs into a target PROJECT, this script
# installs a plugin user-globally so agy can discover it from any workspace.
#
# Moved from crickets to agentm in v4.0.0 / V4 #36 (compound + plugin
# customizations consolidated under agentm). Source plugins now live at
# agentm/harness/plugins/<name>/ rather than crickets/plugins/<name>/.
#
# Usage:
#   bash install-plugin.sh <plugin-name>           # install one plugin
#   bash install-plugin.sh --uninstall <plugin-name>
#   bash install-plugin.sh --list
#   bash install-plugin.sh --help
#
# What it does:
#   1. Reads agentm/harness/plugins/<name>/plugin.md (YAML manifest).
#   2. Generates plugin.json (JSON form for agy) from the YAML frontmatter.
#   3. Copies the plugin tree to ~/.gemini/config/plugins/<name>/:
#        - plugin.json (generated)
#        - skills/<skill-name>/SKILL.md (byte-identical to source)
#        - any other nested content (references/, examples/, policies/)
#   4. Prints a verification command (agy plugin list).
#
# Added crickets v1.2.0 per ADR 0011; moved to agentm in v4.0.0 / V4 #36.
# See wiki/how-to/Add-A-Plugin.md for the authoring walkthrough.

set -euo pipefail

print_help() {
    sed -n '/^# install-plugin.sh/,/^[^#]/p' "$0" | sed 's|^# \?||' | head -n -1
}

# ── argument parsing ──────────────────────────────────────────────────────
ACTION="install"
PLUGIN_NAME=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --uninstall)
            ACTION="uninstall"
            PLUGIN_NAME="${2:-}"
            [[ -z "$PLUGIN_NAME" ]] && { echo "--uninstall requires a plugin name" >&2; exit 2; }
            shift 2
            ;;
        --list)
            ACTION="list"
            shift
            ;;
        --help|-h)
            print_help
            exit 0
            ;;
        --*)
            echo "Unknown option: $1" >&2
            print_help >&2
            exit 2
            ;;
        *)
            if [[ -z "$PLUGIN_NAME" && "$ACTION" == "install" ]]; then
                PLUGIN_NAME="$1"
                shift
            else
                echo "Unexpected positional argument: $1" >&2
                exit 2
            fi
            ;;
    esac
done

# ── locate harness + plugins dir ──────────────────────────────────────────
HARNESS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_PLUGINS="$HARNESS_ROOT/harness/plugins"

# Antigravity plugins root (user-global, legacy ~/.gemini/ path retained per
# agy v1.0.2 conventions).
DEST_ROOT="$HOME/.gemini/config/plugins"

# ── list mode ─────────────────────────────────────────────────────────────
if [[ "$ACTION" == "list" ]]; then
    echo "==> available agentm plugins (source: $SRC_PLUGINS):"
    if [[ ! -d "$SRC_PLUGINS" ]]; then
        echo "    (no plugins directory yet)"
    else
        for d in "$SRC_PLUGINS"/*/; do
            [[ -d "$d" ]] || continue
            local_name="$(basename "$d")"
            if [[ -f "$d/plugin.md" ]]; then
                desc="$(grep '^description:' "$d/plugin.md" | head -1 | sed 's/^description: *//')"
                echo "    - $local_name — $desc"
            else
                echo "    - $local_name (no plugin.md — invalid)"
            fi
        done
    fi
    echo ""
    echo "==> installed agentm plugins (dest: $DEST_ROOT):"
    if [[ ! -d "$DEST_ROOT" ]]; then
        echo "    (no plugins installed yet)"
    else
        for d in "$DEST_ROOT"/*/; do
            [[ -d "$d" ]] || continue
            local_name="$(basename "$d")"
            if [[ -f "$d/plugin.json" ]]; then
                version="$(python3 -c "import json; print(json.load(open('$d/plugin.json')).get('version', 'unknown'))" 2>/dev/null || echo "?")"
                echo "    - $local_name (v$version)"
            else
                echo "    - $local_name (no plugin.json)"
            fi
        done
    fi
    exit 0
fi

# ── uninstall mode ────────────────────────────────────────────────────────
if [[ "$ACTION" == "uninstall" ]]; then
    DEST_DIR="$DEST_ROOT/$PLUGIN_NAME"
    if [[ ! -d "$DEST_DIR" ]]; then
        echo "Error: plugin not found: $DEST_DIR" >&2
        exit 1
    fi
    ts="$(date +%Y%m%d%H%M%S)"
    bak="$DEST_DIR.crickets-bak.$ts"
    mv "$DEST_DIR" "$bak"
    echo "==> uninstalled '$PLUGIN_NAME' (backed up to $bak)"
    exit 0
fi

# ── install mode ──────────────────────────────────────────────────────────
if [[ -z "$PLUGIN_NAME" ]]; then
    echo "Error: <plugin-name> is required" >&2
    print_help >&2
    exit 2
fi

SRC_DIR="$SRC_PLUGINS/$PLUGIN_NAME"
if [[ ! -d "$SRC_DIR" ]]; then
    echo "Error: plugin source not found: $SRC_DIR" >&2
    echo "" >&2
    echo "Available plugins:" >&2
    bash "$0" --list >&2
    exit 1
fi

SRC_MANIFEST="$SRC_DIR/plugin.md"
if [[ ! -f "$SRC_MANIFEST" ]]; then
    echo "Error: plugin manifest not found: $SRC_MANIFEST" >&2
    exit 1
fi

DEST_DIR="$DEST_ROOT/$PLUGIN_NAME"

echo "==> installing plugin '$PLUGIN_NAME' to $DEST_DIR"

# Ensure parent exists.
mkdir -p "$DEST_ROOT"

# Wipe destination if it exists (clean install semantics).
if [[ -d "$DEST_DIR" ]]; then
    ts="$(date +%Y%m%d%H%M%S)"
    bak="$DEST_DIR.crickets-bak.$ts"
    mv "$DEST_DIR" "$bak"
    echo "    backed up prior install: $bak"
fi

mkdir -p "$DEST_DIR"

# Generate plugin.json from the YAML frontmatter via Python helper.
python3 - "$SRC_MANIFEST" "$DEST_DIR/plugin.json" <<'PY'
import sys, json, re

src_manifest = sys.argv[1]
dest_json = sys.argv[2]

with open(src_manifest) as f:
    text = f.read()

# Extract frontmatter (between first two --- lines).
m = re.match(r'^---\n(.*?)\n---\n', text, re.DOTALL)
if not m:
    print(f"Error: no YAML frontmatter in {src_manifest}", file=sys.stderr)
    sys.exit(1)

try:
    import yaml
except ModuleNotFoundError:
    print("Error: pyyaml not installed. run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

fm = yaml.safe_load(m.group(1)) or {}

# Map crickets YAML fields → Antigravity plugin.json fields.
plugin_json = {
    "name": fm.get("name"),
    "version": fm.get("version"),
    "description": fm.get("description"),
}
# Optional fields, only include if present.
for field in ("author", "repository", "license", "keywords"):
    if field in fm:
        plugin_json[field] = fm[field]
# Author can be a string or a dict {name, email}.
if isinstance(plugin_json.get("author"), str):
    plugin_json["author"] = {"name": plugin_json["author"]}

# Required field check.
for required in ("name", "version", "description"):
    if not plugin_json.get(required):
        print(f"Error: plugin.md frontmatter missing required field: {required}", file=sys.stderr)
        sys.exit(1)

with open(dest_json, "w") as f:
    json.dump(plugin_json, f, indent=2)
    f.write("\n")

print(f"    generated {dest_json}")
PY

# Copy nested skills (skills/<name>/SKILL.md + any referenced files).
if [[ -d "$SRC_DIR/skills" ]]; then
    cp -R "$SRC_DIR/skills" "$DEST_DIR/skills"
    skill_count="$(find "$DEST_DIR/skills" -name 'SKILL.md' | wc -l | tr -d ' ')"
    echo "    copied $skill_count skill(s)"
fi

# Copy optional plugin-level dirs (references/, examples/, policies/).
for opt in references examples policies; do
    if [[ -d "$SRC_DIR/$opt" ]]; then
        cp -R "$SRC_DIR/$opt" "$DEST_DIR/$opt"
        echo "    copied $opt/"
    fi
done

# Generate installed_version.json (auto-generated by agy's plugin install;
# we mirror the format for parity).
python3 -c "import json,sys; v=json.load(open('$DEST_DIR/plugin.json'))['version']; json.dump({'version': v}, open('$DEST_DIR/installed_version.json', 'w'))"

echo ""
echo "==> install complete"
echo ""
echo "Verify:"
echo "    agy plugin list                     # should show '$PLUGIN_NAME'"
echo ""
echo "Test (from any directory):"
echo "    agy --print \"use the example-plugin-skill\" --print-timeout 30s"
