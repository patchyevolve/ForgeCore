"""
Project Diagnoser - Comprehensive project-wide health check
"""

import os
from typing import Dict, Any, List
from core.indexer import ProjectIndexer
from core.symbol_validator import SymbolValidator
from core.dependency_validator import DependencyValidator
from core.semantic_validator import SemanticValidator
from tools.smart_validator import SmartValidator
from core.logger import Logger

class ProjectDiagnoser:
    """Runs all validators to find errors and warnings across the project"""
    
    def __init__(self, project_path: str, logger: Logger):
        self.project_path = project_path
        self.logger = logger
        self.indexer = ProjectIndexer(project_path)
        self.symbol_validator = SymbolValidator(self.indexer)
        
        # Load tier policy
        import json
        tier_policy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "policy", "tier_policy.json")
        with open(tier_policy_path, 'r') as f:
            tier_policy = json.load(f)
        self.dependency_validator = DependencyValidator(self.indexer, tier_policy)
        
        self.semantic_validator = SemanticValidator(self.indexer, logger)
        self.smart_validator = SmartValidator(project_path, logger)
        
    def run_diagnosis(self) -> Dict[str, Any]:
        """Run all diagnostic checks"""
        print("\n[DIAGNOSIS] Starting project-wide diagnosis...")
        
        # 1. Indexing
        print("  [1/5] Indexing project...")
        self.indexer.index_project()
        files = self.indexer.get_all_files()
        
        # 2. Symbol Validation
        print(f"  [2/5] Checking symbols in {len(files)} files...")
        symbol_valid, symbol_issues = self.symbol_validator.validate_symbol_usage(
            files, check_undefined=True, check_unused=True
        )
        
        # 3. Module Integrity (Dependencies)
        print("  [3/5] Checking module integrity...")
        deps_valid, deps_issues = self.dependency_validator.validate_module_integrity(files)
        
        # 4. Semantic Validation
        print("  [4/5] Running semantic analysis...")
        semantic_issues = []
        for file in files:
            is_valid, issues = self.semantic_validator.validate_file(file)
            if not is_valid:
                semantic_issues.extend([f"{file}: {i}" for i in issues])
        
        # 5. Build Check (Optional/Fast)
        print("  [5/5] Checking build system...")
        # We don't run a full build here to keep it fast, just check if build files exist
        build_info = self.smart_validator.language_info
        
        results = {
            "files_count": len(files),
            "symbol_issues": symbol_issues,
            "dependency_issues": deps_issues,
            "semantic_issues": semantic_issues,
            "language_info": build_info,
            "is_healthy": all([symbol_valid, deps_valid, not semantic_issues])
        }
        
        return results

    def print_report(self, results: Dict[str, Any]):
        """Print a formatted report of the diagnosis"""
        print("\n" + "="*70)
        print("PROJECT DIAGNOSIS REPORT")
        print("="*70)
        
        print(f"\nFiles analyzed: {results['files_count']}")
        print(f"Primary Language: {results['language_info']['primary_language'] or 'Unknown'}")
        
        if results['is_healthy']:
            print("\n[OK] No major issues found! Project is healthy.")
        else:
            print("\n[!] Issues found:")
            
            if results['symbol_issues']:
                print("\nSymbol Issues:")
                for issue in results['symbol_issues']:
                    print(f"  - {issue}")
            
            if results['dependency_issues']:
                print("\nDependency Issues:")
                for issue in results['dependency_issues']:
                    print(f"  - {issue}")
                    
            if results['semantic_issues']:
                print("\nSemantic Issues:")
                for issue in results['semantic_issues']:
                    print(f"  - {issue}")
        
        print("\n" + "="*70 + "\n")
