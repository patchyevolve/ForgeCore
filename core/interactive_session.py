"""
Interactive Session - Semi-Autonomous User Approval System

Manages user interaction for semi-autonomous code generation:
1. AI generates plan
2. User approves/rejects plan
3. For each step:
   - AI generates patch
   - User approves/rejects/requests changes
   - If rejected: AI reworks and asks again
4. Apply approved patches
"""

from typing import Dict, Any, List, Optional, Tuple
from core.patch_intent import PatchIntent, Operation
from core.planner import Planner
from core.critic import Critic


class InteractiveSession:
    """
    Manages interactive semi-autonomous code generation.
    
    Flow:
    1. User gives task
    2. AI creates plan → User approves
    3. For each step:
       - AI generates code → User approves
       - If rejected: AI reworks
    4. Execute approved changes
    """
    
    def __init__(self, planner: Planner, critic: Critic, logger):
        self.planner = planner
        self.critic = critic
        self.logger = logger
    
    def run_task(self, task_description: str, controller) -> Dict[str, Any]:
        """
        Run interactive task execution.
        
        Args:
            task_description: High-level task from user
            controller: Controller instance
            
        Returns:
            Execution results
        """
        print("\n" + "="*70)
        print("SEMI-AUTONOMOUS MODE")
        print("="*70)
        print(f"\nTask: {task_description}")
        
        # Step 1: Generate initial intent
        print("\n" + "="*70)
        print("STEP 1: AI PLANNING")
        print("="*70)
        
        intent = self._generate_intent_with_approval(
            task_description,
            iteration=1
        )
        
        if not intent:
            return {"status": "cancelled", "reason": "User cancelled planning"}
        
        # Step 2: Execute with approval
        print("\n" + "="*70)
        print("STEP 2: EXECUTION")
        print("="*70)
        
        result = controller.execute_patch_intent(intent)
        
        print(f"\n✅ Result: {result}")
        
        return {
            "status": "completed",
            "result": result,
            "intent": intent.to_dict()
        }
    
    def _generate_intent_with_approval(
        self,
        task: str,
        iteration: int = 1,
        error_context: Optional[List] = None,
        previous_intent: Optional[PatchIntent] = None
    ) -> Optional[PatchIntent]:
        """
        Generate intent and get user approval with progress indicators.
        
        Returns:
            Approved PatchIntent or None if rejected
        """
        max_rework_attempts = 3
        
        for attempt in range(max_rework_attempts):
            print(f"\n🤖 AI is planning... (attempt {attempt + 1}/{max_rework_attempts})")
            
            # Show progress indicator
            import sys
            import time
            import threading
            
            # Progress spinner
            spinner_active = True
            def show_spinner():
                spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
                idx = 0
                while spinner_active:
                    sys.stdout.write(f'\r  {spinner[idx % len(spinner)]} Generating plan...')
                    sys.stdout.flush()
                    time.sleep(0.1)
                    idx += 1
                sys.stdout.write('\r  ✓ Plan generated!     \n')
                sys.stdout.flush()
            
            spinner_thread = threading.Thread(target=show_spinner, daemon=True)
            spinner_thread.start()
            
            try:
                # Generate intent
                intent = self.planner.generate_intent(
                    task,
                    error_context,
                    iteration,
                    previous_intent
                )
                
                # Stop spinner
                spinner_active = False
                spinner_thread.join(timeout=0.5)
                
                # Show intent to user
                approved, feedback = self._show_intent_for_approval(intent, task)
                
                if approved:
                    return intent
                
                # User rejected - add feedback to error context
                if not error_context:
                    error_context = []
                error_context.append({
                    "type": "USER_REJECTION",
                    "feedback": feedback,
                    "attempt": attempt + 1
                })
                
                print(f"\n🔄 AI will rework based on your feedback...")
                
            except Exception as e:
                # Stop spinner on error
                spinner_active = False
                spinner_thread.join(timeout=0.5)
                
                print(f"\n❌ Planning failed: {e}")
                retry = input("\nRetry? (y/n): ").strip().lower()
                if retry != 'y':
                    return None
        
        print(f"\n❌ Max rework attempts ({max_rework_attempts}) reached")
        return None
    
    def _show_intent_for_approval(
        self,
        intent: PatchIntent,
        task: str
    ) -> Tuple[bool, str]:
        """
        Show intent to user and get approval with diff preview.
        
        Returns:
            (approved: bool, feedback: str)
        """
        print("\n" + "-"*70)
        print("📋 AI GENERATED PLAN")
        print("-"*70)
        
        print(f"\nOperation: {intent.operation.value}")
        print(f"Target File: {intent.target_file}")
        print(f"\nPayload:")
        for key, value in intent.payload.items():
            if key == "content" and len(str(value)) > 200:
                print(f"  {key}: {str(value)[:200]}... ({len(str(value))} chars)")
            else:
                print(f"  {key}: {value}")
        
        # Show preview of what will be done
        print(f"\n📝 What this will do:")
        self._explain_intent(intent)
        
        # Show diff preview if possible
        self._show_diff_preview(intent)
        
        print("\n" + "-"*70)
        print("APPROVAL REQUIRED")
        print("-"*70)
        
        while True:
            choice = input("\nApprove this plan? (y/n/m for modify): ").strip().lower()
            
            if choice == 'y':
                return True, ""
            
            elif choice == 'n':
                feedback = input("\nWhy reject? (AI will use this to improve): ").strip()
                return False, feedback if feedback else "User rejected without reason"
            
            elif choice == 'm':
                print("\n📝 Modification options:")
                print("1. Change target file")
                print("2. Modify payload")
                print("3. Cancel")
                
                mod_choice = input("\nChoice (1-3): ").strip()
                
                if mod_choice == '1':
                    new_file = input(f"New target file (current: {intent.target_file}): ").strip()
                    if new_file:
                        # Create modified intent
                        # Note: PatchIntent is frozen, so we need to create new one
                        print("⚠️  File modification not yet implemented")
                
                elif mod_choice == '2':
                    print("⚠️  Payload modification not yet implemented")
                
                # For now, just continue to approval
                continue
            
            else:
                print("Invalid choice. Please enter y, n, or m")
    
    def _show_diff_preview(self, intent: PatchIntent):
        """
        Show diff preview of what will change.
        
        Args:
            intent: Patch intent to preview
        """
        import os
        import difflib
        
        try:
            # Get current file content
            file_path = intent.target_file
            
            # Check if file exists
            if not os.path.exists(file_path):
                if intent.operation == Operation.CREATE_FILE:
                    print(f"\n📄 DIFF PREVIEW (new file):")
                    content = intent.payload.get("content", "")
                    lines = content.splitlines()[:20]  # Show first 20 lines
                    for i, line in enumerate(lines, 1):
                        print(f"  + {i:3d} | {line}")
                    if len(content.splitlines()) > 20:
                        print(f"  ... and {len(content.splitlines()) - 20} more lines")
                return
            
            # Read current content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                old_content = f.read()
            
            # Generate new content (simplified - doesn't actually apply)
            new_content = self._preview_content(old_content, intent)
            
            if new_content is None:
                return  # Can't preview this operation
            
            # Generate diff
            old_lines = old_content.splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            
            diff = list(difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=f"{file_path} (before)",
                tofile=f"{file_path} (after)",
                lineterm=''
            ))
            
            if diff:
                print(f"\n📄 DIFF PREVIEW:")
                # Show first 30 lines of diff
                for line in diff[:30]:
                    if line.startswith('+') and not line.startswith('+++'):
                        print(f"  \033[32m{line}\033[0m")  # Green
                    elif line.startswith('-') and not line.startswith('---'):
                        print(f"  \033[31m{line}\033[0m")  # Red
                    elif line.startswith('@@'):
                        print(f"  \033[36m{line}\033[0m")  # Cyan
                    else:
                        print(f"  {line}")
                
                if len(diff) > 30:
                    print(f"  ... and {len(diff) - 30} more diff lines")
            else:
                print(f"\n📄 No changes detected in preview")
        
        except Exception as e:
            print(f"\n⚠️  Could not generate diff preview: {e}")
    
    def _preview_content(self, old_content: str, intent: PatchIntent) -> Optional[str]:
        """
        Preview what the new content will look like (simplified).
        
        Returns:
            New content or None if can't preview
        """
        op = intent.operation
        
        if op == Operation.CREATE_FILE:
            return intent.payload.get("content", "")
        
        elif op == Operation.APPEND_RAW:
            content = intent.payload.get("content", "")
            return old_content + "\n" + content + "\n"
        
        elif op == Operation.ADD_FUNCTION_STUB:
            func_name = intent.payload.get("name", "unknown")
            return old_content + f"\nvoid {func_name}()\n{{\n}}\n"
        
        elif op == Operation.ADD_INCLUDE:
            header = intent.payload.get("header", "")
            is_system = intent.payload.get("system", False)
            if is_system:
                include_line = f"#include <{header}>"
            else:
                include_line = f'#include "{header}"'
            
            # Insert at top (simplified)
            return include_line + "\n" + old_content
        
        elif op == Operation.REPLACE_CONTENT:
            old = intent.payload.get("old_content", "")
            new = intent.payload.get("new_content", "")
            return old_content.replace(old, new, 1)
        
        # For complex operations, return None
        return None
    
    def _explain_intent(self, intent: PatchIntent):
        """Explain what the intent will do in plain English."""
        op = intent.operation
        file = intent.target_file
        
        if op == Operation.CREATE_FILE:
            lines = len(intent.payload.get("content", "").splitlines())
            print(f"  → Create new file '{file}' with {lines} lines of code")
        
        elif op == Operation.ADD_FUNCTION_STUB:
            func_name = intent.payload.get("name", "unknown")
            print(f"  → Add function stub '{func_name}()' to '{file}'")
        
        elif op == Operation.APPEND_RAW:
            content = intent.payload.get("content", "")
            lines = len(content.splitlines())
            print(f"  → Append {lines} lines to end of '{file}'")
        
        elif op == Operation.REPLACE_FUNCTION:
            func_name = intent.payload.get("name", "unknown")
            print(f"  → Replace function '{func_name}()' body in '{file}'")
        
        elif op == Operation.INSERT_BEFORE:
            anchor = intent.payload.get("anchor", "unknown")
            print(f"  → Insert code before '{anchor}' in '{file}'")
        
        elif op == Operation.INSERT_AFTER:
            anchor = intent.payload.get("anchor", "unknown")
            print(f"  → Insert code after '{anchor}' in '{file}'")
        
        elif op == Operation.ADD_INCLUDE:
            header = intent.payload.get("header", "unknown")
            is_system = intent.payload.get("system", False)
            bracket = "<>" if is_system else '""'
            print(f"  → Add #include {bracket[0]}{header}{bracket[1]} to '{file}'")
        
        elif op == Operation.REPLACE_CONTENT:
            old = intent.payload.get("old_content", "")[:50]
            new = intent.payload.get("new_content", "")[:50]
            print(f"  → Replace '{old}...' with '{new}...' in '{file}'")
        
        else:
            print(f"  → Perform {op.value} on '{file}'")
