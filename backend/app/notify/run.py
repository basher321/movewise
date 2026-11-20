"""Run the notification worker on its own (specs B12 and B22), plus the CV file clean-up (B28).

  python -m app.notify.run          keeps running (systemd service, VPS)
  python -m app.notify.run --once   one round, then exits (cron job, cPanel)
"""

import argparse
import asyncio
import logging

from app.notify.worker import process_once, run_forever


def _cv_cleanup() -> None:
    """B28: remove CV Agent files past their keep period. Never stops the message round."""
    try:
        from app.cv.cleanup import run_once

        run_once()
    except Exception:
        logging.getLogger("app").exception("CV file clean-up failed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send queued email and WhatsApp messages.")
    parser.add_argument("--once", action="store_true", help="run one round and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.once:
        process_once()
        _cv_cleanup()
        return 0
    asyncio.run(run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
