# Grafana Installation Summary for AMG

**Date**: 2026-02-02  
**Status**: ✅ Installed and Running  
**Version**: Grafana 12.3.2 (Docker)

---

## Quick Access

| Item | Value |
|------|-------|
| **URL** | https://grafana.soc.qbnox.com |
| **Initial Login** | admin / admin |
| **Container Status** | ✅ Running (Docker) |
| **Internal Port** | 3100 (127.0.0.1) |
| **Public Port** | 443 (HTTPS) |
| **Proxy** | Nginx with wildcard SSL |
| **Uptime** | 1+ minutes |

---

## Installation Details

### Container Configuration
```bash
docker run -d \
  --name grafana \
  -p 127.0.0.1:3100:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  -e GF_USERS_ALLOW_SIGN_UP=false \
  -e GF_SERVER_ROOT_URL=https://grafana.soc.qbnox.com \
  -v grafana_storage:/var/lib/grafana \
  grafana/grafana:latest
```

### Nginx Reverse Proxy
- **HTTP** → HTTPS redirect
- **TLS Protocols**: TLSv1.2, TLSv1.3
- **SSL Certificate**: /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem
- **HSTS**: 1 year
- **Security Headers**: Enabled

### Data Source
- **Name**: AMG-API
- **Type**: Grafana HTTP API Datasource
- **URL**: https://api.soc.qbnox.com
- **Authentication**: X-API-Key: sk-admin-key-grafana

---

## Available Dashboards

### 1. AMG Memory Statistics
Shows memory distribution and classification metrics:
- Total memory items count
- Distribution by type (short_term, long_term, episodic)
- Distribution by sensitivity (pii, non_pii)
- Distribution by scope (agent, tenant)

### 2. AMG Agent Activity
Tracks agent operations and behavior:
- Total operations across all agents
- Operation breakdown (write, read, query, disable)
- Per-agent statistics
- Last activity timestamps

### 3. AMG System Health
Monitors infrastructure and governance:
- Rate limit violations count
- SSL certificate validity and expiry
- Active governance policies
- Policy configuration details

---

## KPI Metrics

### Memory Management KPIs
```
Total Items     : Integer (target: <1M for performance)
PII Ratio       : % (target: <5-20% depending on use case)
Long-term TTL   : Days (target: 30-90 days average)
Storage Used    : GB (track growth rate)
By Type         : short_term %, long_term %, episodic %
By Scope        : agent %, tenant %
```

### Agent Activity KPIs
```
Total Operations     : Count (total system load)
Operations/Agent/Sec : Rate (target: 10-100)
Read/Write Ratio     : Ratio (target: 3-5:1)
Unique Agents        : Count (agent count in system)
Last 24h Operations  : Count (trend analysis)
Disable Operations   : Count (incident tracking)
```

### System Health KPIs
```
Rate Limit Hits          : Count (target: 0, <50/day acceptable)
Certificate Days Valid   : Days (alert if <7 days)
Policy Count             : Count (target: >0)
API Availability         : % (target: 99.9%+)
Response Time            : ms (target: <200ms)
Error Rate               : % (target: <0.1%)
```

---

## API Endpoints Available

### Statistics & Reporting
```http
GET /stats/memory-summary
    ↳ Memory distribution by type, sensitivity, scope

GET /stats/agent-activity  
    ↳ Agent operations and activity metrics

GET /stats/rate-limit-hits
    ↳ Rate limiting violations and patterns

GET /system/certificate-status
    ↳ SSL certificate validity and renewal info

GET /audit/export?start_date=...&end_date=...
    ↳ Immutable audit trail of policy decisions

GET /config/policies
    ↳ Active governance policies configuration

GET /config/agents
    ↳ Agent registry and configuration
```

All endpoints require header: `X-API-Key: sk-admin-key-grafana`

---

## Architecture

```
┌─────────────────────────────────────────┐
│       Internet (HTTPS/TLS 1.2+)         │
└──────────────────┬──────────────────────┘
                   │
                   ↓
        ┌──────────────────────┐
        │  Nginx Reverse Proxy │
        │  (grafana.*)         │
        │  Port: 443           │
        └──────────┬───────────┘
                   │
                   ↓ (localhost:3100)
        ┌──────────────────────┐
        │    Grafana 12.3.2    │
        │    (Docker)          │
        │    Port: 3100        │
        └──────────┬───────────┘
                   │ (HTTP)
                   ↓
        ┌──────────────────────┐
        │    AMG-API Metrics   │
        │    (soc.qbnox.com)   │
        │    Port: 443         │
        └──────────────────────┘
```

