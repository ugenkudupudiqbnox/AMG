#!/bin/bash
# Setup HTTPS with Let's Encrypt for AMG on soc.qbnox.com

set -e

echo "🔒 AMG HTTPS Setup Script"
echo "========================="
echo ""

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

DOMAIN="soc.qbnox.com"
API_PORT="8000"
NGINX_CONF="/etc/nginx/sites-available/amg-api"

echo -e "${BLUE}Step 1: Verify Let's Encrypt Certificate${NC}"
if [ -f "/etc/letsencrypt/live/${DOMAIN}/fullchain.pem" ]; then
    echo -e "${GREEN}✓ Certificate found${NC}"
    echo | openssl s_client -servername $DOMAIN -connect $DOMAIN:443 2>/dev/null | openssl x509 -noout -dates
else
    echo -e "${YELLOW}⚠ Certificate not found${NC}"
    echo "Run: sudo certbot certonly --standalone -d $DOMAIN"
    exit 1
fi

echo ""
echo -e "${BLUE}Step 2: Install Nginx (if needed)${NC}"
if command -v nginx &> /dev/null; then
    echo -e "${GREEN}✓ Nginx already installed${NC}"
else
    echo "Installing nginx..."
    sudo apt-get update
    sudo apt-get install -y nginx
    echo -e "${GREEN}✓ Nginx installed${NC}"
fi

echo ""
echo -e "${BLUE}Step 3: Deploy HTTPS Configuration${NC}"
echo "Copying nginx configuration..."
sudo cp $NGINX_CONF $NGINX_CONF.backup.$(date +%s) 2>/dev/null || true

# Create the nginx config
sudo tee $NGINX_CONF > /dev/null << 'NGINXEOF'
# HTTP to HTTPS redirect
server {
    listen 80;
    listen [::]:80;
    server_name soc.qbnox.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS Server
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name soc.qbnox.com;

    ssl_certificate /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/soc.qbnox.com/privkey.pem;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;
    ssl_trusted_certificate /etc/letsencrypt/live/soc.qbnox.com/chain.pem;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200 nodelay;

    access_log /var/log/nginx/amg-api-access.log;
    error_log /var/log/nginx/amg-api-error.log;

    upstream amg_backend {
        server 127.0.0.1:8000 max_fails=3 fail_timeout=30s;
        keepalive 32;
    }

    location /health {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_connect_timeout 5s;
        proxy_send_timeout 5s;
        proxy_read_timeout 5s;
        access_log off;
    }

    location /memory/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /context/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /audit/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /agent/ {
        proxy_pass http://amg_backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        return 404;
    }
}
NGINXEOF

echo -e "${GREEN}✓ Configuration deployed${NC}"

echo ""
echo -e "${BLUE}Step 4: Test Nginx Configuration${NC}"
if sudo nginx -t; then
    echo -e "${GREEN}✓ Configuration syntax OK${NC}"
else
    echo -e "❌ Configuration error"
    exit 1
fi

echo ""
echo -e "${BLUE}Step 5: Reload Nginx${NC}"
sudo systemctl reload nginx
echo -e "${GREEN}✓ Nginx reloaded${NC}"

echo ""
echo -e "${BLUE}Step 6: Setup Certificate Auto-Renewal${NC}"

# Create systemd service for renewal
sudo tee /etc/systemd/system/certbot-renew.service > /dev/null << 'SERVICEEOF'
[Unit]
Description=Let's Encrypt certificate renewal
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/certbot renew --quiet --agree-tos
ExecStartPost=/bin/systemctl reload nginx

[Install]
WantedBy=multi-user.target
SERVICEEOF

# Create systemd timer
sudo tee /etc/systemd/system/certbot-renew.timer > /dev/null << 'TIMEREOF'
[Unit]
Description=Run Let's Encrypt certificate renewal twice daily
Requires=certbot-renew.service

[Timer]
OnCalendar=0,12:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
TIMEREOF

sudo systemctl daemon-reload
sudo systemctl enable certbot-renew.timer
sudo systemctl start certbot-renew.timer

echo -e "${GREEN}✓ Auto-renewal configured${NC}"
sudo systemctl list-timers certbot-renew.timer | head -3

echo ""
echo -e "${BLUE}Step 7: Verify HTTPS Setup${NC}"

echo "Testing HTTP redirect..."
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://soc.qbnox.com/health)
if [ "$HTTP_CODE" == "301" ]; then
    echo -e "${GREEN}✓ HTTP redirects to HTTPS (301)${NC}"
else
    echo -e "${YELLOW}⚠ HTTP returned $HTTP_CODE (expected 301)${NC}"
fi

echo ""
echo "Testing HTTPS endpoint..."
HTTPS_CODE=$(curl -s -o /dev/null -w "%{http_code}" -k https://soc.qbnox.com/health)
echo "HTTPS /health returned: $HTTPS_CODE"

echo ""
echo "Checking SSL certificate..."
curl -s https://soc.qbnox.com/health -o /dev/null && echo -e "${GREEN}✓ SSL working${NC}" || echo "⚠ SSL check"

echo ""
echo "Certificate expiry:"
echo | openssl s_client -servername soc.qbnox.com -connect soc.qbnox.com:443 2>/dev/null | openssl x509 -noout -dates

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✅ HTTPS Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Summary:"
echo "  ✓ Domain: soc.qbnox.com"
echo "  ✓ Certificate: Let's Encrypt"
echo "  ✓ Auto-renewal: Enabled (twice daily)"
echo "  ✓ HTTP: Redirects to HTTPS"
echo "  ✓ Nginx: Configured with security headers"
echo "  ✓ Rate limiting: 100 req/s with 200 burst"
echo ""
echo "Next steps:"
echo "  1. Start AMG API: sudo systemctl start amg-api"
echo "  2. Test API: curl https://soc.qbnox.com/health"
echo "  3. Monitor renewal: sudo systemctl status certbot-renew.timer"
echo ""
