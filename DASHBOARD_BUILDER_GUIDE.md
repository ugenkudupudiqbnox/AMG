# Building Dashboards with AMG APIs

This guide explains how to build auditor and system admin dashboards using AMG's audit and statistics APIs.

## Table of Contents

1. [Overview](#overview)
2. [Available APIs](#available-apis)
3. [Authentication](#authentication)
4. [Building with Tools](#building-with-tools)
5. [Example Dashboards](#example-dashboards)
6. [Custom Implementations](#custom-implementations)

---

## Overview

AMG provides **governance-aware APIs** for auditors and system administrators to monitor:
- Memory operations and audit trails
- Agent activity and states
- System health and certificate status
- Policy configuration
- Rate limiting and abuse detection

These APIs are designed to integrate with standard dashboard tools (Grafana, Kibana, Datadog, etc.) or custom applications.

**All dashboard APIs require valid API key authentication.**

---

## Available APIs

### 1. Audit Log Export

**Endpoint:** `GET /audit/export`

**Purpose:** Export audit logs for compliance and analysis.

**Parameters:**
- `agent_id` (optional): Filter by agent
- `start_date` (optional): ISO format (2026-02-01)
- `end_date` (optional): ISO format (2026-02-02)
- `operation` (optional): write | read | query | disable | freeze
- `limit` (optional): Max records (default: 10000)

**Example:**
```bash
curl https://api.example.com/audit/export \
  -H "X-API-Key: sk-admin-key" \
  -G \
  -d "agent_id=agent-123" \
  -d "start_date=2026-02-01" \
  -d "end_date=2026-02-02" \
  -d "operation=write"
```

**Response:**
```json
{
  "count": 245,
  "records": [
    {
      "audit_id": "audit-xyz",
      "timestamp": "2026-02-02T10:30:00Z",
      "agent_id": "agent-123",
      "operation": "write",
      "memory_id": "mem-abc",
      "decision": "allowed",
      "reason": "Policy check passed"
    }
  ],
  "export_timestamp": "2026-02-02T10:35:00Z"
}
```

---

### 2. Memory Summary Statistics

**Endpoint:** `GET /stats/memory-summary`

**Purpose:** Get overview of memory storage (size, types, sensitivity, expiry).

**Example:**
```bash
curl https://api.example.com/stats/memory-summary \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "total_memories": 15432,
  "by_type": {
    "short_term": 1200,
    "long_term": 8900,
    "episodic": 5332
  },
  "by_sensitivity": {
    "pii": 2100,
    "non_pii": 13332
  },
  "by_scope": {
    "agent": 12000,
    "tenant": 3432
  },
  "expired_count": 123,
  "average_ttl_seconds": 1296000
}
```

---

### 3. Agent Activity Statistics

**Endpoint:** `GET /stats/agent-activity`

**Purpose:** Track agent operations and activity patterns.

**Parameters:**
- `limit` (optional): Max audit records to analyze (default: 100)

**Example:**
```bash
curl https://api.example.com/stats/agent-activity \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "active_agents": ["agent-prod-1", "agent-test-1", "agent-eval-1"],
  "agent_stats": {
    "agent-prod-1": {
      "operations_count": 1245,
      "last_activity": "2026-02-02T10:34:00Z",
      "operations": {
        "write": 450,
        "read": 750,
        "query": 45
      }
    },
    "agent-test-1": {
      "operations_count": 89,
      "last_activity": "2026-02-02T10:10:00Z",
      "operations": {
        "write": 45,
        "read": 44
      }
    }
  },
  "disabled_agents": [],
  "summary_timestamp": "2026-02-02T10:35:00Z"
}
```

---

### 4. Rate Limit Statistics

**Endpoint:** `GET /stats/rate-limit-hits`

**Purpose:** Monitor rate limiting and potential abuse.

**Example:**
```bash
curl https://api.example.com/stats/rate-limit-hits \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "rate_limit_hits": 0,
  "note": "Rate limit data comes from Nginx logs",
  "query_example": "grep 'HTTP/2 429' /var/log/nginx/amg-api-access.log | wc -l"
}
```

---

### 5. Policy Configuration

**Endpoint:** `GET /config/policies`

**Purpose:** View current governance policies and constraints.

**Example:**
```bash
curl https://api.example.com/config/policies \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "policy_version": "1.0.0",
  "memory_types": ["short_term", "long_term", "episodic"],
  "sensitivities": ["pii", "non_pii"],
  "scopes": ["agent", "tenant"],
  "default_ttls": {
    "short_term": 0,
    "long_term": 2592000,
    "episodic": 604800
  },
  "policy_constraints": {
    "min_ttl": 0,
    "max_ttl": 31536000,
    "max_memory_items": 10000,
    "max_context_tokens": 8000
  }
}
```

---

### 6. Agent Configuration

**Endpoint:** `GET /config/agents`

**Purpose:** Get list of configured agents and their states.

**Example:**
```bash
curl https://api.example.com/config/agents \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "agents": [
    {
      "agent_id": "prod-agent",
      "enabled": true,
      "state": "enabled"
    },
    {
      "agent_id": "test-agent",
      "enabled": true,
      "state": "enabled"
    }
  ]
}
```

---

### 7. Certificate Status

**Endpoint:** `GET /system/certificate-status`

**Purpose:** Monitor SSL certificate expiry and renewal status.

**Example:**
```bash
curl https://api.example.com/system/certificate-status \
  -H "X-API-Key: sk-admin-key"
```

**Response:**
```json
{
  "domain": "soc.qbnox.com",
  "certificate_info": {
    "notBefore": "Nov  5 00:00:00 2025 GMT",
    "notAfter": "Feb  3 00:00:00 2026 GMT"
  },
  "auto_renewal": "enabled",
  "renewal_schedule": "0,12:00 UTC daily",
  "next_renewal_check": "2026-02-02 12:10 UTC"
}
```

---

## Authentication

All dashboard APIs require API key authentication:

```bash
curl -H "X-API-Key: sk-admin-key" https://api.example.com/stats/memory-summary
```

**Setup admin API keys:**

```bash
# In /etc/default/amg-api on the server
AMG_API_KEYS=sk-admin-key:admin-agent,sk-prod-key:prod-agent,sk-test:test-agent
```

Then restart the API service:
```bash
sudo systemctl restart amg-api
```

---

## Building with Tools

### Grafana Integration

**1. Add HTTP Data Source:**

```
Settings → Data Sources → Add → HTTP

URL: https://api.example.com
Auth: Custom HTTP Header
Header Name: X-API-Key
Header Value: sk-admin-key
```

**2. Create Dashboard with JSON API:**

```json
{
  "dashboard": {
    "title": "AMG Memory Governance",
    "panels": [
      {
        "title": "Memory Summary",
        "targets": [
          {
            "method": "GET",
            "url": "https://api.example.com/stats/memory-summary"
          }
        ]
      }
    ]
  }
}
```

---

### Python Dashboard (Flask)

```python
import requests
from flask import Flask, render_template
from datetime import datetime, timedelta

app = Flask(__name__)

API_KEY = "sk-admin-key"
API_URL = "https://api.example.com"
HEADERS = {"X-API-Key": API_KEY}

@app.route("/dashboard")
def dashboard():
    """Render admin dashboard."""
    
    # Fetch all stats
    memory_stats = requests.get(
        f"{API_URL}/stats/memory-summary",
        headers=HEADERS
    ).json()
    
    agent_stats = requests.get(
        f"{API_URL}/stats/agent-activity",
        headers=HEADERS
    ).json()
    
    cert_status = requests.get(
        f"{API_URL}/system/certificate-status",
        headers=HEADERS
    ).json()
    
    # Fetch recent audit logs (last 24 hours)
    start_date = (datetime.utcnow() - timedelta(days=1)).date()
    audit_logs = requests.get(
        f"{API_URL}/audit/export",
        headers=HEADERS,
        params={"start_date": str(start_date), "limit": 100}
    ).json()
    
    return render_template(
        "dashboard.html",
        memory_stats=memory_stats,
        agent_stats=agent_stats,
        cert_status=cert_status,
        audit_logs=audit_logs,
    )

if __name__ == "__main__":
    app.run(debug=True, port=8080)
```

**HTML Template (dashboard.html):**

```html
<!DOCTYPE html>
<html>
<head>
    <title>AMG Admin Dashboard</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5/dist/css/bootstrap.min.css">
</head>
<body>
    <div class="container-fluid p-4">
        <h1>Agent Memory Governance Dashboard</h1>
        
        <!-- Memory Summary -->
        <div class="row mt-4">
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Total Memories</h5>
                        <h2>{{ memory_stats.total_memories }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Expired Memories</h5>
                        <h2>{{ memory_stats.expired_count }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Active Agents</h5>
                        <h2>{{ agent_stats.active_agents|length }}</h2>
                    </div>
                </div>
            </div>
            <div class="col-md-3">
                <div class="card">
                    <div class="card-body">
                        <h5>Certificate Expires</h5>
                        <p>{{ cert_status.certificate_info.notAfter }}</p>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Memory Breakdown -->
        <div class="row mt-4">
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Memory Types</div>
                    <div class="card-body">
                        <table class="table">
                            {% for type, count in memory_stats.by_type.items() %}
                            <tr>
                                <td>{{ type }}</td>
                                <td>{{ count }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                </div>
            </div>
            
            <div class="col-md-6">
                <div class="card">
                    <div class="card-header">Agent Activity</div>
                    <div class="card-body">
                        <table class="table">
                            {% for agent_id, stats in agent_stats.agent_stats.items() %}
                            <tr>
                                <td>{{ agent_id }}</td>
                                <td>{{ stats.operations_count }} ops</td>
                            </tr>
                            {% endfor %}
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- Recent Audit Logs -->
        <div class="row mt-4">
            <div class="col-12">
                <div class="card">
                    <div class="card-header">Recent Audit Activity</div>
                    <div class="card-body">
                        <table class="table">
                            <thead>
                                <tr>
                                    <th>Timestamp</th>
                                    <th>Agent</th>
                                    <th>Operation</th>
                                    <th>Decision</th>
                                    <th>Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                {% for log in audit_logs.records[:20] %}
                                <tr>
                                    <td>{{ log.timestamp }}</td>
                                    <td>{{ log.agent_id }}</td>
                                    <td>{{ log.operation }}</td>
                                    <td>{{ log.decision }}</td>
                                    <td>{{ log.reason }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
```

---

### Node.js/React Dashboard

```javascript
import React, { useState, useEffect } from 'react';

const API_KEY = 'sk-admin-key';
const API_URL = 'https://api.example.com';

function Dashboard() {
  const [memoryStats, setMemoryStats] = useState(null);
  const [agentStats, setAgentStats] = useState(null);
  const [certStatus, setCertStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchStats = async () => {
      const headers = { 'X-API-Key': API_KEY };

      try {
        const [memory, agents, cert] = await Promise.all([
          fetch(`${API_URL}/stats/memory-summary`, { headers }).then(r => r.json()),
          fetch(`${API_URL}/stats/agent-activity`, { headers }).then(r => r.json()),
          fetch(`${API_URL}/system/certificate-status`, { headers }).then(r => r.json()),
        ]);

        setMemoryStats(memory);
        setAgentStats(agents);
        setCertStatus(cert);
        setLoading(false);
      } catch (error) {
        console.error('Failed to fetch stats:', error);
        setLoading(false);
      }
    };

    fetchStats();
    
    // Refresh every 30 seconds
    const interval = setInterval(fetchStats, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div>Loading dashboard...</div>;

  return (
    <div className="dashboard">
      <h1>AMG Admin Dashboard</h1>
      
      <div className="stats-grid">
        <div className="stat-card">
          <h3>Total Memories</h3>
          <p>{memoryStats?.total_memories || 0}</p>
        </div>
        
        <div className="stat-card">
          <h3>Active Agents</h3>
          <p>{agentStats?.active_agents?.length || 0}</p>
        </div>
        
        <div className="stat-card">
          <h3>Memory Expired Soon</h3>
          <p>{memoryStats?.expired_count || 0}</p>
        </div>
        
        <div class="stat-card">
          <h3>Cert Expires</h3>
          <p>{certStatus?.certificate_info?.notAfter || 'Unknown'}</p>
        </div>
      </div>
      
      <div className="detailed-stats">
        <h2>Memory by Type</h2>
        <ul>
          {Object.entries(memoryStats?.by_type || {}).map(([type, count]) => (
            <li key={type}>{type}: {count}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default Dashboard;
```

---

## Example Dashboards

### Compliance Dashboard

**Widgets:**
- Audit log timeline (operations per day)
- Policy violations (decisions = "denied")
- Agent disable/freeze events
- PII memory retention tracking

**Query:**
```bash
# Get all denied operations (potential violations)
curl https://api.example.com/audit/export \
  -H "X-API-Key: sk-admin-key" \
  -G -d "operation=deny" \
  | jq '.records | group_by(.agent_id) | map({agent: .[0].agent_id, denials: length})'
```

---

### Operations Dashboard

**Widgets:**
- Memory growth over time
- Agent operation counts
- Certificate expiry warning
- Rate limit hits
- System health status

**Query:**
```bash
# Monitor memory growth
for day in {1..7}; do
  date_str=$(date -d "-$day days" +%Y-%m-%d)
  count=$(curl -s https://api.example.com/audit/export \
    -H "X-API-Key: sk-admin-key" \
    -G -d "start_date=$date_str" -d "end_date=$date_str" \
    -d "operation=write" | jq '.count')
  echo "$date_str: $count writes"
done
```

---

### Security Dashboard

**Widgets:**
- Disabled/frozen agents (kill switch activations)
- Failed authentication attempts (401 rate)
- Rate limit violations (429 rate)
- Policy enforcement success rate
- Audit log integrity

**Query:**
```bash
# Monitor policy denials vs allows
curl https://api.example.com/audit/export \
  -H "X-API-Key: sk-admin-key" \
  | jq '
    .records
    | group_by(.decision)
    | map({decision: .[0].decision, count: length})
  '
```

---

## Custom Implementations

### Time-Series Analysis

```python
# Track memory growth over 30 days
import requests
from datetime import datetime, timedelta

API_KEY = "sk-admin-key"
headers = {"X-API-Key": API_KEY}

for i in range(30):
    date = (datetime.utcnow() - timedelta(days=i)).date()
    next_date = (datetime.utcnow() - timedelta(days=i-1)).date()
    
    response = requests.get(
        "https://api.example.com/audit/export",
        headers=headers,
        params={
            "start_date": str(date),
            "end_date": str(next_date),
            "operation": "write"
        }
    )
    
    count = response.json()["count"]
    print(f"{date}: {count} memories written")
```

---

### Alert Integration

```python
# Alert if certificate expires in < 7 days
import requests
from datetime import datetime, timedelta

headers = {"X-API-Key": "sk-admin-key"}
response = requests.get(
    "https://api.example.com/system/certificate-status",
    headers=headers
)

cert = response.json()
expires_str = cert["certificate_info"]["notAfter"]
expires_date = datetime.strptime(expires_str, "%b %d %H:%M:%S %Y %Z")

if (expires_date - datetime.utcnow()).days < 7:
    send_alert(f"Certificate expires in {(expires_date - datetime.utcnow()).days} days")
```

---

## Best Practices

1. **Cache API responses** - Don't call every 5 seconds, use 30-60 second intervals
2. **Filter by date range** - Large exports can be slow; use start_date/end_date
3. **Use pagination** - The `limit` parameter defaults to 10,000; use pagination for large datasets
4. **Monitor cert expiry** - Set up alerts for certificate renewal failures
5. **Track policy denials** - Alert on unexpected policy enforcement changes
6. **Audit log retention** - Implement log archival to prevent storage bloat

---

## Support

- **API Docs**: See USER_GUIDES.md for endpoint details
- **Architecture**: See ARCHITECTURE.md for governance model
- **Policies**: See POLICY_SCHEMA.md for policy definitions
- **Examples**: See example dashboards in this guide

---

Created: February 2, 2026
AMG Version: 1.0.0 (Phase 5 Complete)
