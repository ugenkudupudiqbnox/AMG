import requests
import time
import random
from datetime import datetime

# Configuration
API_URL = "https://api.soc.qbnox.com"
API_KEY = "sk-prod-key"
AGENT_ID = "prod-agent"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

def write_memory(content, m_type, sensitivity, scope="agent"):
    print(f"Writing {m_type} memory: {content[:30]}...")
    payload = {
        "agent_id": AGENT_ID,
        "content": content,
        "memory_type": m_type,
        "sensitivity": sensitivity,
        "scope": scope
    }
    resp = requests.post(f"{API_URL}/memory/write", json=payload, headers=headers)
    if resp.status_code != 200:
        print(f"Error: {resp.text}")
    return resp.json()

def build_context():
    print("Building context...")
    payload = {
        "agent_id": AGENT_ID,
        "memory_types": ["short_term", "long_term", "episodic"]
    }
    resp = requests.post(f"{API_URL}/context/build", json=payload, headers=headers)
    return resp.json()

def toggle_kill_switch(state):
    print(f"Setting agent state to: {state}")
    action = "disable" if state == "disabled" else "enable"
    payload = {
        "reason": "Simulated incident response",
        "actor_id": "admin-123"
    }
    requests.post(f"{API_URL}/agent/{AGENT_ID}/{action}", json=payload, headers=headers)

if __name__ == "__main__":
    print("🚀 Populating AMG production data for Grafana...")
    
    # 1. Create mixed memories
    memories = [
        ("User mentioned they love the product.", "long_term", "non_pii"),
        ("Customer email is ugen@qbnox.com", "long_term", "pii"),
        ("Current task: analyze memory logs", "short_term", "non_pii"),
        ("Last interaction was about pricing", "episodic", "non_pii"),
        ("User asked about GDPR compliance", "long_term", "non_pii"),
        ("Temporary session token: abc-123", "short_term", "pii"),
    ]
    
    for content, m_type, sens in memories:
        write_memory(content, m_type, sens)
        time.sleep(1)
    
    # 2. Build context multiple times (simulates agent retrieval)
    for _ in range(5):
        build_context()
        time.sleep(0.5)
    
    # 3. Simulate a kill-switch toggle (incident simulation)
    toggle_kill_switch("disabled")
    time.sleep(2)
    
    # Try to write while disabled (should fail and log audit denial)
    print("Attempting to write while disabled (expected failure)...")
    write_memory("Sensitive data during freeze", "short_term", "pii")
    
    time.sleep(2)
    toggle_kill_switch("enabled")
    
    # 4. Final summary read
    build_context()
    
    print("\n✅ Data population complete. Check Grafana at https://grafana.soc.qbnox.com")
