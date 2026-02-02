# Agent Memory Governance - User Guides

## Table of Contents
1. Getting Started
2. Python SDK Guide
3. HTTP API Guide
4. LangGraph Integration
5. Deployment & Operations
6. Security & Best Practices
7. Troubleshooting

---

## 1. Getting Started

### Installation

```bash
# Clone repository
git clone https://github.com/ugenkudupudiqbnox/AMG.git
cd AMG

# Install for development
pip install -e .

# Install API dependencies (optional)
pip install fastapi uvicorn pydantic httpx
```

### Quick Test

```bash
# Run all tests
python3 -m pytest tests/ -v

# Expected: 132 tests passing in ~5-6 seconds
```

### Start API Server

```bash
# Development (with auto-reload)
python3 run_api.py --reload

# Production
python3 run_api.py --host 0.0.0.0 --port 8000

# Then visit: http://localhost:8000/docs
```

---

## 2. Python SDK Guide

### Basic Memory Operations

```python
from amg.adapters import InMemoryStorageAdapter
from amg.types import Memory, MemoryPolicy, MemoryType, Sensitivity, Scope

# Create storage
storage = InMemoryStorageAdapter()

# Write memory
policy = MemoryPolicy(
    memory_type=MemoryType.LONG_TERM,
    ttl_seconds=2592000,  # 30 days
    sensitivity=Sensitivity.NON_PII,
    scope=Scope.AGENT,
)
memory = Memory(
    agent_id="agent-123",
    content="Important insight",
    policy=policy,
)

audit = storage.write(memory, {"request_id": "req-abc"})
print(f"Memory written: {memory.memory_id}")
```

### Query Memory

```python
from amg.storage import PolicyCheck
from amg.types import Scope

# Query with policy enforcement
policy_check = PolicyCheck(
    agent_id="agent-123",
    allowed_scopes=[Scope.AGENT],
    allow_read=True
)

memories, audit = storage.query(
    filters={},
    agent_id="agent-123",
    policy_check=policy_check,
)

for mem in memories:
    print(f"Memory: {mem.content}")
    print(f"Expires: {mem.expires_at}")
```

### Governance Controls

```python
from amg.kill_switch import KillSwitch

# Create kill switch
kill_switch = KillSwitch()

# Disable agent (incident response)
audit = kill_switch.disable(
    agent_id="agent-123",
    reason="suspicious_behavior",
    actor_id="admin-456"
)
print(f"Agent disabled. Audit: {audit.audit_id}")

# Freeze writes (read-only mode)
audit = kill_switch.freeze_writes(
    agent_id="agent-123",
    reason="under_investigation",
    actor_id="admin-456"
)

# Check status
status = kill_switch.get_status("agent-123")
print(f"State: {status.state}")
print(f"Memory write: {status.memory_write}")
```

### Build Governed Context

```python
from amg.context import GovernedContextBuilder, ContextRequest

# Create context builder
context_builder = GovernedContextBuilder(
    storage=storage,
    kill_switch=kill_switch,
)

# Build context for agent
request = ContextRequest(
    agent_id="agent-123",
    request_id="req-123",
    filters={
        "memory_types": ["long_term"],
    },
    max_items=20,
    max_tokens=4000,
)

context = context_builder.build(request)
print(f"Context assembled with {len(context.memories)} memories")
print(f"Token count: {context.metadata.get('token_count')}")
```

---

## 3. HTTP API Guide

### Authentication

```bash
# Set API key via environment
export AMG_API_KEYS="sk-abc123:agent-123,sk-def456:agent-456"

# Or disable auth for testing
export AMG_AUTH_DISABLED=true

# Then start server
python3 run_api.py
```

### Write Memory

```bash
curl -X POST http://localhost:8000/memory/write \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-abc123" \
  -d '{
    "agent_id": "agent-123",
    "content": "User reported issue #42",
    "memory_type": "episodic",
    "sensitivity": "non_pii"
  }'
```

**Response:**
```json
{
  "memory_id": "mem-xyz789",
  "audit_id": "audit-abc123",
  "decision": "allowed"
}
```

### Query Memory

