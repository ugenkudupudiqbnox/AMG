# API Authentication & Deployment Guide

## Overview
The AMG HTTP API now includes complete authentication and is ready for production deployment. This guide covers setup, usage, and deployment scenarios.

---

## Quick Start

### 1. Enable Authentication

Set API keys via environment variable:

```bash
export AMG_API_KEYS="sk-agent1:agent-123,sk-agent2:agent-456"
python3 run_api.py --host 0.0.0.0 --port 8000
```

**Format**: `AMG_API_KEYS="key1:agent-id-1,key2:agent-id-2,..."`

### 2. Test with cURL

```bash
# Write memory
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-agent1" \
  -d '{
    "agent_id": "agent-123",
    "content": "Test memory",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Query memory
curl -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-agent1" \
  -d '{
    "agent_id": "agent-123",
    "limit": 10
  }'
```

### 3. Disable Authentication (Testing Only)

```bash
export AMG_AUTH_DISABLED=true
python3 run_api.py
```

---

## API Authentication

All endpoints except `/health` require the `X-API-Key` header.

### Request Header

```
X-API-Key: sk-your-api-key
```

### Configuration

**Environment Variable**:
```bash
AMG_API_KEYS="sk-production-key:prod-agent,sk-staging-key:staging-agent"
```

**Format**: Comma-separated `key:agent_id` pairs

### Response Codes

- `200`: Success
- `401`: Invalid or missing API key
- `403`: Policy violation
- `423`: Agent disabled
- `400`: Bad request
- `404`: Not found
- `503`: Service unavailable

---

## Python Client Example

```python
import requests

BASE_URL = "http://localhost:8000"
API_KEY = "sk-agent1"
AGENT_ID = "agent-123"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

# Write memory
response = requests.post(
    f"{BASE_URL}/memory/write",
    headers=headers,
    json={
        "agent_id": AGENT_ID,
        "content": "Important decision: approved feature X",
        "memory_type": "episodic",
        "sensitivity": "non_pii",
    }
)
print(f"Write: {response.status_code}")
memory_id = response.json()["memory_id"]

# Query memory
response = requests.post(
    f"{BASE_URL}/memory/query",
    headers=headers,
    json={
        "agent_id": AGENT_ID,
        "memory_types": ["episodic"],
        "limit": 10,
    }
)
print(f"Query: {response.status_code}")
print(f"Found {len(response.json()['memories'])} memories")

# Build context
response = requests.post(
    f"{BASE_URL}/context/build",
    headers=headers,
    json={
        "agent_id": AGENT_ID,
        "max_tokens": 4000,
    }
)
context = response.json()["memories"]
print(f"Context: {len(context)} items assembled")

# Disable agent (incident response)
response = requests.post(
    f"{BASE_URL}/agent/{AGENT_ID}/disable",
    headers=headers,
    params={"reason": "suspicious_behavior"},
)
print(f"Agent disabled: {response.json()}")
```

---

## JavaScript/Node Client Example

```javascript
const BASE_URL = "http://localhost:8000";
const API_KEY = "sk-agent1";
const AGENT_ID = "agent-123";

const headers = {
  "X-API-Key": API_KEY,
  "Content-Type": "application/json",
};

// Write memory
async function writeMemory(content) {
  const res = await fetch(`${BASE_URL}/memory/write`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agent_id: AGENT_ID,
      content,
      memory_type: "long_term",
      sensitivity: "non_pii",
    }),
  });
  return res.json();
}

// Query memory
async function queryMemory(filters = {}) {
  const res = await fetch(`${BASE_URL}/memory/query`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agent_id: AGENT_ID,
      ...filters,
      limit: 10,
    }),
  });
  return res.json();
}

// Build context
async function buildContext(maxTokens = 4000) {
  const res = await fetch(`${BASE_URL}/context/build`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agent_id: AGENT_ID,
      max_tokens: maxTokens,
    }),
  });
  return res.json();
}

// Usage
(async () => {
  const write = await writeMemory("User request: Generate report");
  console.log("Memory written:", write.memory_id);

  const query = await queryMemory({ memory_types: ["long_term"] });
  console.log("Found memories:", query.memories.length);

  const context = await buildContext(4000);
  console.log("Context assembled with", context.memories.length, "items");
})();
```

---

## Docker Deployment

### Dockerfile

```dockerfile
FROM python:3.10-slim

WORKDIR /app
COPY . .

RUN pip install -e . && \
    pip install fastapi uvicorn

EXPOSE 8000

ENV AMG_AUTH_DISABLED=false
ENV AMG_API_KEYS="sk-prod-key:prod-agent"

CMD ["python3", "run_api.py", "--host", "0.0.0.0", "--port", "8000"]
```

