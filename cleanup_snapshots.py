"""Clean up pending snapshots that couldn't be deleted due to file locking"""

import os
import shutil
import time

SNAPSHOT_ROOT = "snapshots"

def cleanup_pending_snapshots():
    """Clean up snapshots marked for delayed cleanup"""
    marker_file = os.path.join(SNAPSHOT_ROOT, '.cleanup_pending')
    
    if not os.path.exists(marker_file):
        print("No pending snapshots to clean up")
        return 0
    
    # Read pending paths
    with open(marker_file, 'r') as f:
        pending_paths = [line.strip() for line in f if line.strip()]
    
    if not pending_paths:
        print("No pending snapshots to clean up")
        os.remove(marker_file)
        return 0
    
    print(f"Found {len(pending_paths)} pending snapshots to clean up")
    
    cleaned = 0
    still_pending = []
    
    for path in pending_paths:
        if not os.path.exists(path):
            print(f"  Already cleaned: {path}")
            continue
        
        try:
            # Force garbage collection
            import gc
            gc.collect()
            time.sleep(0.1)
            
            # Try to remove
            shutil.rmtree(path)
            print(f"  Cleaned: {path}")
            cleaned += 1
            
        except PermissionError:
            print(f"  Still locked: {path}")
            still_pending.append(path)
            
        except Exception as e:
            print(f"  Error cleaning {path}: {e}")
            still_pending.append(path)
    
    # Update marker file
    if still_pending:
        with open(marker_file, 'w') as f:
            for path in still_pending:
                f.write(f"{path}\n")
        print(f"\n{len(still_pending)} snapshots still pending")
    else:
        os.remove(marker_file)
        print("\nAll pending snapshots cleaned!")
    
    return cleaned

def cleanup_old_snapshots(days=7):
    """Clean up snapshots older than specified days"""
    if not os.path.exists(SNAPSHOT_ROOT):
        print("No snapshot directory found")
        return 0
    
    import time
    current_time = time.time()
    cutoff_time = current_time - (days * 24 * 60 * 60)
    
    cleaned = 0
    
    for item in os.listdir(SNAPSHOT_ROOT):
        if item.startswith('.'):
            continue
        
        item_path = os.path.join(SNAPSHOT_ROOT, item)
        
        if not os.path.isdir(item_path):
            continue
        
        # Check age
        try:
            mtime = os.path.getmtime(item_path)
            if mtime < cutoff_time:
                shutil.rmtree(item_path)
                print(f"  Cleaned old snapshot: {item}")
                cleaned += 1
        except Exception as e:
            print(f"  Error cleaning {item}: {e}")
    
    return cleaned

def main():
    print("="*60)
    print("SNAPSHOT CLEANUP UTILITY")
    print("="*60)
    
    # Clean pending snapshots
    print("\n1. Cleaning pending snapshots...")
    pending_cleaned = cleanup_pending_snapshots()
    
    # Clean old snapshots
    print("\n2. Cleaning old snapshots (>7 days)...")
    old_cleaned = cleanup_old_snapshots(days=7)
    
    print("\n" + "="*60)
    print(f"CLEANUP COMPLETE")
    print(f"  Pending snapshots cleaned: {pending_cleaned}")
    print(f"  Old snapshots cleaned: {old_cleaned}")
    print("="*60)

if __name__ == "__main__":
    main()
