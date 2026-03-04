import logging
from typing import Dict, Any, Optional
from action_executor import ActionExecutor

logger = logging.getLogger(__name__)

class RollbackManager:
    """
    If verification fails, the Rollback Manager executes the defined
    rollback actions in reverse order to return the system to its initial state.
    """
    
    def __init__(self, action_executor: ActionExecutor):
        self.executor = action_executor
        
    def rollback(self, action: Dict[str, Any]) -> bool:
        """
        Attempts to rollback a specific action if a rollback procedure is defined.
        """
        rollback_def = action.get("rollback")
        if not rollback_def:
            logger.info(f"No rollback defined for action '{action.get('id')}'")
            return False
            
        logger.warning(f"Executing rollback for action '{action.get('id')}'...")
        ok, reason = self.executor.execute(rollback_def)
        
        if ok:
            logger.info(f"Rollback successful: {reason}")
            return True
        else:
            logger.error(f"Rollback failed: {reason}")
            return False
