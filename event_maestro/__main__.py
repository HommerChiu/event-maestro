"""Command line entry point.

    python -m event_maestro serve                     # run the site on :8000
    python -m event_maestro generate --users 500      # backfill 30 days of events
    python -m event_maestro stream --rate 20          # live synthetic traffic
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from . import ga4
from .server import serve
from .simulator import generate_history, stream
from .sink import JsonlSink


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="event_maestro", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", "-o", help="output root (default: $EVENT_MAESTRO_OUTPUT_DIR or ./data)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the Pixel Notes website + /collect endpoint")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)

    yesterday = (datetime.now(ga4.property_timezone()).date() - timedelta(days=1)).isoformat()
    p_gen = sub.add_parser("generate", help="backfill synthetic history")
    p_gen.add_argument("--users", type=int, default=500, help="new readers over the window (default 500)")
    p_gen.add_argument("--days", type=int, default=30, help="window length in days (default 30)")
    p_gen.add_argument("--end-date", default=yesterday, help=f"last day, YYYY-MM-DD (default {yesterday})")
    p_gen.add_argument("--seed", type=int, default=42)
    p_gen.add_argument("--duplicate-rate", type=float, default=0.0,
                       help="share of rows written twice, to practise dedup (e.g. 0.01)")

    p_stream = sub.add_parser("stream", help="write live synthetic traffic until stopped")
    p_stream.add_argument("--rate", type=float, default=10, help="new sessions per minute (default 10)")
    p_stream.add_argument("--duration", type=float, help="stop after N seconds (default: run forever)")
    p_stream.add_argument("--seed", type=int)

    args = parser.parse_args(argv)

    if args.command == "serve":
        serve(args.host, args.port, args.output)
        return 0

    if args.command == "generate":
        end = date.fromisoformat(args.end_date)
        stem = f"generator-{args.seed}-{end:%Y%m%d}-{args.days}d"
        with JsonlSink(args.output, file_stem=stem) as sink:
            for path in {sink.path_for(f"{end - timedelta(days=i):%Y%m%d}") for i in range(-1, args.days)}:
                path.unlink(missing_ok=True)  # re-running with the same args replaces, not appends
            sink.write_many(generate_history(
                users=args.users, days=args.days, end_date=end,
                seed=args.seed, duplicate_rate=args.duplicate_rate,
            ))
            print(f"wrote {sink.rows_written:,} events to {sink.output_dir.resolve()}/raw/ga4_events/")
        return 0

    if args.command == "stream":
        stem = f"stream-{datetime.now():%Y%m%d%H%M%S}"
        with JsonlSink(args.output, file_stem=stem) as sink:
            print(f"streaming ~{args.rate} sessions/min into {sink.output_dir.resolve()}/raw/ga4_events/ (Ctrl+C to stop)")
            try:
                stream(sink, sessions_per_minute=args.rate, duration_s=args.duration, seed=args.seed,
                       on_row=lambda r: print(f"{r['event_date']} {r['event_name']:<20} {r['user_pseudo_id']}"))
            except KeyboardInterrupt:
                pass
            print(f"wrote {sink.rows_written:,} events")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
