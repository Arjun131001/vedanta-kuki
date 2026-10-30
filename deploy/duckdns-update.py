"""Update an already registered DuckDNS name; keep the token out of logs."""
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


def main():
    domain = os.environ.get("DUCKDNS_SUBDOMAIN", "vedant-a")
    token = os.environ.get("DUCKDNS_TOKEN", "")
    if not re.fullmatch(r"[a-z0-9-]+", domain) or not token:
        print("Configure DUCKDNS_SUBDOMAIN and DUCKDNS_TOKEN.", file=sys.stderr)
        return 1
    query = urllib.parse.urlencode({"domains": domain, "token": token, "ip": ""})
    try:
        with urllib.request.urlopen("https://www.duckdns.org/update?" + query, timeout=20) as response:
            result = response.read(100).decode().strip()
    except (urllib.error.URLError, TimeoutError):
        print("DuckDNS request failed; check connectivity.", file=sys.stderr)
        return 1
    if result != "OK":
        print("DuckDNS rejected the update; check registration and token.", file=sys.stderr)
        return 1
    print("DuckDNS address updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
