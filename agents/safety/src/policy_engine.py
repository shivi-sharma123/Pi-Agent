import logging
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class PolicyEngine:
    """
    Evaluates proposed remediation actions against rules.
    Returns (is_approved, reason).
    """
    
    def __init__(self):
        # Basic hardcoded rules based on user prompt risk constraints.
        self.banned_actions = {
            # type: [services that cannot have this action auto-approved]
            "sql_execute": ["postgres-orders", "postgres-payments", "postgres-agents"],
            "container_restart": ["postgres-agents"], # Never restart the agent DB
        }
        
    def evaluate(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        if not action:
            return False, "Empty action payload"
            
        action_type = action.get("type", "unknown")
        params = action.get("params", {})
        target = params.get("target") or params.get("target_db") or "unknown"
        
        # Rule 1: Human Approval flag explicitly set in the runbook?
        if action.get("approval_required") is True:
            return False, "Runbook explicitly requires human approval for this action"
            
        # Rule 2: High risk actions never auto-approved
        if action.get("risk") == "high":
            return False, "High-risk actions require human approval"
            
        # Rule 3: Hardcoded Banned Actions on Core Infrastructure
        if action_type in self.banned_actions:
            if target in self.banned_actions[action_type]:
                return False, f"Action '{action_type}' targeting '{target}' is banned from auto-approval"
                
        # Rule 4: Scale operations above limits?
        if action_type == "container_scale":
            replicas = int(params.get("replicas", 0))
            max_replicas = int(params.get("max_replicas", 5))
            if replicas > max_replicas:
                return False, f"Requested replicas ({replicas}) exceeds hard limit ({max_replicas})"
                
        return True, "Passed all safety policies"
