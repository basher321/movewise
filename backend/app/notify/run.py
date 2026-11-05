"""Run the notification worker on its own (specs B12 and B22).

  python -m app.notify.run          keeps running (systemd service, VPS)
  python -m app.notify.run --once   one round, then exits (cron job, cPanel)
"""

import argparse
import asyncio
import logging

from app.notify.worker import process_once, run_forever


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send queued email and WhatsApp messages.")
    parser.add_argument("--once", action="store_true", help="run one round and exit")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO)
    if args.once:
        process_once()
        return 0
    asyncio.run(run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
