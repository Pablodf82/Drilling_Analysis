import os
from google import genai
from google.genai import types

class AIConsultant:
    def __init__(self):
        # La API Key se lee de forma segura desde las variables de entorno del sistema
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("❌ ERROR: No se encontró la variable de entorno 'GEMINI_API_KEY'")
        
        # Inicializamos el cliente oficial de Gemini
        self.client = genai.Client(api_key=api_key)
        # Usamos gemini-2.5-flash: es ultra rápido y perfecto para análisis de datos estructurados
        self.model_name = "gemini-2.5-flash"

    def ask_recommendation(self, technical_prompt):
        """Envía los datos de perforación a la IA con un rol de ingeniero experto."""
        
        # Definimos las instrucciones del sistema (System Prompt) para moldear el comportamiento de la IA
        system_instruction = """
        Eres un Ingeniero Senior de Perforación y un experto mundial en Optimización de ROP, 
        Análisis de MSE (Mechanical Specific Energy) e Hidráulica de Perforación.
        Tu trabajo es analizar datos comparativos de tramos de 40 metros y proveer diagnósticos 
        críticos, cortos y acciones operativas de inmediato para el perforador (Driller).
        SÉ DIRECTO. No uses introducciones corporativas ni saludos. Ve al grano técnicamente.
        """

        try:
            print("🧠 Consultando con el Asesor de IA (Gemini)...")
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=technical_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2, # Temperatura baja para que sea matemático y preciso, no creativo
                    max_output_tokens=10000
                )
            )
            return response.text
        except Exception as e:
            return f"❌ Error en la conexión con la API: {str(e)}"