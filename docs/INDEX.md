# AMG Documentation Index

> Complete documentation for Agent Memory Governance (AMG)

---

## 📋 Quick Navigation

### Getting Started
- **[Unified Setup Script](../scripts/setup-amg-grafana.sh)** - One-command AMG + Grafana deployment
- **[README.md](../README.md)** - Project overview and core concepts
- **[Contributing](../CONTRIBUTING.md)** - How to contribute to AMG
- **[Security Policy](../SECURITY.md)** - Security reporting and scope
- **[Code of Conduct](../CODE_OF_CONDUCT.md)** - Community guidelines

### Architecture & Design
- **[Architecture Overview](./architecture/ARCHITECTURE.md)** - High-level system design
- **[Implementation Details](./architecture/IMPLEMENTATION.md)** - Core implementation patterns
- **[Policy Schema](./governance/POLICY_SCHEMA.md)** - Governance contract definitions
- **[Governance Model](./governance/GOVERNANCE_MODEL.md)** - Decision principles and policies
- **[Threat Model](./governance/THREAT_MODEL.md)** - Security analysis and risks

### Deployment & Infrastructure
- **[Deployment Checklist](./deployment/DEPLOYMENT_CHECKLIST.md)** - Pre-production checklist
- **[HTTPS Setup](./deployment/HTTPS_SETUP.md)** - SSL/TLS configuration guide
- **[HTTPS Deployment](./deployment/HTTPS_DEPLOYMENT_COMPLETE.md)** - Complete HTTPS setup
- **[API Authentication](./deployment/API_AUTHENTICATION_DEPLOYMENT.md)** - Auth setup guide

### Dashboards & Monitoring
- **[Grafana Dashboards](./dashboards/GRAFANA_DASHBOARDS.md)** - Dashboard guide and KPIs
- **[Grafana Installation](./dashboards/GRAFANA_INSTALLATION_COMPLETE.md)** - Installation summary
- **[Grafana Visualization](./dashboards/GRAFANA_VISUALIZATION_GUIDE.md)** - Visual reference guide
- **[Grafana Subdomain Setup](./dashboards/GRAFANA_SUBDOMAIN_SETUP.md)** - Manual setup guide
- **[Dashboard Builder Guide](./dashboards/DASHBOARD_BUILDER_GUIDE.md)** - Custom dashboard creation
- **[Grafana Setup Notes](./dashboards/GRAFANA_SETUP.md)** - Additional setup notes

### Development Phases
Development phases are archived for historical reference:

#### Phase 3: PostgreSQL
- **[Phase 3 PostgreSQL](./phases/PHASE_3_POSTGRES.md)** - Database implementation

#### Phase 4: LangGraph Integration
- **[Phase 4 Completion](./phases/PHASE_4_COMPLETION.md)** - Integration overview
- **[Phase 4 LangGraph](./phases/PHASE_4_LANGGRAPH.md)** - LangGraph adapter details

#### Phase 5: HTTP API & Authentication
- **[Phase 5 Completion](./phases/PHASE_5_COMPLETION.md)** - Phase summary
- **[Phase 5 HTTP API](./phases/PHASE_5_HTTP_API.md)** - API implementation
- **[Phase 5 Auth Completion](./phases/PHASE_5_AUTH_COMPLETION.md)** - Authentication completion
- **[Project Completion](./phases/PROJECT_COMPLETION.md)** - Final project summary

### User Guides
- **[User Guides](./guides/USER_GUIDES.md)** - Complete operator documentation
  - Getting started with AMG
  - API usage examples
  - Common tasks and workflows
  - Dashboard setup
  - Troubleshooting
- **[Documentation Index](./guides/DOCUMENTATION_INDEX.md)** - Previous documentation index

---

## 📂 Directory Structure

```
docs/
├── INDEX.md                          (this file)
├── architecture/
│   ├── ARCHITECTURE.md              - System design and components
│   └── IMPLEMENTATION.md             - Core implementation patterns
├── governance/
│   ├── POLICY_SCHEMA.md             - Governance contract definitions
│   ├── GOVERNANCE_MODEL.md          - Decision principles
│   └── THREAT_MODEL.md              - Security analysis
├── deployment/
│   ├── DEPLOYMENT_CHECKLIST.md      - Pre-production checks
│   ├── HTTPS_SETUP.md               - SSL/TLS guide
│   ├── HTTPS_DEPLOYMENT_COMPLETE.md - Complete HTTPS setup
│   └── API_AUTHENTICATION_DEPLOYMENT.md - Auth configuration
├── dashboards/
│   ├── GRAFANA_DASHBOARDS.md        - Dashboard guide
│   ├── GRAFANA_INSTALLATION_COMPLETE.md - Installation summary
│   ├── GRAFANA_VISUALIZATION_GUIDE.md - Visual reference
│   ├── GRAFANA_SUBDOMAIN_SETUP.md   - Manual setup
│   ├── DASHBOARD_BUILDER_GUIDE.md   - Custom dashboards
│   └── GRAFANA_SETUP.md             - Setup notes
├── guides/
│   ├── USER_GUIDES.md               - Operator documentation
│   └── DOCUMENTATION_INDEX.md        - Legacy index
└── phases/
    ├── PHASE_3_POSTGRES.md
    ├── PHASE_4_COMPLETION.md
    ├── PHASE_4_LANGGRAPH.md
    ├── PHASE_5_COMPLETION.md
    ├── PHASE_5_HTTP_API.md
    ├── PHASE_5_AUTH_COMPLETION.md
    └── PROJECT_COMPLETION.md
```

