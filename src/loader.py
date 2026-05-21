import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path

class DrillingLoader:
    def __init__(self, db_path="data_base/drilling.db"):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.cur = self.conn.cursor()

    def get_curve_id(self, mnemonic):
        self.cur.execute("SELECT curve_id FROM curve_catalog WHERE canonical_mnem = ?", (mnemonic,))
        res = self.cur.fetchone()
        if res: return res[0]
        
        self.cur.execute("INSERT INTO curve_catalog (canonical_mnem, osdu_name) VALUES (?, ?)", (mnemonic, mnemonic))
        self.conn.commit()
        return self.cur.lastrowid

    def calculate_kpis(self, df):
        """Cálculo de HOLE_MD, MSE en BAR, y conversión de variables hidráulicas."""
        # Forzar conversión a numérico de todo el dataframe
        df = df.apply(pd.to_numeric, errors='coerce')

        # 1. HOLE_MD: Máximo acumulado de la profundidad de la broca
        bit_col = next((c for c in ['DEPTH_BIT', 'DEPTH_BIT_V', 'Bit_MD'] if c in df.columns), None)
        if bit_col:
            df['HOLE_MD'] = df[bit_col].ffill().fillna(0).cummax()

        # 2. MSE (Mechanical Specific Energy) en BAR
        wob  = df.get('BWAB-T', df.get('WOB', 0))       # t (toneladas)
        torq = df.get('BTAB-T', df.get('TORQ', 0))     # kN.m
        rpm  = df.get('RPM_SURF', df.get('RPM', 0))     # rpm
        rop  = df.get('ROP_AVG', df.get('ROP', 0))      # m/h
        area = (8.5 ** 2) * 0.7854 * 0.00064516         # Área para 8.5" en m²

        with np.errstate(divide='ignore', invalid='ignore'):
            # MSE en PSI: (WOB/Area) + (120*PI*RPM*Torque)/(Area*ROP)
            # 120 * PI es aprox 377
            mse_psi = (wob * 2204.62 / (area * 1550)) + (377 * rpm * torq * 737.56) / (area * 1550 * rop * 3.28)
            
            # Conversión de PSI a BAR (1 psi = 0.0689476 bar)
            df['MSE'] = mse_psi * 0.0689476
            df['MSE'] = df['MSE'].replace([np.inf, -np.inf], 0).fillna(0)

        # 3. HIDRÁULICA:
        flow_gpm = df.get('FLOW_PUMP', df.get('FR_TOTAL', df.get('MUD_FLOW_IN', df.get('FLOW_IN', 0))))
        df['FLOW_LMIN'] = flow_gpm * 3.78541

        # Presión: Buscamos variantes comunes de Stand Pipe Pressure
        spp_psi = df.get('PRESS_SPP', df.get('SPP', df.get('PUMP_PRESS', df.get('PRESS_PUMP', 0))))
        df['SPP_BAR'] = spp_psi * 0.0689476

        return df

    def load_well_file(self, file_path):
        well_name = Path(file_path).stem
        if "_Drilling" in well_name: well_name = well_name.split('_Drilling')[0]

        self.cur.execute("INSERT OR IGNORE INTO wells (well_name) VALUES (?)", (well_name,))
        self.cur.execute("SELECT well_id FROM wells WHERE well_name = ?", (well_name,))
        well_id = self.cur.fetchone()[0]

        df = pd.read_csv(file_path, low_memory=False)
        if df.iloc[0].astype(str).str.contains('[a-zA-Z]').any():
            df = df.drop(index=0).reset_index(drop=True)

        df = self.calculate_kpis(df)

        data_to_insert = []
        for col in df.columns:
            curve_id = self.get_curve_id(col)
            values = df[col].fillna(0).tolist()
            timestamps = df.index.tolist()
            for ts, val in zip(timestamps, values):
                data_to_insert.append((well_id, curve_id, ts, float(val)))

        self.cur.executemany("INSERT OR REPLACE INTO time_data VALUES (?, ?, ?, ?)", data_to_insert)
        self.conn.commit()
        return len(df)
