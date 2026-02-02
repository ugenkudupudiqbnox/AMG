"""HTTP API layer for Agent Memory Governance.

Exposes AMG as a REST service for language-agnostic integration.
"""

from .server import create_app

__all__ = ["create_app"]
