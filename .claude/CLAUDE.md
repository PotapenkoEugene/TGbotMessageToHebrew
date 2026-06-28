## Active Obsidian Project
- Project: TGbot_MessageToHebrew
- File: ~/Orthidian/projects/TGbot_MessageToHebrew.md

## LLM Backend
This project uses Claude Code subscription via `claude-agent-sdk` (persistent session, not per-call subprocess) — NOT the Anthropic API / ANTHROPIC_API_KEY. Auth = CLAUDE_CODE_OAUTH_TOKEN from sops. Never suggest switching to API key billing.

## Deployment
Claude Code sessions run DIRECTLY on Mac Studio (this is the deploy machine). `tgbot-update` is a local shell command — run it directly, never via SSH. Always run autonomously, never ask permission:

```bash
bash -li -c "tgbot-update"
```

If a session somehow runs remotely and SSH is needed: `ssh -o StrictHostKeyChecking=no ortho@mac-studio 'bash -li -c "tgbot-update"'` (SSH key `~/.ssh/mac_studio_ed25519` required on that remote machine).

## README Maintenance

After shipping a user-visible feature change, ask **before** the `/done` prompt:

> "Feature affects user-visible behavior. Run `/readme-update`? (y/n)"

Wait for yes/no. If yes, invoke the `readme-update` skill. If no, continue.

**Triggers:** new/removed/renamed command, new/removed env var, changed output format, new automatic behavior, new skip rule or threshold, changed runtime requirement.

**Does NOT trigger:** refactors, internal renames, test-only changes, model or perf tuning that does not change user-visible output.

README sections to keep in sync: Features, Using the bot (commands table, skip rules, output format), Self-hosting (env vars table, install steps), Architecture, Roadmap.
