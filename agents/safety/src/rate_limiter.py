import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class RateLimiter:
    """
    Prevents the agent from entering a retry loop (e.g., repeatedly restarting a container).
    Uses a simple in-memory history log.
    """
    
    def __init__(self, limit_per_hour: int = 3, cooldown_mins: int = 15):
        self.action_history = []
        self.limit_per_hour = limit_per_hour
        self.cooldown_mins = cooldown_mins
        
    def _fingerprint(self, action: Dict[str, Any]) -> str:
        # We hash the type and target to identify "identical" actions
        action_type = action.get("type", "")
        params = action.get("params", {})
        target = params.get("target") or params.get("target_db") or ""
        
        raw = f"{action_type}:{target}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def check(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """Returns True if the action is ALLOWED, False if Rate Limited."""
        
        fingerprint = self._fingerprint(action)
        now = datetime.utcnow()
        
        # Prune old history
        cutoff = now - timedelta(hours=1)
        self.action_history = [x for x in self.action_history if x["timestamp"] > cutoff]
        
        # Find matching past actions
        matches = [x for x in self.action_history if x["fingerprint"] == fingerprint]
        
        # 1. Total attempts check
        if len(matches) >= self.limit_per_hour:
            return False, f"Rate limit exceeded: executed {len(matches)} times in the last hour."
            
        # 2. Cooldown check
        if matches:
            last_execution = max(x["timestamp"] for x in matches)
            if (now - last_execution).total_seconds() < (self.cooldown_mins * 60):
                return False, f"In cooldown period: executed recently at {last_execution.isoformat()}"
                
        return True, "Rate limit passed"
        
    def record(self, action: Dict[str, Any]):
        """Records a successfully approved action to update limits."""
        self.action_history.append({
            "fingerprint": self._fingerprint(action),
            "timestamp": datetime.utcnow(),
            "action": action
        })