```bash
curl -X POST http://localhost:8000/memory/query \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-abc123" \
  -d '{
    "agent_id": "agent-123",
    "memory_types": ["episodic"],
    "limit": 10
  }'
```

### Build Context

```bash
curl -X POST http://localhost:8000/context/build \
  -H "Content-Type: application/json" \
  -H "X-API-Key: sk-abc123" \
  -d '{
    "agent_id": "agent-123",
    "memory_types": ["long_term"],
    "max_tokens": 4000
  }'
```

### Incident Response

```bash
# Freeze agent writes
curl -X POST "http://localhost:8000/agent/agent-123/freeze?reason=suspicious_pattern"

# Check status
curl http://localhost:8000/agent/agent-123/status

# If confirmed malicious, disable
curl -X POST "http://localhost:8000/agent/agent-123/disable?reason=confirmed_attack"
```

### Get Audit Trail

```bash
# Retrieve audit logs
curl "http://localhost:8000/audit/audit-abc123"
```

---

## 4. LangGraph Integration

### Setup

```python
from amg.adapters.langgraph import LangGraphMemoryAdapter
from amg.adapters import InMemoryStorageAdapter
from amg.kill_switch import KillSwitch
from amg.context import GovernedContextBuilder

# Initialize AMG components
storage = InMemoryStorageAdapter()
kill_switch = KillSwitch()
context_builder = GovernedContextBuilder(storage, kill_switch)

# Create LangGraph adapter
adapter = LangGraphMemoryAdapter(
    storage=storage,
    kill_switch=kill_switch,
    context_builder=context_builder,
)
```

### Build Context for Agent

```python
# In your LangGraph node
context = adapter.build_context(
    agent_id="my-agent",
    memory_filters={"memory_types": ["long_term"]},
    max_tokens=4000,
)

# Use in state
state["context"] = [m.content for m in context.memories]
```

### Record Memory After Action

```python
# After agent takes an action
audit = adapter.record_memory(
    agent_id="my-agent",
    content=f"Action: {action}, Result: {result}",
    memory_type="episodic",
    sensitivity="non_pii",
    scope="agent",
)

print(f"Action recorded: {audit.audit_id}")
```

### Check Agent State

```python
# Before allowing execution
if not adapter.check_agent_enabled(agent_id="my-agent"):
    raise Exception("Agent is disabled")

# Get detailed status
status = adapter.get_agent_status(agent_id="my-agent")
print(f"Memory items: {status['memory_count']}")
print(f"State: {status['state']}")
```

---

## 5. Deployment & Operations

### Docker Deployment

```dockerfile
# Dockerfile
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

### Docker Compose

```yaml
version: '3.8'

services:
  amg-api:
    build: .
    ports:
      - "8000:8000"
    environment:
      AMG_AUTH_DISABLED: "false"
      AMG_API_KEYS: "sk-key1:agent-1,sk-key2:agent-2"
    volumes:
      - ./logs:/app/logs
    restart: unless-stopped

  # Optional: Postgres for production storage
  amg-postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: amg
      POSTGRES_USER: amg
      POSTGRES_PASSWORD: secure-password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

### Systemd Service (Linux)

```bash
# Copy service file
sudo cp amg-api.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable amg-api
sudo systemctl start amg-api

# Check status
sudo systemctl status amg-api

# View logs
sudo journalctl -u amg-api -f
```

### Health Monitoring

```bash
#!/bin/bash
# health-check.sh

while true; do
  response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)
  
  if [ "$response" -eq 200 ]; then
    echo "✅ API healthy"
  else
    echo "⚠️  API unhealthy (status: $response)"
    # Trigger alert
    notify_ops "AMG API health check failed"
  fi
  
  sleep 60
done
```

### SSL/HTTPS Setup

#### Option 1: Let's Encrypt (Recommended for Public Internet)

Let's Encrypt provides free, automatically-renewing SSL certificates for public domains.

**Prerequisites:**
- Public domain name (e.g., `api.example.com`)
- Port 80 and 443 accessible from the internet
- Nginx or Apache installed

**Installation & Setup:**