---

## Configuration Files

### Nginx Configuration
**File**: `/etc/nginx/sites-available/grafana-amg`  
**Symlink**: `/etc/nginx/sites-enabled/grafana-amg`

Features:
- HTTP to HTTPS redirect
- TLS 1.2/1.3 only
- HSTS header (1 year)
- Proxy to 127.0.0.1:3100
- X-Forwarded headers for client IP

### Docker Volume
**Name**: `grafana_storage`  
**Path**: `/var/lib/grafana`  
**Contents**: Dashboards, datasources, user data

---

## Security Considerations

✅ **Implemented**:
- HTTPS/TLS 1.2+ encryption
- Admin authentication required
- Sign-up disabled (admin-only access)
- Wildcard SSL certificate
- HSTS enabled
- X-API-Key authentication to backend

⚠️ **TODO** (Recommended):
- [ ] Change initial admin password (admin/admin)
- [ ] Create read-only viewer account (if multi-user needed)
- [ ] Enable SMTP for alert notifications
- [ ] Configure audit logging
- [ ] Set up backup/restore procedures
- [ ] Document disaster recovery

---

## First-Time Access

1. **Visit**: https://grafana.soc.qbnox.com
2. **Login**: admin / admin
3. **Change Password**: Admin → Profile → Change Password
4. **Verify Datasource**: Data Sources → AMG-API (should show green)
5. **View Dashboards**: Click on "Dashboards" in left sidebar

---

## Monitoring & Alerts

### Recommended Alert Rules

1. **High Memory Usage**
   - Condition: total_items > 5,000,000
   - Action: Review retention policies

2. **PII Accumulation**
   - Condition: pii_ratio > 25%
   - Action: Audit PII classification

3. **Certificate Expiry**
   - Condition: days_remaining < 7
   - Action: Trigger renewal (automated)

4. **Rate Limiting**
   - Condition: daily_hits > 100
   - Action: Review limits and agent quotas

5. **Agent Disable**
   - Condition: Any disable operation
   - Action: Page on-call engineer

---

## Troubleshooting

### Grafana Not Accessible
```bash
# Check container status
ssh ubuntu@soc.qbnox.com
sudo docker ps | grep grafana

# View logs
sudo docker logs grafana --tail 50

# Restart if needed
sudo docker restart grafana
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

### Port Already in Use
```bash
# Check what's on port 3100
sudo lsof -i :3100

# If conflict, change GRAFANA_PORT environment variable
```

### HTTPS Certificate Issues
```bash
# Verify certificate
openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem \
  -noout -dates

# Check renewal status
sudo certbot renew --dry-run
```

---

## Maintenance

### Daily
- Monitor dashboard metrics for anomalies
- Check rate limiting violations

### Weekly
- Review agent activity trends
- Verify certificate renewal (automated)

### Monthly
- Analyze memory growth trends
- Audit policy effectiveness
- Test disaster recovery

### Quarterly
- Update Grafana version
- Review and update alert thresholds
- Capacity planning assessment

---

## Next Steps

1. **⚠️ Security**
   - Change admin password immediately
   - Enable SMTP for notifications

2. **Configuration**
   - Create custom dashboards as needed
   - Set up alert rules

3. **Documentation**
   - Document custom dashboards
   - Create runbooks for on-call

4. **Monitoring**
   - Set up external uptime monitoring
   - Configure log aggregation

---

## Documentation References

- [Grafana Dashboards Guide](./GRAFANA_DASHBOARDS.md)
- [Grafana Subdomain Setup](./GRAFANA_SUBDOMAIN_SETUP.md)
- [User Guides - Dashboard Setup](./USER_GUIDES.md#section-6-dashboard-setup--monitoring)
- [API Documentation](./README.md)
- [Deployment Checklist](./DEPLOYMENT_CHECKLIST.md)

---

## Support

For issues or questions:
1. Check [GRAFANA_DASHBOARDS.md](./GRAFANA_DASHBOARDS.md) troubleshooting section
2. Review Docker logs: `sudo docker logs grafana`
3. Check Nginx configuration: `sudo nginx -t`
4. Verify API connectivity: `curl https://api.soc.qbnox.com/health`

---

**Last Updated**: 2026-02-02 11:44 UTC  
**Commit**: 136a2b6  
**Branch**: main
