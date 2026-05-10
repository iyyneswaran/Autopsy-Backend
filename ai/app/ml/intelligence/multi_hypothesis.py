import json
import httpx
import os
from typing import List, Dict, Any
from app.core.logger import logger

class MultiHypothesisEngine:
    """
    Generates competing investigation hypotheses (e.g. Homicide vs. Suicide)
    using the Featherless AI API (Google Gemma reasoning).
    Evaluates evidence permutations using Bayesian-style weighting.
    """
    
    def __init__(self):
        self.api_key = os.getenv("FEATHERLESS_API_KEY", "mock-key")
        self.base_url = "https://api.featherless.ai/v1"
        self.model = "google/gemma-3-pro"
        
    async def generate_hypotheses(self, case_evidence: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Takes correlated case evidence and generates competing hypotheses.
        Returns a structured JSON response containing:
        - hypothesis_type
        - confidence_score
        - supporting_evidence
        - contradicting_evidence
        - missing_evidence_needed
        """
        prompt = self._build_prompt(case_evidence)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a world-class AI forensic reasoning engine. Your task is to analyze autopsy and investigation data to generate competing hypotheses. Output valid JSON strictly matching the requested schema."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.3
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60.0
                )
                response.raise_for_status()
                
                result = response.json()
                content = result["choices"][0]["message"]["content"]
                
                hypotheses = json.loads(content)
                return hypotheses.get("hypotheses", [])
                
        except Exception as e:
            logger.error(f"Failed to generate multi-hypothesis reasoning: {e}")
            return [
                {
                    "hypothesis_type": "Unknown",
                    "confidence_score": 0.0,
                    "explanation": f"Reasoning engine failed: {str(e)}",
                    "supporting_evidence": [],
                    "contradicting_evidence": []
                }
            ]

    def _build_prompt(self, case_evidence: Dict[str, Any]) -> str:
        """Constructs the forensic reasoning chain-of-thought prompt."""
        
        evidence_str = json.dumps(case_evidence, indent=2)
        
        return f"""
Analyze the following correlated forensic evidence and generate at least 3 competing hypotheses regarding the cause and manner of death (e.g., Homicide, Suicide, Accidental, Natural, Environmental).

Evidence Data:
{evidence_str}

Use chain-of-thought reasoning internally to weigh the evidence. 
Respond ONLY with a JSON object in this exact schema:

{{
  "hypotheses": [
    {{
      "hypothesis_type": "Homicide (Staged Suicide)",
      "confidence_score": 0.85,
      "explanation": "Brief explanation of why this hypothesis is viable based on forensic rules.",
      "supporting_evidence": ["Evidence ID 1", "Evidence ID 2"],
      "contradicting_evidence": ["Evidence ID 3"],
      "missing_evidence_needed": ["Toxicology report", "CCTV of rear entrance"]
    }}
  ]
}}
"""

hypothesis_engine = MultiHypothesisEngine()
