# Grafana Setup for AMG - Complete

## ✅ Status: Running

Grafana has been successfully installed and configured on **soc.qbnox.com** for monitoring AMG.

---

## 🔐 Access Credentials

| Item | Value |
|------|-------|
| **URL** | https://grafana.soc.qbnox.com |
| **Username** | admin |
| **Password** | ZXrDDLndlBxn9ECW |

⚠️ **Important**: Change the admin password immediately after first login.

---

## 📡 AMG Data Source Configuration

The Grafana instance is pre-configured with an AMG data source:

| Setting | Value |
|---------|-------|
| **Name** | AMG |
| **Type** | Prometheus (HTTP) |
| **URL** | https://soc.qbnox.com |
| **Auth** | Custom HTTP Header |
| **Header Name** | X-API-Key |
| **Header Value** | sk-admin-key |

This data source connects Grafana to the AMG governance API, enabling you to query:
- Memory statistics (`/stats/memory-summary`)
- Agent activity (`/stats/agent-activity`)
- Audit logs (`/audit/export`)
- System status (`/system/certificate-status`)
- Rate limit hits (`/stats/rate-limit-hits`)

---

## 🚀 Quick Start

### 1. Access Grafana

Open: https://grafana.soc.qbnox.com

Log in with:
- Username: `admin`
- Password: `ZXrDDLndlBxn9ECW`

### 2. Create Your First Dashboard

1. Go to **Dashboards** → **Create** → **Dashboard**
2. Click **Add Panel** → **Add Data Source Query**
3. Select `AMG` as the data source
4. Enter a query path (e.g., `/stats/memory-summary`)
5. Configure visualization (Stat, Graph, Table, etc.)
6. Save dashboard

### 3. Example Panel: Memory Usage

```json
{
  "datasource": "AMG",
  "targets": [
    {
      "url": "https://soc.qbnox.com/stats/memory-summary",
      "method": "GET"
    }
  ],
  "type": "stat",
  "title": "Total Memory Items"
}
```

---

## 📊 Available API Endpoints

All these endpoints are available through the AMG data source:

| Endpoint | Purpose |
|----------|---------|
| `/audit/export` | Export audit logs (compliance) |
| `/stats/memory-summary` | Memory breakdown by type/sensitivity/scope |
| `/stats/agent-activity` | Agent operation counts |
| `/stats/rate-limit-hits` | Rate limiting statistics |
| `/config/policies` | Governance policies |
| `/config/agents` | Agent registry and status |
| `/system/certificate-status` | SSL certificate expiry |

**Complete Reference:** See [DASHBOARD_BUILDER_GUIDE.md](DASHBOARD_BUILDER_GUIDE.md)

---

## 🔧 Configuration Files

| File | Purpose | Location |
|------|---------|----------|
| **Grafana Config** | Main settings | `/opt/grafana/conf/custom.ini` |
| **Nginx Proxy** | HTTPS reverse proxy | `/etc/nginx/sites-available/grafana-proxy` |
| **Data Source Config** | AMG provisioning | `/opt/grafana/conf/provisioning/datasources/amg.yaml` |
| **Logs** | Grafana logs | `/opt/grafana/data/log/grafana.log` |

---

## 📝 Managing Grafana

### View Logs

```bash
ssh ubuntu@soc.qbnox.com
tail -f /opt/grafana/data/log/grafana.log
```

### Restart Grafana

```bash
ssh ubuntu@soc.qbnox.com
sudo pkill -f grafana-server
sudo nohup /opt/grafana/bin/grafana-server --config=/opt/grafana/conf/custom.ini --homepath=/opt/grafana > /opt/grafana/data/log/grafana.log 2>&1 &
```

### Check Grafana Process

```bash
ssh ubuntu@soc.qbnox.com
ps aux | grep grafana
```

---

## 🔒 Security Considerations

### 1. Change Admin Password

After first login, immediately change the default password:

1. Click profile icon (bottom left)
2. Select "Change password"
3. Enter new strong password (min 8 chars, mixed case + numbers)

### 2. Authentication

- Grafana is only accessible via HTTPS (port 443)
- Uses same Let's Encrypt certificate as AMG API
- HTTP traffic auto-redirects to HTTPS (301)

### 3. Data Source Security

- AMG API key is stored in provisioning config (readable by Grafana user)
- Only HTTPS connections allowed (no cleartext API keys)
- Consider using separate read-only API key for Grafana

---

## 🎯 Example Dashboards

See [DASHBOARD_BUILDER_GUIDE.md](DASHBOARD_BUILDER_GUIDE.md) for complete dashboard examples:

- **Compliance Dashboard**: Policy violations, audit trails, deny logs
- **Operations Dashboard**: Memory growth trends, agent counts, certificate expiry alerts
- **Security Dashboard**: Disabled agents, failed auth attempts, suspicious activity

---

## 🐛 Troubleshooting

### Grafana Not Responding

1. Check process:
   ```bash
   ps aux | grep grafana
   ```

2. Check logs:
   ```bash
   tail -f /opt/grafana/data/log/grafana.log
   ```

3. Restart:
   ```bash
   sudo pkill -f grafana-server
   # Wait 5 seconds, then start again (see "Restart Grafana" above)
   ```

### Data Source Connection Failure

1. Verify AMG API is running:
   ```bash
   curl -s https://soc.qbnox.com/health -H "X-API-Key: sk-admin-key"
   ```

2. Check Grafana logs for connection errors:
   ```bash
   tail -100 /opt/grafana/data/log/grafana.log | grep -i error
   ```

3. Verify API key is correct in:
   ```bash
   cat /opt/grafana/conf/provisioning/datasources/amg.yaml
   ```

### HTTPS Certificate Issues

Let's Encrypt certificate auto-renews on Feb 3, 2026. If you see certificate warnings:

```bash
# Check certificate expiry
echo | openssl s_client -servername grafana.soc.qbnox.com \
  -connect grafana.soc.qbnox.com:443 2>/dev/null | \
  openssl x509 -noout -dates
```

---

## 📈 Next Steps

1. **Create dashboards** using the AMG data source
2. **Set up alerts** for policy violations, cert expiry
3. **Configure team access** (Grafana → Admin → Users)
4. **Integrate with alerting** (PagerDuty, Slack, etc.)
5. **Schedule exports** for compliance reports

---

## 📚 Additional Resources

- [USER_GUIDES.md - Dashboard Setup Section](USER_GUIDES.md#6-dashboard-setup--monitoring)
- [DASHBOARD_BUILDER_GUIDE.md](DASHBOARD_BUILDER_GUIDE.md)
- [Grafana Official Docs](https://grafana.com/docs)
- [AMG API Documentation](PHASE_5_HTTP_API.md)

---

## 🔑 Server Information

| Property | Value |
|----------|-------|
| **Domain** | soc.qbnox.com |
| **IP Address** | 172.26.6.91 |
| **Grafana URL** | https://grafana.soc.qbnox.com |
| **Grafana Port (internal)** | 3001 |
| **Nginx Port (public)** | 443 (HTTPS) / 80 (HTTP→HTTPS redirect) |
| **OS** | Ubuntu 22.04.5 LTS |
| **Certificate** | Let's Encrypt (auto-renewing) |
| **Process ID** | 1892278 |

---

**Setup Date**: February 2, 2026 11:08 UTC  
**Status**: ✅ Production Ready
