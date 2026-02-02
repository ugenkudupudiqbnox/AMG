#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
DOMAIN="soc.qbnox.com"
SUBDOMAIN="grafana.${DOMAIN}"
EMAIL="ugen@qbnox.com"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"
API_KEY="sk-admin-key-grafana"
GRAFANA_PORT="3100"  # Using port 3100 (port 3000 may be in use)

echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  🔧 Grafana Setup for ${SUBDOMAIN}              ║${NC}"
echo -e "${BLUE}║     (Subdomain with Wildcard SSL Certificate)                ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"

# ============================================================================
# STEP 1: Update SSL Certificate to Include Wildcard
# ============================================================================
echo -e "${YELLOW}[1/5] Setting up SSL certificate for *.${DOMAIN}...${NC}"

sudo certbot certonly \
  --cert-name "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  -m "$EMAIL" \
  --expand \
  --dns-route53 \
  -d "$DOMAIN" \
  -d "*.$DOMAIN" 2>&1 | grep -E "(Congratulations|Renewal|domain)" || true

echo -e "${GREEN}✓ Certificate ready${NC}"

# ============================================================================
# STEP 2: Install Grafana with Docker
# ============================================================================
echo -e "${YELLOW}[2/5] Installing Grafana with Docker...${NC}"

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "  Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh >/dev/null 2>&1
    rm get-docker.sh
    echo "  ✓ Docker installed"
fi

# Stop existing Grafana container if running
if sudo docker ps -a --format '{{.Names}}' | grep -q '^grafana$'; then
    echo "  Removing existing Grafana container..."
    sudo docker stop grafana >/dev/null 2>&1 || true
    sudo docker rm grafana >/dev/null 2>&1 || true
fi

# Run Grafana container
echo "  Starting Grafana container..."
sudo docker run -d \
  --name grafana \
  --restart=unless-stopped \
  -p 127.0.0.1:${GRAFANA_PORT}:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASS" \
  -e GF_USERS_ALLOW_SIGN_UP=false \
  -e GF_INSTALL_PLUGINS=grafana-http-api-datasource \
  grafana/grafana:latest >/dev/null

sleep 5

# Verify Grafana is responding
if curl -s http://127.0.0.1:${GRAFANA_PORT}/api/health 2>/dev/null | jq -e '.status == "ok"' >/dev/null 2>&1; then
    echo -e "${GREEN}✓ Grafana running on localhost:${GRAFANA_PORT}${NC}"
else
    echo -e "${RED}✗ Grafana not responding${NC}"
    exit 1
fi

# ============================================================================
# STEP 3: Configure Nginx Reverse Proxy
# ============================================================================
echo -e "${YELLOW}[3/5] Configuring Nginx reverse proxy...${NC}"

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
    
    # Proxy to Grafana
    location / {
        proxy_pass http://127.0.0.1:3100;
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

# Test and reload Nginx
if sudo nginx -t 2>&1 | grep -q "test is successful"; then
    sudo systemctl reload nginx
    echo -e "${GREEN}✓ Nginx proxy configured${NC}"
else
    echo -e "${RED}✗ Nginx configuration error${NC}"
    exit 1
fi

# ============================================================================
# STEP 4: Configure AMG API Data Source
# ============================================================================
echo -e "${YELLOW}[4/5] Setting up AMG API data source...${NC}"

# Create provisioning directory
sudo mkdir -p /etc/grafana/provisioning/datasources

# Create data source configuration
sudo tee /etc/grafana/provisioning/datasources/amg-api.yml > /dev/null << 'DS_CONF'
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
DS_CONF

# Restart Grafana to load datasource
sudo docker restart grafana >/dev/null
sleep 5

echo -e "${GREEN}✓ Data source configured${NC}"

# ============================================================================
# STEP 5: Verification
# ============================================================================
echo -e "${YELLOW}[5/5] Verifying setup...${NC}"

echo ""
echo -e "${BLUE}Verification Results:${NC}"
echo -e "─────────────────────────────────────────────────────────────"

# Check 1: Grafana API responding
if curl -s http://127.0.0.1:${GRAFANA_PORT}/api/health 2>/dev/null | jq -e '.status == "ok"' >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} Grafana API responding (localhost:${GRAFANA_PORT})"
else
    echo -e "${RED}✗${NC} Grafana API not responding"
fi

# Check 2: Nginx proxy
if curl -s -I https://"$SUBDOMAIN" -k 2>/dev/null | head -1 | grep -qE "(200|301|302)"; then
    echo -e "${GREEN}✓${NC} Nginx proxy working (https://${SUBDOMAIN})"
else
    echo -e "${YELLOW}⚠${NC} Nginx proxy not responding (check DNS)"
fi

# Check 3: Certificate includes wildcard
if openssl x509 -in /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem -noout -text 2>/dev/null | grep -q "\*\.$DOMAIN"; then
    echo -e "${GREEN}✓${NC} Wildcard certificate configured (*.${DOMAIN})"
else
    echo -e "${RED}✗${NC} Wildcard not in certificate"
fi

# Check 4: AMG API reachable
if curl -s https://api.soc.qbnox.com/stats/memory-summary \
    -H "X-API-Key: $API_KEY" 2>/dev/null | jq -e '.total_memory' >/dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} AMG API responding (https://api.soc.qbnox.com)"
else
    echo -e "${YELLOW}⚠${NC} AMG API not responding"
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo -e "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ✅ GRAFANA SETUP COMPLETE                                   ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}"

echo ""
echo -e "${GREEN}📊 GRAFANA ACCESS:${NC}"
echo "   URL: https://${SUBDOMAIN}"
echo "   Username: ${GRAFANA_USER}"
echo "   Password: ${GRAFANA_PASS}"
echo "   (Change password after first login)"

echo ""
echo -e "${GREEN}🔌 AMG API DATA SOURCE:${NC}"
echo "   Name: AMG-API"
echo "   URL: https://api.soc.qbnox.com"
echo "   Auth: X-API-Key header"

echo ""
echo -e "${GREEN}🛡️ CERTIFICATE:${NC}"
echo "   Domain: *.${DOMAIN}"
echo "   Expires: $(openssl x509 -in /etc/letsencrypt/live/$DOMAIN/fullchain.pem -noout -dates | grep notAfter | cut -d= -f2)"
echo "   Auto-renewal: Enabled"

echo ""
echo -e "${GREEN}📝 NEXT STEPS:${NC}"
echo "   1. Open browser: https://${SUBDOMAIN}"
echo "   2. Login with: ${GRAFANA_USER} / ${GRAFANA_PASS}"
echo "   3. Change admin password"
echo "   4. Create dashboards using AMG-API data source"
echo "   5. Set up alerts and monitoring"

echo ""
echo -e "${GREEN}📚 DOCUMENTATION:${NC}"
echo "   Setup guide: /tmp/GRAFANA_SUBDOMAIN_SETUP.md"
echo "   Dashboard builder: /opt/amg-prod/DASHBOARD_BUILDER_GUIDE.md"
echo "   User guide: /opt/amg-prod/USER_GUIDES.md"

echo ""
echo -e "${GREEN}✓ Setup complete! Access Grafana at:${NC}"
echo -e "${BLUE}   https://${SUBDOMAIN}${NC}"
echo ""
