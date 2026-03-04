import logging
import docker
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    Executes a concrete remediation action.
    Supports restarting containers, executing SQL (mocked), and circuit breaking (mocked).
    """
    
    def __init__(self):
        try:
            # We connect to the local docker socket to perform real actions
            self.client = docker.from_env()
        except docker.errors.DockerException as e:
            logger.warning(f"Could not connect to Docker socket, using dummy execution mode. Error: {e}")
            self.client = None
            
    def execute(self, action: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Executes a proposed action (assumed to be already approved).
        """
        try:
            action_type = action.get("type")
            params = action.get("params", {})
            
            if action_type == "container_restart":
                return self._restart_container(params.get("target"))
            elif action_type == "circuit_breaker":
                return self._trigger_circuit_breaker(params.get("target"), params.get("state"))
            else:
                return False, f"Unknown action type: {action_type}"
                
        except Exception as e:
            logger.exception("Failed to execute action")
            return False, str(e)
            
    def _restart_container(self, container_name: str) -> Tuple[bool, str]:
        if not container_name:
            return False, "Missing target container name"
            
        if not self.client:
            logger.info(f"DUMMY EXECUTION: Restarted container '{container_name}'")
            return True, "Executed in dummy mode"
            
        try:
            # Docker Python SDK looks for containers exactly matching the name
            # Because compose prefixes things, we'll do a partial match
            containers = self.client.containers.list(all=True)
            target = None
            for c in containers:
                if container_name in c.name:
                    target = c
                    break
                    
            if not target:
                return False, f"Container matching '{container_name}' not found"
                
            logger.info(f"Restarting container: {target.name}")
            target.restart(timeout=10)
            return True, f"Successfully restarted container '{target.name}'"
            
        except docker.errors.APIError as e:
            return False, f"Docker API error: {e}"

    def _trigger_circuit_breaker(self, target: str, state: str) -> Tuple[bool, str]:
        """
        Mock implementation. In reality, this would make an HTTP call to the API Gateway
        admin port or an Istio control plane to apply a circuit breaker.
        """
        logger.info(f"Triggering Circuit Breaker for {target} -> state: {state}")
        # Insert actual istio/envoy control logic here
        return True, "Successfully opened circuit breaker (mocked)"
