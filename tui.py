#!/usr/bin/env python
"""
ForgeCore Graphical TUI - Professional App-based System
The definitive entry point for interactive and single-shot coding tasks.
"""

import sys
import os
import json
from datetime import datetime
from core.controller import Controller
from core.logger import Logger
from core.interactive_session import InteractiveSession

# Colors for professional terminal output
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

class ForgeTUI:
    """Literal App-based TUI for ForgeCore Graphical"""
    
    def __init__(self, project_path):
        self.project_path = os.path.abspath(project_path)
        self.logger = None
        self.controller = None
        self.session = None
        self.task_count = 0
        self.history_path = os.path.join(os.getcwd(), "forge_task_history.json")
        self.config_file = "forgecore_config.json"

    def initialize(self, silent=False):
        """Initialize the core system and components"""
        if not silent:
            print("\n" + Colors.HEADER + "="*70 + Colors.ENDC)
            print(Colors.BOLD + "  FORGECORE GRAPHICAL - INITIALIZING" + Colors.ENDC)
            print(Colors.HEADER + "="*70 + Colors.ENDC)
            print(f"\n{Colors.OKBLUE}[PROJECT]{Colors.ENDC} {self.project_path}")

        try:
            # Check project path
            if not os.path.exists(self.project_path):
                 if not silent:
                    print(f"{Colors.FAIL}[!] Project path does not exist: {self.project_path}{Colors.ENDC}")
                 return False

            # Initialize components
            self.logger = Logger()
            self.controller = Controller(self.project_path, self.logger)
            
            # Initial indexing
            if not silent:
                print(f"{Colors.OKCYAN}[INFO] Indexing project...{Colors.ENDC}")
            stats = self.controller.indexer.index_project()
            self.controller._index_fresh = True
            
            if not silent:
                print(f"  {Colors.OKGREEN}[OK]{Colors.ENDC} Index complete: {stats['total_files']} files, {stats['total_symbols']} symbols")
            
            # Create interactive session
            self.session = InteractiveSession(
                planner=self.controller.planner,
                critic=self.controller.critic,
                logger=self.logger
            )
            
            if not silent:
                self.show_project_summary()
                print(f"\n{Colors.OKGREEN}[OK] System ready!{Colors.ENDC}")
                print(Colors.HEADER + "="*70 + Colors.ENDC + "\n")
            
            return True
            
        except Exception as e:
            if not silent:
                print(f"\n{Colors.FAIL}[ERROR] Initialization failed: {e}{Colors.ENDC}")
            return False

    def show_project_summary(self):
        """Show a high-level summary of the project state"""
        lang_info = self.controller.validator.language_info
        print(f"\n{Colors.BOLD}Project Analysis:{Colors.ENDC}")
        print(f"  Language:       {Colors.OKBLUE}{lang_info['primary_language'] or 'Unknown'}{Colors.ENDC}")
        print(f"  Build System:   {Colors.OKBLUE}{lang_info['build_system'] or 'None detected'}{Colors.ENDC}")
        
        try:
            print(f"\n{Colors.BOLD}Execution Constraints:{Colors.ENDC}")
            print(f"  Max iterations:            {Colors.WARNING}{self.controller.max_iterations}{Colors.ENDC}")
            print(f"  Max files per transaction: {Colors.WARNING}{self.controller.max_files_per_patch}{Colors.ENDC}")
            print(f"  Rewrite ratio threshold:   {Colors.WARNING}{self.controller.rewrite_ratio_threshold:.0%}{Colors.ENDC}")
        except Exception:
            pass

    def execute_task(self, task_description):
        """Execute a single task with full feedback loop"""
        self.task_count += 1
        
        print("\n" + Colors.HEADER + "="*70 + Colors.ENDC)
        print(f"{Colors.BOLD}TASK #{self.task_count}{Colors.ENDC}")
        print(Colors.HEADER + "="*70 + Colors.ENDC)
        print(f"\n{Colors.OKBLUE}Description:{Colors.ENDC} {task_description}\n")

        # Capture file set before run
        files_before = self._get_file_list()
        
        try:
            result = self.session.run_task(task_description, self.controller)
            
            print("\n" + Colors.HEADER + "="*70 + Colors.ENDC)
            print(f"{Colors.BOLD}TASK COMPLETE{Colors.ENDC}")
            print(Colors.HEADER + "="*70 + Colors.ENDC)
            
            status = result['status']
            status_color = Colors.OKGREEN if status == 'completed' else Colors.FAIL
            print(f"\nStatus: {status_color}{status.upper()}{Colors.ENDC}")
            
            if status == 'completed':
                print(f"\n{Colors.OKGREEN}[OK] Task completed successfully!{Colors.ENDC}")
                files_after = self._get_file_list()
                self._show_changes(files_before, files_after)
            
            # Record in task history
            self._record_task_history(task_description, status)
            
            print(f"\nLog file: {Colors.OKCYAN}{self.logger.log_path}{Colors.ENDC}")
            print(Colors.HEADER + "="*70 + Colors.ENDC + "\n")
            
            return 0 if status == 'completed' else 1
            
        except KeyboardInterrupt:
            print(f"\n\n{Colors.WARNING}[!] Task interrupted by user{Colors.ENDC}\n")
            return 1
        except Exception as e:
            print(f"\n{Colors.FAIL}[ERROR] Task failed: {e}{Colors.ENDC}\n")
            return 1

    def _get_file_list(self):
        """Get snapshot of project files"""
        files = {}
        try:
            for root, dirs, filenames in os.walk(self.project_path):
                dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['build', 'bin', 'obj', '__pycache__']]
                for filename in filenames:
                    if not filename.startswith('.'):
                        rel_path = os.path.relpath(os.path.join(root, filename), self.project_path)
                        full_path = os.path.join(root, filename)
                        files[rel_path] = os.path.getmtime(full_path)
        except:
            pass
        return files

    def _show_changes(self, before, after):
        """Show created/modified files"""
        created = []
        modified = []
        for filepath in after:
            if filepath not in before:
                created.append(filepath)
            elif after[filepath] != before.get(filepath):
                modified.append(filepath)
        
        if created or modified:
            print(f"\n{Colors.BOLD}Changes made:{Colors.ENDC}")
            for f in created:
                print(f"  {Colors.OKGREEN}[+]{Colors.ENDC} Created: {f}")
            for f in modified:
                print(f"  {Colors.OKBLUE}[~]{Colors.ENDC} Modified: {f}")

    def _record_task_history(self, task_description, status):
        """Save task info to history file"""
        try:
            history = []
            if os.path.exists(self.history_path):
                with open(self.history_path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            
            entry = {
                "id": (history[-1]["id"] + 1) if history else 1,
                "description": task_description,
                "status": status,
                "project": self.project_path,
                "timestamp": datetime.now().isoformat()
            }
            history.append(entry)
            with open(self.history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2)
        except:
            pass

    def run_interactive(self):
        """Main REPL loop"""
        if not self.initialize():
            return 1
            
        print(f"Type '{Colors.OKCYAN}help{Colors.ENDC}' for commands, '{Colors.OKCYAN}exit{Colors.ENDC}' to quit\n")
        
        while True:
            try:
                user_input = input(f"{Colors.BOLD}forge>{Colors.ENDC} ").strip()
                if not user_input: continue
                
                cmd = user_input.lower()
                if cmd in ['exit', 'quit', 'q']: break
                elif cmd == 'help': self.show_help()
                elif cmd == 'status': self.show_status()
                elif cmd == 'clear': os.system('cls' if os.name == 'nt' else 'clear')
                elif cmd.startswith('task '): self.execute_task(user_input[5:].strip())
                else: self.execute_task(user_input)
                
            except KeyboardInterrupt:
                print("\n\nUse 'exit' to quit\n")
            except EOFError:
                break
        
        print("\nGoodbye!\n")
        return 0

    def show_help(self):
        """Show interactive help"""
        print("\n" + Colors.HEADER + "="*70 + Colors.ENDC)
        print(Colors.BOLD + "  COMMANDS" + Colors.ENDC)
        print(Colors.HEADER + "="*70 + Colors.ENDC)
        print("\n  <task description>     Execute a task directly")
        print("  status                 Show system status")
        print("  clear                  Clear screen")
        print("  help                   Show this help")
        print("  exit / quit            Exit the application")
        print(Colors.HEADER + "="*70 + Colors.ENDC + "\n")

    def show_status(self):
        """Show app status"""
        print(f"\n{Colors.BOLD}System Status:{Colors.ENDC}")
        print(f"  Project: {self.project_path}")
        print(f"  Planner: {'[OK]' if self.controller.planner.use_llm else '[OFF]'}")
        print(f"  Critic:  {'[OK]' if self.controller.critic.use_llm else '[OFF]'}")
        print(f"  Logs:    {self.logger.log_path}\n")

def get_config_path():
    """Load project path from last session"""
    config_file = "forgecore_config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                return json.load(f).get('project_path')
        except: pass
    return None

def save_config_path(path):
    """Save project path for next session"""
    config_file = "forgecore_config.json"
    try:
        config = {}
        if os.path.exists(config_file):
            with open(config_file, 'r') as f: config = json.load(f)
        config['project_path'] = os.path.abspath(path)
        with open(config_file, 'w') as f: json.dump(config, f, indent=2)
    except: pass

def main():
    # Set UTF-8 encoding for Windows
    if sys.platform == 'win32':
        try:
            import codecs
            sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
        except Exception:
            pass

    # Setup project path
    project_path = None
    explicit_path = False

    # Check command line args for direct path or --project flag
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        if sys.argv[1] not in ["task", "config", "test", "clean", "demo", "help"]:
            project_path = os.path.abspath(sys.argv[1])
            explicit_path = True

    if not project_path and '--project' in sys.argv:
        idx = sys.argv.index('--project')
        if idx + 1 < len(sys.argv):
            project_path = os.path.abspath(sys.argv[idx + 1])
            explicit_path = True

    # If no explicit path provided, enter interactive setup
    if not explicit_path:
        print("\n" + Colors.HEADER + "=" * 70 + Colors.ENDC)
        print(Colors.BOLD + "  FORGECORE GRAPHICAL - PROJECT SETUP" + Colors.ENDC)
        print(Colors.HEADER + "=" * 70 + Colors.ENDC)

        last_path = get_config_path()
        if last_path:
            print(f"\nLast used project: {Colors.OKBLUE}{last_path}{Colors.ENDC}")
            choice = input("Use this project? (y/n, or enter new path): ").strip()
            
            if not choice or choice.lower() == 'y':
                project_path = last_path
            elif choice.lower() == 'n':
                project_path = None # Will ask below
            else:
                project_path = os.path.abspath(choice)
        
        if not project_path:
            print(f"\n{Colors.OKCYAN}Enter the full path to your project folder.{Colors.ENDC}")
            print("If the folder doesn't exist, it will be created for you.\n")
            
            while True:
                path_input = input("Project path: ").strip()
                if not path_input:
                    print(f"  {Colors.FAIL}[!] Please enter a valid path.{Colors.ENDC}\n")
                    continue
                project_path = os.path.abspath(path_input)
                break
    
    # Check if project exists, if not offer to create it
    if not os.path.exists(project_path):
        print(f"\n{Colors.WARNING}[!] Project path does not exist: {project_path}{Colors.ENDC}")
        create = input("Create new project folder? (y/n): ").strip().lower()
        if create == 'y':
            try:
                os.makedirs(project_path, exist_ok=True)
                print(f"  {Colors.OKGREEN}[OK] Created project folder: {project_path}{Colors.ENDC}")
            except Exception as e:
                print(f"  {Colors.FAIL}[ERROR] Could not create folder: {e}{Colors.ENDC}")
                return 1
        else:
            print(f"\n{Colors.FAIL}Aborted. No project folder selected.{Colors.ENDC}")
            return 1

    save_config_path(project_path)
    app = ForgeTUI(project_path)

    # Command Routing
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        
        if cmd == "task":
            task_desc = " ".join([arg for arg in sys.argv[2:] if arg != '--project' and sys.argv[sys.argv.index(arg)-1] != '--project'])
            if app.initialize(silent=False):
                return app.execute_task(task_desc)
        
        elif cmd == "config":
            # Simple config helper
            print(f"\nCurrent Project: {Colors.OKBLUE}{project_path}{Colors.ENDC}")
            new = input("New path (leave empty to keep): ").strip()
            if new: save_config_path(new)
            return 0
            
        elif cmd == "test":
            import subprocess
            return subprocess.run([sys.executable, "tests/run_all_tests.py"]).returncode
            
        elif cmd == "demo":
            import demo_full_cycle
            return 0 if demo_full_cycle.main() else 1
            
        elif cmd == "clean":
            import cleanup_test_artifacts
            cleanup_test_artifacts.clean_main_cpp()
            return 0
            
        elif cmd in ["help", "-h", "--help"]:
            # Need an instance to show help if we use the class method, 
            # or just call print_usage directly if we move it out.
            # For now, let's just show a simple help.
            print("\n" + Colors.HEADER + "="*70 + Colors.ENDC)
            print(Colors.BOLD + "  FORGECORE GRAPHICAL - HELP" + Colors.ENDC)
            print(Colors.HEADER + "="*70 + Colors.ENDC)
            print(f"\n{Colors.BOLD}Usage:{Colors.ENDC}")
            print(f"  python tui.py [project_path]         Start interactive mode")
            print(f"  python tui.py task \"description\"     Run a single task")
            print(f"  python tui.py test                   Run all tests")
            print(f"  python tui.py config                 Configure project path")
            print(f"  python tui.py demo                   Run a demo cycle")
            print(f"  python tui.py clean                  Clean test artifacts")
            print(Colors.HEADER + "="*70 + Colors.ENDC + "\n")
            return 0

    # Default to Interactive Mode
    return app.run_interactive()

if __name__ == "__main__":
    sys.exit(main())
