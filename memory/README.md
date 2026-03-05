# Memory Module Handbook

The `memory/` directory handles long-term persistence for project metadata, indexing, and task history.

## Components

- **[forgecore.db](file:///d:/codeWorks/ForgeCore/memory/forgecore.db)**: An SQLite database that stores:
    - **Project Index**: File paths, hashes, and language info.
    - **Symbol Table**: Classes, functions, and variables for cross-file validation.
    - **Task History**: Record of previously executed commands and their outcomes.
- **[database.py](file:///d:/codeWorks/ForgeCore/memory/database.py)**: Python wrapper for database operations, implementing connection pooling and transaction lifecycle management.

## Database Schema Highlights

- `files` table: Tracks file integrity and timestamps.
- `symbols` table: Maps symbols to their locations and signatures.
- `tasks` table: Stores natural language inputs and corresponding patch intents.
