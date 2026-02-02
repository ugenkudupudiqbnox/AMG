# Grafana Dashboards for AMG Monitoring

**Status**: Installed and running at `https://grafana.soc.qbnox.com`
**Automatic Provisioning**: Enabled (Dashboards are automatically created on setup)

---

## Automatic Dashboards

The standard AMG suite includes the following pre-built dashboards:

### 1. AMG Governance Overview
- **Path**: Search for "AMG Governance Overview" in Grafana
- **Panels**:
  - **Total Memories**: Live count of all stored memory items.
  - **Memory by Type**: Donut chart showing distribution of short-term, long-term, and episodic memories.
- **Data Source**: Automatically connected to `AMG-API`.

---

## Quick Start

### Access
- **URL**: https://grafana.soc.qbnox.com
- **Initial Login**: admin / admin
- **⚠️ Security**: Change password immediately after login

### Infrastructure
- **Container**: Grafana 12.3.2 (Docker)
- **Internal Port**: 3100 (127.0.0.1:3100)
- **Public Port**: 443 (HTTPS via Nginx)
- **Reverse Proxy**: Nginx with wildcard SSL certificate
- **Datasource**: AMG-API (https://api.soc.qbnox.com)
- **Authentication**: X-API-Key: sk-admin-key-grafana

---

## Available Dashboards

### 1. AMG Memory Statistics
**Purpose**: Monitor memory usage by classification

**Panels**:
- **Total Memory Items** (Stat) - Aggregate count of all memory items
- **Memory by Type** (Pie Chart) - Distribution: short_term | long_term | episodic
- **Memory by Sensitivity** (Pie Chart) - Distribution: pii | non_pii
- **Memory by Scope** (Pie Chart) - Distribution: agent | tenant

**Data Source**: `/stats/memory-summary`

**Example Response**:
```json
{
  "total_items": 1245,
  "by_type": {
    "short_term": 234,
    "long_term": 890,
    "episodic": 121
  },
  "by_sensitivity": {
    "pii": 156,
    "non_pii": 1089
  },
  "by_scope": {
    "agent": 945,
    "tenant": 300
  },
  "total_size_bytes": 2850432,
  "average_ttl_seconds": 7776000,
  "last_update": "2026-02-02T11:45:00Z"
}
```

**Key Metrics**:
- Total memory items in system
- Long-term vs short-term ratio (storage cost indicator)
- PII vs non-PII split (data sensitivity management)
- Agent vs tenant scope distribution (isolation verification)

---

### 2. AMG Agent Activity
**Purpose**: Track agent behavior and operations

**Panels**:
- **Agent Operations Summary** (Stat) - Total operations across all agents
- **Operation Types** (Bar Gauge) - Count by operation type: write | read | query | disable

**Data Source**: `/stats/agent-activity`

**Example Response**:
```json
{
  "total_operations": 12847,
  "by_operation": {
    "write": 5234,
    "read": 6789,
    "query": 789,
    "disable": 35
  },
  "unique_agents": 24,
  "operations_per_agent": 534.5,
  "last_24h_operations": 3456,
  "top_agents": [
    {
      "agent_id": "agent-001",
      "operations": 1234,
      "last_operation": "2026-02-02T11:40:00Z"
    },
    {
      "agent_id": "agent-002",
      "operations": 987,
      "last_operation": "2026-02-02T11:35:00Z"
    }
  ]
}
```

**Key Metrics**:
- Total operations (system load indicator)
- Read/write ratio (access patterns)
- Agent count and average operations (distribution)
- Disable operations (incident response tracking)

---

### 3. AMG System Health
**Purpose**: Infrastructure and governance health monitoring

**Panels**:
- **Rate Limit Hits** (Stat) - Total rate limit violations
- **Certificate Status** (Stat) - SSL certificate expiry and validity
- **Policies** (Table) - Active governance policies

**Data Sources**: 
- `/stats/rate-limit-hits`
- `/system/certificate-status`
- `/config/policies`

**Example Response (Rate Limits)**:
```json
{
  "total_hits": 42,
  "by_limit_type": {
    "memory_write_per_minute": 15,
    "query_per_second": 18,
    "context_size_tokens": 9
  },
  "top_violators": [
    {
      "agent_id": "agent-005",
      "hits": 12,
      "limit": "memory_write_per_minute",
      "first_hit": "2026-02-01T08:00:00Z",
      "last_hit": "2026-02-02T10:30:00Z"
    }
  ],
  "last_reset": "2026-02-02T00:00:00Z",
  "reset_frequency": "daily"
}
```

**Example Response (Certificate)**:
```json
{
  "status": "valid",
  "domain": "*.soc.qbnox.com",
  "issuer": "Let's Encrypt",
  "issued_at": "2026-01-05T10:15:00Z",
  "expires_at": "2026-04-05T10:15:00Z",
  "days_remaining": 62,
  "renewal_date": "2026-03-19T10:15:00Z",
  "auto_renewal": true
}
```

**Example Response (Policies)**:
```json
{
  "policies": [
    {
      "id": "policy-001",
      "name": "default_pii_retention",
      "memory_type": "long_term",
      "sensitivity": "pii",
      "ttl_seconds": 604800,
      "scope": "tenant",
      "created_at": "2025-01-01T00:00:00Z",
      "version": "1.2.0"
    },
    {
      "id": "policy-002",
      "name": "default_non_pii_retention",
      "memory_type": "long_term",
      "sensitivity": "non_pii",
      "ttl_seconds": 2592000,
      "scope": "agent",
      "created_at": "2025-01-01T00:00:00Z",
      "version": "1.2.0"
    }
  ],
  "total_policies": 2,
  "version": "1.2.0"
}
```

**Key Metrics**:
- Rate limit violations (throttling effectiveness)
- Certificate expiry (operational risk)
- Policy count and configuration (governance coverage)

---

## KPI Definitions

### Memory KPIs
| KPI | Calculation | Threshold | Action |
|-----|-------------|-----------|--------|
| **Total Items** | sum of all memory records | <1M | Normal |
| **Total Items** | sum of all memory records | >5M | Review retention policy |
| **PII Ratio** | pii_items / total_items | <5% | Normal |
| **PII Ratio** | pii_items / total_items | >20% | Review PII handling |
| **Long-term Avg TTL** | avg TTL of long_term memory | <30 days | Risk: data loss |
| **Long-term Avg TTL** | avg TTL of long_term memory | >90 days | Normal |

### Agent Activity KPIs
| KPI | Calculation | Threshold | Action |
|-----|-------------|-----------|--------|
| **Ops/Agent/Sec** | total_ops / unique_agents / seconds | <10 | Underutilized |
| **Ops/Agent/Sec** | total_ops / unique_agents / seconds | 10-100 | Normal |
| **Ops/Agent/Sec** | total_ops / unique_agents / seconds | >100 | High load, review |
| **Read/Write Ratio** | read_ops / write_ops | 3-5 | Normal (reads dominate) |
| **Read/Write Ratio** | read_ops / write_ops | <1 | Unusual: more writes |
| **Disable Ops %** | disable_ops / total_ops * 100 | 0-1% | Normal |
| **Disable Ops %** | disable_ops / total_ops * 100 | >5% | Incident investigation |

### System Health KPIs
| KPI | Calculation | Threshold | Action |
|-----|-------------|-----------|--------|
| **Rate Limit Hits** | total violations | 0 | Normal |
| **Rate Limit Hits** | total violations | >50/day | Policy too strict |
| **Certificate Valid** | expires_at > now | >7 days | Normal |
| **Certificate Valid** | expires_at > now | <7 days | Urgent renewal |
| **Policy Count** | count of active policies | >0 | Governance active |
| **Policy Count** | count of active policies | 0 | ⚠️ No policies defined |

---

## API Endpoints for Custom Dashboards

All endpoints require `X-API-Key: sk-admin-key-grafana` header.

### Memory Statistics
```http
GET /stats/memory-summary
```

Returns memory distribution by type, sensitivity, and scope.

### Agent Activity  
```http
GET /stats/agent-activity
```

Returns operation counts and per-agent statistics.

### Rate Limit Statistics
```http
GET /stats/rate-limit-hits
```

Returns rate limit violations and violator details.

### Certificate Status
```http
GET /system/certificate-status
```

Returns SSL certificate validity, expiry, and renewal info.

### Audit Log Export
```http
GET /audit/export?start_date=2026-02-01&end_date=2026-02-02&operation=write
```

Returns immutable audit records (policy enforcement decisions).

### Governance Policies
```http
GET /config/policies
```

Returns active governance policies.

### Agent Registry
```http
GET /config/agents
```

Returns registered agents and their configuration.

---

## Dashboard Creation Guide

### Creating a Custom Dashboard in Grafana

1. **Login**: Visit https://grafana.soc.qbnox.com, login as admin/admin
2. **New Dashboard**: Click "+" → "Dashboard"
3. **Add Panel**: Click "Add a new panel"
4. **Configure**:
   - **Data Source**: Select "AMG-API"
   - **URL**: Enter endpoint (e.g., `/stats/memory-summary`)
   - **HTTP Headers**: Add `X-API-Key: sk-admin-key-grafana`
5. **Visualize**: Choose panel type (Stat, Pie Chart, Bar Gauge, Table, etc.)
6. **Save**: Click "Save dashboard"

### Example: Memory Growth Over Time

```json
{
  "title": "Memory Growth Tracking",
  "panels": [
    {
      "title": "Total Items Over Time",
      "type": "timeseries",
      "datasource": "AMG-API",
      "targets": [
        {
          "url": "/stats/memory-summary"
        }
      ],
      "fieldConfig": {
        "defaults": {
          "custom": {
            "hideFrom": {
              "tooltip": false,
              "viz": false,
              "legend": false
            }
          }
        }
      }
    }
  ]
}
```

---

## Alerting & Monitoring

### Recommended Alerts

1. **Memory Size Alert**
   - Threshold: Total size > 10GB
   - Action: Investigate retention policies, consider archival

2. **PII Ratio Alert**
   - Threshold: PII items > 25% of total
   - Action: Review PII classification and TTL

3. **Certificate Expiry Alert**
   - Threshold: Expires in < 7 days
   - Action: Trigger renewal (automated via Let's Encrypt)

4. **Rate Limit Alert**
   - Threshold: >100 violations/day
   - Action: Tune rate limits or increase agent quota

5. **Agent Disable Alert**
   - Threshold: Any disable operation
   - Action: Page on-call engineer, review audit logs

---

## Performance Tuning

### Dashboard Refresh Rates
- **Memory Statistics**: 5-minute refresh (stable data)
- **Agent Activity**: 1-minute refresh (operational data)
- **System Health**: 5-minute refresh (stable data)

### Query Optimization
- Use date range filters to limit data volume
- Filter by agent_id for specific agent analysis
- Cache policy responses (changes infrequently)

---

## Troubleshooting

### Grafana Not Responding
```bash
ssh ubuntu@soc.qbnox.com
sudo docker logs grafana
```

### Datasource Connection Failed
```bash
# Verify AMG API is running
curl -I https://api.soc.qbnox.com/stats/memory-summary \
  -H "X-API-Key: sk-admin-key-grafana"

# Check Nginx proxy
sudo nginx -t
sudo systemctl reload nginx
```

### Nginx Certificate Error
```bash
# Verify certificate
openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem -noout -dates

# Reload Nginx if cert updated
sudo systemctl reload nginx
```

---

## Production Checklist

- [ ] Change Grafana admin password
- [ ] Create read-only viewer role (if multi-user)
- [ ] Enable SMTP for alerts
- [ ] Configure dashboard refresh rates
- [ ] Set up certificate renewal monitoring
- [ ] Create runbooks for common issues
- [ ] Document custom dashboards
- [ ] Test alert notifications
- [ ] Back up Grafana configuration

---

## References

- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [AMG API Documentation](./README.md)
- [AMG Policy Schema](./POLICY_SCHEMA.md)
- [Deployment Guide](./HTTPS_DEPLOYMENT_COMPLETE.md)
