import json
import httpx
import os
from typing import List, Dict, Any
from app.core.logger import logger

class ForensicNLPProcessor:
    """
    Advanced Medical NER and Forensic Entity Extractor.
    Utilizes Google Gemma (via Featherless AI) to extract structured
    forensic ontology mappings from unstructured autopsy reports.
    """
    
    def __init__(self):
        self.api_key = os.getenv("FEATHERLESS_API_KEY", "mock-key")
        self.base_url = "https://api.featherless.ai/v1"
        self.model = "google/gemma-3-pro"
        
    async def extract_medical_entities(self, text: str) -> Dict[str, Any]:
        """
        Extracts structured forensic entities including cause of death, 
        injuries, body conditions, toxins, organs, and wound characteristics.
        """
        prompt = f"""
You are an expert Forensic Pathologist AI. Extract all relevant forensic data from the following autopsy/medical text.
Preserve forensic explainability and note any uncertainties.

Text:
{text}

Output ONLY a valid JSON object matching this schema:
{{
  "cause_of_death": "string",
  "manner_of_death": "string or null",
  "estimated_postmortem_interval": "string or null",
  "victim_demographics": {{
    "age": "string",
    "sex": "string"
  }},
  "injuries": [
    {{
      "type": "string",
      "location": "string",
      "severity": "string",
      "characteristics": "string"
    }}
  ],
  "toxins_detected": ["string"],
  "postmortem_indicators": {{
    "rigor_mortis": "string",
    "lividity": "string",
    "decomposition_stage": "string"
  }},
  "environmental_observations": ["string"]
}}
"""
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You extract structured medical and forensic entities. Output valid JSON only."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=45.0
                )
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                return json.loads(content)
                
        except Exception as e:
            logger.error(f"Failed to extract forensic entities via Featherless API: {e}")
            return {
                "error": "NLP Extraction Failed",
                "message": str(e)
            }

forensic_nlp_processor = ForensicNLPProcessor()

def extract_medical_entities(text: str) -> Dict[str, Any]:
    """Wrapper function to match previous API usage structure."""
    import asyncio
    
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
        
    if loop and loop.is_running():
        # In case we're already running in an async context but this sync function is called, 
        # using asyncio.run() would crash. Best to use a new event loop or create_task.
        # But uvicorn threadpool calls sync functions.
        # Safe fallback for standard sync thread calling async:
        pass
        
    return asyncio.run(forensic_nlp_processor.extract_medical_entities(text))