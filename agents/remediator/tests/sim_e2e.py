import asyncio
import json
import uuid
from datetime import datetime
import nats
from nats.js.api import StreamConfig

# Shared message subjects
from shared.messaging.subjects import (
    DIAGNOSER_RESULTS as SUBJECT_DIAGNOSER_RESULTS,
    SAFETY_REVIEWS as SUBJECT_SAFETY_REVIEWS,
    SAFETY_DECISIONS as SUBJECT_SAFETY_DECISIONS,
    REMEDIATOR_EXECUTIONS as SUBJECT_REMEDIATOR_EXECUTIONS
)

async def main():
    nc = await nats.connect("nats://localhost:4222")
    js = nc.jetstream()

    # Create subjects just in case `init_nats.py` hasn't run
    streams = {
        "DIAGNOSER_STREAM": [SUBJECT_DIAGNOSER_RESULTS],
        "SAFETY_STREAM": [SUBJECT_SAFETY_REVIEWS, SUBJECT_SAFETY_DECISIONS],
        "REMEDIATOR_STREAM": [SUBJECT_REMEDIATOR_EXECUTIONS],
    }

    for name, subjects in streams.items():
        try:
            await js.add_stream(name=name, subjects=subjects)
        except Exception:
            pass # Stream exists

    print("--- [SIMULATION] Starting E2E run ---")

    # We will subscribe to the output of the whole loop to see if Remediator finishes
    sub = await js.subscribe(SUBJECT_REMEDIATOR_EXECUTIONS, durable="sim-consumer")

    correlation_id = str(uuid.uuid4())
    print(f"--- [SIMULATION] Injecting Mock Diagnosis (ID: {correlation_id}) ---")

    mock_diagnosis = {
        "message_id": str(uuid.uuid4()),
        "correlation_id": correlation_id,
        "source_agent": "agents.diagnoser",
        "target_agent": "agents.remediator",
        "message_type": "diagnosis_result",
        "priority": 1,
        "timestamp": datetime.utcnow().isoformat(),
        "payload": {
            "root_cause": {
                "category": "memory_leak",
                "service": "user-svc",
                "confidence": 95,
                "reasoning": "Memory usage monotonic increase over 24h"
            }
        },
        "context": {"env": "prod"},
        "ttl_seconds": 300,
        "retry_count": 0,
        "trace_id": str(uuid.uuid4())
    }

    try:
        await js.publish(SUBJECT_DIAGNOSER_RESULTS, json.dumps(mock_diagnosis).encode())
    except Exception as e:
        print(f"Failed to publish mock diagnosis: {e}")
    
    # 2. Remediator Agent should receive this, map it to `memory_leak.yml`, render it, and
    # structure it as an Action. Then it publishes a Review Request -> Safety Agent.
    
    # 3. Safety Agent receives it, runs Blast Radius ("low"), Rate Limit ("ok"), Policy Engine ("ok").
    # It publishes an Approved decision -> Remediator Agent.
    
    # 4. Remediator receives approval, executes dummy docker Restart on `user-svc`.
    
    # 5. Remediator runs Verification (mocked to True after 15s).
    
    # 6. Remediator publishes Execution Result -> Subscription below.

    print("--- [SIMULATION] Waiting for remediation to complete (Expect ~15 seconds)... ---")
    
    try:
        # Wait for the loop to close
        msg = await sub.next_msg(timeout=30.0)
        await msg.ack()
        res = json.loads(msg.data.decode())
        
        print("\n--- [SIMULATION] Remediation Loop Complete! ---")
        print(f"Status: {res['payload']['status']}")
        print(f"Details: {res['payload']['details']}")
        print(f"Action: {res['payload']['action_type']}")
        
    except TimeoutError:
        print("\n--- [SIMULATION] TIMEOUT! Remediation loop did not complete in time. ---")
        
    await nc.close()

if __name__ == '__main__':
    asyncio.run(main())
