"""
CLI entry point for the Avatar Engine web server.

Usage:
    python -m avatar_engine.web --provider gemini --port 8420
    avatar-web --provider claude --model claude-sonnet-4-5 --port 8420
"""

import argparse
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Avatar Engine Web Server",
        prog="avatar-web",
    )
    parser.add_argument(
        "-p", "--provider",
        default="gemini",
        choices=["gemini", "claude", "codex"],
        help="AI provider (default: gemini)",
    )
    parser.add_argument(
        "-m", "--model",
        default=None,
        help="Model name override",
    )
    parser.add_argument(
        "-c", "--config",
        default=None,
        help="Path to YAML config file",
    )
    parser.add_argument(
        "-w", "--working-dir",
        default=None,
        help="Working directory for AI session",
    )
    parser.add_argument(
        "--system-prompt",
        default="",
        help="System prompt for the AI",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8420,
        help="Server port (default: 8420)",
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Server host (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--cors-origins",
        nargs="*",
        default=None,
        help="Allowed CORS origins",
    )
    parser.add_argument(
        "--no-static",
        action="store_true",
        help="Don't serve static web-demo files",
    )
    parser.add_argument(
        "--static-dir",
        default=None,
        help="Directory with built frontend assets (overrides default)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)",
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    try:
        import uvicorn
    except ImportError:
        print(
            "uvicorn is required. Install with: uv sync --extra web",
            file=sys.stderr,
        )
        sys.exit(1)

    from .server import create_app

    app = create_app(
        provider=args.provider,
        model=args.model,
        config_path=args.config,
        working_dir=args.working_dir,
        system_prompt=args.system_prompt,
        cors_origins=args.cors_origins,
        serve_static=not args.no_static,
        static_dir=args.static_dir,
    )

    print(f"\n  Avatar Engine Web Server")
    print(f"  Provider: {args.provider}")
    if args.model:
        print(f"  Model: {args.model}")
    print(f"  URL: http://{args.host}:{args.port}")
    print(f"  WebSocket: ws://{args.host}:{args.port}/api/avatar/ws")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
