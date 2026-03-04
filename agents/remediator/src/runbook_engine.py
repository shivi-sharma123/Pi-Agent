import os
import yaml
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class RunbookEngine:
    """
    Loads YAML runbooks from disk and matches incoming Root Cause 
    Analyses (RCAs) to specific executable action plans.
    """
    
    def __init__(self, runbook_dir: str = None):
        if runbook_dir is None:
            # Default to the 'runbooks' folder natively beside 'src'
            runbook_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "runbooks"))
        self.runbook_dir = runbook_dir
        self.runbooks = self._load_runbooks()
        
    def _load_runbooks(self) -> dict:
        loaded = {}
        if not os.path.exists(self.runbook_dir):
            logger.warning(f"Runbook directory {self.runbook_dir} does not exist.")
            return loaded
            
        for filename in os.listdir(self.runbook_dir):
            if filename.endswith((".yml", ".yaml")):
                path = os.path.join(self.runbook_dir, filename)
                try:
                    with open(path, "r") as f:
                        rb = yaml.safe_load(f)
                        if rb and "id" in rb:
                            loaded[rb["id"]] = rb
                            logger.info(f"Loaded runbook: {rb['id']}")
                except Exception as e:
                    logger.error(f"Failed to load runbook {path}: {e}")
        return loaded
        
    def find_match(self, diagnosis: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Matches a diagnosis (e.g. category='memory_leak') to the first applicable runbook.
        """
        rc = diagnosis.get("root_cause", {})
        category = rc.get("category")
        confidence = rc.get("confidence", 0)
        
        if not category:
            logger.warning("Diagnosis missing root_cause category")
            return None
            
        for rb_id, rb in self.runbooks.items():
            matches = rb.get("matches", {})
            
            # Category match
            if matches.get("root_cause_category") == category:
                # Confidence match
                min_conf = matches.get("confidence_minimum", 0)
                if confidence >= min_conf:
                    logger.info(f"Matched diagnosis to runbook: {rb_id}")
                    return rb
                    
        logger.info(f"No matching runbook found for category='{category}'")
        return None
        
    def render_action(self, action: Dict[str, Any], diagnosis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Interpolates template variables like `{{diagnosis.root_cause.service}}` in the action params.
        """
        import copy
        import re
        
        rendered = copy.deepcopy(action)
        params = rendered.get("params", {})
        
        # Super simple {{key}} interpolator for MVP
        for k, v in params.items():
            if isinstance(v, str) and "{{" in v:
                if "{{diagnosis.root_cause.service}}" in v:
                    service = diagnosis.get("root_cause", {}).get("service", "unknown")
                    params[k] = v.replace("{{diagnosis.root_cause.service}}", service)
                    
        rendered["params"] = params
        return rendered
