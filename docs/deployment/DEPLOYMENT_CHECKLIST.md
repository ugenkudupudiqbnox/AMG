# AMG Deployment Checklist

## Pre-Deployment Verification

### Testing
- [x] All 164 tests passing
- [x] Authentication tests (32) passing
- [x] API tests (28) passing  
- [x] Governance tests (42) passing
- [x] Memory store tests (20) passing
- [x] Postgres adapter tests (20) passing
- [x] LangGraph adapter tests (27) passing

### Code Quality
- [x] No syntax errors
- [x] All imports valid
- [x] Type hints present
- [x] Docstrings complete
- [x] Error handling comprehensive

### Documentation
- [x] USER_GUIDES.md complete
- [x] API_AUTHENTICATION_DEPLOYMENT.md complete
- [x] PHASE_5_HTTP_API.md complete
- [x] PHASE_5_COMPLETION.md complete
- [x] PHASE_5_AUTH_COMPLETION.md complete
- [x] README.md updated
- [x] ARCHITECTURE.md updated

### Security
- [x] API key validation implemented
- [x] Authentication on all protected endpoints
- [x] Kill switch integrated
- [x] Audit logging complete
- [x] No hardcoded secrets
- [x] HTTPS deployment guide provided

---

## Deployment Steps

### Step 1: Choose Deployment Method

Select one of:
- [ ] **Docker** (recommended for cloud)
- [ ] **Systemd** (recommended for Linux servers)
- [ ] **Manual Python** (development only)

### Step 2: Configure Environment

Create `.env` file or set environment variables:

```bash
export AMG_API_KEYS="sk-prod-key:prod-agent,sk-staging:staging-agent"
export AMG_AUTH_DISABLED=false
```

**Never commit `.env` to version control**

### Step 3: Deploy API Server

#### Option A: Docker

```bash
# Build image
docker build -t amg-api:latest .

# Run container
docker run -d \
  --name amg-api \
  -p 8000:8000 \
  -e AMG_API_KEYS="sk-prod:prod-agent" \
  amg-api:latest

# Verify
curl -H "X-API-Key: sk-prod" http://localhost:8000/health
```

#### Option B: Systemd

```bash
# Copy service file
sudo cp amg-api.service /etc/systemd/system/

# Create environment file
sudo tee /home/ubuntu/AMG/.env > /dev/null <<EOF
AMG_API_KEYS="sk-prod:prod-agent"
AMG_AUTH_DISABLED=false
EOF

# Start service
sudo systemctl daemon-reload
sudo systemctl enable amg-api
sudo systemctl start amg-api

# Verify
curl -H "X-API-Key: sk-prod" http://localhost:8000/health
```

#### Option C: Manual Python

```bash
export AMG_API_KEYS="sk-prod:prod-agent"
nohup python3 run_api.py --host 0.0.0.0 --port 8000 > api.log 2>&1 &
```

### Step 4: Setup Reverse Proxy (Production)

#### Nginx Configuration

```nginx
upstream amg {
    server localhost:8000;
}

server {
    listen 443 ssl http2;
    server_name api.example.com;

    ssl_certificate /etc/ssl/certs/cert.pem;
    ssl_certificate_key /etc/ssl/private/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/s;
    limit_req zone=api_limit burst=200;

    location / {
        proxy_pass http://amg;
        proxy_set_header X-API-Key $http_x_api_key;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Health check endpoint (no auth)
    location /health {
        proxy_pass http://amg;
    }
}
```

### Step 5: Setup Monitoring

#### Health Check Script

```bash
#!/bin/bash
# health_check.sh

while true; do
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "X-API-Key: sk-prod" \
        https://api.example.com/health)
    
    if [ "$response" != "200" ]; then
        # Alert ops
        echo "AMG API unhealthy: $response" | mail -s "Alert" ops@example.com
        # Restart if needed
        systemctl restart amg-api
    fi
    
    sleep 60
done
```

#### Metrics Collection

```bash
#!/bin/bash
# metrics.sh - Send metrics to monitoring system

while true; do
    # Memory usage
    mem=$(docker stats --no-stream amg-api | grep -oP '\d+\.\d+%' | head -1)
    
    # Response time
    response_time=$(curl -s -o /dev/null -w "%{time_total}" \
        -H "X-API-Key: sk-prod" \
        https://api.example.com/health)
    
    # Send to monitoring
    curl -X POST https://monitoring.example.com/metrics \
        -d "memory=$mem&response_time=$response_time"
    
    sleep 30
done
```

### Step 6: Setup Logging

#### Log Rotation (Systemd)

```ini
# /etc/logrotate.d/amg-api

/var/log/amg-api.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    create 0644 ubuntu ubuntu
    sharedscripts
    postrotate
        systemctl reload amg-api > /dev/null 2>&1 || true
    endscript
}
```

#### Log Aggregation

```bash
# Tail logs to central logging system
tail -f /var/log/amg-api.log | \
    curl -X POST -d @- https://logging.example.com/api/v1/events
```

### Step 7: Configure Backup & Disaster Recovery

#### Database Backup (Postgres)

```bash
#!/bin/bash
# backup_postgres.sh

BACKUP_DIR="/backups/amg"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

# Dump database
pg_dump -U amg amg > $BACKUP_DIR/amg_$TIMESTAMP.sql

# Compress
gzip $BACKUP_DIR/amg_$TIMESTAMP.sql

# Upload to S3
aws s3 cp $BACKUP_DIR/amg_$TIMESTAMP.sql.gz \
    s3://backups/amg/

# Cleanup old backups (keep 30 days)
find $BACKUP_DIR -name "*.sql.gz" -mtime +30 -delete
```

