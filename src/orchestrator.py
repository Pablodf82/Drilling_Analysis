import sqlite3
import time
from pathlib import Path
from loader import DrillingLoader

def run_pipeline():
    base_dir = Path(__file__).resolve().parent.parent
    db_path = base_dir / "data_base" / "drilling.db"
    input_dir = base_dir / "data_input"
    
    loader = DrillingLoader(str(db_path))
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    
    cur.execute("SELECT file_name FROM files_log")
    processed = {row[0] for row in cur.fetchall()}
    
    new_files = [f for f in input_dir.rglob("*.csv") if f.name not in processed]
    
    for f in new_files:
        print(f"📦 Procesando: {f.name}")
        count = loader.load_well_file(str(f))
        if count > 0:
            cur.execute("INSERT INTO files_log VALUES (?)", (f.name,))
            conn.commit()

    cur.execute("PRAGMA wal_checkpoint(FULL);")
    conn.close()
    print("--- Pipeline finalizado ---")

if __name__ == "__main__":
    run_pipeline()