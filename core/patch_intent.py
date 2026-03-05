from enum import Enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class Operation(Enum):
    APPEND_RAW = "append_raw"
    ADD_FUNCTION_STUB = "add_function_stub"
    REPLACE_FUNCTION = "replace_function"
    INSERT_BEFORE = "insert_before"
    INSERT_AFTER = "insert_after"
    ADD_INCLUDE = "add_include"
    REPLACE_CONTENT = "replace_content"
    CREATE_FILE = "create_file"  # NEW: Create new file with content


@dataclass(frozen=True)
class FileMutation:
    """Single file mutation within a multi-file intent"""
    target_file: str
    operation: Operation
    payload: Dict[str, Any]
    
    def __post_init__(self):
        # Validate target_file
        if not isinstance(self.target_file, str) or not self.target_file.strip():
            raise ValueError("target_file must be a non-empty string")
        
        # Validate operation
        if not isinstance(self.operation, Operation):
            raise ValueError("operation must be Operation enum")
        
        # Validate payload
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a dictionary")
        
        # Operation-specific validation
        self._validate_payload()
    
    def _validate_payload(self):
        """Validate payload based on operation type"""
        if self.operation == Operation.APPEND_RAW:
            if "content" not in self.payload:
                raise ValueError("append_raw requires 'content' in payload")
            if not isinstance(self.payload["content"], str):
                raise ValueError("'content' must be a string")

        elif self.operation == Operation.ADD_FUNCTION_STUB:
            if "name" not in self.payload:
                raise ValueError("add_function_stub requires 'name' in payload")
            if not isinstance(self.payload["name"], str):
                raise ValueError("'name' must be a string")
            if not self.payload["name"].isidentifier():
                raise ValueError("function name must be a valid identifier")
        
        elif self.operation == Operation.REPLACE_FUNCTION:
            if "name" not in self.payload:
                raise ValueError("replace_function requires 'name' in payload")
            if "body" not in self.payload:
                raise ValueError("replace_function requires 'body' in payload")
            if not isinstance(self.payload["name"], str):
                raise ValueError("'name' must be a string")
            if not isinstance(self.payload["body"], str):
                raise ValueError("'body' must be a string")
        
        elif self.operation == Operation.INSERT_BEFORE:
            if "anchor" not in self.payload:
                raise ValueError("insert_before requires 'anchor' in payload")
            if "content" not in self.payload:
                raise ValueError("insert_before requires 'content' in payload")
            if not isinstance(self.payload["anchor"], str):
                raise ValueError("'anchor' must be a string")
            if not isinstance(self.payload["content"], str):
                raise ValueError("'content' must be a string")
        
        elif self.operation == Operation.INSERT_AFTER:
            if "anchor" not in self.payload:
                raise ValueError("insert_after requires 'anchor' in payload")
            if "content" not in self.payload:
                raise ValueError("insert_after requires 'content' in payload")
            if not isinstance(self.payload["anchor"], str):
                raise ValueError("'anchor' must be a string")
            if not isinstance(self.payload["content"], str):
                raise ValueError("'content' must be a string")
        
        elif self.operation == Operation.ADD_INCLUDE:
            if "header" not in self.payload:
                raise ValueError("add_include requires 'header' in payload")
            if not isinstance(self.payload["header"], str):
                raise ValueError("'header' must be a string")
        
        elif self.operation == Operation.REPLACE_CONTENT:
            if "old_content" not in self.payload:
                raise ValueError("replace_content requires 'old_content' in payload")
            if "new_content" not in self.payload:
                raise ValueError("replace_content requires 'new_content' in payload")
            if not isinstance(self.payload["old_content"], str):
                raise ValueError("'old_content' must be a string")
            if not isinstance(self.payload["new_content"], str):
                raise ValueError("'new_content' must be a string")
        
        elif self.operation == Operation.CREATE_FILE:
            if "content" not in self.payload:
                raise ValueError("create_file requires 'content' in payload")
            if not isinstance(self.payload["content"], str):
                raise ValueError("'content' must be a string")
        
        else:
            raise ValueError(f"Unsupported operation: {self.operation}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        return {
            "target_file": self.target_file,
            "operation": self.operation.value,
            "payload": self.payload
        }


