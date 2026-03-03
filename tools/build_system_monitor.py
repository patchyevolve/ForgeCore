"""
Build System Monitor - Detects and warns about build system changes

Monitors:
- CMakeLists.txt modifications
- Build target creation
- Public API exposure
- Cross-tier dependencies
"""

import os
from typing import List, Dict, Tuple, Optional


class BuildSystemMonitor:
    """
    Monitors build system files and warns about critical changes.
    """
    
    BUILD_FILES = {
        'cmake': ['CMakeLists.txt', 'cmake'],
        'msbuild': ['.sln', '.vcxproj', '.csproj'],
        'make': ['Makefile', 'makefile'],
        'cargo': ['Cargo.toml'],
        'npm': ['package.json'],
        'maven': ['pom.xml'],
        'gradle': ['build.gradle', 'settings.gradle']
    }
    
    def __init__(self, project_path: str, logger):
        self.project_path = project_path
        self.logger = logger
    
    def check_modifications(
        self,
        modified_files: List[str]
    ) -> Tuple[bool, List[str]]:
        """
        Check if build system files are being modified.
        
        Args:
            modified_files: List of files being modified
            
        Returns:
            (requires_confirmation: bool, warnings: List[str])
        """
        warnings = []
        requires_confirmation = False
        
        for file in modified_files:
            file_lower = file.lower()
            
            # Check if it's a build file
            for build_system, patterns in self.BUILD_FILES.items():
                for pattern in patterns:
                    if pattern in file_lower:
                        warnings.append(
                            f"⚠️  Modifying build file: {file} ({build_system})"
                        )
                        requires_confirmation = True
                        
                        self.logger.log_event(
                            state="VALIDATION",
                            event="BUILD_FILE_MODIFICATION",
                            details={
                                "file": file,
                                "build_system": build_system
                            }
                        )
        
        return requires_confirmation, warnings
    
    def detect_new_targets(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> List[str]:
        """
        Detect new build targets being added.
        
        Args:
            file_path: Path to build file
            old_content: Original content
            new_content: Modified content
            
        Returns:
            List of warnings
        """
        warnings = []
        file_lower = file_path.lower()
        
        # CMake target detection
        if 'cmakelists.txt' in file_lower:
            old_targets = self._extract_cmake_targets(old_content)
            new_targets = self._extract_cmake_targets(new_content)
            added_targets = new_targets - old_targets
            
            if added_targets:
                warnings.append(
                    f"⚠️  New CMake targets: {', '.join(added_targets)}"
                )
        
        # MSBuild project detection
        elif file_lower.endswith(('.vcxproj', '.csproj')):
            warnings.append(
                "⚠️  MSBuild project file modified - review carefully"
            )
        
        # Cargo target detection
        elif 'cargo.toml' in file_lower:
            if '[lib]' in new_content and '[lib]' not in old_content:
                warnings.append("⚠️  New Cargo library target added")
            if '[[bin]]' in new_content and '[[bin]]' not in old_content:
                warnings.append("⚠️  New Cargo binary target added")
        
        # npm scripts detection
        elif 'package.json' in file_lower:
            warnings.append(
                "⚠️  package.json modified - check dependencies and scripts"
            )
        
        return warnings
    
    def _extract_cmake_targets(self, content: str) -> set:
        """Extract CMake target names."""
        import re
        targets = set()
        
        # Match add_executable and add_library
        patterns = [
            r'add_executable\s*\(\s*(\w+)',
            r'add_library\s*\(\s*(\w+)'
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            targets.update(matches)
        
        return targets
    
    def check_public_api_changes(
        self,
        file_path: str,
        old_content: str,
        new_content: str
    ) -> List[str]:
        """
        Check for public API changes.
        
        Args:
            file_path: Path to file
            old_content: Original content
            new_content: Modified content
            
        Returns:
            List of warnings
        """
        warnings = []
        
        # Check header files for API changes
        if file_path.endswith(('.h', '.hpp', '.hxx')):
            # Check for new public functions
            old_public = self._extract_public_functions(old_content)
            new_public = self._extract_public_functions(new_content)
            
            added = new_public - old_public
            removed = old_public - new_public
            
            if added:
                warnings.append(
                    f"⚠️  New public functions in {file_path}: {', '.join(list(added)[:3])}"
                )
            
            if removed:
                warnings.append(
                    f"⚠️  Removed public functions in {file_path}: {', '.join(list(removed)[:3])}"
                )
        
        return warnings
    
    def _extract_public_functions(self, content: str) -> set:
        """Extract public function declarations."""
        import re
        functions = set()
        
        # Simple pattern for function declarations
        # Matches: return_type function_name(params);
        pattern = r'^\s*(?:virtual\s+)?(?:static\s+)?[\w:<>]+\s+(\w+)\s*\([^)]*\)\s*(?:const)?\s*;'
        
        for line in content.splitlines():
            # Skip private/protected sections (simple heuristic)
            if 'private:' in line or 'protected:' in line:
                break
            
            match = re.search(pattern, line)
            if match:
                functions.add(match.group(1))
        
        return functions
    
    def check_cross_tier_dependencies(
        self,
        file_path: str,
        content: str,
        tier_policy: Dict[str, List[str]]
    ) -> List[str]:
        """
        Check for cross-tier dependencies.
        
        Args:
            file_path: Path to file
            content: File content
            tier_policy: Tier policy dict
            
        Returns:
            List of warnings
        """
        warnings = []
        
        # Determine file's tier
        file_tier = self._get_file_tier(file_path, tier_policy)
        
        # Extract includes
        import re
        includes = re.findall(r'#include\s*[<"]([^>"]+)[>"]', content)
        
        for include in includes:
            include_tier = self._get_file_tier(include, tier_policy)
            
            # Check for tier violations
            if file_tier == 'tier0' and include_tier in ['tier1', 'tier2']:
                warnings.append(
                    f"⚠️  Tier violation: tier0 file {file_path} includes {include_tier} file {include}"
                )
            
            elif file_tier == 'tier1' and include_tier == 'tier2':
                warnings.append(
                    f"⚠️  Tier violation: tier1 file {file_path} includes tier2 file {include}"
                )
        
        return warnings
    
    def _get_file_tier(self, file_path: str, tier_policy: Dict[str, List[str]]) -> str:
        """Determine file's tier."""
        normalized = file_path.replace("\\", "/").lower()
        
        for tier_name, prefixes in tier_policy.items():
            for prefix in prefixes:
                if normalized.startswith(prefix.lower()):
                    return tier_name
        
        return "tier0"
