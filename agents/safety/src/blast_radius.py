import json
import logging
from typing import Dict, Any, List

import networkx as nx

logger = logging.getLogger(__name__)

class BlastRadiusCalculator:
    """
    Computes the impact of an action based on service dependency topological sort.
    """
    def __init__(self):
        self.graph = nx.DiGraph()
        self._build_static_graph()

    def _build_static_graph(self):
        """
        Builds the MVP dependency graph based on the known cluster topology.
        Nodes are services; directed edges represent A relies on B.
        """
        # Node: Name -> Dict of attrs
        services = [
            "api-gateway", "user-svc", "auth-svc", "order-svc", 
            "payment-svc", "product-svc", "search-svc", 
            "notification-worker", "inventory-worker", "analytics-worker",
            "redis", "postgres-orders", "postgres-payments", "nats", "elasticsearch"
        ]
        self.graph.add_nodes_from(services)

        edges = [
            ("api-gateway", "user-svc"),
            ("api-gateway", "order-svc"),
            ("api-gateway", "product-svc"),
            ("api-gateway", "auth-svc"),
            ("user-svc", "redis"),
            ("auth-svc", "redis"),
            ("auth-svc", "user-svc"),
            ("order-svc", "postgres-orders"),
            ("order-svc", "nats"),
            ("order-svc", "payment-svc"),
            ("order-svc", "inventory-worker"),
            ("payment-svc", "postgres-payments"),
            ("payment-svc", "nats"),
            ("product-svc", "elasticsearch"),
            ("search-svc", "elasticsearch"),
            ("notification-worker", "nats"),
            ("inventory-worker", "nats"),
            ("inventory-worker", "postgres-orders"),
            ("analytics-worker", "nats")
        ]
        self.graph.add_edges_from(edges)

    def calculate(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculates blast radius for a given action.
        """
        params = action.get("params", {})
        target = params.get("target") or params.get("target_db")
        
        if not target or target not in self.graph:
            return {
                "risk_level": "unknown",
                "affected_services": [],
                "impact_score": 0.0,
                "reason": f"Target '{target}' is unknown to dependency graph."
            }
            
        # If I restart target X, who depends on X?
        # A depends on B = Edge(A, B).
        # We need all nodes that can reach X via a directed path.
        affected = list(nx.ancestors(self.graph, target))
        impact_score = len(affected) / max(1, len(self.graph.nodes))
        
        risk_level = "low"
        if impact_score > 0.5:
            risk_level = "high"
        elif impact_score > 0.2:
            risk_level = "medium"
            
        # Core infrastructure like DBs inherently affects many
        if target in ["postgres-orders", "nats", "redis"]:
            risk_level = "critical"
            impact_score = 1.0
            
        return {
            "risk_level": risk_level,
            "affected_services": affected,
            "impact_score": impact_score,
            "reason": f"Action affects {len(affected)} upstream services."
        }