#### Backup Schedule

```bash
# In crontab
0 2 * * * /usr/local/bin/backup_postgres.sh  # Daily at 2 AM
```

---

## Post-Deployment Verification

### Health Checks

```bash
# Check API health
curl -H "X-API-Key: sk-prod" https://api.example.com/health

# Check API key validation
curl -H "X-API-Key: invalid" https://api.example.com/health
# Should return 401

# Test memory write
curl -X POST https://api.example.com/memory/write \
  -H "X-API-Key: sk-prod" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "agent-123",
    "content": "Test",
    "memory_type": "long_term",
    "sensitivity": "non_pii"
  }'

# Should return 200 with memory_id
```

### Security Checks

```bash
# Verify HTTPS/TLS
curl -I https://api.example.com/health
# Check: Connection: keep-alive, not Connection: close

# Verify API key required
curl https://api.example.com/memory/write -X POST
# Should return 401

# Verify rate limiting
for i in {1..300}; do
  curl -H "X-API-Key: sk-prod" https://api.example.com/health
done
# Should return 429 (Too Many Requests) after limit
```

### Performance Tests

```bash
# Load test with wrk
wrk -t4 -c100 -d30s \
  -H "X-API-Key: sk-prod" \
  https://api.example.com/health

# Load test with ab
ab -n 10000 -c 100 \
  -H "X-API-Key: sk-prod" \
  https://api.example.com/health
```

---

## Monitoring Alerts

Setup alerts for:

- [ ] API response time > 1 second
- [ ] Memory usage > 80%
- [ ] CPU usage > 75%
- [ ] 401 errors > 10/minute (possible attack)
- [ ] 500 errors > 0 (immediate attention)
- [ ] Disk usage > 90%
- [ ] Database connection errors

---

## Incident Response

### API Down

1. Check service status: `sudo systemctl status amg-api`
2. View logs: `sudo journalctl -u amg-api -n 50`
3. Restart service: `sudo systemctl restart amg-api`
4. Check database connectivity
5. If persistent, rollback to previous version

### High Error Rate

1. Check recent deploys
2. Review error logs for patterns
3. Check database performance
4. Monitor agent disable/freeze commands
5. Consider rate limiting adjustment

### Security Incident

1. Disable compromised API keys immediately:
   ```bash
   export AMG_API_KEYS="sk-new-key:agent-123"
   systemctl restart amg-api
   ```
2. Review audit logs for unauthorized access
3. Check which agents were compromised
4. Disable compromised agents if needed
5. Notify affected clients

### Database Corruption

1. Stop API server: `sudo systemctl stop amg-api`
2. Restore from backup: `psql -U amg amg < backup.sql`
3. Verify database integrity: `psql -U amg amg -c "SELECT COUNT(*) FROM memory;"`
4. Restart API server: `sudo systemctl start amg-api`

---

## Production Checklist

**Before Going Live:**

- [ ] All tests passing (164/164)
- [ ] API keys configured in production environment
- [ ] HTTPS/TLS certificate installed
- [ ] Reverse proxy (Nginx) configured
- [ ] Database backups automated
- [ ] Monitoring alerts configured
- [ ] Log aggregation setup
- [ ] Rate limiting enabled
- [ ] Health check endpoint monitored
- [ ] Incident response procedures documented
- [ ] API key rotation procedures in place
- [ ] Audit log retention policy set
- [ ] Documentation reviewed by ops team
- [ ] Runbook created for common issues
- [ ] On-call escalation procedures defined

---

## Rollback Procedure

If deployment fails:

```bash
# 1. Identify previous working version
git log --oneline | head -10

# 2. Checkout previous version
git checkout <commit-hash>

# 3. Reinstall dependencies
pip install -e .

# 4. Restart service
sudo systemctl restart amg-api

# 5. Verify health
curl -H "X-API-Key: sk-prod" https://api.example.com/health
```

---

## Success Criteria

Deployment is successful when:

- ✅ Health check returns 200
- ✅ API key validation working (401 on invalid key)
- ✅ Memory write succeeds with valid key
- ✅ Memory query returns data
- ✅ Context build completes
- ✅ Kill switch disables agents
- ✅ Audit logs record all actions
- ✅ Response time < 500ms
- ✅ No errors in logs
- ✅ Monitoring shows normal metrics

---

## Post-Deployment Support

### Common Issues

**Q: API not responding**
A: Check service status: `sudo systemctl status amg-api`

**Q: API key not working**
A: Verify format: `AMG_API_KEYS="key:agent-id"`

**Q: High memory usage**
A: Check number of active agents in logs

**Q: Database connection error**
A: Verify Postgres is running and credentials are correct

**Q: Rate limiting too strict**
A: Adjust in Nginx config: `limit_req_zone ... rate=200r/s;`

### Getting Help

- Check documentation: [USER_GUIDES.md](USER_GUIDES.md)
- Review logs: `sudo journalctl -u amg-api -f`
- Read troubleshooting: [API_AUTHENTICATION_DEPLOYMENT.md](API_AUTHENTICATION_DEPLOYMENT.md)
- Open GitHub issue with error details

---

**Last Updated**: February 2, 2026  
**Version**: 1.0.0  
**Status**: Production Ready
