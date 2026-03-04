import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class HumanApprovalGateway:
    """
    Formats the final safety response. In a real environment, this handles
    publishing interactive cards to Slack/Dashboard to wait for human clicks.
    For MVP, we just formulate the JSON response.
    """
    
    def format_approval_request(
        self,
        incident_id: str,
        diagnosis: Dict[str, Any],
        action: Dict[str, Any],
        policy_reason: str,
        blast_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generates the payload that would be sent to a human dashboard for review.
        """
        request_payload = {
            "incident_id": incident_id,
            "status": "pending_human_approval",
            "reason": policy_reason,
            "proposed_action": action,
            "blast_radius": blast_info,
            "context": {
                "root_cause_service": diagnosis.get("root_cause", {}).get("service"),
                "root_cause_category": diagnosis.get("root_cause", {}).get("category"),
            }
        }
        return request_payload
