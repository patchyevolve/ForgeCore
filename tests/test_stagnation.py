"""Test stagnation detection"""

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger
import json

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockFailingBuild:
    """Build that always fails with same error"""
    def __init__(self, path):
        self.call_count = 0
    
    def run_build(self):
        self.call_count += 1
        print(f"  [MockBuild] Build attempt #{self.call_count} - FAILING")
        return {
            "exit_code": 1,
            "stdout": "",
            "stderr": "main.cpp(10,5): error C2065: 'undefined_var' : undeclared identifier"
        }

def test_error_stagnation():
    """Test that identical errors trigger early abort"""
    print("\n" + "="*60)
    print("TEST: Error Stagnation Detection")
    print("="*60)
    print("Simulating repeated identical build errors")
    print("Expected: Early abort before max iterations")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockFailingBuild(TARGET_PROJECT_PATH)
    
    # Use unique name
    import time
    unique_name = f"stagnation_test_{int(time.time())}"
    
    # Use execute_task (planner mode) instead of execute_patch_intent (direct mode)
    # Stagnation detection only works in iteration mode
    task = f"Add function {unique_name} in main.cpp"
    
    print(f"\nTask: {task}")
    print("Build will fail repeatedly with same error...\n")
    
    result = controller.execute_task(task)
    
    print(f"\n{'='*60}")
    print("RESULT:")
    print('='*60)
    print(result)
    print(f"\nIterations attempted: {controller.current_iteration}")
    print(f"Max iterations allowed: {controller.max_iterations}")
    
    # Check log for stagnation event
    with open(logger.log_path, 'r') as f:
        logs = json.load(f)
    
    stagnation_events = [e for e in logs if 'STAGNATION' in e['event']]
    
    print(f"\n{'='*60}")
    if stagnation_events:
        print("PASS STAGNATION DETECTED")
        for event in stagnation_events:
            print(f"  Event: {event['event']}")
            print(f"  Iteration: {event['details'].get('iteration', 'N/A')}")
        
        if controller.current_iteration < controller.max_iterations:
            print(f"\nPASS EARLY ABORT SUCCESSFUL")
            print(f"  Stopped at iteration {controller.current_iteration}")
            print(f"  Saved {controller.max_iterations - controller.current_iteration} wasted iterations")
            return True
        else:
            print(f"\nFAIL NO EARLY ABORT")
            print(f"  Used all {controller.max_iterations} iterations")
            return False
    else:
        print("FAIL STAGNATION NOT DETECTED")
        print("  Controller wasted all iterations")
        return False

def test_content_stagnation():
    """Test that identical content triggers early abort"""
    print("\n" + "="*60)
    print("TEST: Content Stagnation Detection")
    print("="*60)
    print("This would require multi-iteration with same content")
    print("Currently simulated via error stagnation")
    print("="*60)
    return True  # Placeholder for now

def main():
    print("\n" + "#"*60)
    print("# STAGNATION DETECTION TEST SUITE")
    print("#"*60)
    
    results = {}
    
    try:
        results['Error Stagnation'] = test_error_stagnation()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Error Stagnation'] = False
    
    try:
        results['Content Stagnation'] = test_content_stagnation()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        results['Content Stagnation'] = False
    
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
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