```bash
# 1. Install Certbot (Let's Encrypt client)
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# 2. Create certificate for your domain
sudo certbot certonly --standalone -d api.example.com

# If you already have Nginx running:
# sudo certbot certonly --nginx -d api.example.com

# 3. Verify certificate location
ls -la /etc/letsencrypt/live/api.example.com/
# You should see: fullchain.pem and privkey.pem
```

**Nginx Configuration (Reverse Proxy):**

```nginx
# /etc/nginx/sites-available/amg-api

# HTTP → HTTPS redirect
server {
    listen 80;
    server_name api.example.com;
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name api.example.com;
    
    # SSL Certificates
    ssl_certificate /etc/letsencrypt/live/api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.example.com/privkey.pem;
    
    # TLS Security
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200 nodelay;
    
    # Proxy to API backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Keep alive
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
```

**Enable and Test:**

```bash
# Test Nginx configuration
sudo nginx -t

# Enable and reload
sudo systemctl reload nginx

# Test HTTPS
curl -I https://api.example.com/health

# Check certificate
echo | openssl s_client -servername api.example.com \
  -connect api.example.com:443 2>/dev/null | \
  openssl x509 -noout -dates
```

**Automatic Certificate Renewal:**

```bash
# 1. Create systemd service
sudo tee /etc/systemd/system/certbot-renew.service << EOF
[Unit]
Description=Certbot Renewal Service
After=network.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --agree-tos
ExecStartPost=/bin/systemctl reload nginx

[Install]
WantedBy=multi-user.target
EOF

# 2. Create systemd timer (runs twice daily)
sudo tee /etc/systemd/system/certbot-renew.timer << EOF
[Unit]
Description=Certbot Renewal Timer
Requires=certbot-renew.service

[Timer]
OnCalendar=0,12:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
EOF

# 3. Enable and start
sudo systemctl daemon-reload
sudo systemctl enable certbot-renew.timer
sudo systemctl start certbot-renew.timer

# 4. Verify
sudo systemctl list-timers certbot-renew.timer
```

---

#### Option 2: Self-Signed Certificates (For Internal/Private Networks)

Self-signed certificates are free and don't require a domain name. Use for internal deployments, testing, or private networks.

**Create Self-Signed Certificate:**

```bash
# 1. Generate private key (4096-bit RSA, 365 days validity)
sudo openssl genrsa -out /etc/ssl/private/amg-api.key 4096

# 2. Create certificate signing request
sudo openssl req -new \
  -key /etc/ssl/private/amg-api.key \
  -out /tmp/amg-api.csr \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"

# 3. Self-sign the certificate
sudo openssl x509 -req -days 365 \
  -in /tmp/amg-api.csr \
  -signkey /etc/ssl/private/amg-api.key \
  -out /etc/ssl/certs/amg-api.crt

# 4. Set permissions
sudo chmod 600 /etc/ssl/private/amg-api.key
sudo chmod 644 /etc/ssl/certs/amg-api.crt

# 5. Verify certificate
openssl x509 -in /etc/ssl/certs/amg-api.crt -text -noout
```

**One-Line Alternative (All-in-One):**

```bash
# Generate key + certificate in one command (365 days)
sudo openssl req -x509 -newkey rsa:4096 -nodes \
  -keyout /etc/ssl/private/amg-api.key \
  -out /etc/ssl/certs/amg-api.crt \
  -days 365 \
  -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
```

**Nginx Configuration (Self-Signed):**

```nginx
# /etc/nginx/sites-available/amg-api

server {
    listen 443 ssl http2;
    server_name localhost;
    
    # Self-signed certificate paths
    ssl_certificate /etc/ssl/certs/amg-api.crt;
    ssl_certificate_key /etc/ssl/private/amg-api.key;
    
    # TLS Configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    
    # Security Headers (same as Let's Encrypt)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    
    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200 nodelay;
    
    # Proxy to API
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
    }
}

# Optional: HTTP redirect (for internal networks)
server {
    listen 80;
    server_name localhost;
    location / {
        return 301 https://$server_name$request_uri;
    }
}
```

**Enable and Test:**

```bash
# Test Nginx configuration
sudo nginx -t

# Reload Nginx
sudo systemctl reload nginx

# Test HTTPS (accept self-signed warning)
curl -k -I https://localhost/health

# Or use proper certificate validation by trusting the certificate
# (See "Client-Side Certificate Trust" below)
```

