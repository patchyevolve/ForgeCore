# ForgeCore

**Semi-Autonomous AI Code Generation System**

ForgeCore is an interactive CLI tool that uses dual LLM agents (Qwen 2.5 Coder + DeepSeek Coder) to generate, modify, and validate code with 22 safety layers.

## Features

- 🤖 **Dual-Agent System**: Planner (Qwen) + Critic (DeepSeek) work together
- 🔒 **22 Safety Layers**: Tier enforcement, symbol validation, call graph analysis, etc.
- 🌍 **Language-Agnostic**: C++, Python, JavaScript, TypeScript, Rust, Go, Java, C#
- 💬 **Interactive CLI**: Start once, run multiple tasks
- 👁️ **Real-Time Feedback**: See what's being created/modified
- 📊 **Diff Preview**: Review changes before approval
- 🔄 **Smart Rollback**: Automatic rollback on validation failure

## Quick Start

### Prerequisites

1. **Python 3.8+**
2. **Ollama** with models:
   ```bash
   ollama pull qwen2.5-coder:7b-instruct
   ollama pull deepseek-coder:6.7b-instruct
   ```

### Installation

```bash
git clone <repo-url>
cd ForgeCore
pip install -r requirements.txt
```

### Usage

#### Interactive Mode (Recommended)

```bash
python forge.py [project_path]
```

Then use natural language:
```
forge> create a tic-tac-toe game in C++
forge> add a factorial function
forge> create file utils.cpp with helper functions
forge> ls
forge> cat main.cpp
forge> exit
```

#### Single Task Mode

```bash
python cli.py task "add a function to calculate fibonacci"
```

## Commands

### Interactive Mode Commands

- `<task>` - Execute a task (natural language)
- `ls` / `list` - List files in project
- `tree` - Show project structure
- `cat <file>` - View file content
- `status` - Show system status
- `history` - Show task history
- `help` - Show help
- `exit` / `quit` - Exit

## Architecture

```
ForgeCore/
├── core/                   # Core system
│   ├── planner.py         # AI Planner (Qwen)
│   ├── critic.py          # AI Critic (DeepSeek)
│   ├── controller.py      # Execution engine
│   ├── context_manager.py # Smart context handling
│   └── ...
├── tools/                  # Validation tools
│   ├── smart_validator.py
│   ├── language_detector.py
│   └── ...
├── policy/                 # Safety policies
│   ├── invariants.json
│   └── tier_policy.json
├── forge.py               # Interactive CLI
└── cli.py                 # Single-task CLI
```

## Safety Layers (22 Total)

1. Tier enforcement
2. File integrity guards
3. Symbol validation
4. Call graph validation
5. Dependency validation
6. Rewrite ratio limits
7. Line count limits
8. File count limits
9. Path traversal checks
10. Stagnation detection
11. Build system monitoring
12. Public API change detection
13. Cross-tier dependency checks
14. Module integrity checks
15. Atomic multi-file commits
16. Snapshot/rollback system
17. Baseline tracking
18. Content fingerprinting
19. Error classification
20. Critic pre-review
21. Critic post-review
22. Smart validation (adaptive)

## Example Session

```bash
$ python forge.py D:\myproject

======================================================================
FORGECORE - INTERACTIVE MODE
======================================================================

Project: D:\myproject

[INFO] Empty project detected - ready to build from scratch!

[OK] System ready!

forge> create a complete tic-tac-toe game in C++

🤖 AI is planning...
  ✓ Plan generated!

Operation: CREATE_FILE
Target File: tic_tac_toe.cpp

📄 DIFF PREVIEW (new file):
  +   1 | #include <iostream>
  +   2 | #include <vector>
  ...

Approve this plan? (y/n/m for modify): y

[Executing...]

TASK COMPLETE
Status: completed
[OK] Task completed successfully!

Changes made:
  [+] Created: tic_tac_toe.cpp

forge> ls

Total files: 1
  tic_tac_toe.cpp                               2049 bytes

forge> exit

Goodbye!
```

## Configuration

Create `forgecore_config.json`:
```json
{
  "project_path": "D:\\path\\to\\your\\project"
}
```

Or use command line:
```bash
python cli.py config
```

## Testing

```bash
python cli.py test
```

## How It Works

1. **User gives task** in natural language
2. **Planner (Qwen)** generates PatchIntent
3. **Critic (DeepSeek)** reviews intent (pre-execution)
4. **User approves** after seeing diff preview
5. **Controller executes** with 22 safety checks
6. **Validation runs** (build, symbols, call graph, etc.)
7. **Critic reviews** result (post-execution)
8. **Success or rollback** based on validation

## Development

- **Language**: Python 3.8+
- **LLMs**: Qwen 2.5 Coder 7B, DeepSeek Coder 6.7B
- **Database**: SQLite (for indexing)
- **Architecture**: State machine with transaction context

## License

MIT

## Contributing

Contributions welcome! Please ensure all 46 tests pass:
```bash
python cli.py test
```

## Status

✅ Production-ready
✅ 100% test coverage (46/46 tests)
✅ All safety layers active
✅ Dual-agent system operational