### Build & Run

```bash
# Build
docker build -t amg-api:latest .

# Run
docker run -p 8000:8000 \
  -e AMG_API_KEYS="sk-test:agent-123" \
  amg-api:latest

# Access
curl -H "X-API-Key: sk-test" http://localhost:8000/health
```

### Docker Compose

```yaml
version: '3.8'

services:
  amg-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      AMG_API_KEYS: "sk-key1:agent-1,sk-key2:agent-2"
      AMG_AUTH_DISABLED: "false"
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "-H", "X-API-Key: sk-key1", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Systemd Service (Linux)

### Setup

```bash
# Copy service file
sudo cp scripts/amg-api.service /etc/systemd/system/

# Reload systemd
sudo systemctl daemon-reload

# Create .env file for secrets
sudo nano /home/ubuntu/AMG/.env
# Add: AMG_API_KEYS="sk-prod-key:prod-agent"

# Start service
sudo systemctl enable amg-api
sudo systemctl start amg-api

# Check status
sudo systemctl status amg-api
sudo journalctl -u amg-api -f
```

### Service File Content

```ini
[Unit]
Description=Agent Memory Governance API
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/AMG
EnvironmentFile=/home/ubuntu/AMG/.env
ExecStart=/usr/bin/python3 run_api.py --host 0.0.0.0 --port 8000
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

---

## Production Security

### 1. API Key Rotation

```bash
# Old keys
export AMG_API_KEYS="sk-old-key:agent-123"

# Rotate to new key
export AMG_API_KEYS="sk-new-key:agent-123"

# Clients update to new key
curl -H "X-API-Key: sk-new-key" http://localhost:8000/health
```

### 2. TLS/HTTPS Setup

Use Nginx reverse proxy:

```nginx
server {
    listen 443 ssl;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
    }
}
```

### 3. Rate Limiting

```nginx
# In nginx.conf
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;

location / {
    limit_req zone=api_limit burst=200;
    proxy_pass http://localhost:8000;
}
```

### 4. Monitoring

```bash
#!/bin/bash
# Monitor API health

while true; do
  response=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "X-API-Key: sk-prod-key" \
    http://localhost:8000/health)
  
  if [ "$response" != "200" ]; then
    echo "⚠️  API unhealthy: $response" | mail -s "AMG Alert" ops@example.com
    systemctl restart amg-api
  fi
  
  sleep 60
done
```

---

## Troubleshooting

### API Key Not Working

```bash
# Verify API key format
echo $AMG_API_KEYS
# Should show: sk-key:agent-id

# Test with correct key
curl -H "X-API-Key: sk-key" http://localhost:8000/health

# Test without auth
export AMG_AUTH_DISABLED=true
curl http://localhost:8000/health
```

### Authentication Always Fails

```bash
# Check if auth is actually enabled
printenv | grep AMG_

# Reset auth config
systemctl restart amg-api

# Check logs
journalctl -u amg-api -n 50
```

### API Not Responding

```bash
# Check if running
ps aux | grep run_api

# Check port
lsof -i :8000

# Check logs
tail -f /var/log/amg-api.log
```

---

## API Endpoints (Summary)

| Method | Endpoint | Auth | Purpose |
|--------|----------|------|---------|
| GET | `/health` | No | Health check |
| POST | `/memory/write` | Yes | Write memory |
| POST | `/memory/query` | Yes | Query memories |
| POST | `/context/build` | Yes | Build context |
| GET | `/audit/{id}` | Yes | Get audit log |
| POST | `/agent/{id}/disable` | Yes | Disable agent |
| POST | `/agent/{id}/freeze` | Yes | Freeze writes |
| GET | `/agent/{id}/status` | Yes | Check status |

---

## Key Security Practices

1. **Never commit API keys** to version control
2. **Use environment variables** or secrets manager
3. **Rotate keys regularly** (monthly recommended)
4. **Enable HTTPS** in production
5. **Monitor audit logs** for anomalies
6. **Use strong, random keys** (min 32 characters)
7. **Restrict API access** by IP/firewall
8. **Enable rate limiting** to prevent abuse

---

## Next Steps

1. Configure API keys for your agents
2. Deploy API server (Docker/Systemd)
3. Test endpoints with your API key
4. Integrate into your LLM framework
5. Monitor performance and audit logs
6. Set up alerts for anomalies

---

Created: February 2, 2026
AMG Version: 1.0.0 (Phase 5 Complete with Authentication)