**Certificate Renewal (Self-Signed):**

Self-signed certificates don't auto-renew. Create a renewal script:

```bash
#!/bin/bash
# /usr/local/bin/renew-self-signed.sh

CERT_FILE="/etc/ssl/certs/amg-api.crt"
DAYS_UNTIL_EXPIRY=$(openssl x509 -in $CERT_FILE -noout -checkend 86400 2>/dev/null)

if [ $? -eq 0 ]; then
    echo "Certificate still valid"
else
    echo "Certificate expiring soon, generating new one..."
    
    sudo openssl req -x509 -newkey rsa:4096 -nodes \
      -keyout /etc/ssl/private/amg-api.key \
      -out /etc/ssl/certs/amg-api.crt \
      -days 365 \
      -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
    
    sudo systemctl reload nginx
    echo "Certificate renewed"
fi
```

Setup automatic renewal:

```bash
# 1. Make script executable
sudo chmod +x /usr/local/bin/renew-self-signed.sh

# 2. Add to crontab (run daily)
echo "0 0 * * * /usr/local/bin/renew-self-signed.sh" | sudo crontab -

# 3. Verify cron job
sudo crontab -l
```

---

#### Option 3: Comparison

| Feature | Let's Encrypt | Self-Signed |
|---------|--------------|-------------|
| Cost | Free | Free |
| Setup Time | ~5 min | ~2 min |
| Auto-Renewal | Yes | Manual (cron) |
| Browser Warning | No | Yes* |
| Public Trust | Yes | No |
| Use Case | Public APIs | Internal/Testing |
| Security | A+ rating | Secure (if accepted) |

*Self-signed certificates show browser warnings unless explicitly trusted.

---

#### Client-Side Certificate Handling

