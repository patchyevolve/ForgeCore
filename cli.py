"""
ForgeCore CLI - Semi-Autonomous C++ Code Generation

Usage:
    python cli.py <command> [options]

Commands:
    task <description>     Execute task with AI planning and user approval
    demo                   Run full cycle demonstration
    test                   Run all test suites
    clean                  Clean up test artifacts

Options:
    --project <path>       Specify project path (default: from config or hardcoded)

Examples:
    python cli.py task "Add function hello_world in main.cpp"
    python cli.py task "Create new file utils.cpp" --project D:\\myproject
    python cli.py demo
    python cli.py test

Mode: SEMI-AUTONOMOUS
- AI generates plan → You approve
- AI generates code → You approve
- If rejected → AI reworks
"""

import sys
import os
import json
from core.controller import Controller
from core.logger import Logger
from core.interactive_session import InteractiveSession
from core.patch_intent import PatchIntent, Operation

# Default project path - can be overridden with --project flag or config file
DEFAULT_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"
CONFIG_FILE = "forgecore_config.json"

def load_config():
    """Load configuration from file if exists."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load config file: {e}")
    return {}

def save_config(config):
    """Save configuration to file."""
    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, indent=2, fp=f)
        print(f"✓ Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"Warning: Could not save config file: {e}")

def get_project_path(args):
    """Get project path from args, config, or default."""
    # Check command line args
    if '--project' in args:
        idx = args.index('--project')
        if idx + 1 < len(args):
            return args[idx + 1]
    
    # Check config file
    config = load_config()
    if 'project_path' in config:
        return config['project_path']
    
    # Use default
    return DEFAULT_PROJECT_PATH

class RealBuild:
    """Real build system integration"""
    def __init__(self, path):
        self.path = path
    
    def run_build(self):
        """Run actual build - placeholder for real implementation"""
        # TODO: Integrate with actual build system (MSBuild, CMake, etc.)
        return {"exit_code": 0, "stdout": "Build successful", "stderr": ""}

def cmd_task(task_description, project_path):
    """Execute a task with interactive approval"""
    print("\n" + "="*70)
    print("FORGECORE - SEMI-AUTONOMOUS CODE GENERATION")
    print("="*70)
    print(f"\nTask: {task_description}")
    print(f"Project: {project_path}")
    
    # Show key invariants / safety rails
    print("\nExecution constraints:")
    print("  - Semi-autonomous mode with user approval")
    
    # Initialize components
    logger = Logger()
    controller = Controller(project_path, logger)
    
    # Show detected language
    lang_info = controller.validator.language_info
    print(f"\n📊 Project Analysis:")
    print(f"  Language: {lang_info['primary_language'] or 'Unknown'}")
    print(f"  Build System: {lang_info['build_system'] or 'None detected'}")
    if lang_info['is_multi_language']:
        print(f"  Multi-language: {', '.join(lang_info['all_languages'])}")
    
    # Show core safety limits
    try:
        print("\nSafety limits:")
        print(f"  Max iterations: {controller.max_iterations}")
        print(f"  Max files per transaction: {controller.max_files_per_patch}")
        print(f"  Max lines per file change: {controller.max_lines_per_file}")
        print(f"  Rewrite ratio threshold: {controller.rewrite_ratio_threshold:.0%}")
    except Exception:
        pass
    
    # Create interactive session
    session = InteractiveSession(
        planner=controller.planner,
        critic=controller.critic,
        logger=logger
    )
    
    # Capture file set before run
    try:
        files_before = set(os.listdir(project_path))
    except Exception:
        files_before = None
    
    # Run interactive task
    result = session.run_task(task_description, controller)
    
    print("\n" + "="*70)
    print("SESSION COMPLETE")
    print("="*70)
    print(f"\nStatus: {result['status']}")
    print(f"Log file: {logger.log_path}")
    
    # Show what was created/modified
    try:
        print("\nArtifacts:")
        
        # New files on disk
        new_files = []
        if files_before is not None:
            files_after = set(os.listdir(project_path))
            new_files = sorted(f for f in (files_after - files_before))
        
        if new_files:
            print("  Created files:")
            for f in new_files:
                full = os.path.join(project_path, f)
                if os.path.isfile(full):
                    size = os.path.getsize(full)
                    print(f"    [+] {f} ({size} bytes)")
        else:
            print("  Created files: none detected")
        
        # Modified files as tracked by controller
        modified = sorted(controller.modified_files) if getattr(controller, "modified_files", None) else []
        if modified:
            print("  Modified files (relative to project root):")
            for f in modified:
                print(f"    [~] {f}")
        else:
            print("  Modified files: none recorded")
    except Exception:
        pass
    
    return 0 if result['status'] == 'completed' else 1

def cmd_demo():
    """Run full cycle demonstration"""
    import demo_full_cycle
    return 0 if demo_full_cycle.main() else 1

def cmd_test():
    """Run all test suites"""
    import subprocess
    test_runner = os.path.join("tests", "run_all_tests.py")
    result = subprocess.run([sys.executable, test_runner])
    return result.returncode

def cmd_clean():
    """Clean up test artifacts"""
    import cleanup_test_artifacts
    try:
        cleanup_test_artifacts.clean_main_cpp()
        print("\n✓ Cleanup complete")
        return 0
    except Exception as e:
        print(f"\n✗ Cleanup failed: {e}")
        return 1

def cmd_config():
    """Configure ForgeCore settings"""
    print("\n" + "="*70)
    print("FORGECORE CONFIGURATION")
    print("="*70)
    
    config = load_config()
    
    print("\nCurrent settings:")
    print(f"  Project path: {config.get('project_path', DEFAULT_PROJECT_PATH)}")
    
    print("\nWhat would you like to configure?")
    print("1. Set project path")
    print("2. Reset to defaults")
    print("3. Cancel")
    
    choice = input("\nChoice (1-3): ").strip()
    
    if choice == '1':
        new_path = input("\nEnter project path: ").strip()
        if new_path and os.path.exists(new_path):
            config['project_path'] = new_path
            save_config(config)
            print(f"✓ Project path set to: {new_path}")
        elif new_path:
            print(f"✗ Path does not exist: {new_path}")
        else:
            print("✗ No path provided")
    
    elif choice == '2':
        config = {}
        save_config(config)
        print("✓ Configuration reset to defaults")
    
    return 0

def print_usage():
    """Print usage information"""
    print(__doc__)

def main():
    if len(sys.argv) < 2:
        print_usage()
        return 1
    
    command = sys.argv[1].lower()
    
    # Get project path from args/config
    project_path = get_project_path(sys.argv)
    
    if command == "task":
        if len(sys.argv) < 3:
            print("Error: Task description required")
            print("Usage: python cli.py task \"<description>\" [--project <path>]")
            return 1
        
        # Extract task description (everything except --project and its value)
        task_parts = []
        skip_next = False
        for i, arg in enumerate(sys.argv[2:], 2):
            if skip_next:
                skip_next = False
                continue
            if arg == '--project':
                skip_next = True
                continue
            task_parts.append(arg)
        
        task_description = " ".join(task_parts)
        return cmd_task(task_description, project_path)
    
    elif command == "demo":
        return cmd_demo()
    
    elif command == "test":
        return cmd_test()
    
    elif command == "clean":
        return cmd_clean()
    
    elif command == "config":
        return cmd_config()
    
    elif command in ["help", "-h", "--help"]:
        print_usage()
        return 0
    
    else:
        print(f"Error: Unknown command '{command}'")
        print_usage()
        return 1

if __name__ == "__main__":
    sys.exit(main())
