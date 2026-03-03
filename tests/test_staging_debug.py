"""Debug staging write layer"""

from core.controller import Controller
from core.patch_intent import PatchIntent, Operation
from core.logger import Logger
import json

TARGET_PROJECT_PATH = r"D:\codeWorks\graphicstics\graphicstuff"

class MockBuild:
    def __init__(self, path):
        pass
    def run_build(self):
        return {"exit_code": 0, "stdout": "", "stderr": ""}

def main():
    print("\n" + "="*60)
    print("STAGING DEBUG TEST")
    print("="*60)
    
    logger = Logger()
    controller = Controller(TARGET_PROJECT_PATH, logger)
    controller.builder = MockBuild(TARGET_PROJECT_PATH)
    
    # Use a unique function name
    import time
    unique_name = f"staging_debug_{int(time.time())}"
    
    intent = PatchIntent(
        operation=Operation.ADD_FUNCTION_STUB,
        target_file="main.cpp",
        payload={"name": unique_name}
    )
    
    print(f"\nAdding function: {unique_name}")
    result = controller.execute_patch_intent(intent)
    print(f"\nResult: {result}")
    
    # Check log
    print(f"\nChecking log: {logger.log_path}")
    with open(logger.log_path, 'r') as f:
        logs = json.load(f)
    
    print(f"\nTotal log entries: {len(logs)}")
    
    # Show all events
    print("\nAll events in log:")
    for i, entry in enumerate(logs):
        print(f"  {i+1}. {entry['state']:20} -> {entry['event']}")
    
    # Check for staging event
    staged_events = [e for e in logs if e['event'] == 'APPLYING_STAGED_WRITES']
    
    print(f"\n{'='*60}")
    if staged_events:
        print("PASS STAGING EVENT FOUND")
        for event in staged_events:
            print(f"  Timestamp: {event['timestamp']}")
            print(f"  State: {event['state']}")
            print(f"  Details: {event['details']}")
    else:
        print("FAIL STAGING EVENT NOT FOUND")
        print("\nPossible reasons:")
        print("  1. Execution aborted before staging phase")
        print("  2. Duplicate function detected")
        print("  3. Other validation failure")
    
    print("="*60)

if __name__ == "__main__":
    main()


