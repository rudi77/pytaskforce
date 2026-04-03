# Taskforce Butler Agent

Event-driven personal assistant daemon with scheduling, trigger rules, and Google Workspace integration.

## Features

- Scheduler with cron/interval/one-shot jobs
- Trigger rules (event-to-action automation)
- Google Calendar, Gmail, Drive integration
- Communication Gateway (Telegram, Teams, Slack)
- Butler role specialization (accountant, personal assistant)

## Installation

```bash
cd agents/butler
uv sync
```

## Usage

```bash
taskforce-butler start --profile butler
taskforce-butler status
taskforce-butler rules list
```

## Note

This is a pre-built agent that depends on the `taskforce` core framework.
The Butler-specific infrastructure (scheduler, event sources, communication gateway)
lives in this package, not in the framework core.
