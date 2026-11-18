#!/usr/bin/env python3
"""Small, sequential HTTP GET load generator using only Python's standard library.

WSL example (from manifest/):
    python3 scripts/light-load.py http://YOUR_ALB/api/health
    python3 scripts/light-load.py http://YOUR_ALB/api/health --rps 3 --duration 120

At most one request runs at a time. No retries or automatic redirects.
"""

import argparse
import http.client
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url", help="Full HTTP(S) endpoint, for example http://YOUR_ALB/api/health")
    parser.add_argument("--rps", type=float, default=2, help="Maximum requests per second: 0.1 to 5 (default: 2)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds: 1 to 300 (default: 60)")
    args = parser.parse_args()
    try:
        target = urllib.parse.urlsplit(args.url)
        valid_url = target.scheme in ("http", "https") and bool(target.hostname) and not target.fragment
        target.port  # Validate an explicitly supplied port.
    except ValueError:
        valid_url = False
    if not valid_url:
        parser.error("url must be a valid HTTP(S) URL without a fragment")
    if not math.isfinite(args.rps) or not 0.1 <= args.rps <= 5:
        parser.error("--rps must be between 0.1 and 5")
    if not 1 <= args.duration <= 300:
        parser.error("--duration must be between 1 and 300 seconds")

    opener = urllib.request.build_opener(NoRedirect())
    request = urllib.request.Request(args.url, headers={"User-Agent": "tikto-light-load/1.0"}, method="GET")
    interval = 1 / args.rps
    codes = Counter()
    count = success = 0
    total_ms = max_ms = 0.0
    started = time.monotonic()
    deadline = started + args.duration
    next_report = started + 5

    def report(final=False):
        elapsed = time.monotonic() - started
        average = total_ms / count if count else 0
        rate = count / elapsed if elapsed else 0
        print(
            f"{'DONE' if final else 'RUN '} {elapsed:.1f}s | requests={count} "
            f"ok={success} failed={count - success} | actual_rps={rate:.2f} "
            f"avg={average:.0f}ms max={max_ms:.0f}ms | {dict(codes)}",
            flush=True,
        )

    print(
        f"GET {args.url}\nMaximum {args.rps:g} requests/s for {args.duration}s; "
        "one request at a time. Ctrl+C to stop.\n"
        "Latency measures time to response headers; response bodies are not downloaded.",
        flush=True,
    )
    try:
        while time.monotonic() < deadline:
            request_started = time.monotonic()
            remaining = deadline - request_started
            if remaining <= 0:
                break
            try:
                # Close after receiving headers so large responses are not buffered.
                with opener.open(request, timeout=min(3.0, remaining)) as response:
                    status = response.status
            except urllib.error.HTTPError as error:
                status = error.code
                error.close()
            except (urllib.error.URLError, http.client.HTTPException, OSError, ValueError) as error:
                status = "NETWORK_ERROR"
                if codes[status] == 0:
                    print(f"First network error: {error}", flush=True)

            latency_ms = (time.monotonic() - request_started) * 1000
            count += 1
            success += isinstance(status, int) and 200 <= status < 300
            codes[status] += 1
            total_ms += latency_ms
            max_ms = max(max_ms, latency_ms)
            now = time.monotonic()
            if now >= next_report:
                report()
                next_report = now + 5
            # Never catch up with bursts after a slow response.
            wait = min(request_started + interval, deadline) - time.monotonic()
            if wait > 0:
                time.sleep(wait)
    except KeyboardInterrupt:
        print("\nStopped by user.", flush=True)
    report(final=True)
    return 0 if count and success == count else 1


if __name__ == "__main__":
    raise SystemExit(main())
