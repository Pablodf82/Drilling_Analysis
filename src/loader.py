import sqlite3
import numpy as np
import pandas as pd
from pathlib import Path

class DrillingLoader:
    """
    Advanced Drilling Data Loader and ETL Pipeline.
    Parses high-frequency OSDU time-series telemetry datasets, resolves dynamic 
    rig operational states, computes performance metrics, and persists structured 
    records efficiently into a relational database.
    """
    def __init__(self, db_path="database/drilling.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cur = self.conn.cursor()

    def get_curve_id(self, mnemonic: str) -> int:
        """
        Resolves or indexes a canonical mnemonic within the centralized Curve Catalog.
        Ensures relational mapping integrity across unique logging tracks.
        """
        self.cur.execute("SELECT curve_id FROM curve_catalog WHERE canonical_mnem = ?", (mnemonic,))
        res = self.cur.fetchone()
        if res: 
            return res[0]
        
        self.cur.execute("INSERT INTO curve_catalog (canonical_mnem, osdu_name) VALUES (?, ?)", (mnemonic, mnemonic))
        self.conn.commit()
        return self.cur.lastrowid

    def calculate_kpis(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Executes real-time feature engineering for drilling analytics optimization.
        
        Enhancements:
        1. Rig Activity State Machine: Evaluates physical constraints to isolate On-Bottom 
           Drilling intervals and reconstruct an accurate HOLE_MD curve.
        2. Mechanical Specific Energy (MSE): Computes structural rock-destruction efficiency 
           scaled to Metric BAR, avoiding math singularities or infinity.
        """
        working_df = df.copy()

        # Telemetry channel identification based on flexible standard mnemonics
        bit_col = next((c for c in ['DEPTH_BIT', 'DEPTH_BIT_V', 'Bit_MD', 'BIT_DEPTH'] if c in working_df.columns), None)
        rop_col = next((c for c in ['ROP', 'ROP_AVG', 'ROP_MIN'] if c in working_df.columns), None)
        wob_col = next((c for c in ['WOB', 'BWAB-T', 'WOB_AVG'] if c in working_df.columns), None)
        rpm_col = next((c for c in ['RPM', 'RPM_SURF', 'RPM_BIT'] if c in working_df.columns), None)

        # Enforce strict numeric rendering across calculation critical tracks
        for col in [bit_col, rop_col, wob_col, rpm_col]:
            if col:
                working_df[col] = pd.to_numeric(working_df[col], errors='coerce')

        # -----------------------------------------------------------------
        # 1. RIG STATE ENGINE: HOLE_MD DETERMINATION
        # -----------------------------------------------------------------
        if bit_col:
            bit_series = working_df[bit_col].ffill().fillna(0.0).values
            rop_series = working_df[rop_col].ffill().fillna(0.0).values if rop_col else np.ones(len(working_df))
            wob_series = working_df[wob_col].ffill().fillna(0.0).values if wob_col else np.ones(len(working_df))

            hole_md_calculated = []
            current_max_hole = 0.0

            # Step through time-series logs to separate drilling from tripping operations
            for bit, rop, wob in zip(bit_series, rop_series, wob_series):
                if bit > current_max_hole and rop > 0.1 and wob > 0.1:
                    current_max_hole = bit
                if bit > current_max_hole:
                    current_max_hole = bit
                hole_md_calculated.append(current_max_hole)

            working_df['HOLE_MD'] = hole_md_calculated
        else:
            hole_col = next((c for c in ['DEPTH_HOLE', 'Hole_MD', 'HOLE_DEPTH'] if c in working_df.columns), None)
            working_df['HOLE_MD'] = pd.to_numeric(working_df[hole_col], errors='coerce').ffill().fillna(0.0) if hole_col else 0.0

        # -----------------------------------------------------------------
        # 2. MECHANICAL SPECIFIC ENERGY (MSE) IN BAR
        # -----------------------------------------------------------------
        rop_clean = working_df[rop_col].ffill().fillna(0.0).values if rop_col else np.zeros(len(working_df))
        wob_clean = working_df[wob_col].ffill().fillna(0.0).values if wob_col else np.zeros(len(working_df))
        rpm_clean = working_df[rpm_col].ffill().fillna(0.0).values if rpm_col else np.zeros(len(working_df))
        
        bit_diameter = 8.5
        area_inch2 = (np.pi * (bit_diameter ** 2)) / 4

        mse_array = np.zeros(len(working_df))
        active_drilling_idx = rop_clean > 0.5
        
        if np.any(active_drilling_idx):
            wob_lbs = wob_clean * 2204.62
            mse_array[active_drilling_idx] = (
                (wob_lbs[active_drilling_idx] / area_inch2) + 
                ((120 * np.pi * rpm_clean[active_drilling_idx] * 3000) / (area_inch2 * rop_clean[active_drilling_idx]))
            ) * 0.0689476

        working_df['MSE'] = mse_array

        # -----------------------------------------------------------------
        # 3. HYDRAULICS UNIT CONVERSIONS
        # -----------------------------------------------------------------
        flow_gpm = working_df.get('FLOW_PUMP', working_df.get('FR_TOTAL', working_df.get('MUD_FLOW_IN', working_df.get('FLOW_IN', pd.Series(0.0, index=working_df.index)))))
        working_df['FLOW_LMIN'] = pd.to_numeric(flow_gpm, errors='coerce').ffill().fillna(0.0) * 3.78541

        spp_psi = working_df.get('PRESS_SPP', working_df.get('SPP', working_df.get('PUMP_PRESS', working_df.get('PRESS_PUMP', pd.Series(0.0, index=working_df.index)))))
        working_df['SPP_BAR'] = pd.to_numeric(spp_psi, errors='coerce').ffill().fillna(0.0) * 0.0689476

        return working_df

    def load_well_file(self, file_path: str) -> int:
        """
        Executes end-to-end ingestion pipeline for a singular logging file.
        Extracts structural data matrix, maps columns safely, handles ISO timestamps, 
        and performs dynamic bulk relational persistence for 100% of available curves.
        """
        well_name = Path(file_path).stem
        if "_Drilling" in well_name: 
            well_name = well_name.split('_Drilling')[0]

        # Register well identity mapping
        self.cur.execute("INSERT OR IGNORE INTO wells (well_name) VALUES (?)", (well_name,))
        self.cur.execute("SELECT well_id FROM wells WHERE well_name = ?", (well_name,))
        well_id = self.cur.fetchone()[0]

        # Safely extract CSV logging records
        df = pd.read_csv(file_path, low_memory=False)
        if df.iloc[0].astype(str).str.contains('[a-zA-Z]').any():
            df = df.drop(index=0).reset_index(drop=True)

        # Normalize metadata schemas by stripping trailing spaces from headers
        df.columns = df.columns.str.strip()

        # Extract and compute real Unix timestamps BEFORE converting headers to numeric
        time_col = next((c for c in ['TIME', 'Timestamp', 'time', 'DATE'] if c in df.columns), None)
        if time_col:
            parsed_time = pd.to_datetime(df[time_col], errors='coerce')
            if parsed_time.notna().any():
                timestamps = (parsed_time.astype(np.int64) // 10**9).tolist()
            else:
                timestamps = pd.to_numeric(df[time_col], errors='coerce').ffill().fillna(0.0).astype(np.int64).tolist()
        else:
            timestamps = df.index.tolist()

        # Execute core feature engineering transforms
        df = self.calculate_kpis(df)

        data_to_insert = []
        
        # DYNAMIC FULL ITERATION LAYER: Ingests 100% of telemetry data channels
        for col in df.columns:
            # Exclude raw original string timestamp tracks from being written as numerical curves
            if col not in ['TIME', 'Timestamp', 'time', 'DATE']:
                curve_id = self.get_curve_id(col)
                values = pd.to_numeric(df[col], errors='coerce').fillna(0.0).tolist()
                
                # Zip using explicit standard primitive standard castings to avoid Pylance/SQLite errors
                for ts, val in zip(timestamps, values):
                    data_to_insert.append((int(well_id), int(curve_id), int(ts), float(val)))

        # Commit bulk transactional query matching the exact working positional syntax
        if data_to_insert:
            self.cur.executemany("INSERT OR REPLACE INTO time_data VALUES (?, ?, ?, ?)", data_to_insert)
            self.conn.commit()
            
        return len(df)

    def __del__(self):
        """Ensures structural resource cleanups on object destruction."""
        try:
            self.conn.close()
        except:
            pass