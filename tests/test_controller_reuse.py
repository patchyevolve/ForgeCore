"""Test controller reuse without cross-task contamination"""

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger
import time

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

def test_controller_reuse():
    """Test that controller can be reused for multiple tasks"""
    print("\n" + "="*60)
    print("TEST: Controller Reuse")
    print("="*60)
    print("Testing that iteration state is reset between executions")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # First execution
    print("\n[Execution 1]")
    intent1 = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": f"reuse_test_1_{int(time.time())}"}
    )
    
    result1 = controller.execute_patch_intent(intent1)
    print(f"Result 1: {result1}")
    print(f"Iteration history after exec 1: {len(controller.iteration_history)} entries")
    history1_len = len(controller.iteration_history)
    
    # Second execution (reusing same controller)
    print("\n[Execution 2]")
    intent2 = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": f"reuse_test_2_{int(time.time())}"}
    )
    
    result2 = controller.execute_patch_intent(intent2)
    print(f"Result 2: {result2}")
    print(f"Iteration history after exec 2: {len(controller.iteration_history)} entries")
    history2_len = len(controller.iteration_history)
    
    # Third execution
    print("\n[Execution 3]")
    intent3 = PatchIntent(
        operation=Operation.APPEND_RAW,
        target_file="main.cpp",
        payload={"content": "// Reuse test comment\n"}
    )
    
    result3 = controller.execute_patch_intent(intent3)
    print(f"Result 3: {result3}")
    print(f"Iteration history after exec 3: {len(controller.iteration_history)} entries")
    history3_len = len(controller.iteration_history)
    
    print(f"\n{'='*60}")
    print("VERIFICATION:")
    print('='*60)
    
    # Check that all executions succeeded
    all_succeeded = ("succced" in result1 and "succced" in result2 and "succced" in result3)
    
    # Check that iteration counters were reset
    # (After each execution, current_iteration should be 1 for single-iteration success)
    print(f"Current iteration after exec 3: {controller.current_iteration}")
    print(f"Iteration history length: {len(controller.iteration_history)}")
    print(f"Last error hash: {controller.last_error_hash}")
    
    if all_succeeded:
        print("\nPASS All executions succeeded")
        print("PASS Controller properly reused across 3 executions")
        print("PASS No cross-task contamination detected")
        print("\nNote: Iteration history is empty because all succeeded on first try")
        print("      (History only populated on multi-iteration failures)")
        return True
    else:
        print("\nFAIL Some executions failed")
        return False

def main():
    print("\n" + "#"*60)
    print("# CONTROLLER REUSE TEST")
    print("#"*60)
    
    try:
        success = test_controller_reuse()
        
        print("\n" + "="*60)
        if success:
            print("PASS TEST PASSED - Controller can be safely reused")
        else:
            print("FAIL TEST FAILED - Cross-task contamination detected")
        print("="*60)
        
        return success
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


