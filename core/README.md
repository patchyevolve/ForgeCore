# Core Module Handbook

The `core/` directory contains the heart of ForgeCore's execution logic, managing the state machine, AI agents, and transactional integrity.

## Key Components

- **[planner.py](file:///d:/codeWorks/ForgeCore/core/planner.py)**: Interfaces with the Planner LLM (Qwen) to generate code change intents.
- **[critic.py](file:///d:/codeWorks/ForgeCore/core/critic.py)**: Interfaces with the Critic LLM (DeepSeek) to review and validate plans and results.
- **[controller.py](file:///d:/codeWorks/ForgeCore/core/controller.py)**: The central orchestrator that manages the execution flow and integrates all safety layers.
- **[indexer.py](file:///d:/codeWorks/ForgeCore/core/indexer.py)**: Manages the SQLite-based project indexing and symbol tracking.
- **[snapshot.py](file:///d:/codeWorks/ForgeCore/core/snapshot.py)**: Handles filesystem snapshots for atomic rollbacks.
- **[context_manager.py](file:///d:/codeWorks/ForgeCore/core/context_manager.py)**: Manages the context window for LLMs, including history and relevant code snippets.
- **[state_machine.py](file:///d:/codeWorks/ForgeCore/core/state_machine.py)**: Defines the valid states and transitions for the ForgeCore execution engine.
- **[transaction_context.py](file:///d:/codeWorks/ForgeCore/core/transaction_context.py)**: Isolated state container for a single task execution.

## Logic Flow

1. **State Machine**: Transitions from `IDLE` -> `PLANNING` -> `APPLYING` -> `VERIFYING` -> `COMMIT`.
2. **Transactionality**: Every operation is wrapped in a transaction that can be rolled back on any validation failure.
3. **Dual-Agent**: The Planner proposes, the Critic validates. Both must pass for a commit to occur.
