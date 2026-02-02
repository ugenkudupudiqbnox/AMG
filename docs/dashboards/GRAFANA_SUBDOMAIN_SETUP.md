# Grafana Setup for grafana.soc.qbnox.com

This guide sets up Grafana for monitoring AMG on a separate, secure subdomain using wildcard SSL certificates.

## Architecture

```
┌─────────────────────────────────────┐
│  https://grafana.soc.qbnox.com      │
│  (public HTTPS, wildcard cert)      │
└────────────┬────────────────────────┘
             │ Nginx reverse proxy
             ▼
┌─────────────────────────────────────┐
│  Grafana on localhost:3000          │
│  (internal, Docker or systemd)      │
└────────────┬────────────────────────┘
             │ HTTP API
             ▼
┌─────────────────────────────────────┐
│  https://api.soc.qbnox.com          │
│  (AMG API with X-API-Key)           │
└─────────────────────────────────────┘
```

## Prerequisites

- Production server: soc.qbnox.com (172.26.6.91)
- DNS: grafana.soc.qbnox.com → 172.26.6.91 (already configured)
- Certificates: *.soc.qbnox.com wildcard (Let's Encrypt)
- Nginx: Already installed and configured for api.soc.qbnox.com

## Step 1: Update SSL Certificate to Include Wildcard

Expand existing certificate to include wildcard domain:

```bash
# On production server
sudo certbot certonly --cert-name soc.qbnox.com \
  --non-interactive --agree-tos \
  -m ugen@qbnox.com \
  --expand \
  --dns-route53 \
  -d soc.qbnox.com \
  -d "*.soc.qbnox.com"
```

**Verify certificate includes both domains:**

```bash
sudo openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem \
  -noout -text | grep -A1 "Subject Alternative Name"

# Should show:
# soc.qbnox.com, *.soc.qbnox.com
```

## Step 2: Install Grafana

### Option A: Docker (Recommended - Fastest)

```bash
# On production server
sudo docker run -d \
  --name grafana \
  --restart=unless-stopped \
  -p 127.0.0.1:3000:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD=admin \
  -e GF_USERS_ALLOW_SIGN_UP=false \
  -e GF_INSTALL_PLUGINS=grafana-http-api-datasource \
  grafana/grafana:latest

# Verify
curl -s http://127.0.0.1:3000/api/health | jq '.status'
# Should return: "ok"
```

### Option B: Systemd (If prefer no Docker)

```bash
# Add Grafana repository
sudo mkdir -p /etc/apt/keyrings
wget -q -O - https://apt.grafana.com/gpg.key | gpg --dearmor | \
  sudo tee /etc/apt/keyrings/grafana.gpg > /dev/null

echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | \
  sudo tee /etc/apt/sources.list.d/grafana.list > /dev/null

# Install
sudo apt-get update
sudo apt-get install -y grafana-server

# Start
sudo systemctl enable grafana-server
sudo systemctl start grafana-server

# Verify
sudo systemctl status grafana-server --no-pager
```

## Step 3: Configure Nginx Reverse Proxy

Create Nginx configuration for grafana.soc.qbnox.com:

```bash
sudo tee /etc/nginx/sites-available/grafana-amg > /dev/null << 'NGINX_CONF'
# HTTP redirect to HTTPS
server {
    listen 80;
    server_name grafana.soc.qbnox.com;
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    server_name grafana.soc.qbnox.com;
    
    # Wildcard SSL Certificate
    ssl_certificate /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/soc.qbnox.com/privkey.pem;
    
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
    
    # Logging
    access_log /var/log/nginx/grafana-access.log;
    error_log /var/log/nginx/grafana-error.log;
    
    # Proxy to Grafana (localhost:3000)
    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Connection "";
        
        # Timeouts
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
NGINX_CONF

# Enable site
sudo ln -sf /etc/nginx/sites-available/grafana-amg /etc/nginx/sites-enabled/grafana-amg

# Test and reload
sudo nginx -t
sudo systemctl reload nginx

# Verify
curl -I https://grafana.soc.qbnox.com 2>&1 | head -5
# Should show: 302 Found or 200 OK (redirect to login)
```

## Step 4: Configure AMG API Data Source

Create Grafana provisioning config:

```bash
# Create provisioning directory
sudo mkdir -p /etc/grafana/provisioning/datasources

# Create data source config
sudo tee /etc/grafana/provisioning/datasources/amg-api.yml > /dev/null << 'DATASOURCE_CONF'
apiVersion: 1

datasources:
  - name: AMG-API
    type: grafana-http-api-datasource
    url: https://api.soc.qbnox.com
    access: proxy
    isDefault: true
    jsonData:
      httpMethod: GET
      customHeaders:
        X-API-Key: "sk-admin-key-grafana"
DATASOURCE_CONF

# Restart Grafana to load provisioning
sudo systemctl restart grafana-server
# OR if using Docker:
# sudo docker restart grafana

# Wait for restart
sleep 5

# Verify data source via API
curl -s http://127.0.0.1:3000/api/datasources \
  -H "Authorization: Bearer $(curl -s -X POST http://127.0.0.1:3000/api/login \
    -H "Content-Type: application/json" \
    -d '{"user":"admin","password":"admin"}' | jq -r '.token')" | jq '.[] | .name'

# Should include: "AMG-API"
```

## Step 5: Test and Verify

### Test Grafana is Accessible

```bash
# From your local machine
curl -I https://grafana.soc.qbnox.com

# Should show:
# HTTP/2 302 Found
# Location: https://grafana.soc.qbnox.com/login
```

### Test Data Source

```bash
# From production server
curl -s http://127.0.0.1:3000/api/datasources | jq '.[] | {name, url}'

# Should show:
# {
#   "name": "AMG-API",
#   "url": "https://api.soc.qbnox.com"
# }
```

### Test AMG API Connection

```bash
# Verify AMG API is responding
curl -s https://api.soc.qbnox.com/stats/memory-summary \
  -H "X-API-Key: sk-admin-key-grafana" | jq '.total_memory'

# Should return a number
```

## Step 6: Create Dashboards

Open browser to: **https://grafana.soc.qbnox.com**

Default login:
- Username: `admin`
- Password: `admin`

### Create Dashboard Manually

1. Click "+ Create" → "Dashboard"
2. Click "Add a new panel"
3. Data source: Select "AMG-API"
4. Add query:
   - URL: `https://api.soc.qbnox.com/stats/memory-summary`
   - Method: GET
5. Visualize results

### Import Pre-Built Dashboard

Example dashboard JSON for memory statistics:

```bash
# Via Grafana API
curl -X POST https://grafana.soc.qbnox.com/api/dashboards/db \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_TOKEN>" \
  -d '{
    "dashboard": {
      "title": "AMG Memory Statistics",
      "tags": ["amg"],
      "panels": [
        {
          "title": "Total Memory Items",
          "type": "stat",
          "datasource": "AMG-API",
          "targets": [{
            "url": "https://api.soc.qbnox.com/stats/memory-summary",
            "method": "GET"
          }],
          "fieldConfig": {
            "defaults": {
              "mappings": [],
              "thresholds": {
                "mode": "absolute",
                "steps": [
                  { "color": "green", "value": null }
                ]
              }
            }
          }
        }
      ]
    },
    "overwrite": true
  }'
```

## Step 7: Monitoring & Maintenance

### Check Grafana Status

```bash
# If using Docker
sudo docker ps | grep grafana

# If using systemd
sudo systemctl status grafana-server --no-pager
```

### View Logs

```bash
# If using Docker
sudo docker logs grafana

# If using systemd
sudo journalctl -u grafana-server -f
```

### Monitor Certificate Expiry

```bash
# Check when certificate expires
openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem \
  -noout -dates

# Should show renewal in < 30 days (Let's Encrypt auto-renews)
```

### Restart Grafana

```bash
# If using Docker
sudo docker restart grafana

# If using systemd
sudo systemctl restart grafana-server
```

## Troubleshooting

### Grafana Not Responding

```bash
# Check if Grafana is running
curl -s http://127.0.0.1:3000/api/health | jq '.'

# If Docker: check logs
sudo docker logs grafana | tail -20

# If systemd: check status
sudo systemctl status grafana-server --no-pager
```

### Data Source Not Working

```bash
# Verify API key is correct
curl -s https://api.soc.qbnox.com/stats/memory-summary \
  -H "X-API-Key: sk-admin-key-grafana" | jq '.' 

# Should return memory statistics, not 401

# Check Nginx proxy
curl -v https://grafana.soc.qbnox.com/api/datasources 2>&1 | grep X-Forward
```

### SSL Certificate Issues

```bash
# Verify wildcard certificate
sudo openssl x509 -in /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem \
  -noout -text | grep "Subject Alternative Name"

# Should include: *.soc.qbnox.com

# Test HTTPS connection
curl -I https://grafana.soc.qbnox.com
```

### DNS Not Resolving

```bash
# Verify DNS in AWS Route 53
nslookup grafana.soc.qbnox.com

# Should return: 172.26.6.91

# If not resolving, check AWS Route 53:
# - Record: grafana.soc.qbnox.com
# - Type: A
# - Value: 172.26.6.91
```

## Security Considerations

✅ **SSL/TLS**: Wildcard certificate covers grafana.soc.qbnox.com  
✅ **Authentication**: Grafana admin login required  
✅ **API Key**: Separate admin API key (sk-admin-key-grafana) for dashboard queries  
✅ **Isolation**: Grafana runs on internal port 3000, exposed only via Nginx proxy  
✅ **Headers**: Security headers (HSTS, X-Frame-Options, etc.) configured  
✅ **Logging**: Access logs at `/var/log/nginx/grafana-access.log`

## Next Steps

1. ✅ DNS configured (grafana.soc.qbnox.com)
2. ✅ Wildcard certificate (*.soc.qbnox.com)
3. ✅ Grafana installed
4. ✅ Nginx proxy configured
5. ✅ AMG API data source configured
6. Create dashboards for:
   - Memory statistics (total, by type, by sensitivity)
   - Agent activity (operations, activity patterns)
   - Governance events (policy violations, disables)
   - Infrastructure (certificate expiry, rate limits)

## References

- [Grafana Provisioning](https://grafana.com/docs/grafana/latest/setup-grafana/configure-grafana/)
- [HTTP API Datasource](https://grafana.com/grafana/plugins/grafana-http-api-datasource)
- [Nginx Reverse Proxy](https://grafana.com/tutorials/deploy-grafana-on-ubuntu/nginx)
- [Let's Encrypt Wildcard](https://letsencrypt.org/docs/faq/#does-let-s-encrypt-issue-wildcard-certificates)
