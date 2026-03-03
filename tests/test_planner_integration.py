"""Test planner integration with controller"""

from core.controller import Controller
from core.logger import Logger
import json
import time

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

def test_planner_simple_task():
    """Test planner with simple task"""
    print("\n" + "="*60)
    print("TEST 1: Planner Simple Task")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Use unique name to avoid duplicates
    unique_name = f"planner_test_{int(time.time())}"
    task = f"Add function {unique_name} in main.cpp"
    
    print(f"Task: {task}")
    result = controller.execute_task(task)
    print(f"\nResult: {result}")
    
    # Check log for planner events
    with open(logger.log_path, 'r') as f:
        logs = json.load(f)
    
    planner_events = [e for e in logs if 'PLANNER' in e['event']]
    
    print(f"\n{'='*60}")
    if planner_events:
        print("PASS PLANNER EVENTS FOUND")
        for event in planner_events:
            print(f"  {event['event']}: {event.get('details', {})}")
    else:
        print("FAIL NO PLANNER EVENTS")
    
    if "completed successfully" in result.lower():
        print("\nPASS PASS - Task completed via planner")
        return True
    else:
        print(f"\nFAIL FAIL - Task failed: {result}")
        return False

def test_planner_refinement():
    """Test planner refinement across iterations"""
    print("\n" + "="*60)
    print("TEST 2: Planner Refinement (Simulated)")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    
    # Use failing build to trigger refinement
    class MockFailingBuild:
        def __init__(self):
            self.call_count = 0
        
        def run_build(self):
            self.call_count += 1
            if self.call_count == 1:
                # First iteration fails
                return {
                    "exit_code": 1,
                    "stdout": "",
                    "stderr": "main.cpp(10): error: undefined symbol 'missing_func'"
                }
            else:
                # Second iteration succeeds
                return {"exit_code": 0, "stdout": "", "stderr": ""}
    
    controller.builder = MockFailingBuild()
    
    unique_name = f"refine_test_{int(time.time())}"
    task = f"Add function {unique_name} in main.cpp"
    
    print(f"Task: {task}")
    print("Build will fail once, then succeed...")
    
    result = controller.execute_task(task)
    print(f"\nResult: {result}")
    print(f"Iterations: {controller.current_iteration}")
    
    # Check log for refinement
    with open(logger.log_path, 'r') as f:
        logs = json.load(f)
    
    refining_events = [e for e in logs if 'REFINING' in e['event']]
    
    print(f"\n{'='*60}")
    if refining_events:
        print("PASS REFINEMENT DETECTED")
        for event in refining_events:
            print(f"  {event['event']}: {event.get('details', {})}")
    
    if controller.current_iteration > 1:
        print(f"\nPASS PASS - Planner refined across {controller.current_iteration} iterations")
        return True
    else:
        print("\nWARN  Only 1 iteration (expected multi-iteration)")
        return False

def test_planner_append_task():
    """Test planner with append operation"""
    print("\n" + "="*60)
    print("TEST 3: Planner Append Task")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    task = "Append to main.cpp: // Planner integration test comment"
    
    print(f"Task: {task}")
    result = controller.execute_task(task)
    print(f"\nResult: {result}")
    
    if "completed successfully" in result.lower():
        print("\nPASS PASS - Append task completed")
        return True
    else:
        print(f"\nFAIL FAIL - Task failed: {result}")
        return False

def test_backward_compatibility():
    """Test that execute_patch_intent still works"""
    print("\n" + "="*60)
    print("TEST 4: Backward Compatibility")
    print("="*60)
    
    from core.patch_intent import PatchIntent, Operation
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    unique_name = f"compat_test_{int(time.time())}"
    
    intent = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": unique_name}
    )
    
    print(f"Using execute_patch_intent (old API)")
    result = controller.execute_patch_intent(intent)
    print(f"\nResult: {result}")
    
    if "succced" in result:
        print("\nPASS PASS - Old API still works")
        return True
    else:
        print(f"\nFAIL FAIL - Old API broken: {result}")
        return False

def main():
    print("\n" + "#"*60)
    print("# PLANNER INTEGRATION TEST SUITE")
    print("#"*60)
    
    results = {}
    
    try:
        results['Simple Task'] = test_planner_simple_task()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Simple Task'] = False
    
    try:
        results['Refinement'] = test_planner_refinement()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Refinement'] = False
    
    try:
        results['Append Task'] = test_planner_append_task()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Append Task'] = False
    
    try:
        results['Backward Compat'] = test_backward_compatibility()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Backward Compat'] = False
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, success in results.items():
        status = "PASS PASS" if success else "FAIL FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if all(results.values()):
        print("\nOK All planner integration tests passed!")
        print("   • Planner generates intents from tasks")
        print("   • Planner refines across iterations")
        print("   • Multiple operation types supported")
        print("   • Backward compatibility maintained")
    
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


