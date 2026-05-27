#!/usr/bin/env python3
"""manifest-info.py — extract fields from a customization manifest.

The bash and pwsh installers shell out to this script rather than parsing
YAML themselves. Keeps the manifest schema in one place.

Usage:
  python3 manifest-info.py <manifest-file> [field]
  python3 manifest-info.py <manifest-file> --shell

Without a field, prints all known fields as key=value lines (lists become
key=v1,v2,v3). With --shell, prints uppercase shell-eval-ready assignments
(SKILL_KIND=skill, SKILL_HOSTS=claude-code,antigravity,gemini-cli, etc.).

Exit:
  0  success
  1  file not found, no frontmatter, or YAML parse error
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    print("manifest-info: pyyaml not installed. run: pip install pyyaml", file=sys.stderr)
    sys.exit(1)


FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# Known scalar + list fields (anything else is ignored at output time)
SCALAR_FIELDS = ("name", "description", "kind", "version", "install_scope", "deprecated")
LIST_FIELDS = ("supported_hosts", "contents")


def parse_manifest(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    m = FRONTMATTER_RE.match(text)
    if not m:
        print(f"manifest-info: no YAML frontmatter in {path}", file=sys.stderr)
        sys.exit(1)
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as e:
        print(f"manifest-info: invalid YAML frontmatter in {path}: {e}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(fm, dict):
        print(f"manifest-info: frontmatter is not a mapping in {path}", file=sys.stderr)
        sys.exit(1)
    return fm


def format_value(value) -> str:
    """Stringify a value for shell consumption."""
    if isinstance(value, list):
        # bundle contents are list-of-dicts (kind: name); flatten to "kind:name,kind:name"
        parts = []
        for item in value:
            if isinstance(item, dict):
                for k, v in item.items():
                    parts.append(f"{k}:{v}")
            else:
                parts.append(str(item))
        return ",".join(parts)
    return str(value) if value is not None else ""


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    path = Path(argv[1])
    if not path.is_file():
        print(f"manifest-info: file not found: {path}", file=sys.stderr)
        return 1

    fm = parse_manifest(path)

    shell_mode = False
    target_field = None
    if len(argv) >= 3:
        if argv[2] == "--shell":
            shell_mode = True
        else:
            target_field = argv[2]

    if target_field is not None:
        # Print just that field's value (empty string if absent)
        value = fm.get(target_field, "")
        print(format_value(value))
        return 0

    # Print all known fields
    for f in SCALAR_FIELDS + LIST_FIELDS:
        if f in fm:
            value = format_value(fm[f])
            if shell_mode:
                # Convert to uppercase shell var: name → NAME, supported_hosts → SUPPORTED_HOSTS
                key = f.upper()
                # Shell-safe single-quote the value
                escaped = value.replace("'", "'\\''")
                print(f"{key}='{escaped}'")
            else:
                print(f"{f}={value}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
