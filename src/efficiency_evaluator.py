import sqlite3
import pandas as pd

class EfficiencyEvaluator:
    def __init__(self, db_path="data_base/drilling.db"):
        self.db_path = db_path

    def get_interval_data(self, well_name, start_depth, end_depth):
        conn = sqlite3.connect(self.db_path)
        query = f"""
        WITH interval_times AS (
            SELECT timestamp FROM time_data t
            JOIN curve_catalog c ON t.curve_id = c.curve_id
            JOIN wells w ON t.well_id = w.well_id
            WHERE w.well_name = '{well_name}' AND c.canonical_mnem = 'HOLE_MD'
              AND t.value BETWEEN {start_depth} AND {end_depth}
        )
        SELECT t.timestamp, c.canonical_mnem as mnemonic, t.value
        FROM time_data t
        JOIN curve_catalog c ON t.curve_id = c.curve_id
        JOIN wells w ON t.well_id = w.well_id
        WHERE w.well_name = '{well_name}' AND t.timestamp IN (SELECT timestamp FROM interval_times)
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df.pivot(index='timestamp', columns='mnemonic', values='value') if not df.empty else pd.DataFrame()

    def evaluate_efficiency(self, well_name, current_depth, step=40):
        s_now, e_now = current_depth - step, current_depth
        s_prev, e_prev = s_now - step, s_now
        
        df_now = self.get_interval_data(well_name, s_now, e_now)
        df_prev = self.get_interval_data(well_name, s_prev, e_prev)
        
        if df_now.empty or df_prev.empty:
            print(f"❌ Datos insuficientes para comparar tramos en {well_name}")
            return

        def get_metrics(df):
            return {
                'rop': df.get('ROP_AVG', df.get('ROP', pd.Series([0]))).median(),
                'mse': df.get('MSE', pd.Series([0])).median(),
                'flow': df.get('FLOW_LMIN', pd.Series([0])).median(),
                'spp': df.get('SPP_BAR', pd.Series([0])).median(),
                'wob': df.get('BWAB-T', df.get('WOB', pd.Series([0]))).median(),
                'rpm': df.get('RPM_SURF', df.get('RPM', pd.Series([0]))).median(),
                'ss': df.get('DHT001_TIME_IN_SEVERE_STICK_SLIP', pd.Series([0])).mean()
            }

        m_now = get_metrics(df_now)
        m_prev = get_metrics(df_prev)

        # Cálculo de variaciones (Deltas)
        delta_rop = ((m_now['rop'] - m_prev['rop']) / m_prev['rop'] * 100) if m_prev['rop'] > 0 else 0
        delta_mse = ((m_now['mse'] - m_prev['mse']) / m_prev['mse'] * 100) if m_prev['mse'] > 0 else 0

        # Mostrar Reporte Comparativo Técnico en Consola
        print(f"\n{'='*65}")
        print(f"📊 REPORTE DE EFICIENCIA COMPARATIVO: {well_name}")
        print(f"Intervalos: [{s_prev}-{s_now}m] vs [{s_now}-{e_now}m]")
        print(f"{'-'*65}")
        print(f"🚀 ROP:        {m_prev['rop']:.2f} -> {m_now['rop']:.2f} m/h ({delta_rop:+.1f}%)")
        print(f"💎 MSE:        {m_prev['mse']:.2f} -> {m_now['mse']:.2f} bar ({delta_mse:+.1f}%)")
        print(f"🥤 Flow Rate:  {m_prev['flow']:.0f} -> {m_now['flow']:.0f} l/min")
        print(f"💉 SPP:        {m_prev['spp']:.1f} -> {m_now['spp']:.1f} bar")
        print(f"🌀 Stick-Slip: {m_prev['ss']:.2f} -> {m_now['ss']:.2f}")
        print(f"{'='*65}")

        # Construimos el prompt estructurado
        prompt_para_ia = f"""
CONTEXTO PARA IA:
Analiza el desempeño de perforación del Pozo {well_name}.
Comparativa de tramo {s_prev}-{s_now}m vs {s_now}-{e_now}m:
- ROP: {m_prev['rop']:.1f} -> {m_now['rop']:.1f} m/h
- MSE: {m_prev['mse']:.1f} -> {m_now['mse']:.1f} bar
- Flow Rate: {m_prev['flow']:.0f} -> {m_now['flow']:.0f} l/min
- SPP: {m_prev['spp']:.1f} -> {m_now['spp']:.1f} bar
- WOB actual: {m_now['wob']:.1f} t | RPM actual: {m_now['rpm']:.0f}
- severe_stick_slip_score: {m_now['ss']:.2f}

TAREA: 
1. Diagnostica si la variación de ROP es por un cambio litológico o por ineficiencia mecánica.
2. Determina si los parámetros hidráulicos actuales en l/min y bar garantizaran una óptima limpieza de fondo para {m_now['rop']:.1f} m/h.
3. Sugere ajustes precisos en WOB y RPM para estabilizar u optimizar el MSE.
"""
        
        print("\n📝 PROMPT ENVIADO A LA API:")
        print(f'"""{prompt_para_ia}"""')

        # --- CONEXIÓN AUTOMÁTICA CON LA API DE GEMINI ---
        try:
            from ai_consultant import AIConsultant
            ai = AIConsultant()
            recomendacion = ai.ask_recommendation(prompt_para_ia)
            
            print("\n🤖 RECOMENDACIÓN OPERATIVA DE LA IA:")
            print(recomendacion)
            
        except Exception as e:
            print(f"\n⚠️ Módulo de IA no disponible o sin API Key configurada. Detalle: {e}")

if __name__ == "__main__":
    evaluator = EfficiencyEvaluator()
    evaluator.evaluate_efficiency('25_2-D-3 Y1', 3540)