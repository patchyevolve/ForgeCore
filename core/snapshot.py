from operator import truediv
import os
import shutil
import subprocess
from datetime import date, datetime

class SnapshotManager:
    def __init__(self, target_project_path: str, snapshot_root: str = "snapshots"):
        self.target_project_path: str = os.path.abspath(target_project_path)
        self.snapshot_root: str = snapshot_root
        os.makedirs(self.snapshot_root, exist_ok=True)

        self.snapshot_id: str | None = None
        self.snapshot_path: str | None = None

    def _is_git_repo(self):
        return os.path.isdir(os.path.join(self.target_project_path, ".git"))

    def create_snapshot(self, target_files=None):
        """Create a snapshot (full or selective)"""
        self.snapshot_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.snapshot_path = os.path.join(self.snapshot_root, self.snapshot_id)
        os.makedirs(self.snapshot_path, exist_ok=True)
        
        if target_files:
            self._create_selective_snapshot(target_files)
        elif self._is_git_repo():
            self._create_git_snapshot()
        else:
            self._create_filesystem_snapshot()

    def rollback(self):
        """Rollback to the current snapshot"""
        if self._is_git_repo():
            # snapshot_path should have been set by create_snapshot
            assert self.snapshot_path is not None, "No snapshot path defined"
            if not os.path.exists(self.snapshot_path):
                self._rollback_git()
                return
        # otherwise fall back to filesystem rollback
        self._rollback_filesystem()

    def _create_git_snapshot(self):
        """Use git stash for snapshots (only if no selective files)"""
        subprocess.run(
            ["git", "stash", "push", "-u"],
            cwd=self.target_project_path,
            check=True
        )

    def _create_filesystem_snapshot(self):
        """Full directory copy snapshot"""
        assert self.snapshot_path is not None, "snapshot_path not set"
        shutil.copytree(
            self.target_project_path,
            self.snapshot_path,
            dirs_exist_ok=True
        )

    def _create_selective_snapshot(self, target_files):
        """Copy only specific files to snapshot"""
        assert self.snapshot_path is not None, "snapshot_path must be set before selective copy"
        for rel_path in target_files:
            src = os.path.join(self.target_project_path, rel_path)
            dst = os.path.join(self.snapshot_path, rel_path)
            
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

    def _rollback_git(self):
        """Rollback using git stash"""
        subprocess.run(
            ["git", "stash", "pop"],
            cwd=self.target_project_path,
            check=True
        )

    def _rollback_filesystem(self):
        """Restore files from the snapshot directory"""
        if not self.snapshot_path or not os.path.exists(self.snapshot_path):
            raise RuntimeError("No valid snapshot to rollback to.")

        # Selective restore: only overwrite files present in the snapshot
        # This works for both full and selective snapshots
        for root, dirs, files in os.walk(self.snapshot_path):
            # snapshot_path should exist per previous check
            assert self.snapshot_path is not None
            rel_root = os.path.relpath(root, self.snapshot_path)
            if rel_root == ".":
                rel_root = ""
            
            for file in files:
                src = os.path.join(root, file)
                dst = os.path.join(self.target_project_path, rel_root, file)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

    def cleanup_snapshot(self):
        """Clean up snapshot with retry logic for Windows file locking"""
        if self.snapshot_path and os.path.exists(self.snapshot_path):
            import time
            max_retries = 3
            retry_delay = 0.5  # seconds
            
            for attempt in range(max_retries):
                try:
                    # Force garbage collection to release file handles
                    import gc
                    gc.collect()
                    
                    # Try to remove the snapshot
                    shutil.rmtree(self.snapshot_path)
                    break  # Success
                    
                except PermissionError as e:
                    if attempt < max_retries - 1:
                        # Wait and retry
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff
                    else:
                        # Final attempt failed - try alternative cleanup
                        try:
                            self._force_cleanup_windows(self.snapshot_path)
                        except Exception as cleanup_error:
                            # Log but don't fail - snapshot cleanup is not critical
                            print(f"Warning: Could not cleanup snapshot {self.snapshot_path}: {cleanup_error}")
                            # Mark for later cleanup
                            self._mark_for_delayed_cleanup(self.snapshot_path)
                
                except Exception as e:
                    # Unexpected error
                    print(f"Warning: Unexpected error during cleanup: {e}")
                    break

        self.snapshot_id = None
        self.snapshot_path = None
    
    def _force_cleanup_windows(self, path):
        """Force cleanup on Windows using system commands"""
        import platform
        
        if platform.system() == 'Windows':
            # Use Windows rmdir command which is more aggressive
            import subprocess
            try:
                subprocess.run(
                    ['cmd', '/c', 'rmdir', '/s', '/q', path],
                    check=False,
                    capture_output=True,
                    timeout=10
                )
            except Exception:
                pass
    
    def _mark_for_delayed_cleanup(self, path):
        """Mark snapshot for delayed cleanup"""
        # Create a marker file for background cleanup
        marker_file = os.path.join(self.snapshot_root, '.cleanup_pending')
        try:
            with open(marker_file, 'a') as f:
                f.write(f"{path}\n")
        except Exception:
            pass