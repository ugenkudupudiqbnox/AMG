# Architecture

## Overview
Agent Memory Governance (AMG) is a governance-first control plane for AI agent memory and context.
It enforces policy, auditability, and deterministic behavior outside of the LLM and agent code.

## Core Planes
1. Governance Control Plane
2. Memory Management Plane
3. Agent Execution Plane (untrusted)

## Key Properties
- No direct memory access by agents
- All context is curated via AMG
- Append-only audit logs
- Immediate kill switch capability

## Deployment Model
AMG is designed to run as a standalone service, sidecar, or internal platform component.
