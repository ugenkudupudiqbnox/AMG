# Policy Schema

## Purpose
Defines how memory is governed in AMG.

## Core Fields
- memory_type: short_term | long_term | episodic
- ttl_seconds: integer
- sensitivity: pii | non_pii
- scope: agent | tenant
- allow_read: boolean
- allow_write: boolean

## Example
```yaml
memory_type: episodic
ttl_seconds: 604800
sensitivity: pii
scope: tenant
allow_read: true
allow_write: false
```