---

## 🚀 Quick Start Paths

### For Operators
1. Read [README.md](../README.md)
2. Review [User Guides](./guides/USER_GUIDES.md)
3. Set up dashboards: [Grafana Dashboards](./dashboards/GRAFANA_DASHBOARDS.md)
4. See [Deployment Checklist](./deployment/DEPLOYMENT_CHECKLIST.md)

### For Developers
1. Study [Architecture](./architecture/ARCHITECTURE.md)
2. Review [Implementation](./architecture/IMPLEMENTATION.md)
3. Understand [Governance Model](./governance/GOVERNANCE_MODEL.md)
4. Check [Threat Model](./governance/THREAT_MODEL.md)
5. Contribute: [Contributing Guide](../CONTRIBUTING.md)

### For Security/Compliance Teams
1. Review [Threat Model](./governance/THREAT_MODEL.md)
2. Study [Policy Schema](./governance/POLICY_SCHEMA.md)
3. Check [Governance Model](./governance/GOVERNANCE_MODEL.md)
4. Read [Security Policy](../SECURITY.md)

### For Deployment/DevOps
1. Check [Deployment Checklist](./deployment/DEPLOYMENT_CHECKLIST.md)
2. Follow [HTTPS Setup](./deployment/HTTPS_SETUP.md)
3. Set up API: [API Authentication](./deployment/API_AUTHENTICATION_DEPLOYMENT.md)
4. Configure monitoring: [Grafana Dashboards](./dashboards/GRAFANA_DASHBOARDS.md)

### For Monitoring/SRE
1. Review [Grafana Installation](./dashboards/GRAFANA_INSTALLATION_COMPLETE.md)
2. Create dashboards: [Visualization Guide](./dashboards/GRAFANA_VISUALIZATION_GUIDE.md)
3. Configure alerts: [Dashboard Guide](./dashboards/GRAFANA_DASHBOARDS.md)
4. Understand KPIs: [Dashboard Guide](./dashboards/GRAFANA_DASHBOARDS.md#kpi-definitions)

---

## 📖 Documentation Guidelines

### For Readers
- Each markdown file is self-contained (can be read independently)
- Files include table of contents with section links
- Code examples are included where applicable
- Troubleshooting sections provided for common issues

### For Contributors
- New documentation should go in appropriate subdirectory
- Update this INDEX.md when adding new docs
- Keep README.md for critical getting-started content only
- Use descriptive titles and clear structure

---

## 🔗 External References

- [Grafana Documentation](https://grafana.com/docs/grafana/latest/)
- [Docker Documentation](https://docs.docker.com/)
- [Nginx Documentation](https://nginx.org/en/docs/)
- [Let's Encrypt Documentation](https://letsencrypt.org/docs/)

---

## 📝 Document Categories

### Essential (Root Level)
- ✅ **README.md** - Project overview
- ✅ **CONTRIBUTING.md** - Contribution guidelines
- ✅ **SECURITY.md** - Security policy
- ✅ **CODE_OF_CONDUCT.md** - Community standards

### Architecture & Design (docs/architecture/, docs/governance/)
- Architecture decisions and system design
- Implementation patterns and practices
- Policy definitions and governance rules
- Security threat analysis

### Deployment (docs/deployment/)
- Infrastructure setup procedures
- Configuration guides
- Authentication and security setup
- Pre-deployment checklists

### Operations (docs/dashboards/, docs/guides/)
- Grafana dashboard creation and maintenance
- Operator procedures and workflows
- User guides and tutorials
- Troubleshooting and FAQ

### Historical (docs/phases/)
- Development phase documentation
- Archive of past work and decisions
- Reference for project evolution

---

## 📞 Support

For questions or issues:
1. Check the relevant documentation in this index
2. Review troubleshooting sections in user guides
3. See [Contributing Guide](../CONTRIBUTING.md) for how to report issues
4. Review [Security Policy](../SECURITY.md) for security concerns

---

**Last Updated**: 2026-02-02  
**Structure**: Organized by purpose (architecture, deployment, operations, etc.)  
**Maintenance**: Update INDEX.md when adding or modifying documentation
