#!/usr/bin/env python3
"""HTTP API server runner for Agent Memory Governance.

Usage:
    python3 run_api.py [--host 0.0.0.0] [--port 8000]

Example:
    python3 run_api.py
    python3 run_api.py --host 0.0.0.0 --port 8080

The API will be available at http://localhost:8000/docs for interactive testing.
"""

import argparse
import sys
import uvicorn

try:
    from amg.api.server import create_app
except ImportError as e:
    print(f"Error: Could not import AMG API module. {e}")
    print("Make sure to install AMG with: pip install -e .")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Agent Memory Governance HTTP API Server"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Server host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Server port (default: 8000)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes",
    )

    args = parser.parse_args()

    app = create_app()

    print(f"\n{'='*60}")
    print(f"Agent Memory Governance API Server")
    print(f"{'='*60}")
    print(f"Starting server on http://{args.host}:{args.port}")
    print(f"Interactive docs: http://{args.host}:{args.port}/docs")
    print(f"OpenAPI schema: http://{args.host}:{args.port}/openapi.json")
    print(f"{'='*60}\n")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
