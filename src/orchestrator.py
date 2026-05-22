import sqlite3
import logging
from pathlib import Path
from loader import DrillingLoader

# Configure logging for professional production monitoring
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

def run_pipeline():
    """
    Orchestrates the data ingestion pipeline.
    Scans the input directory for new drilling CSV files, verifies against 
    the database log to prevent duplicate processing, and loads new data.
    """
    base_dir = Path(__file__).resolve().parent.parent
    
    # Updated path to match the new 'database' folder name from db_schema.py
    db_path = base_dir / "database" / "drilling.db"
    input_dir = base_dir / "data_input"
    
    if not db_path.exists():
        logging.error(f"Database not found at {db_path}. Please run db_schema.py first.")
        return

    if not input_dir.exists():
        logging.warning(f"Input directory not found at {input_dir}. Creating it now.")
        input_dir.mkdir(parents=True, exist_ok=True)
        return

    loader = DrillingLoader(str(db_path))
    conn = None
    
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        
        # Fetch already processed files to avoid duplication
        cur.execute("SELECT file_name FROM files_log")
        processed_files = {row[0] for row in cur.fetchall()}
        
        # Scan for new CSV files recursively
        new_files = [
            file for file in input_dir.rglob("*.csv") 
            if file.name not in processed_files
        ]
        
        if not new_files:
            logging.info("🔄 No new drilling files detected. Pipeline is up to date.")
            return

        # Process each new file
        for file in new_files:
            logging.info(f"📦 Processing file: {file.name}")
            
            # Load data using the specialized loader class
            rows_inserted = loader.load_well_file(str(file))
            
            if rows_inserted > 0:
                cur.execute(
                    "INSERT INTO files_log (file_name) VALUES (?)", 
                    (file.name,)
                )
                conn.commit()
                logging.info(f"✅ Successfully ingested {rows_inserted} rows from {file.name}")
            else:
                logging.warning(f"⚠️ File {file.name} was read but yielded no valid data.")

        # Optimize database file and commit changes to disk (WAL mode checkpoint)
        cur.execute("PRAGMA wal_checkpoint(FULL);")
        logging.info("🚀 Data pipeline execution completed successfully.")
        
    except sqlite3.Error as error:
        logging.error(f"❌ Database error during pipeline execution: {error}")
        if conn:
            conn.rollback()
            
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    run_pipeline()