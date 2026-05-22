import os
import sys
import logging
from google import genai
from google.genai import types
from dotenv import load_dotenv

# Initialize priority logging bootstrap for analytical telemetry
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Load environmental workspace secrets from the root hide file (.env)
load_dotenv()

class AIConsultant:
    """
    Production-Grade Drilling Engineering Analytics Agent.
    
    Leverages Google's GenAI SDK framework to process high-frequency 
    time-series interval metrics, synthesizing advanced rock mechanics, 
    hydraulics behavior, and optimization paradigms into executive operational summaries.
    """
    def __init__(self):
        """
        Initializes the generative engine client and validates infrastructure state.
        Authenticates implicitly via the global OS environment dictionary.
        """
        self.api_key = os.environ.get("GEMINI_API_KEY")
        
        # Defensive assertion layer to preemptively catch credentials pipeline failures
        if not self.api_key:
            logging.critical(
                "❌ CRITICAL: 'GEMINI_API_KEY' environment variable not found in current context. "
                "Generative AI execution thread terminated."
            )
            raise ValueError("Missing GEMINI_API_KEY environment variable.")
            
        # The Client topology automatically binds to os.environ["GEMINI_API_KEY"] internally
        self.client = genai.Client()
        self.model_name = "gemini-2.5-flash"

    def generate_efficiency_summary(self, payload_text: str) -> str:
        """
        Submits structured well interval delta datasets to the reasoning model.
        
        Applies strict engineering constraints and system guidelines to generate 
        actionable insights detailing ROP enhancement vs. MSE reduction anomalies.
        
        Args:
            payload_text (str): Raw string containing compiled drilling performance statistics.
            
        Returns:
            str: Specialized technical interpretation and downhole performance review.
        """
        system_instruction = (
            "You are an expert Senior Drilling Engineer and Downhole Rock Mechanics Analyst. "
            "Review the provided drilling interval comparative data. Synthesize a concise, "
            "highly professional technical review focusing on parameter optimization, MSE reduction, "
            "hydraulic energy distribution efficiency, and explicit operational recommendations for subsequent runs."
        )

        try:
            logging.info("Initiating structural content generation sequence via Gemini Client...")
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=payload_text,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2,  # Low temperature restricts hallucinations, forcing strictly factual reporting
                    max_output_tokens=10000
                )
            )
            return response.text
            
        except Exception as error:
            logging.error(f"❌ Core execution failed inside GenAI reasoning subsystem module: {str(error)}")
            raise error

# --- EXECUTION RUNTIME TEST LAYER ---
if __name__ == "__main__":
    # Test payload mimicking the metric output of your telemetry evaluator pipeline
    sample_payload = """
    📊 DRILLING EFFICIENCY COMPARATIVE REPORT: 25_2-D-6 Y3
    Interval Windows: [6185.4m - 6225.4m] vs [6225.4m - 6265.4m]
    ----------------------------------------------------------------------
    🚀 ROP:        103.15 -> 110.26 m/h (+6.9%)
    💎 MSE:        1775.10 -> 1626.61 bar (-8.4%)
    🥤 Flow Rate:  4194 -> 4192 L/min
    💉 SPP:        10.7 -> 11.2 bar
    🌀 Stick-Slip: 0.00 -> 0.00
    🌀 WOB:        11.6 Tons
    🌀 RPM:        139 rpm
    """
    
    print("⏳ Executing local integration sanity check...")
    try:
        consultant = AIConsultant()
        report_insights = consultant.generate_efficiency_summary(sample_payload)
        print("\n" + "="*70 + "\n🤖 LOCAL VERIFICATION COMPLETED - REAL-TIME REPORT OUTPUT:\n" + "="*70)
        print(report_insights)
    except Exception as e:
        print(f"\n⚠️ Local validation skipped or halted: {e}")