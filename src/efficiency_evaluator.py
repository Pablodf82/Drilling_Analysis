import sqlite3
import logging
from pathlib import Path
import pandas as pd
from dotenv import load_dotenv

# Configure logging for pipeline metrics monitoring (Custom time format without milliseconds)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

class EfficiencyEvaluator:
    """
    Evaluates real-time drilling efficiency by comparing operational metrics 
    between historical and current depth intervals. Generates automated engineering 
    insights to feed the downstream AI advisor.
    """
    def __init__(self, db_path=None):
        # Resolve absolute paths based on project root layout
        base_dir = Path(__file__).resolve().parent.parent
        
        if db_path is None:
            self.db_path = base_dir / "database" / "drilling.db"
        else:
            self.db_path = Path(db_path)
            
        # Forces dotenv to look precisely at the root directory level
        env_path = base_dir / ".env"
        load_dotenv(dotenv_path=env_path)

    def get_interval_data(self, well_name: str, start_depth: float, end_depth: float) -> pd.DataFrame:
        """
        Retrieves downhole time-series logs for a specific depth window.
        Uses parameterized queries to prevent SQL injection vulnerabilities.
        """
        conn = sqlite3.connect(str(self.db_path))
        
        query = """
        WITH interval_times AS (
            SELECT timestamp 
            FROM time_data t
            JOIN curve_catalog c ON t.curve_id = c.curve_id
            JOIN wells w ON t.well_id = w.well_id
            WHERE w.well_name = ? 
              AND c.canonical_mnem = 'HOLE_MD'
              AND t.value BETWEEN ? AND ?
        )
        SELECT t.timestamp, c.canonical_mnem as mnemonic, t.value
        FROM time_data t
        JOIN curve_catalog c ON t.curve_id = c.curve_id
        JOIN wells w ON t.well_id = w.well_id
        WHERE w.well_name = ? 
          AND t.timestamp IN (SELECT timestamp FROM interval_times)
        """
        
        try:
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(well_name, start_depth, end_depth, well_name)
            )
            
            if df.empty:
                return pd.DataFrame()
                
            return df.pivot(index='timestamp', columns='mnemonic', values='value')
            
        except sqlite3.Error as error:
            logging.error(f"❌ Database syntax error during interval lookup: {error}")
            return pd.DataFrame()
            
        finally:
            conn.close()

    def evaluate_efficiency(self, well_name: str = None, current_depth: float = None, step: float = 40.0):
        """
        Compares current drilling parameters against the previous interval benchmark.
        Automatically isolates the absolute latest chronologically active well, 
        filtering strictly for valid bottom-hole excavation state (ROP > 0 AND WOB > 0)
        referenced via absolute 'HOLE_MD'.
        """
        if not well_name or not current_depth:
            logging.info("Searching database for the most recent active drilling operation context...")
            
            if not self.db_path.exists():
                logging.error(f"❌ Database file not found at expected location: {self.db_path}")
                return

            conn = sqlite3.connect(str(self.db_path))
            cur = conn.cursor()
            
            # ROBUST RIG-STATE DRILLING MACHINE (SQL Pivot Strategy):
            # 1. Finds the latest well ID by absolute chronology.
            # 2. Reconstructs channels per timestamp and filters for active On-Bottom Drilling (ROP > 0.5 and WOB > 0.5).
            query_latest = """
                WITH target_well AS (
                    SELECT well_id 
                    FROM time_data 
                    ORDER BY timestamp DESC 
                    LIMIT 1
                ),
                pivoted_telemetry AS (
                    SELECT 
                        t.timestamp,
                        t.well_id,
                        MAX(CASE WHEN c.canonical_mnem = 'HOLE_MD' THEN t.value END) as hole_depth,
                        MAX(CASE WHEN c.canonical_mnem IN ('ROP', 'ROP_AVG') THEN t.value END) as rop_val,
                        MAX(CASE WHEN c.canonical_mnem IN ('WOB', 'BWAB-T') THEN t.value END) as wob_val
                    FROM time_data t
                    JOIN curve_catalog c ON t.curve_id = c.curve_id
                    WHERE t.well_id = (SELECT well_id FROM target_well)
                    GROUP BY t.timestamp, t.well_id
                )
                SELECT w.well_name, MAX(pt.hole_depth)
                FROM pivoted_telemetry pt
                JOIN wells w ON pt.well_id = w.well_id
                WHERE pt.rop_val > 0.5 
                  AND pt.wob_val > 0.5
                  AND pt.hole_depth IS NOT NULL;
            """
            try:
                cur.execute(query_latest)
                res = cur.fetchone()
                if res and res[0] and res[1]:
                    well_name = res[0]
                    current_depth = res[1]
                    logging.info(f"🔄 Rig Operational State: ON-BOTTOM DRILLING DETECTED")
                    logging.info(f"🔄 Target Resolved: Well '{well_name}' | Max Active Hole Depth: {current_depth:.1f}m")
                else:
                    logging.error("❌ Context Auto-Detection failed. No active drilling records (ROP & WOB > 0.5) found for the latest well.")
                    return
            except sqlite3.Error as error:
                logging.error(f"❌ Database error during dynamic rig state resolution: {error}")
                return
            finally:
                conn.close()

        s_now, e_now = current_depth - step, current_depth
        s_prev, e_prev = s_now - step, s_now
        
        df_now = self.get_interval_data(well_name, s_now, e_now)
        df_prev = self.get_interval_data(well_name, s_prev, e_prev)
        
        if df_now.empty or df_prev.empty:
            logging.warning(f"⚠️ Insufficient operational logging points within depth slices for well: {well_name}")
            return

        def _get_interval_medians(df: pd.DataFrame) -> dict:
            return {
                'rop': df.get('ROP_AVG', df.get('ROP', pd.Series([0]))).median(),
                'mse': df.get('MSE', pd.Series([0])).median(),
                'flow': df.get('FLOW_LMIN', pd.Series([0])).median(),
                'spp': df.get('SPP_BAR', pd.Series([0])).median(),
                'wob': df.get('BWAB-T', df.get('WOB', pd.Series([0]))).median(),
                'rpm': df.get('RPM_SURF', df.get('RPM', pd.Series([0]))).median(),
                'ss': df.get('DHT001_TIME_IN_SEVERE_STICK_SLIP', pd.Series([0])).mean()
            }

        m_now = _get_interval_medians(df_now)
        m_prev = _get_interval_medians(df_prev)

        delta_rop = ((m_now['rop'] - m_prev['rop']) / m_prev['rop'] * 100) if m_prev['rop'] > 0 else 0
        delta_mse = ((m_now['mse'] - m_prev['mse']) / m_prev['mse'] * 100) if m_prev['mse'] > 0 else 0

        print(f"\n{'='*70}")
        print(f"📊 DRILLING EFFICIENCY COMPARATIVE REPORT: {well_name}")
        print(f"Interval Windows: [{s_prev:.1f}m - {s_now:.1f}m] vs [{s_now:.1f}m - {e_now:.1f}m]")
        print(f"{'-'*70}")
        print(f"🚀 ROP:        {m_prev['rop']:.2f} -> {m_now['rop']:.2f} m/h ({delta_rop:+.1f}%)")
        print(f"💎 MSE:        {m_prev['mse']:.2f} -> {m_now['mse']:.2f} bar ({delta_mse:+.1f}%)")
        print(f"🥤 Flow Rate:  {m_prev['flow']:.0f} -> {m_now['flow']:.0f} L/min")
        print(f"💉 SPP:        {m_prev['spp']:.1f} -> {m_now['spp']:.1f} bar")
        print(f"🌀 Stick-Slip: {m_prev['ss']:.2f} -> {m_now['ss']:.2f}")
        print(f"🌀 WOB:        {m_now['wob']:.1f} Tons")
        print(f"🌀 RPM:        {m_now['rpm']:.0f} rpm")
        print(f"{'='*70}")

        ai_prompt = f"""
DRILLING SYSTEM PERFORMANCE CONTEXT:
Analyze engineering parameters and optimization opportunities for Well {well_name}.
Comparative segment breakdown: Benchmark [{s_prev:.1f}m - {s_now:.1f}m] vs Active [{s_now:.1f}m - {e_now:.1f}m]:
- ROP (Rate of Penetration): {m_prev['rop']:.1f} -> {m_now['rop']:.1f} m/h
- MSE (Mechanical Specific Energy): {m_prev['mse']:.1f} -> {m_now['mse']:.1f} bar
- Mud Flow Rate: {m_prev['flow']:.0f} -> {m_now['flow']:.0f} L/min
- Standpipe Pressure (SPP): {m_prev['spp']:.1f} -> {m_now['spp']:.1f} bar
- Operating Setpoints (Active): WOB: {m_now['wob']:.1f} Metric Tons | Surface RPM: {m_now['rpm']:.0f}
- Downhole Vibration Severity Index (Severe Stick-Slip): {m_now['ss']:.2f}

REQUIRED DISCIPLINARY ACTIONS:
1. DIAGNOSTIC EVALUATION: Assess whether the ROP variance indicates a lithological formation change (boundary transition) or downhole mechanical inefficiency.
2. HYDRAULIC CLEANING AUDIT: Determine if current volumetric flow rates (L/min) and system backpressure (bar) provide sufficient annular velocity to prevent cutting beds for an ROP of {m_now['rop']:.1f} m/h.
3. ADVISORY RECOMMENDATIONS: Suggest targeted structural adjustments to WOB or RPM setpoints to mitigate dysfunctions and optimize Mechanical Specific Energy (MSE).
"""
        
        logging.info("Sending structured engineering payload to generative AI model pipeline...")

        try:
            from ai_consultant import AIConsultant
            ai = AIConsultant()
            recommendation = ai.generate_efficiency_summary(ai_prompt)
            
            print("\n🤖 AI REAL-TIME ADVISORY ACTION PLAN:")
            print(recommendation)
            
        except Exception as e:
            logging.error(f"❌ Core AI reasoning system module unavailable: {e}")


if __name__ == "__main__":
    evaluator = EfficiencyEvaluator()
    evaluator.evaluate_efficiency()