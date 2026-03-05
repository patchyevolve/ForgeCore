"""
Dependency Graph Validator
Validates module integrity: circular dependencies, tier violations
"""

import os
from typing import Set, List, Tuple, Dict, Optional


class CircularDependencyError(Exception):
    """Raised when circular dependency is detected"""
    pass


class TierViolationError(Exception):
    """Raised when tier dependency rules are violated"""
    pass


class DependencyValidator:
    """Validates dependency graph for integrity issues"""
    
    def __init__(self, indexer, tier_policy: Dict[str, List[str]]):
        self.indexer = indexer
        self.tier_policy = tier_policy
        
        # Build reverse tier mapping: file_prefix -> tier_level
        # Sort prefixes by length (descending) to handle overlaps correctly
        # e.g., "src/crypto/" should match before "src/"
        self.file_to_tier = {}
        prefix_tier_pairs = []
        
        for tier_name, prefixes in tier_policy.items():
            tier_level = self._tier_name_to_level(tier_name)
            for prefix in prefixes:
                prefix_tier_pairs.append((prefix.lower(), tier_level))
        
        # Sort by prefix length (longest first) to handle overlapping prefixes
        prefix_tier_pairs.sort(key=lambda x: len(x[0]), reverse=True)
        
        # Build ordered dict (Python 3.7+ dicts maintain insertion order)
        for prefix, tier_level in prefix_tier_pairs:
            self.file_to_tier[prefix] = tier_level
    
    def _tier_name_to_level(self, tier_name: str) -> int:
        """Convert tier name to numeric level (lower is more restricted)"""
        if tier_name == "tier0":
            return 0
        elif tier_name == "tier1":
            return 1
        elif tier_name == "tier2":
            return 2
        else:
            return 0  # Default to tier0 (most permissive)
    
    def _get_file_tier(self, file_path: str) -> int:
        """Get tier level for a file"""
        normalized = file_path.replace("\\", "/").lower()
        
        for prefix, tier_level in self.file_to_tier.items():
            if normalized.startswith(prefix.lower()):
                return tier_level
        
        return 0  # Default to tier0
    
    def validate_module_integrity(self, modified_files: Set[str]) -> Tuple[bool, List[str]]:
        """
        Validate module integrity for modified files
        
        Returns:
            (is_valid, issues) - True if valid, list of issue descriptions
        """
        issues = []
        
        # 1. Check for circular dependencies
        try:
            self._check_circular_dependencies(modified_files)
        except CircularDependencyError as e:
            issues.append(f"Circular dependency: {e}")
        
        # 2. Check for tier violations
        try:
            self._check_tier_violations(modified_files)
        except TierViolationError as e:
            issues.append(f"Tier violation: {e}")
        
        return (len(issues) == 0, issues)
    
    def _check_circular_dependencies(self, modified_files: Set[str]):
        """
        Detect circular dependencies using DFS
        
        Raises CircularDependencyError if cycle detected
        """
        # Build dependency graph for modified files and their dependencies
        graph = self._build_dependency_graph(modified_files)
        
        # DFS to detect cycles
        visited = set()
        rec_stack = set()
        
        for file in graph.keys():
            if file not in visited:
                if self._has_cycle_dfs(file, graph, visited, rec_stack, []):
                    # Cycle detected (exception already raised in _has_cycle_dfs)
                    pass
    
    def _build_dependency_graph(self, modified_files: Set[str]) -> Dict[str, List[str]]:
        """Build dependency graph from includes"""
        graph = {}
        
        # Get all files to check (modified + their dependencies)
        files_to_check = set(modified_files)
        
        # Add direct dependencies of modified files
        for file in modified_files:
            includes = self._get_file_includes(file)
            files_to_check.update(includes)
        
        # Build graph
        for file in files_to_check:
            includes = self._get_file_includes(file)
            graph[file] = includes
        
        return graph
    
    def _get_file_includes(self, file_path: str) -> List[str]:
        """Get list of files included by this file"""
        cursor = self.indexer.conn.cursor()
        cursor.execute(
            "SELECT included_file FROM includes WHERE source_file = ?",
            (file_path,)
        )
        
        includes = []
        for row in cursor.fetchall():
            included = row[0]
            # Try to resolve to actual file in index
            resolved = self._resolve_include(included)
            if resolved:
                includes.append(resolved)
        
        return includes
    
    def _resolve_include(self, include_path: str) -> Optional[str]:
        """Resolve include path to actual file in index"""
        # Simple resolution: check if file exists in index
        cursor = self.indexer.conn.cursor()
        
        # Try exact match
        cursor.execute("SELECT path FROM files WHERE path = ?", (include_path,))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        # Try matching filename
        filename = os.path.basename(include_path)
        cursor.execute("SELECT path FROM files WHERE path LIKE ?", (f"%{filename}",))
        result = cursor.fetchone()
        if result:
            return result[0]
        
        return None
    
    def _has_cycle_dfs(self, node: str, graph: Dict[str, List[str]], 
                       visited: Set[str], rec_stack: Set[str], path: List[str]) -> bool:
        """
        DFS to detect cycles
        
        Returns True if cycle detected
        Raises CircularDependencyError with cycle path
        """
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        
        # Check all neighbors
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if self._has_cycle_dfs(neighbor, graph, visited, rec_stack, path):
                    return True
            elif neighbor in rec_stack:
                # Cycle detected!
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                cycle_str = " -> ".join(cycle)
                raise CircularDependencyError(cycle_str)
        
        path.pop()
        rec_stack.remove(node)
        return False
    
    def _check_tier_violations(self, modified_files: Set[str]):
        """
        Check for tier dependency violations
        
        Rule: Higher tier (more restricted) cannot depend on lower tier
        Example: tier2 (crypto) cannot include tier0 (physics)
        
        Raises TierViolationError if violation detected
        """
        for file in modified_files:
            file_tier = self._get_file_tier(file)
            includes = self._get_file_includes(file)
            
            for included_file in includes:
                included_tier = self._get_file_tier(included_file)
                
                # Check if higher tier depends on lower tier
                if file_tier > included_tier:
                    raise TierViolationError(
                        f"{file} (tier{file_tier}) includes {included_file} (tier{included_tier}). "
                        f"Higher tiers cannot depend on lower tiers."
                    )
