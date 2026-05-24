## Active Obsidian Project
- Project: TGbot_MessageToHebrew
- File: ~/Orthidian/projects/TGbot_MessageToHebrew.md

## LLM Backend
This project uses Claude Code subscription via `claude-agent-sdk` (persistent session, not per-call subprocess) — NOT the Anthropic API / ANTHROPIC_API_KEY. Auth = CLAUDE_CODE_OAUTH_TOKEN from sops. Never suggest switching to API key billing.

## Deployment
Bot runs on Mac Studio via launchd (ssh ortho@mac-studio, no password). Always run `tgbot-update` via SSH autonomously — never ask permission. Command: `ssh -o StrictHostKeyChecking=no ortho@mac-studio 'bash -li -c "tgbot-update"'`
