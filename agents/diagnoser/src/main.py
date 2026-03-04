import asyncio
import os
import sys
import logging

from agents.diagnoser.src.rca_engine import RCAEngine

# Configure basic logging for the entrypoint
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    
    logger.info(f"Starting Diagnoser RCAEngine with NATS={nats_url}")
    
    agent = RCAEngine(nats_url=nats_url)
    await agent.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Diagnoser interrupted by user.")
        sys.exit(0)
