# One-Page Governance Diagram

```
┌──────────────┐
│ Agent / LLM  │
│ (Untrusted)  │
└──────┬───────┘
       │ context request
┌──────▼──────────┐
│ Governance Plane │
│ ────────────── │
│ Policy Engine   │
│ Retrieval Guard │
│ Audit Logger    │
│ Kill Switch     │
└──────┬──────────┘
       │ approved context
┌──────▼──────────┐
│ Memory Stores   │
│ (TTL enforced) │
└────────────────┘
```

All access is governed, logged, and revocable.
