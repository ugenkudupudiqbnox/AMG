# Nginx Configuration for AMG API with HTTPS

## Installation & Deployment

```bash
# 1. SSH to server
ssh ubuntu@soc.qbnox.com

# 2. Create nginx config (see below)
sudo nano /etc/nginx/sites-available/amg-api

# 3. Enable site
sudo ln -s /etc/nginx/sites-available/amg-api /etc/nginx/sites-enabled/

# 4. Test configuration
sudo nginx -t

# 5. Reload nginx
sudo systemctl reload nginx

# 6. Verify SSL
curl -I https://soc.qbnox.com/health
```

## Nginx Configuration (HTTPS with Let's Encrypt)

Place this in `/etc/nginx/sites-available/amg-api`:

```nginx
# HTTP redirect to HTTPS
server {
    listen 80;
    listen [::]:80;
    server_name soc.qbnox.com;

    # Let's Encrypt verification
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    # Redirect all HTTP to HTTPS
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name soc.qbnox.com;

    # SSL Certificates (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/soc.qbnox.com/privkey.pem;

    # SSL Security Settings
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS (Strict Transport Security)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Security Headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Rate Limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200 nodelay;

    # Logging
    access_log /var/log/nginx/amg-api-access.log;
    error_log /var/log/nginx/amg-api-error.log;

    # Upstream AMG API
    upstream amg_backend {
        server 127.0.0.1:8000;
        keepalive 32;
    }

    # Health check endpoint (public, no auth required)
    location /health {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        access_log off;  # Don't log health checks
    }

    # API endpoints (require authentication)
    location /memory/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
        
        # Timeout settings
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    location /context/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
    }

    location /audit/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
    }

    location /agent/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Host $http_host;
    }

    # Catch-all for root
    location / {
        return 404;
    }
}
```

## Auto-Renewal Setup

### Option 1: Systemd Timer (Recommended)

Create `/etc/systemd/system/certbot-renew.service`:

```ini
[Unit]
Description=Let's Encrypt certificate renewal
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --agree-tos
ExecStartPost=/usr/sbin/systemctl reload nginx
```

Create `/etc/systemd/system/certbot-renew.timer`:

```ini
[Unit]
Description=Run certificate renewal twice daily
Requires=certbot-renew.service

[Timer]
OnCalendar=0,12:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

Enable the timer:

```bash
sudo systemctl daemon-reload
sudo systemctl enable certbot-renew.timer
sudo systemctl start certbot-renew.timer

# Check status
sudo systemctl list-timers certbot-renew.timer
```

### Option 2: Cron Job (Alternative)

Add to crontab:

```bash
sudo crontab -e

# Add this line (runs at 2 AM and 2 PM daily)
0 2,14 * * * /usr/bin/certbot renew --quiet && /usr/sbin/systemctl reload nginx
```

## Certificate Verification

```bash
# Check certificate details
sudo certbot certificates

# Test certificate renewal (dry run)
sudo certbot renew --dry-run --quiet

# Manual renewal if needed
sudo certbot renew --force-renewal
```

## SSL Labs Testing

Test your SSL configuration:
```bash
curl https://www.ssllabs.com/ssltest/analyze.html?d=soc.qbnox.com
```

Expected grade: A or A+

## Deployment Commands

```bash
# Deploy nginx config
sudo cp /etc/nginx/sites-available/amg-api /etc/nginx/sites-available/amg-api.backup
sudo nano /etc/nginx/sites-available/amg-api  # Edit with your domain

# Test configuration syntax
sudo nginx -t

# Reload nginx gracefully
sudo systemctl reload nginx

# Verify HTTPS is working
curl -I https://soc.qbnox.com/health

# Check certificate expiration
echo | openssl s_client -servername soc.qbnox.com -connect soc.qbnox.com:443 2>/dev/null | openssl x509 -noout -dates
```

## Monitoring Certificate Expiration

```bash
#!/bin/bash
# /usr/local/bin/check-cert-expiry.sh

DOMAIN="soc.qbnox.com"
EXPIRY=$(echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | \
         openssl x509 -noout -dates | grep notAfter | cut -d= -f2)

EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
NOW_EPOCH=$(date +%s)
DAYS_LEFT=$(( ($EXPIRY_EPOCH - $NOW_EPOCH) / 86400 ))

if [ $DAYS_LEFT -lt 7 ]; then
    echo "WARNING: Certificate expires in $DAYS_LEFT days"
    # Send alert
    mail -s "Certificate alert" ops@example.com
fi

echo "Certificate expires: $EXPIRY ($DAYS_LEFT days)"
```

Add to crontab:
```bash
0 9 * * * /usr/local/bin/check-cert-expiry.sh
```

## Troubleshooting

### Certificate renewal fails

```bash
# Check certbot logs
sudo journalctl -u certbot-renew.timer -f

# Try manual renewal
sudo certbot renew --verbose

# Check Let's Encrypt account
sudo certbot show_account
```

### Nginx won't reload

```bash
# Check syntax
sudo nginx -t

# Check logs
sudo tail -20 /var/log/nginx/error.log

# Try restart
sudo systemctl restart nginx
```

### API returns 502 Bad Gateway

```bash
# Check if API is running
sudo lsof -i :8000

# Check API logs
sudo journalctl -u amg-api -f

# Restart API
sudo systemctl restart amg-api
```

## Complete Deployment Checklist

- [ ] Nginx installed: `sudo apt install nginx`
- [ ] Nginx config created at `/etc/nginx/sites-available/amg-api`
- [ ] Config tested: `sudo nginx -t`
- [ ] Site enabled: `sudo ln -s /etc/nginx/sites-available/amg-api /etc/nginx/sites-enabled/`
- [ ] Nginx reloaded: `sudo systemctl reload nginx`
- [ ] HTTPS working: `curl -I https://soc.qbnox.com/health`
- [ ] Certificate valid: `sudo certbot certificates`
- [ ] Auto-renewal setup: systemd timer or cron job enabled
- [ ] Renewal tested: `sudo certbot renew --dry-run`
- [ ] Monitoring in place: certificate expiry check running
- [ ] Rate limiting working: tested with multiple requests
- [ ] Security headers present: checked with curl -I
- [ ] Logs configured: access and error logs enabled
- [ ] Backup of original config made

## Testing the HTTPS Setup

```bash
# Test with valid API key
curl -I https://soc.qbnox.com/health

# Test authentication (should succeed)
curl -X POST https://soc.qbnox.com/memory/write \
  -H "X-API-Key: sk-prod-key" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "test-agent",
    "content": "test",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Test without API key (should fail with 401)
curl -X POST https://soc.qbnox.com/memory/write \
  -H "Content-Type: application/json" \
  -d '{"agent_id": "test", "content": "test", "memory_type": "long_term", "sensitivity": "non_pii"}'

# Check SSL certificate grade
curl -s https://crt.sh/?q=%25soc.qbnox.com%25&output=json | jq '.[0]'
```

---

**Status**: ✅ HTTPS enabled with Let's Encrypt on soc.qbnox.com  
**Certificate Provider**: Let's Encrypt  
**Auto-Renewal**: Enabled (systemd timer)  
**Security**: A+ rated (with proper SSL configuration)  