**Python Client (Let's Encrypt - Automatic):**

```python
import httpx

# Let's Encrypt certificates are system-trusted (no special handling)
client = httpx.Client()
response = client.get("https://api.example.com/health")
print(response.status_code)
```

**Python Client (Self-Signed - Trust Certificate):**

```python
import httpx
import certifi
from httpx import SSLConfig

# Option 1: Disable verification (not recommended for production)
client = httpx.Client(verify=False)
response = client.get("https://localhost/health")

# Option 2: Trust specific certificate (recommended)
ssl_context = SSLConfig(ca_certs="/path/to/amg-api.crt").build()
client = httpx.Client(verify=ssl_context)
response = client.get("https://localhost/health")
```

**Command-Line (Self-Signed - Trust Certificate):**

```bash
# Disable verification (quick testing only)
curl -k -I https://localhost/health

# Or: Trust the certificate
curl --cacert /etc/ssl/certs/amg-api.crt https://localhost/health
```

**System-Wide Trust (Self-Signed - Linux):**

```bash
# Copy certificate to system trust store
sudo cp /etc/ssl/certs/amg-api.crt /usr/local/share/ca-certificates/
sudo update-ca-certificates

# Now curl and other tools will trust it
curl -I https://localhost/health  # No -k flag needed
```

---

#### Monitoring & Maintenance

**Check Certificate Expiration:**

```bash
# Check certificate expiry date
openssl x509 -in /etc/ssl/certs/amg-api.crt -noout -dates

# Or for Let's Encrypt
sudo certbot certificates

# Show days until expiry
echo | openssl s_client -servername api.example.com \
  -connect api.example.com:443 2>/dev/null | \
  openssl x509 -noout -dates | grep notAfter
```

**Monitor Certificate Renewal (Let's Encrypt):**

```bash
# View renewal attempts
sudo journalctl -u certbot-renew.timer -f

# Manual renewal test
sudo certbot renew --dry-run

# View renewal status
sudo systemctl status certbot-renew.timer
```

**Nginx SSL Testing:**

```bash
# Test SSL configuration quality
echo | openssl s_client -connect localhost:443 -tls1_3

# Check TLS version
echo | openssl s_client -connect localhost:443 2>/dev/null | grep Protocol

# List enabled ciphers
openssl s_client -connect localhost:443 -cipher 'ALL' 2>/dev/null | grep Cipher
```

---

## 6. Security & Best Practices

### API Key Management

```bash
# Generate strong API keys
openssl rand -hex 32

# Store in environment (never in code)
export AMG_API_KEYS="sk-$(openssl rand -hex 16):agent-prod-123"

# Or use secrets manager
# AWS Secrets Manager, HashiCorp Vault, etc.
```

### Network Security

```bash
# Run API only on internal network
python3 run_api.py --host 127.0.0.1 --port 8000  # Local only

# Or use reverse proxy with TLS
# nginx → localhost:8000 (internal)
```

### Audit Log Analysis

```python
# Retrieve and analyze audit logs
logs = storage.get_audit_log(agent_id="agent-123")

# Look for unusual patterns
for log in logs:
    if log.decision == "denied":
        print(f"Blocked attempt: {log.reason}")
    
    if log.operation == "disable":
        print(f"Agent disabled by {log.actor_id}: {log.reason}")
```

### Data Retention

```python
# TTL automatically enforced
# But you can also manually delete old memories

from datetime import datetime, timedelta

cutoff = datetime.utcnow() - timedelta(days=90)
logs = storage.get_audit_log()

for log in logs:
    if log.timestamp < cutoff:
        # Handle retention/archival
        pass
```

---

## 7. Troubleshooting

### Tests Failing

```bash
# Run with verbose output
python3 -m pytest tests/ -vv --tb=short

# Run specific test
python3 -m pytest tests/test_api.py::TestMemoryWrite -v

# Run with coverage
python3 -m pytest tests/ --cov=src/amg
```

### API Not Responding

```bash
# Check if server is running
ps aux | grep run_api

# Check logs
tail -f /tmp/amg_api.log

# Test connectivity
curl -v http://localhost:8000/health

# Check firewall
sudo ufw status
sudo lsof -i :8000
```

### Memory Queries Empty

```python
# Verify memory was written
memories, _ = storage.query(
    filters={},
    agent_id="agent-123",
    policy_check=PolicyCheck(
        agent_id="agent-123",
        allowed_scopes=[Scope.AGENT, Scope.TENANT],
        allow_read=True
    )
)

print(f"Total memories: {len(memories)}")

# Check if expired
for mem in storage.get_all_memories():
    if mem.is_expired():
        print(f"Memory {mem.memory_id} is expired")
```

### Agent Disabled

```python
# Check status
status = kill_switch.get_status("agent-123")
print(f"State: {status.state}")

# If disabled, re-enable (if permitted)
# Note: there's no "enable" method - disable is permanent
# You must create a new agent ID

# Or use freeze for temporary blocking
```

### Authentication Issues

```bash
# Check if auth is enabled
env | grep AMG_AUTH

# Test with API key
curl -H "X-API-Key: sk-invalid" http://localhost:8000/health
# Should return 401

# Test without auth
export AMG_AUTH_DISABLED=true
python3 run_api.py
```

---

## Support & Resources

- **Documentation**: See [PHASE_5_HTTP_API.md](PHASE_5_HTTP_API.md)
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **Security**: See [SECURITY.md](SECURITY.md)
- **Tests**: Run `python3 -m pytest tests/ -v`
- **Issues**: GitHub Issues on project repository

---

## Quick Reference

### Memory Types
- `short_term`: Request-scoped only, not persisted
- `long_term`: Persisted with TTL (30 days default)
- `episodic`: Persisted with TTL (episodic pattern, 7 days default)

### Sensitivity
- `pii`: Personal Identifiable Information (shorter TTL)
- `non_pii`: General information (longer TTL)

### Scopes
- `agent`: Agent-specific memory (isolated per agent)
- `tenant`: Shared tenant memory (visible to all agents in tenant)

### HTTP Status Codes
- `200`: Success
- `400`: Bad request (validation error)
- `401`: Unauthorized (invalid/missing API key)
- `403`: Forbidden (policy enforcement failed)
- `423`: Locked (agent disabled/frozen)
- `404`: Not found
- `503`: Service unavailable

---

Created: February 2, 2026
AMG Version: 1.0.0 (Phase 5 Complete)
