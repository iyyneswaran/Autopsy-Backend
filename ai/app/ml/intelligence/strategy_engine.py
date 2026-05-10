from typing import List, Dict, Any
from app.core.logger import logger

class InvestigationStrategyEngine:
    """
    Investigation Intelligence Orchestration Layer.
    Prioritizes leads, recommends next actions, and identifies critical evidence gaps.
    """
    
    def analyze_investigation_state(
        self, 
        hypotheses: List[Dict[str, Any]], 
        timeline_gaps: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyzes the current state of hypotheses and temporal gaps to generate
        actionable next steps for human investigators.
        """
        logger.info("Generating investigation strategy and lead prioritization.")
        
        recommendations = []
        critical_gaps = []
        
        # 1. Analyze Timeline Gaps
        for gap in timeline_gaps:
            if gap.get("duration_hours", 0) > 2:
                critical_gaps.append({
                    "type": "temporal_gap",
                    "description": f"Unaccounted time window between {gap.get('start')} and {gap.get('end')}."
                })
                recommendations.append({
                    "action": "Acquire CCTV",
                    "priority": "HIGH",
                    "target": "Surrounding area of crime scene",
                    "reasoning": f"Need to close a {gap.get('duration_hours')} hour timeline gap."
                })

        # 2. Analyze Hypotheses and Missing Evidence
        best_hypothesis = None
        highest_score = 0.0
        
        for hyp in hypotheses:
            score = hyp.get("confidence_score", 0.0)
            if score > highest_score:
                highest_score = score
                best_hypothesis = hyp
                
            missing_evidence = hyp.get("missing_evidence_needed", [])
            for item in missing_evidence:
                # Deduplicate recommendations
                if not any(r.get("action") == "Acquire Evidence" and r.get("target") == item for r in recommendations):
                    recommendations.append({
                        "action": "Acquire Evidence",
                        "priority": "HIGH" if score > 0.6 else "MEDIUM",
                        "target": item,
                        "reasoning": f"Required to validate or disprove hypothesis: {hyp.get('hypothesis_type')}"
                    })

        # Sort recommendations by priority
        priority_map = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
        recommendations.sort(key=lambda x: priority_map.get(x["priority"], 0), reverse=True)

        return {
            "primary_hypothesis": best_hypothesis.get("hypothesis_type") if best_hypothesis else "Inconclusive",
            "highest_confidence": highest_score,
            "critical_gaps": critical_gaps,
            "recommended_actions": recommendations,
            "investigation_status": "Active - Requires Lead Follow-up" if recommendations else "Analysis Complete"
        }

strategy_engine = InvestigationStrategyEngine()
