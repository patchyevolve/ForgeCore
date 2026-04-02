# ForgeCore Graphical

**ForgeCore Graphical** is an interactive TUI (Terminal User Interface) app and CLI tool that uses dual LLM agents (Qwen 2.5 Coder + DeepSeek Coder) to generate, modify, and validate code with 22 safety layers.

## 🚀 Quick Start

### 1. Interactive Mode (Full App Experience)
Run the professional TUI app:
```bash
python tui.py
```
Or use the shortcut:
```bash
python forge.py
```

### 2. Single Task Mode (CLI)
Execute a specific task directly:
```bash
python tui.py task "Add a factorial function to math_utils.py"
```

## Features
- 🤖 **Dual-Agent System**: Planner (Qwen) + Critic (DeepSeek) work together
- 🧠 **Advanced Reasoning**: Full "Thinking" and "Planning" phases before code is generated
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

For detailed instructions on setting up and customizing local and remote LLM providers (Ollama, Groq, etc.), see the **[LLM Provider Guide](file:///d:/codeWorks/ForgeCore/LLM_PROVIDER_GUIDE.md)**.

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
│   ├── planner.py         # AI Planner (Qwen 2.5 Coder 7B)
│   ├── critic.py          # AI Critic (DeepSeek Coder 6.7B)
│   ├── controller.py      # Main execution engine
│   ├── context_manager.py # Smart context & history management
│   ├── indexer.py         # Project indexing (SQLite)
│   ├── snapshot.py        # Rollback & backup system
│   └── ...
├── tools/                  # Validation & environment tools
│   ├── smart_validator.py  # Language-agnostic build/syntax checker
│   ├── language_detector.py # Automatic file type detection
│   └── ...
├── policy/                 # Safety & tier policies
│   ├── invariants.json     # Global system constraints
│   └── tier_policy.json    # File access & modification tiers
├── memory/                 # Persistence layer
│   └── forgecore.db        # SQLite database for indexing
├── forge.py               # Interactive CLI (Stateful)
└── cli.py                 # Single-task CLI (Stateless)
```

## Safety Layers (22 Total)

ForgeCore implements a comprehensive 22-layer safety stack:

### Pre-Mutation (Syntactic)
1. **Operation Support**: Validates if the requested action is supported.
2. **File Indexing**: Ensures target files are tracked and valid.
3. **Symbol Duplication**: Prevents duplicate definitions before writing.
4. **Critic Intent Review**: Dual-agent review of the plan before execution.

### Mutation Stage (Structural)
5. **Rewrite Ratio (Per-File)**: Prevents excessive modification of single files.
6. **Rewrite Ratio (Cross-File)**: Limits total project-wide changes.
7. **Line Limit**: Caps the size of generated content.
8. **File Count Limit**: Prevents accidental massive refactors.
9. **Path Traversal**: Blocks access outside the project root.
10. **File Integrity Guard**: Ensures files haven't changed during execution.
11. **Tier Enforcement**: Protects core/system files from AI modification.
12. **Build System Warnings**: Alerts on changes to critical configuration files.

### Post-Mutation (Semantic)
13. **Type Safety**: Basic type check for common languages.
14. **Data Flow Analysis**: Detects uninitialized variables or use-before-def.
15. **Resource Tracking**: Identifies potential memory leaks or null pointers.
16. **Invariant Checking**: Prevents division by zero or array bounds errors.
17. **Effect Tracking**: Monitors side effects in pure functions.

### Execution & Verification
18. **Build Validation**: Language-agnostic syntax/compilation check.
19. **Module Integrity**: Verifies file-level dependencies.
20. **Symbol Validation**: Cross-file symbol resolution check.
21. **Call Graph Integrity**: Detects illegal cycles or recursions.
22. **Final Critic Review**: Post-execution review of the actual result.

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
