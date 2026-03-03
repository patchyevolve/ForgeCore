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

    def index_project(self):
        self._clear_existing_data()
        for root, dirs, files in os.walk(self.project_root):

            # Exclude vendor/build directories
            dirs[:] = [
                d for d in dirs
                if d.lower() not in {".vs", "x64", "libraries", "build", "debug", "release"}
            ]

            for file in files:
                if file.endswith((".cpp", ".hpp", ".h", ".cc", ".cxx")):
                    full_path = os.path.join(root, file)
                    relative_path = os.path.relpath(full_path, self.project_root)
                    self._index_file(relative_path,full_path)
        self.conn.commit()

    def _clear_existing_data(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM files")
        cursor.execute("DELETE FROM includes")
        cursor.execute("DELETE FROM symbols")
        cursor.execute("DELETE FROM dependencies")
        print("Cleared existing index data")
        self.conn.commit()

    def _index_file(self, relative_path, full_path):
        cursor = self.conn.cursor()

        cursor.execute(
            "INSERT OR IGNORE INTO files (path) VALUES (?)",
           (relative_path,)
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
        self.conn.commit()

    def close(self):
        self.db.close()