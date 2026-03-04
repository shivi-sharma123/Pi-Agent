import os
import sys
import asyncio
import logging

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from orchestrator_agent import OrchestratorAgent

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    agent = OrchestratorAgent()
    try:
        asyncio.run(agent.start())
    except KeyboardInterrupt:
        pass
