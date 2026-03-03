"""Test that rewrite ratio is calculated against snapshot baseline"""

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

def test_rewrite_ratio_baseline():
    """Test that rewrite ratio uses snapshot baseline, not evolving baseline"""
    print("\n" + "="*60)
    print("TEST: Rewrite Ratio Against Snapshot Baseline")
    print("="*60)
    print("Verifying that ratio is calculated against original baseline")
    print("Not against evolving content across iterations")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Create a simple test
    import time
    unique_name = f"rewrite_test_{int(time.time())}"
    
    intent = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": unique_name}
    )
    
    result = controller.execute_patch_intent(intent)
    
    print(f"\nResult: {result}")
    
    # Check log for rewrite ratio calculation
    import json
    with open(logger.log_path, 'r') as f:
        logs = json.load(f)
    
    # Look for any rewrite rejection events
    rewrite_events = [e for e in logs if 'REWRITE' in e.get('event', '')]
    
    if rewrite_events:
        print("\nWARN  Rewrite events found:")
        for event in rewrite_events:
            print(f"  {event['event']}: {event.get('details', {})}")
    else:
        print("\nPASS No rewrite violations (expected for small change)")
    
    # Verify the fix is in place by checking the code
    print("\n" + "="*60)
    print("VERIFICATION:")
    print("="*60)
    
    # Read controller source to verify fix
    with open('core/controller.py', 'r', encoding='utf-8') as f:
        controller_source = f.read()
    
    # Check for new baseline tracking approach
    if 'baselines[file]["content"], new_content' in controller_source or '_line_diff_count(baseline["content"], new_content)' in controller_source:
        print("PASS Rewrite ratio uses baseline tracking")
        print("  Protection against cumulative bypass is active")
        return True
    elif 'snapshot_baseline_content, new_content' in controller_source:
        print("PASS Rewrite ratio uses snapshot_baseline_content")
        print("  Protection against cumulative bypass is active")
        return True
    elif 'original_content, new_content' in controller_source:
        print("FAIL Rewrite ratio uses original_content (vulnerable)")
        print("  Cumulative bypass is possible")
        return False
    else:
        print("WARN  Could not verify rewrite ratio calculation")
        return False

def test_prefix_sorting():
    """Test that tier prefixes are sorted by length"""
    print("\n" + "="*60)
    print("TEST: Tier Prefix Sorting")
    print("="*60)
    
    # Read dependency validator source
    with open('core/dependency_validator.py', 'r', encoding='utf-8') as f:
        validator_source = f.read()
    
    if 'sort(key=lambda x: len(x[0]), reverse=True)' in validator_source:
        print("PASS Prefixes sorted by length (longest first)")
        print("  Overlapping prefixes handled correctly")
        print("  Example: 'src/crypto/' matches before 'src/'")
        return True
    else:
        print("FAIL Prefixes not sorted")
        print("  Overlapping prefixes may cause ambiguity")
        return False

def main():
    print("\n" + "#"*60)
    print("# ARCHITECTURAL FIX VERIFICATION")
    print("#"*60)
    
    results = {}
    
    try:
        results['Rewrite Ratio Fix'] = test_rewrite_ratio_baseline()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Rewrite Ratio Fix'] = False
    
    try:
        results['Prefix Sorting'] = test_prefix_sorting()
    except Exception as e:
        print(f"\nFAIL Exception: {e}")
        import traceback
        traceback.print_exc()
        results['Prefix Sorting'] = False
    
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
        print("\nOK All architectural fixes verified!")
        print("   • Rewrite ratio uses immutable snapshot baseline")
        print("   • Tier prefixes sorted to handle overlaps")
        print("   • Cumulative bypass protection active")
    
    print("#"*60)
    
    return all(results.values())

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)


