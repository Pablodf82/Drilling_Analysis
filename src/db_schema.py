import sqlite3
import os
from pathlib import Path

def setup_database():
    db_path = Path("data_base/drilling.db")
    if db_path.exists():
        os.remove(db_path)
        print("🗑️ Base de datos antigua eliminada.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    # Tabla de Pozos
    cur.execute("CREATE TABLE wells (well_id INTEGER PRIMARY KEY, well_name TEXT UNIQUE)")

    # Tabla de Catálogo (AQUÍ ESTÁ LA COLUMNA QUE FALTABA)
    cur.execute("""
        CREATE TABLE curve_catalog (
            curve_id INTEGER PRIMARY KEY,
            canonical_mnem TEXT UNIQUE,
            osdu_name TEXT,
            unit TEXT
        )
    """)

    # Tabla de Datos
    cur.execute("""
        CREATE TABLE time_data (
            well_id INTEGER,
            curve_id INTEGER,
            timestamp REAL,
            value REAL,
            PRIMARY KEY (well_id, curve_id, timestamp)
        )
    """)

    # Tabla de Log para el Orchestrator
    cur.execute("CREATE TABLE files_log (file_name TEXT UNIQUE)")

    conn.commit()
    conn.close()
    print("✅ Nueva estructura de DB creada con 'canonical_mnem'.")

if __name__ == "__main__":
    setup_database()