import requests
import time
import random
import sys

# Configuration
API_URL = "https://api.soc.qbnox.com"
API_KEY = "sk-test" # Using sk-test as it's the common dev key
AGENT_PREFIX = "test-agent-"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

SAMPLES = [
    ("User asked about project schedule.", "long_term", "non_pii"),
    ("Confidential phone: +1-555-0199", "long_term", "pii"),
    ("Processing current query for agent.", "short_term", "non_pii"),
    ("Previous session ended abruptly.", "episodic", "non_pii"),
    ("User identity verified via email: test@example.com", "long_term", "pii"),
    ("Task status updated to completed.", "short_term", "non_pii"),
    ("Billing address: 123 Governance Way", "long_term", "pii"),
    ("Agent is currently in reflection mode.", "episodic", "non_pii"),
]

def run_stream():
    print(f"📡 Starting AMG Live Test Stream to {API_URL}")
    print("Press Ctrl+C to stop.")
    
    count = 0
    try:
        while True:
            agent_id = f"{AGENT_PREFIX}{random.randint(0, 5)}"
            action = random.choice(["write", "build", "status", "write", "write"]) # Favor writes
            
            if action == "write":
                content, m_type, sens = random.choice(SAMPLES)
                payload = {
                    "agent_id": agent_id,
                    "content": f"{content} (Update {count})",
                    "memory_type": m_type,
                    "sensitivity": sens,
                    "scope": "agent"
                }
                print(f"[{count}] Writing to {agent_id}...")
                requests.post(f"{API_URL}/memory/write", json=payload, headers=headers)
            
            elif action == "build":
                print(f"[{count}] Building context for {agent_id}...")
                payload = {"agent_id": agent_id}
                requests.post(f"{API_URL}/context/build", json=payload, headers=headers)
            
            elif action == "status":
                print(f"[{count}] Polling status for {agent_id}...")
                requests.get(f"{API_URL}/agent/{agent_id}/status", headers=headers)

            count += 1
            # Sleep between 1 and 3 seconds
            time.sleep(random.uniform(1.0, 3.0))
            
    except KeyboardInterrupt:
        print("\nStopping stream...")
        sys.exit(0)

if __name__ == "__main__":
    run_stream()
