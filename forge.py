#!/usr/bin/env python
"""
ForgeCore Interactive CLI - Semi-Autonomous Code Generation

Start the interactive session and give tasks continuously.
"""

import sys
import os
from datetime import datetime
from core.controller import Controller
from core.logger import Logger
from core.interactive_session import InteractiveSession

class ForgeREPL:
    """Interactive REPL for ForgeCore"""
    
    def __init__(self, project_path):
        self.project_path = project_path
        self.logger = None
        self.controller = None
        self.session = None
        self.task_count = 0
        from datetime import datetime  # used in history entries
        self.history_path = os.path.join(os.getcwd(), "forge_task_history.json")
        
    def initialize(self):
        """Initialize the system"""
        print("\n" + "="*70)
        print("FORGECORE - INTERACTIVE MODE")
        print("="*70)
        print(f"\nProject: {self.project_path}")
        
        # Check if project is empty
        try:
            files = [f for f in os.listdir(self.project_path) 
                    if os.path.isfile(os.path.join(self.project_path, f))]
            if not files:
                print("\n[INFO] Empty project detected - ready to build from scratch!")
            else:
                print(f"\n[INFO] Found {len(files)} existing files")
        except:
            pass
        
        print("\nInitializing...")
        
        try:
            # Initialize components
            self.logger = Logger()
            self.controller = Controller(self.project_path, self.logger)
            
            # Perform initial indexing to build context
            print("[INFO] Indexing project...")
            stats = self.controller.indexer.index_project()
            self.controller._index_fresh = True
            
            print(f"  [OK] Index complete: {stats['total_files']} files, {stats['total_symbols']} symbols")
            if stats['indexed_now'] > 0:
                print(f"  [OK] Successfully indexed {stats['indexed_now']} new/modified files")
            
            # Show detected language
            lang_info = self.controller.validator.language_info
            print(f"\n[OK] Project Analysis:")
            print(f"  Language: {lang_info['primary_language'] or 'Unknown (will detect from first file)'}")
            print(f"  Build System: {lang_info['build_system'] or 'None detected'}")
            if lang_info['is_multi_language']:
                print(f"  Multi-language: {', '.join(lang_info['all_languages'])}")
            
            # Show core safety limits / execution constraints
            try:
                print(f"\n[OK] Execution Constraints:")
                print(f"  Max iterations: {self.controller.max_iterations}")
                print(f"  Max files per transaction: {self.controller.max_files_per_patch}")
                print(f"  Max lines per file change: {self.controller.max_lines_per_file}")
                print(f"  Rewrite ratio threshold: {self.controller.rewrite_ratio_threshold:.0%}")
            except Exception:
                # Do not let UI summary break initialization
                pass
            
            # Create interactive session
            self.session = InteractiveSession(
                planner=self.controller.planner,
                critic=self.controller.critic,
                logger=self.logger
            )
            
            print("\n[OK] System ready!")
            print("\n" + "="*70)
            
            return True
            
        except Exception as e:
            print(f"\n[ERROR] Initialization failed: {e}")
            return False
    
    def show_help(self):
        """Show help message"""
        print("\n" + "="*70)
        print("COMMANDS")
        print("="*70)
        print("\nTask Commands:")
        print("  <task description>     Execute a task (e.g., 'add factorial function')")
        print("  task <description>     Same as above")
        print("\nSystem Commands:")
        print("  help                   Show this help")
        print("  status                 Show system status")
        print("  diagnose               Run project-wide diagnosis")
        print("  history                Show task history")
        print("  agents                 Show agent stack (planner / critic)")
        print("  timeline               Show high-level state timeline for this session")
        print("  ls / list              List files in project")
        print("  tree                   Show project structure")
        print("  cat <file>             Show file content")
        print("  clear                  Clear screen")
        print("  exit / quit            Exit ForgeCore")
        print("\nExamples:")
        print("  > create a C++ project with main.cpp")
        print("  > add a factorial function")
        print("  > create file utils.cpp with helper functions")
        print("  > add include iostream to main.cpp")
        print("="*70 + "\n")
    
    def show_status(self):
        """Show system status"""
        print("\n" + "="*70)
        print("SYSTEM STATUS")
        print("="*70)
        print(f"\nProject: {self.project_path}")
        print(f"Tasks completed: {self.task_count}")
        print(f"Planner LLM: {'[OK] Enabled' if self.controller.planner.use_llm else '[X] Disabled'}")
        print(f"Critic LLM: {'[OK] Enabled' if self.controller.critic.use_llm else '[X] Disabled'}")
        print(f"Log file: {self.logger.log_path}")
        
        # Show execution / safety limits for quick reference
        try:
            print("\nExecution constraints:")
            print(f"  Max iterations: {self.controller.max_iterations}")
            print(f"  Max files per transaction: {self.controller.max_files_per_patch}")
            print(f"  Max lines per file change: {self.controller.max_lines_per_file}")
            print(f"  Rewrite ratio threshold: {self.controller.rewrite_ratio_threshold:.0%}")
        except Exception:
            pass
        print("="*70 + "\n")
    
    def show_agents(self):
        """Show active agents and LLM configuration"""
        print("\n" + "="*70)
        print("AGENT STACK")
        print("="*70)
        try:
            planner = self.controller.planner
            critic = self.controller.critic
            
            print("\nPlanner:")
            print(f"  Status: {'[OK] Enabled' if planner.use_llm else '[X] LLM disabled'}")
            model = getattr(getattr(planner, 'llm_client', None), 'model', None)
            if model:
                print(f"  Model:  {model}")
            
            print("\nCritic:")
            print(f"  Status: {'[OK] Enabled' if critic.use_llm else '[X] LLM disabled'}")
            critic_model = getattr(getattr(critic, 'llm_client', None), 'model', None)
            if critic_model:
                print(f"  Model:  {critic_model}")
        except Exception as e:
            print(f"\n[ERROR] Could not inspect agents: {e}")
        print("="*70 + "\n")
    
    def show_timeline(self):
        """Show high-level state timeline from the current log"""
        print("\n" + "="*70)
        print("SESSION TIMELINE")
        print("="*70)
        try:
            import json
            with open(self.logger.log_path, "r", encoding="utf-8") as f:
                events = json.load(f)
            
            # Focus on key milestones and state transitions
            interesting = []
            for e in events:
                ev = e.get("event", "")
                if ev == "STATE_TRANSITION" or ev in {
                    "PLANNER_INVOKED",
                    "INTENT_GENERATED",
                    "APPLYING_STAGED_WRITES",
                    "SMART_VALIDATION_START",
                    "FINAL_CRITIC_REVIEW",
                    "POST_BUILD_VALIDATION_FAILED",
                    "MODULE_INTEGRITY_PASSED"
                }:
                    interesting.append(e)
            
            if not interesting:
                print("\nNo timeline events recorded yet in this session.")
            else:
                print("")
                for idx, e in enumerate(interesting, 1):
                    ts = e.get("timestamp", "")[11:19]  # HH:MM:SS
                    state = e.get("state", "")
                    ev = e.get("event", "")
                    details = e.get("details", {})
                    summary = ""
                    if ev == "STATE_TRANSITION":
                        summary = f"{details.get('from','?')} → {details.get('to','?')}"
                    elif ev == "PLANNER_INVOKED":
                        summary = f"Planner invoked (iteration {details.get('iteration')})"
                    elif ev == "INTENT_GENERATED":
                        summary = f"Intent: {details.get('operation')} → {details.get('target_file')}"
                    elif ev == "APPLYING_STAGED_WRITES":
                        files = details.get("files", [])
                        summary = f"Applying writes to {len(files)} file(s)"
                    elif ev == "SMART_VALIDATION_START":
                        summary = f"Validation on {len(details.get('modified_files', []))} file(s)"
                    elif ev == "FINAL_CRITIC_REVIEW":
                        summary = f"Final critic on {details.get('file')} (approved={details.get('approved')})"
                    elif ev == "POST_BUILD_VALIDATION_FAILED":
                        summary = details.get("reason", "")[:80]
                    elif ev == "MODULE_INTEGRITY_PASSED":
                        summary = "Post-build checks passed"
                    else:
                        summary = ""
                    
                    print(f"  {idx:02d}. [{ts}] {ev} @ {state}{' - ' + summary if summary else ''}")
        except Exception as e:
            print(f"\n[ERROR] Could not read timeline from log: {e}")
        print("\n(Full details are in the JSON log.)")
        print("="*70 + "\n")
    
    def show_history(self):
        """Show task history (recent tasks with IDs)"""
        print("\n" + "="*70)
        print("TASK HISTORY")
        print("="*70)
        try:
            import json
            if not os.path.exists(self.history_path):
                print("\nNo tasks recorded yet.")
            else:
                with open(self.history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
                if not history:
                    print("\nNo tasks recorded yet.")
                else:
                    print(f"\nTotal tasks recorded: {len(history)}")
                    print("Recent tasks:")
                    # Show last 10
                    for entry in history[-10:]:
                        tid = entry.get("id")
                        status = entry.get("status", "?")
                        desc = entry.get("description", "")[:80]
                        print(f"  #{tid}: [{status}] {desc}")
                    print("\nHint: use 'replay <id>' to rerun a previous task.")
        except Exception as e:
            print(f"\nError reading history: {e}")
        print("="*70 + "\n")
    
    def diagnose_project(self):
        """Run project-wide diagnosis"""
        try:
            from tools.project_diagnoser import ProjectDiagnoser
            diagnoser = ProjectDiagnoser(self.project_path, self.logger)
            results = diagnoser.run_diagnosis()
            diagnoser.print_report(results)
        except Exception as e:
            print(f"\n[ERROR] Diagnosis failed: {e}")

    def list_files(self):
        """List files in project"""
        print("\n" + "="*70)
        print("PROJECT FILES")
        print("="*70)
        try:
            files = []
            for root, dirs, filenames in os.walk(self.project_path):
                # Skip hidden and build directories
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'bin', 'obj', 'Debug', 'Release']]
                
                for filename in filenames:
                    if not filename.startswith('.'):
                        rel_path = os.path.relpath(os.path.join(root, filename), self.project_path)
                        file_size = os.path.getsize(os.path.join(root, filename))
                        files.append((rel_path, file_size))
            
            if not files:
                print("\nNo files in project yet.")
            else:
                print(f"\nTotal files: {len(files)}\n")
                for filepath, size in sorted(files):
                    size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
                    print(f"  {filepath:<40} {size_str:>15}")
        except Exception as e:
            print(f"\nError listing files: {e}")
        print("="*70 + "\n")
    
    def show_tree(self):
        """Show project structure as tree"""
        print("\n" + "="*70)
        print("PROJECT STRUCTURE")
        print("="*70)
        try:
            print(f"\n{os.path.basename(self.project_path)}/")
            self._print_tree(self.project_path, "", set())
        except Exception as e:
            print(f"\nError showing tree: {e}")
        print("="*70 + "\n")
    
    def _print_tree(self, directory, prefix, skip_dirs):
        """Helper to print directory tree"""
        try:
            entries = []
            for entry in os.listdir(directory):
                if entry.startswith('.'):
                    continue
                if entry in ['build', 'bin', 'obj', 'Debug', 'Release', '__pycache__']:
                    continue
                full_path = os.path.join(directory, entry)
                entries.append((entry, os.path.isdir(full_path)))
            
            entries.sort(key=lambda x: (not x[1], x[0]))  # Dirs first, then files
            
            for i, (entry, is_dir) in enumerate(entries):
                is_last = i == len(entries) - 1
                current_prefix = "└── " if is_last else "├── "
                print(f"{prefix}{current_prefix}{entry}{'/' if is_dir else ''}")
                
                if is_dir:
                    extension = "    " if is_last else "│   "
                    self._print_tree(
                        os.path.join(directory, entry),
                        prefix + extension,
                        skip_dirs
                    )
        except PermissionError:
            pass
    
    def show_file(self, filename):
        """Show file content"""
        print("\n" + "="*70)
        print(f"FILE: {filename}")
        print("="*70)
        try:
            filepath = os.path.join(self.project_path, filename)
            if not os.path.exists(filepath):
                print(f"\nFile not found: {filename}")
            else:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    lines = content.splitlines()
                    print(f"\n{len(lines)} lines, {len(content)} bytes\n")
                    for i, line in enumerate(lines, 1):
                        print(f"{i:4d} | {line}")
        except Exception as e:
            print(f"\nError reading file: {e}")
        print("="*70 + "\n")
    
    def execute_task(self, task_description):
        """Execute a task"""
        self.task_count += 1
        
        print("\n" + "="*70)
        print(f"TASK #{self.task_count}")
        print("="*70)
        print(f"\n{task_description}\n")
        
        # Quick agent / safety snapshot for this task
        try:
            print("[AGENTS]")
            print(f"  Planner: {'LLM ON' if self.controller.planner.use_llm else 'LLM OFF'}")
            print(f"  Critic:  {'LLM ON' if self.controller.critic.use_llm else 'LLM OFF'}")
            print("[LIMITS]")
            print(f"  Iterations: up to {self.controller.max_iterations}")
            print(f"  Files/tx:   up to {self.controller.max_files_per_patch}")
        except Exception:
            pass
        
        # Show files before
        files_before = self._get_file_list()
        
        try:
            result = self.session.run_task(task_description, self.controller)
            
            print("\n" + "="*70)
            print("TASK COMPLETE")
            print("="*70)
            print(f"\nStatus: {result['status']}")
            # Show engine message/result string if available
            engine_msg = result.get("result")
            if engine_msg:
                print(f"\nEngine: {engine_msg}")
            
            if result['status'] == 'completed':
                print("[OK] Task completed successfully!")
                
                # Show what changed
                files_after = self._get_file_list()
                self._show_changes(files_before, files_after)
            
            # Record in task history (best-effort)
            self._record_task_history(task_description, result.get("status", "unknown"))
                
            if result['status'] == 'cancelled':
                print("[X] Task cancelled")
            else:
                print(f"[!] Task ended with status: {result['status']}")
            
            print("\n" + "="*70 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n[!] Task interrupted by user\n")
        except Exception as e:
            print(f"\n[ERROR] Task failed: {e}\n")
    
    def _get_file_list(self):
        """Get list of files in project"""
        files = {}
        try:
            for root, dirs, filenames in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'bin', 'obj', 'Debug', 'Release']]
                for filename in filenames:
                    if not filename.startswith('.'):
                        rel_path = os.path.relpath(os.path.join(root, filename), self.project_path)
                        full_path = os.path.join(root, filename)
                        files[rel_path] = os.path.getmtime(full_path)
        except:
            pass
        return files
    
    def _record_task_history(self, task_description, status):
        """Append task entry to persistent history file"""
        import json
        try:
            history = []
            if os.path.exists(self.history_path):
                with open(self.history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            next_id = (history[-1]["id"] + 1) if history else 1
            entry = {
                "id": next_id,
                "description": task_description,
                "status": status,
                "log_path": self.logger.log_path if self.logger else None,
                "project": self.project_path,
                "timestamp": datetime.now().isoformat()
            }
            history.append(entry)
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except Exception:
            # History is best-effort; ignore failures
            pass
    
    def _show_changes(self, before, after):
        """Show what files were created/modified, with basic stats"""
        created = []
        modified = []
        
        for filepath in after:
            if filepath not in before:
                created.append(filepath)
            elif after[filepath] != before.get(filepath):
                modified.append(filepath)
        
        if not (created or modified):
            print("\nNo file changes detected.")
            return
        
        print("\nChanges made:")
        
        # Created files with size and a short preview
        for filepath in created:
            full_path = os.path.join(self.project_path, filepath)
            try:
                size = os.path.getsize(full_path)
                size_str = f"{size:,} bytes" if size < 1024 else f"{size/1024:.1f} KB"
            except Exception:
                size_str = "unknown size"
            print(f"  [+] Created: {filepath} ({size_str})")
            
            # Show first few lines for quick visual confirmation
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
                preview_lines = lines[:10]
                for i, line in enumerate(preview_lines, 1):
                    print(f"       {i:3d} | {line}")
                if len(lines) > 10:
                    print(f"       ... ({len(lines) - 10} more lines)")
            except Exception:
                pass
        
        # Modified files, just list path (controller/validator already printed per-iteration impact)
        for filepath in modified:
            print(f"  [~] Modified: {filepath}")
    
    def run(self):
        """Run the interactive REPL"""
        if not self.initialize():
            return 1
        
        self.show_help()
        
        print("Type 'help' for commands, 'exit' to quit\n")
        
        while True:
            try:
                # Get input
                user_input = input("forge> ").strip()
                
                if not user_input:
                    continue
                
                # Parse command
                command = user_input.lower()
                
                # System commands
                if command in ['exit', 'quit', 'q']:
                    print("\nGoodbye!\n")
                    break
                
                elif command == 'help':
                    self.show_help()
                
                elif command == 'status':
                    self.show_status()
                
                elif command == 'diagnose':
                    self.diagnose_project()
                
                elif command == 'agents':
                    self.show_agents()
                
                elif command == 'timeline':
                    self.show_timeline()
                
                elif command == 'history':
                    self.show_history()
                
                elif command == 'clear':
                    os.system('cls' if os.name == 'nt' else 'clear')
                
                elif command in ['ls', 'list']:
                    self.list_files()
                
                elif command == 'tree':
                    self.show_tree()
                
                elif command.startswith('cat '):
                    filename = user_input[4:].strip()
                    if filename:
                        self.show_file(filename)
                    else:
                        print("ERROR: Please provide a filename\n")
                
                # Task command
                elif command.startswith('task '):
                    task_desc = user_input[5:].strip()
                    if task_desc:
                        self.execute_task(task_desc)
                    else:
                        print("ERROR: Please provide a task description\n")
                
                # Direct task (anything else is treated as a task)
                else:
                    self.execute_task(user_input)
            
            except KeyboardInterrupt:
                print("\n\nUse 'exit' to quit\n")
                continue
            
            except EOFError:
                print("\n\nGoodbye!\n")
                break
            
            except Exception as e:
                print(f"\nERROR: {e}\n")
                continue
        
        return 0


def _save_project_config(project_path):
    """Save project path to config for future runs."""
    import json
    config_file = "forgecore_config.json"
    try:
        config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                config = json.load(f)
        config['project_path'] = project_path
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception:
        pass  # Best-effort


def main():
    """Main entry point"""
    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except Exception:
            pass  # If encoding setup fails, continue anyway
    
    # Get project path from args or config or interactive prompt
    project_path = None
    
    if len(sys.argv) > 1:
        project_path = os.path.abspath(sys.argv[1])
    else:
        # Try to load from config
        config_file = "forgecore_config.json"
        last_path = None
        if os.path.exists(config_file):
            import json
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                    last_path = config.get('project_path')
            except Exception:
                pass
        
        print("\n" + "=" * 70)
        print("FORGECORE - PROJECT SETUP")
        print("=" * 70)
        
        if last_path:
            print(f"\nLast used project: {last_path}")
            choice = input("Use this project? (y/n, or enter new path): ").strip()
            
            if not choice or choice.lower() == 'y':
                project_path = last_path
            elif choice.lower() == 'n':
                project_path = None # Will ask below
            else:
                project_path = os.path.abspath(choice)
        
        if not project_path:
            print("\nEnter the full path to your project folder.")
            print("If the folder doesn't exist, it will be created for you.\n")
            
            while True:
                path_input = input("Project path: ").strip()
                if not path_input:
                    print("  [!] Please enter a valid path.\n")
                    continue
                project_path = os.path.abspath(path_input)
                break
    
    # Check if project exists, if not offer to create it
    if not os.path.exists(project_path):
        print(f"\n[!] Project path does not exist: {project_path}")
        create = input("Create new project folder? (y/n): ").strip().lower()
        if create == 'y':
            try:
                os.makedirs(project_path, exist_ok=True)
                print(f"  [OK] Created project folder: {project_path}")
            except Exception as e:
                print(f"  [ERROR] Could not create folder: {e}")
                return 1
        else:
            print("\nAborted. Usage: python forge.py [project_path]")
            return 1
            
    # Save to config for future runs
    _save_project_config(project_path)
    
    # Run REPL
    repl = ForgeREPL(project_path)
    return repl.run()


if __name__ == "__main__":
    sys.exit(main())
