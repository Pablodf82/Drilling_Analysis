import sqlite3
import os
from pathlib import Path

def setup_database():
    """
    Initializes the SQLite database schema for drilling analytics.
    Deletes any existing database at the target path to ensure a clean setup,
    creates the required directory structure, and defines the core tables.
    """
    # Changed 'data_base' to 'database' for standard English naming
    db_path = Path("database/drilling.db")
    
    if db_path.exists():
        try:
            os.remove(db_path)
            print("🗑️ Legacy database file removed.")
        except OSError as e:
            print(f"⚠️ Warning: Could not remove existing database: {e}")

    # Ensure the target directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()

        # Wells Table
        cur.execute("""
            CREATE TABLE wells (
                well_id INTEGER PRIMARY KEY, 
                well_name TEXT UNIQUE
            )
        """)

        # Curve Catalog Table (Maps mnemonics to OSDU data standards)
        cur.execute("""
            CREATE TABLE curve_catalog (
                curve_id INTEGER PRIMARY KEY,
                canonical_mnem TEXT UNIQUE,
                osdu_name TEXT,
                unit TEXT
            )
        """)

        # Time-series Log Data Table
        cur.execute("""
            CREATE TABLE time_data (
                well_id INTEGER,
                curve_id INTEGER,
                timestamp REAL,
                value REAL,
                PRIMARY KEY (well_id, curve_id, timestamp)
            )
        """)

        # Orchestrator File Processing Log Table
        cur.execute("""
            CREATE TABLE files_log (
                file_name TEXT UNIQUE
            )
        """)

        conn.commit()
        print("✅ New database schema initialized successfully with 'canonical_mnem'.")
        
    except sqlite3.Error as e:
        print(f"❌ Database initialization error: {e}")
        if conn:
            conn.rollback()
            
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    setup_database()