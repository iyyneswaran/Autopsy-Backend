import os
import httpx
from typing import List, Dict, Any
from app.core.logger import logger

# Note: In a true production environment, FAISS or Qdrant would be initialized here.
# For this architecture implementation, we mock the vector embedding retrieval 
# but implement the full RAG conversational pipeline architecture.

class InvestigatorCopilot:
    """
    Conversational AI Copilot for investigators.
    Uses RAG (Retrieval-Augmented Generation) to ground Gemma responses
    in factual case evidence, timelines, and hypotheses.
    """
    
    def __init__(self):
        self.api_key = os.getenv("FEATHERLESS_API_KEY", "mock-key")
        self.base_url = "https://api.featherless.ai/v1"
        self.model = "google/gemma-3-pro"
        
    async def _retrieve_context(self, case_id: str, query: str) -> str:
        """
        Retrieves relevant forensic context from the vector database (FAISS/Qdrant).
        (Mocked retrieval for architectural demonstration).
        """
        # In production:
        # query_embedding = embed_text(query)
        # results = vector_db.search(query_embedding, filter={"case_id": case_id})
        # return format_results(results)
        
        return "Autopsy report indicates postmortem interval of 4-6 hours. Liver temp was 90F. CCTV shows suspect entering at 23:45."

    async def answer_question(self, case_id: str, query: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        Answers investigator queries using contextual memory and forensic RAG.
        """
        if conversation_history is None:
            conversation_history = []
            
        context = await self._retrieve_context(case_id, query)
        
        system_prompt = f"""
You are an expert AI forensic investigator copilot named 'Atopsy'.
Your job is to assist human investigators by answering questions based strictly on the retrieved case evidence.
Do not hallucinate. If the answer is not in the evidence, say so.
Provide explainable, objective, and scientifically sound forensic reasoning.

Retrieved Context for Case {case_id}:
{context}
"""
        
        messages = [{"role": "system", "content": system_prompt}]
        
        # Append sliding window of conversation history for contextual memory
        for msg in conversation_history[-5:]:  # Keep last 5 turns
            messages.append(msg)
            
        messages.append({"role": "user", "content": query})
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.4
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()
                
                result = response.json()
                answer = result["choices"][0]["message"]["content"]
                
                return {
                    "success": True,
                    "answer": answer,
                    "cited_evidence": ["doc_autopsy_1", "cctv_meta_2"] # Mocked citations
                }
                
        except Exception as e:
            logger.error(f"Copilot failed to answer query: {e}")
            return {
                "success": False,
                "answer": "I am currently unable to reach the AI reasoning engine to process your request.",
                "error": str(e)
            }

copilot_engine = InvestigatorCopilot()
