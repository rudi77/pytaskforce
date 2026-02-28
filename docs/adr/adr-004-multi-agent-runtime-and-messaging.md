# ADR 004: Multi-Agent Runtime Tracking & Messaging

## Status
Accepted

## Context
Taskforce needs to support long-running, multi-agent workflows where planners can
spawn sub-agents and sessions can run for hours without losing progress. The core
architecture must remain decoupled from infrastructure concerns such as message
queues, heartbeat persistence, and checkpoint storage.

## Decision
We introduce:

1. **Core Protocols** for messaging and runtime tracking (`MessageBusProtocol`,
   `HeartbeatStoreProtocol`, `CheckpointStoreProtocol`, `AgentRuntimeTrackerProtocol`,
   `SubAgentSpawnerProtocol`).
2. **Infrastructure Adapters** in `taskforce/infrastructure/` for
   message buses and runtime stores.
3. **Sub-Agent Spawner** in the application layer to encapsulate session creation
   and tool-driven orchestration with isolated contexts.
4. **Runtime tracking hooks** in the agent loop to emit heartbeats and checkpoint
   state for recovery.

## Consequences
- Core remains free of infrastructure dependencies while still defining clear
  contracts for long-running coordination.
- Infrastructure adapters can be swapped (e.g., Redis/NATS/SQS) without changes
  to core logic.
- Agents can be resumed after restarts using checkpoints and heartbeat data.

## Alternatives Considered
- Embedding queue clients directly in core (rejected: violates clean architecture).
- Relying solely on the state manager for heartbeats (rejected: lacked explicit
  runtime metadata for recovery).
