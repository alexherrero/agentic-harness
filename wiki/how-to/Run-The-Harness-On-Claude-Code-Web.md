# How to run the full harness on Claude Code (web) with Drive vault read/write

> [!NOTE]
> **Goal:** Boot an ephemeral Claude Code web container as a fully configured agentm workstation — full harness in user scope plus read/write access to your `AgentMemory` Google Drive vault.
> **Prereqs:** A Claude Code web environment whose network policy allows `github.com` and `*.googleapis.com`; `python3`, `git`, `curl`, `unzip` in the container; rclone on a machine with a browser (your laptop) for the one-time auth.

## Why this is sync, not a mount

The web container has no `CAP_SYS_ADMIN`, so `rclone mount` (FUSE) is killed on start. Instead the bootstrap **pulls** the vault to a local directory, the harness operates on real files there (`MEMORY_VAULT_PATH`), and you **push** changes back. `rclone sync` does update-in-place, create, *and* delete — fuller write semantics than the create-only Drive MCP, but **batched** rather than live. See [ADR: web-session vault access](../explanation/decisions) for the rationale.

## Steps

1. **Mint the Drive token** (one-time, on your laptop with rclone installed):

   ```bash
   rclone authorize "drive"
   ```

   Consent in the browser; it prints a JSON token. Copy the whole blob.

2. **Add the token as an environment secret.** In the web environment config (Settings → Environment → Variables), add a **secret**:

   ```
   AGENTM_RCLONE_TOKEN = <the JSON token from step 1>
   ```

   Store it as a secret, not a plain variable. It is never committed — the bootstrap reconstructs `rclone.conf` from it each session.

3. **Wire the setup script.** In the same config, set the environment's setup script to run the committed bootstrap:

   ```bash
   bash /home/user/agentm/scripts/bootstrap-web-session.sh
   ```

4. **Start a fresh session.** The bootstrap is idempotent and runs every session:
   - lays out `~/Antigravity/{agentm,crickets}` (clones crickets if absent)
   - installs the harness in user scope (`~/.claude`)
   - installs rclone (pinned, via GitHub releases — the rclone CDN is firewalled)
   - rebuilds the `gdrive` remote from `AGENTM_RCLONE_TOKEN`
   - pulls `gdrive:AgentMemory` → `~/vault/AgentMemory` and points the harness at it

## Verify

```bash
ls ~/.claude/commands/                 # plan.md work.md review.md release.md bugfix.md setup.md
rclone listremotes                     # expect: gdrive:
agentm-vault status                    # remote configured: yes; local file count
python3 ~/Antigravity/agentm/scripts/agentm_config.py --get vault_path
```

## Pushing changes back to Drive

After the harness writes to the vault, sync back (dry-run + confirm by default):

```bash
agentm-vault push
```

| Command | Effect |
|---|---|
| `agentm-vault pull` | Drive → `~/vault/AgentMemory` (run at session start; bootstrap does this) |
| `agentm-vault push` | `~/vault/AgentMemory` → Drive, after preview + `y/N` |
| `agentm-vault status` | remote/local file counts + `rclone check` diff |
| `agentm-vault setup` | reprints the one-time auth instructions |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `AGENTM_RCLONE_TOKEN not set` in bootstrap log | Add the secret (step 2); the vault stays read-only until then. |
| `403 Forbidden` fetching rclone | The rclone CDN is blocked; the bootstrap already uses GitHub releases. Confirm `github.com` is allowed by the network policy. |
| `no 'gdrive:' remote` from `agentm-vault` | Token missing/expired. Re-run `rclone authorize "drive"` and update the secret. |
| `rclone mount` killed / FUSE error | Expected — the container lacks `CAP_SYS_ADMIN`. Use `agentm-vault pull/push`, not a mount. |
| Vault edits not on Drive | You haven't pushed. Run `agentm-vault push` and confirm the dry-run diff. |

## Security notes

- The token grants `scope=drive` (full read/write across your Drive). Keep it in the environment's **secret** store; never commit it or echo it into logs.
- `agentm-vault push` mirrors deletions to Drive. Keep the dry-run + confirm default unless you have backups.
- The container is ephemeral; only what you `push` (to Drive) or `git push` (to a repo) survives a recycle.

See [How to install into a project](Install-Into-Project) for the project-scoped install, and [Use AgentMemory in any agent](Use-AgentMemory-In-Any-Agent) for how the memory layer consumes the vault.
