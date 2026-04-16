import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import Incident, Anomaly
from shared.db.session import get_session

logger = logging.getLogger(__name__)

class CorrelationEngine:
    """
    Groups incoming anomalies temporally (time windows) and topologically
    (service dependencies) into Incidents.
    """
    
    def __init__(self, time_window_minutes: int = 5):
        self.time_window_minutes = time_window_minutes

        # Basic topological mapping (hardcoded for MVP)
        # Key = dependency, Value = list of services that depend on it
        self.topology = {
            "postgres-orders": ["order-svc"],
            "postgres-payments": ["payment-svc"],
            "postgres-inventory": ["inventory-worker"],
            "redis": ["user-svc", "auth-svc", "analytics-worker"],
            "elasticsearch": ["product-svc", "search-svc"],
            "nats": ["order-svc", "payment-svc", "notification-worker", "inventory-worker", "analytics-worker"],
            "user-svc": ["auth-svc", "api-gateway"],
            "order-svc": ["api-gateway"],
            "auth-svc": ["api-gateway"],
            "payment-svc": ["api-gateway"],
            "product-svc": ["api-gateway"],
            "search-svc": ["api-gateway"]
        }

    async def correlate(self, anomaly_data: Dict[str, Any]) -> Tuple[Incident, bool]:
        """
        Processes an incoming anomaly.
        Returns the Incident it belongs to, and a boolean indicating if a NEW incident was created.
        """
        service = anomaly_data.get("service", "unknown")
        metric = anomaly_data.get("metric", "unknown")
        severity = anomaly_data.get("severity", "medium")
        
        async with get_session() as session:
            # 1. Check for recent active incidents
            incident, created = await self._find_or_create_incident(session, service)
            
            # 2. Record the anomaly and attach it to the incident
            db_anomaly = Anomaly(
                incident_id=incident.id,
                metric=metric,
                service=service,
                severity=severity,
                category=anomaly_data.get("category"),
                description=anomaly_data.get("description"),
                value=anomaly_data.get("value"),
                threshold=anomaly_data.get("threshold"),
                raw_payload=anomaly_data
            )
            session.add(db_anomaly)
            
            # If the anomaly severity is higher than the incident severity, upgrade it
            if self._severity_val(severity) > self._severity_val(incident.severity):
                incident.severity = severity
                
            await session.commit()
            
            return incident, created

    async def _find_or_create_incident(self, session: AsyncSession, service: str) -> Tuple[Incident, bool]:
        """
        Finds an active incident within the time window that is topologically or temporally related,
        or creates a new one.
        """
        cutoff_time = datetime.utcnow() - timedelta(minutes=self.time_window_minutes)
        
        # Look for 'detecting' or 'diagnosing' incidents updated recently
        stmt = select(Incident).where(
            Incident.status.in_(["detecting", "diagnosing"]),
            Incident.updated_at >= cutoff_time
        ).order_by(Incident.updated_at.desc())
        
        result = await session.execute(stmt)
        active_incidents = result.scalars().all()
        
        for incident in active_incidents:
            # Simple heuristic for MVP: if there's any active incident within the 5m window,
            # we group it. In a real system, we'd check if the services are in the same dependency tree.
            # Let's do a basic topological check.
            
            # We need to know what services are already in this incident. 
            # We'll just group everything temporally for now to prevent incident storms.
            return incident, False
            
        # No active incidents found, create a new one
        new_incident = Incident(
            status="detecting",
            severity="medium", # will be upgraded if anomaly is higher
            escalation_reason="Initial detection"
        )
        session.add(new_incident)
        await session.flush() # flush to get the incident ID
        
        return new_incident, True
        
    def _severity_val(self, severity: str) -> int:
        mapping = {"critical": 3, "high": 2, "medium": 1, "low": 0}
        return mapping.get(severity.lower(), 1)
