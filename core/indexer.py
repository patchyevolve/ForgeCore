import os
import re
from memory.database import ForgeDatabase

class ProjectIndexer:

    INCLUDE_PATTERN = re.compile(r'#include\s*["<](.+)[">]')
    CLASS_PATTERN = re.compile(r'^\s*class\s+(\w+)')
    STRUCT_PATTERN = re.compile(r'^\s*struct\s+(\w+)')
    NAMESPACE_PATTERN = re.compile(r'^\s*namespace\s+(\w+)')
    # Function declarations/definitions.
    # Note: we intentionally DO NOT anchor the pattern to end-of-line so that
    # signatures like `int main() {` (opening brace on same line) are matched.
    FUNCTION_PATTERN = re.compile(
        r'^\s*[a-zA-Z_][\w:<>\*&\s]+\s+(\w+)\s*\([^;]*\)'
    )

    def __init__(self, project_root):
        self.project_root = os.path.abspath(project_root)
        self.db = ForgeDatabase()
        self.conn = self.db.get_connection()
        self._transaction_depth = 0
    
    def begin_transaction(self):
        """Begin a database transaction with savepoint support"""
        self._transaction_depth += 1
        savepoint_name = f"sp_{self._transaction_depth}"
        self.conn.execute(f"SAVEPOINT {savepoint_name}")
        return savepoint_name
    
    def commit_transaction(self, savepoint_name=None):
        """Commit a database transaction"""
        if savepoint_name:
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        else:
            self.conn.commit()
        if self._transaction_depth > 0:
            self._transaction_depth -= 1
    
    def rollback_transaction(self, savepoint_name=None):
        """Rollback a database transaction"""
        if savepoint_name:
            self.conn.execute(f"ROLLBACK TO SAVEPOINT {savepoint_name}")
            self.conn.execute(f"RELEASE SAVEPOINT {savepoint_name}")
        else:
            self.conn.rollback()
        if self._transaction_depth > 0:
            self._transaction_depth -= 1

    def index_project(self):
        """Index the project incrementally based on file modification times"""
        # Get all currently indexed files and their mtimes
        cursor = self.conn.cursor()
        cursor.execute("SELECT path, mtime FROM files")
        indexed_files = {row[0]: row[1] for row in cursor.fetchall()}
        
        present_files = set()
        indexed_count = 0
        
        for root, dirs, files in os.walk(self.project_root):
            # Exclude vendor/build directories
            dirs[:] = [
                d for d in dirs
                if d.lower() not in {".vs", "x64", "libraries", "build", "debug", "release", "__pycache__", ".git"}
            ]

            for file in files:
                if file.endswith((".cpp", ".hpp", ".h", ".cc", ".cxx", ".py")):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.project_root)
                    present_files.add(relative_path)
                    
                    try:
                        current_mtime = os.path.getmtime(full_path)
                    except OSError:
                        continue

                    # Index if file is new or modified
                    if relative_path not in indexed_files or indexed_files[relative_path] != current_mtime:
                        self._index_file(relative_path, full_path, current_mtime)
                        indexed_count += 1
        
        # Remove files that are no longer present
        files_to_remove = set(indexed_files.keys()) - present_files
        if files_to_remove:
            self.reindex_files(list(files_to_remove)) # reindex_files handles deletion if path doesn't exist

        # Only commit if not in a transaction
        if self._transaction_depth == 0:
            self.conn.commit()
            
        # Return summary stats
        cursor.execute("SELECT COUNT(*) FROM files")
        total_files = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM symbols")
        total_symbols = cursor.fetchone()[0]
        
        return {
            "indexed_now": indexed_count,
            "total_files": total_files,
            "total_symbols": total_symbols,
            "removed": len(files_to_remove)
        }

    def _clear_existing_data(self):
        """Force clear all index data"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files")
        cursor.execute("DELETE FROM includes")
        cursor.execute("DELETE FROM symbols")
        cursor.execute("DELETE FROM dependencies")
        print("Cleared existing index data")
        if self._transaction_depth == 0:
            self.conn.commit()

    def _index_file(self, relative_path, full_path, mtime=None):
        cursor = self.conn.cursor()

        if mtime is None:
            try:
                mtime = os.path.getmtime(full_path)
            except OSError:
                mtime = 0

        cursor.execute(
            "INSERT OR REPLACE INTO files (path, mtime) VALUES (?, ?)",
           (relative_path, mtime)
        )

        with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()

        for line_number, line in enumerate(lines, start=1):

            # Includes
            match = self.INCLUDE_PATTERN.search(line)
            if match:
                included = match.group(1)
                cursor.execute(
                    "INSERT INTO includes (source_file, included_file) VALUES (?, ?)",
                    (relative_path, included)
                )

            # Class definitions
            match = self.CLASS_PATTERN.search(line)
            if match:
                cursor.execute(
                    "INSERT INTO symbols (name, type, file, line) VALUES (?, ?, ?, ?)",
                    (match.group(1), "class", relative_path, line_number)
                )

            # Struct definitions
            match = self.STRUCT_PATTERN.search(line)
            if match:
                cursor.execute(
                    "INSERT INTO symbols (name, type, file, line) VALUES (?, ?, ?, ?)",
                    (match.group(1), "struct", relative_path, line_number)
                )

            # Namespace definitions
            match = self.NAMESPACE_PATTERN.search(line)
            if match:
                cursor.execute(
                    "INSERT INTO symbols (name, type, file, line) VALUES (?, ?, ?, ?)",
                    (match.group(1), "namespace", relative_path, line_number)
                )

            # Function definitions (simple heuristic)
            match = self.FUNCTION_PATTERN.search(line)
            if match:
                name = match.group(1)

                # Case 1: opening brace on the same line as the signature,
                # e.g. `int main() {`
                # We only care that a `{` appears after the closing `)`.
                signature_end = match.end()
                if "{" in line[signature_end:]:
                    cursor.execute(
                        "INSERT INTO symbols (name, type, file, line) VALUES (?, ?, ?, ?)",
                        (name, "function", relative_path, line_number)
                    )
                else:
                    # Case 2: brace on a subsequent non-empty line, e.g.:
                    #   int main()
                    #   {
                    next_line_index = line_number
                    while next_line_index < len(lines):
                        next_line = lines[next_line_index].strip()
                        if next_line == "":
                            next_line_index += 1
                            continue
                        if next_line.startswith("{"):
                            cursor.execute(
                                "INSERT INTO symbols (name, type, file, line) VALUES (?, ?, ?, ?)",
                                (name, "function", relative_path, line_number)
                            )
                        break


    def reindex_files(self, files):
        cursor = self.conn.cursor()

        for relative_path in files:

            #remove old entries for this file
            cursor.execute("DELETE FROM includes WHERE source_file = ?", (relative_path,))
            cursor.execute("DELETE FROM symbols WHERE file = ?", (relative_path,))
            cursor.execute("DELETE FROM files WHERE path = ?", (relative_path,))

            full_path = os.path.join(self.project_root, relative_path)

            if os.path.exists(full_path):
                self._index_file(relative_path, full_path)
        # Only commit if not in a transaction
        if self._transaction_depth == 0:
            self.conn.commit()

    def close(self):
        self.db.close()