"""WebUI server entry point."""

from __future__ import annotations

import argparse

import uvicorn

from bluesnail.web.app import build_default_agent, create_app
from bluesnail.web.llm_config import load_config


def create_web_app():
    """Factory used by uvicorn (supports --reload)."""
    config = load_config()
    return create_app(build_default_agent(config), config)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run BlueSnail WebUI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument(
        "--reload",
        dest="reload",
        action="store_true",
        default=True,
        help="Auto-reload on code changes (default: enabled)",
    )
    parser.add_argument(
        "--no-reload",
        dest="reload",
        action="store_false",
        help="Disable auto-reload",
    )
    args = parser.parse_args()

    print(
        "BlueSnail WebUI starting...\n"
        f"  URL: http://{args.host}:{args.port}\n"
        "  LLM API: GET/PUT /api/llm/config, POST /api/llm/test\n"
        f"  Reload: {'on' if args.reload else 'off'}"
    )

    if args.reload:
        uvicorn.run(
            "bluesnail.web.server:create_web_app",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
        )
    else:
        uvicorn.run(create_web_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
