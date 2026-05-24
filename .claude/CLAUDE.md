## Active Obsidian Project
- Project: TGbot_MessageToHebrew
- File: ~/Orthidian/projects/TGbot_MessageToHebrew.md

## LLM Backend
This project uses Claude Code subscription via `claude-agent-sdk` (persistent session, not per-call subprocess) — NOT the Anthropic API / ANTHROPIC_API_KEY. Auth = CLAUDE_CODE_OAUTH_TOKEN from sops. Never suggest switching to API key billing.

## Deployment
Bot runs on Mac Studio via launchd (ssh ortho@mac-studio, no password). Always run `tgbot-update` via SSH autonomously — never ask permission. Command: `ssh -o StrictHostKeyChecking=no ortho@mac-studio 'bash -li -c "tgbot-update"'`

## README Maintenance

After shipping a user-visible feature change, ask **before** the `/done` prompt:

> "Feature affects user-visible behavior. Run `/readme-update`? (y/n)"

Wait for yes/no. If yes, invoke the `readme-update` skill. If no, continue.

**Triggers:** new/removed/renamed command, new/removed env var, changed output format, new automatic behavior, new skip rule or threshold, changed runtime requirement.

**Does NOT trigger:** refactors, internal renames, test-only changes, model or perf tuning that does not change user-visible output.

README sections to keep in sync: Features, Using the bot (commands table, skip rules, output format), Self-hosting (env vars table, install steps), Architecture, Roadmap.