@dataclass(frozen=True)
class PatchIntent:
    """
    Multi-file atomic intent with backward compatibility
    
    Can be created in two ways:
    1. Single-file (backward compatible): PatchIntent(operation, target_file, payload)
    2. Multi-file: PatchIntent(file_mutations=[...], description="...")
    """
    operation: Optional[Operation] = None
    target_file: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    file_mutations: Optional[List[FileMutation]] = None
    description: str = ""
    schema_version: int = 2

    def __post_init__(self):
        # Determine mode: single-file or multi-file
        if self.file_mutations is not None:
            # Multi-file mode
            if not isinstance(self.file_mutations, list):
                raise ValueError("file_mutations must be a list")
            if len(self.file_mutations) == 0:
                raise ValueError("file_mutations cannot be empty")
            if not all(isinstance(m, FileMutation) for m in self.file_mutations):
                raise ValueError("All items in file_mutations must be FileMutation instances")
            
            # Ensure single-file fields are not set
            if self.operation is not None or self.target_file is not None or self.payload is not None:
                raise ValueError("Cannot specify both file_mutations and single-file fields (operation/target_file/payload)")
        
        else:
            # Single-file mode (backward compatibility)
            if self.operation is None or self.target_file is None or self.payload is None:
                raise ValueError("Single-file mode requires operation, target_file, and payload")
            # narrow types for mypy
            assert self.operation is not None
            assert self.target_file is not None
            assert self.payload is not None

            # Validate single-file fields
            if not isinstance(self.target_file, str) or not self.target_file.strip():
                raise ValueError("target_file must be a non-empty string")
            if not isinstance(self.payload, dict):
                raise ValueError("payload must be a dictionary")
            # Create internal FileMutation for consistency (handled via properties)
    
    @property
    def is_multi_file(self) -> bool:
        """Check if this is a multi-file intent"""
        return self.file_mutations is not None
    
    @property
    def mutations(self) -> List[FileMutation]:
        """Get all mutations (works for both single and multi-file)"""
        if self.file_mutations is not None:
            return self.file_mutations
        else:
            # Single-file mode: create FileMutation on the fly
            assert self.target_file is not None
            assert self.operation is not None
            assert self.payload is not None
            return [FileMutation(
                target_file=self.target_file,
                operation=self.operation,
                payload=self.payload
            )]
    
    @property
    def target_files(self) -> List[str]:
        """Get all target files"""
        return [m.target_file for m in self.mutations]
    
    @classmethod
    def single_file(cls, target_file: str, operation: Operation, payload: Dict[str, Any], description: str = ""):
        """
        Create a single-file intent (backward compatible factory method)
        
        Args:
            target_file: Target file path
            operation: Operation to perform
            payload: Operation-specific payload
            description: Optional description
        
        Returns:
            PatchIntent instance
        """
        return cls(
            operation=operation,
            target_file=target_file,
            payload=payload,
            description=description or f"{operation.name} on {target_file}"
        )
    
    @classmethod
    def multi_file(cls, mutations: List[FileMutation], description: str = ""):
        """
        Create a multi-file intent
        
        Args:
            mutations: List of FileMutation instances
            description: Human-readable description
        
        Returns:
            PatchIntent instance
        """
        if not description:
            files = [m.target_file for m in mutations]
            description = f"Multi-file mutation on {len(files)} file(s): {', '.join(files[:3])}"
            if len(files) > 3:
                description += f" and {len(files) - 3} more"
        
        return cls(
            file_mutations=mutations,
            description=description
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation"""
        if self.is_multi_file:
            assert self.file_mutations is not None
            return {
                "file_mutations": [m.to_dict() for m in self.file_mutations],
                "description": self.description,
                "schema_version": self.schema_version
            }
        else:
            # Single-file mode (backward compatible)
            assert self.operation is not None
            assert self.target_file is not None
            assert self.payload is not None
            return {
                "operation": self.operation.value,
                "target_file": self.target_file,
                "payload": self.payload,
                "description": self.description,
                "schema_version": self.schema_version
            }
