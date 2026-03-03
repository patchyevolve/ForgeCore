from locale import normalize
import os
import json

class TierViolationError(Exception):
    pass

class  ToolDispatcher:
    def __init__(self, target_project_path, policy_path="policy/tier_policy.json"):
        self.target_project_path = os.path.abspath(target_project_path)

        with open(policy_path, "r") as f:
            self.tier_policy = json.load(f)

    def _resolve_path(self, relative_path):
        if not isinstance(relative_path, str) or not relative_path.strip():
            raise PermissionError("Invalid path")

        full_path = os.path.abspath(
            os.path.join(self.target_project_path, relative_path)
        )

        project_root = os.path.abspath(self.target_project_path)

        # Proper boundary check
        if os.path.commonpath([project_root, full_path]) != project_root:
            raise PermissionError("Path traversal detected")

        return full_path

    def _normalize(self, path):
        return path.replace("\\", "/").lower()

    def _get_tier(self, relative_path):
        normalized = self._normalize(relative_path)

        for tier_name, prefixes in self.tier_policy.items():
            for prefix in prefixes:
                if normalized.startswith(prefix.lower()):
                    return tier_name

        return "tier0"

    def read_file(self, relative_path):
        full_path = self._resolve_path(relative_path)

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def overwrite_file(self, relative_path, new_content, allow_tier1=False):
        tier = self._get_tier(relative_path)

        if tier == "tier2":
            raise TierViolationError(f"Modification denied: {relative_path} is Tier 2")

        if tier == "tier1" and not allow_tier1:
            raise TierViolationError(
                f"Tier 1 modificationn requiers confirmation: {relative_path}"    
            )

        full_path = self._resolve_path(relative_path)

        with open (full_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return {
            "status": "success",
            "file": relative_path,
            "tier": tier
        }
    
    def create_file(self, relative_path, content, allow_tier1=False):
        """
        Create a new file with content.
        
        Args:
            relative_path: Path relative to project root
            content: File content
            allow_tier1: Allow tier1 file creation
            
        Returns:
            Status dict
            
        Raises:
            TierViolationError: If tier policy violated
            FileExistsError: If file already exists
        """
        # Check if file already exists
        full_path = self._resolve_path(relative_path)
        if os.path.exists(full_path):
            raise FileExistsError(f"File already exists: {relative_path}")
        
        # Check tier policy
        tier = self._get_tier(relative_path)
        
        if tier == "tier2":
            raise TierViolationError(f"Creation denied: {relative_path} is Tier 2")
        
        if tier == "tier1" and not allow_tier1:
            raise TierViolationError(
                f"Tier 1 creation requires confirmation: {relative_path}"
            )
        
        # Create parent directories if needed
        parent_dir = os.path.dirname(full_path)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)
        
        # Write file
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return {
            "status": "success",
            "file": relative_path,
            "tier": tier,
            "created": True
        }


def create_file(self, relative_path, content, allow_tier1=False):
    """
    Create a new file with content.

    Args:
        relative_path: Path relative to project root
        content: File content
        allow_tier1: Allow tier1 file creation

    Returns:
        Status dict

    Raises:
        TierViolationError: If tier policy violated
        FileExistsError: If file already exists
    """
    # Check if file already exists
    full_path = self._resolve_path(relative_path)
    if os.path.exists(full_path):
        raise FileExistsError(f"File already exists: {relative_path}")

    # Check tier policy
    tier = self._get_tier(relative_path)

    if tier == "tier2":
        raise TierViolationError(f"Creation denied: {relative_path} is Tier 2")

    if tier == "tier1" and not allow_tier1:
        raise TierViolationError(
            f"Tier 1 creation requires confirmation: {relative_path}"
        )

    # Create parent directories if needed
    parent_dir = os.path.dirname(full_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    # Write file
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return {
        "status": "success",
        "file": relative_path,
        "tier": tier,
        "created": True
    }

