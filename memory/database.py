import os
import sqlite3

class ForgeDatabase:
    def __init__(self, db_path="memory/forgecore.db"):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self._initialize_schema()

    def _initialize_schema(self):
        cursor = self.conn.cursor()

        #files table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE,
                mtime REAL,
                semantic_context TEXT,
                last_indexed TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        #includes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS includes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_file TEXT,
                included_file TEXT
            )
        """)

        #symbols table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                type TEXT,
                file TEXT,
                line INTEGER
            )
        """)

        #dependencies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dependencies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file TEXT,
                depends_on TEXT
            )
        """)

        self.conn.commit()
        self._migrate_schema()

    def _migrate_schema(self):
        """Add missing columns to existing tables"""
        cursor = self.conn.cursor()
        
        # Check if mtime exists in files table
        cursor.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'mtime' not in columns:
            print("[INFO] Migrating database: adding mtime column to files table")
            cursor.execute("ALTER TABLE files ADD COLUMN mtime REAL")
            self.conn.commit()

        if 'semantic_context' not in columns:
            print("[INFO] Migrating database: adding semantic_context column to files table")
            cursor.execute("ALTER TABLE files ADD COLUMN semantic_context TEXT")
            self.conn.commit()

    def get_symbol_definition(self, symbol_name):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT file, line, type FROM symbols WHERE name = ?",
            (symbol_name,)
        )
        return cursor.fetchall()


    def get_file_includes(self, file_path):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT included_file FROM includes WHERE source_file = ?",
            (file_path,)
        )
        return cursor.fetchall()


    def get_all_symbols_in_file(self, file_path):
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT name, type, line FROM symbols WHERE file = ?",
            (file_path,)
        )
        return cursor.fetchall()

    def get_connection(self):
        return self.conn

    def close(self):
        self.conn.close()

