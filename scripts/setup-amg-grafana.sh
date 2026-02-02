#!/bin/bash
set -e

# Unified AMG + Grafana Setup Script
# - Installs/starts AMG API (systemd or manual)
# - Installs Grafana (Docker)
# - Configures Nginx reverse proxy and SSL
# - Injects AMG API key into Grafana data source
#
# Usage: sudo ./scripts/setup-amg-grafana.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

DOMAIN="soc.qbnox.com"
SUBDOMAIN="grafana.${DOMAIN}"
EMAIL="ugen@qbnox.com"
GRAFANA_USER="admin"
GRAFANA_PASS="admin"
GRAFANA_PORT="3100"
AMG_API_URL="https://api.soc.qbnox.com"

# Step 1: Ensure AMG API is running
# (Assume systemd service is set up)
echo -e "${YELLOW}[1/5] Ensuring AMG API is running...${NC}"
sudo systemctl restart amg-api.service || true
sleep 5
# Internal check on localhost
if curl -s "http://127.0.0.1:8000/openapi.json" | grep -q 'Agent Memory Governance'; then
  echo -e "${GREEN}✓ AMG API is running locally${NC}"
else
  echo -e "${RED}✗ AMG API not responding at http://127.0.0.1:8000${NC}"
  # Fallback to public check
  if curl -sk "$AMG_API_URL/openapi.json" | grep -q 'Agent Memory Governance'; then
    echo -e "${GREEN}✓ AMG API is running (public)${NC}"
  else
    echo -e "${RED}✗ AMG API not responding at $AMG_API_URL${NC}"
    exit 1
  fi
fi

# Step 2: Obtain AMG API key
echo -e "${YELLOW}[2/5] Obtaining AMG API key...${NC}"
API_KEY=""
# Try to auto-detect from environment or config
if [ -f /etc/amg/api.key ]; then
  API_KEY=$(cat /etc/amg/api.key)
elif [ -f /etc/default/amg-api ]; then
  # Extract first key from AMG_API_KEYS=key1:agent1,key2:agent2
  API_KEY=$(grep "AMG_API_KEYS=" /etc/default/amg-api | cut -d'=' -f2 | cut -d':' -f1 | cut -d',' -f1)
fi
if [ -z "$API_KEY" ]; then
  read -p "Enter AMG API key for Grafana: " API_KEY
fi
if [ -z "$API_KEY" ]; then
  echo -e "${RED}✗ No API key provided${NC}"
  exit 1
fi

# Step 3: Install Grafana (Docker)
echo -e "${YELLOW}[3/5] Installing Grafana...${NC}"
if ! command -v docker &> /dev/null; then
  echo "  Installing Docker..."
  curl -fsSL https://get.docker.com -o get-docker.sh
  sudo sh get-docker.sh >/dev/null 2>&1
  rm get-docker.sh
  echo "  ✓ Docker installed"
fi
if sudo docker ps -a --format '{{.Names}}' | grep -q '^grafana$'; then
  echo "  Removing existing Grafana container..."
  sudo docker stop grafana >/dev/null 2>&1 || true
  sudo docker rm grafana >/dev/null 2>&1 || true
fi
sudo docker run -d \
  --name grafana \
  --restart=unless-stopped \
  -p 127.0.0.1:${GRAFANA_PORT}:3000 \
  -e GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASS" \
  -e GF_USERS_ALLOW_SIGN_UP=false \
  -e GF_INSTALL_PLUGINS="marcusolsson-json-datasource" \
  -v /etc/grafana/provisioning:/etc/grafana/provisioning \
  grafana/grafana:latest >/dev/null

echo "  Waiting for Grafana to start (max 60s)..."
for i in {1..30}; do
  if curl -s http://127.0.0.1:${GRAFANA_PORT}/api/health | grep -q 'ok'; then
    echo -e "${GREEN}✓ Grafana running on localhost:${GRAFANA_PORT}${NC}"
    break
  fi
  if [ $i -eq 30 ]; then
    echo -e "${RED}✗ Grafana not responding after 60s${NC}"
    exit 1
  fi
  sleep 2
done

# Step 4: Configure Nginx reverse proxy for Grafana
echo -e "${YELLOW}[4/5] Configuring Nginx reverse proxy...${NC}"
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
    ssl_certificate /etc/letsencrypt/live/soc.qbnox.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/soc.qbnox.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;
    ssl_stapling on;
    ssl_stapling_verify on;
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    access_log /var/log/nginx/grafana-access.log;
    error_log /var/log/nginx/grafana-error.log;
    location / {
        proxy_pass http://127.0.0.1:3100;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Connection "";
        proxy_connect_timeout 30s;
        proxy_send_timeout 30s;
        proxy_read_timeout 30s;
    }
}
NGINX_CONF
sudo ln -sf /etc/nginx/sites-available/grafana-amg /etc/nginx/sites-enabled/grafana-amg
if sudo nginx -t 2>&1 | grep -q "test is successful"; then
    sudo systemctl reload nginx
    echo -e "${GREEN}✓ Nginx proxy configured${NC}"
else
    echo -e "${RED}✗ Nginx configuration error${NC}"
    exit 1
fi

# Step 5: Provision AMG API data source and dashboards in Grafana
echo -e "${YELLOW}[5/5] Provisioning AMG API data source and dashboards...${NC}"
sudo mkdir -p /etc/grafana/provisioning/datasources
sudo mkdir -p /etc/grafana/provisioning/dashboards
sudo mkdir -p /var/lib/grafana/dashboards

# Data source provisioning
sudo tee /etc/grafana/provisioning/datasources/amg-api.yml > /dev/null << DS_CONF
apiVersion: 1
datasources:
  - name: AMG-API
    type: marcusolsson-json-datasource
    url: ${AMG_API_URL}
    access: proxy
    isDefault: true
    jsonData:
      httpMethod: GET
      customHeaders:
        X-API-Key: "${API_KEY}"
DS_CONF

# Dashboard provisioning
sudo tee /etc/grafana/provisioning/dashboards/amg.yml > /dev/null << DB_CONF
apiVersion: 1
providers:
  - name: 'AMG'
    orgId: 1
    folder: ''
    type: file
    disableDeletion: false
    editable: true
    options:
      path: /etc/grafana/provisioning/dashboards
DB_CONF

# Copy dashboard JSON
sudo cp /opt/amg-prod/config/grafana/dashboards/amg-overview.json /etc/grafana/provisioning/dashboards/amg-overview.json

sudo docker restart grafana >/dev/null
sleep 5
echo -e "${GREEN}✓ AMG API data source and dashboards configured in Grafana${NC}"

# Summary
echo -e "\n${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  ✅ AMG + GRAFANA SETUP COMPLETE                             ║${NC}"
echo -e "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}\n"
echo -e "${GREEN}Grafana:   https://${SUBDOMAIN}  (admin/${GRAFANA_PASS})${NC}"
echo -e "${GREEN}AMG API:   ${AMG_API_URL} (X-API-Key header)${NC}"
echo -e "${GREEN}DataSource: AMG-API (provisioned)${NC}\n"
echo -e "${GREEN}Next: Login to Grafana and build dashboards!${NC}\n"
