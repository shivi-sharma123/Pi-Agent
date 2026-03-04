import argparse
import asyncio
import logging
import os
import sys

# Configure logging before loading agents
import structlog
from shared.logging.logger import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

from agents.observer.src.health_observer import HealthObserver
from agents.observer.src.log_observer import LogObserver
from agents.observer.src.metrics_observer import MetricsObserver
from agents.observer.src.synthetic_prober import SyntheticProber
from shared.config.settings import settings


def parse_args():
    parser = argparse.ArgumentParser(description="SRE Agent Swarm - Observer Node")
    parser.add_argument(
        "--type", 
        type=str, 
        choices=["metrics", "logs", "health", "synthetic"],
        default=os.environ.get("OBSERVER_TYPE", "metrics"),
        help="The type of observer to run"
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    nats_url = settings.NATS_URL
    
    agent = None
    if args.type == "metrics":
        agent = MetricsObserver(nats_url=nats_url)
    elif args.type == "logs":
        agent = LogObserver(nats_url=nats_url)
    elif args.type == "health":
        agent = HealthObserver(nats_url=nats_url)
    elif args.type == "synthetic":
        agent = SyntheticProber(nats_url=nats_url)
    else:
        logger.error("Unknown observer type", type=args.type)
        sys.exit(1)
        
    logger.info("Starting Observer Agent", type=args.type, nats_url=nats_url)
    
    try:
        await agent.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Shutting down...")
    except Exception as e:
        logger.exception("Agent crashed", traceback=str(e))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
