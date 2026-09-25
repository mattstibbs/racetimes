"""Check a live Race Times site from outside, as a visitor's browser would (slice 12).

    python scripts/check_live.py                      # racetimes.co.uk, club "demo"
    python scripts/check_live.py example.org --club exesc

It proves, rather than assumes, what production needs: HTTPS with a valid
certificate on the service's address, on a club's, and on a subdomain made up
on the spot (so the wildcard certificate really covers every club); plain
HTTP and www redirected; the security headers; and /health/ answering "ok".
Each check prints PASS or FAIL, and it exits with 1 if any failed.

Standard library only, so it runs anywhere Python does, with nothing
installed. It changes nothing on the site. Email, Sentry and the uptime
monitor are checked by hand: see docs/production.md.
"""

import argparse
import secrets
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request

CERTIFICATE_DAYS_LEFT = 14  # Render renews well before this


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # a redirect is an answer to check, not to follow


_opener = urllib.request.build_opener(_NoRedirects)


def fetch(url):
    """(status, headers, body) for one GET, redirects not followed. Certificates are verified."""
    request = urllib.request.Request(url, headers={"User-Agent": "race-times-check-live"})
    try:
        with _opener.open(request, timeout=20) as response:
            return response.status, response.headers, response.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as error:  # 3xx, 4xx and 5xx arrive here
        return error.code, error.headers, ""


# --- What each answer must look like. Plain functions of the answer, so they're tested. ---------


def healthy(status, headers, body):
    return status == 200 and body.strip() == "ok"


def redirects_to(target):
    def check(status, headers, body):
        return status in (301, 308) and headers.get("Location") == target
    return check


def secure_headers(status, headers, body):
    hsts = headers.get("Strict-Transport-Security", "")
    return (
        status == 200
        and "max-age=" in hsts and "includeSubDomains" in hsts
        and headers.get("X-Frame-Options") == "DENY"
        and headers.get("Referrer-Policy") == "same-origin"
    )


def days_left(host):
    """Days until the certificate for ``host`` expires (verified as a browser would)."""
    context = ssl.create_default_context()
    with socket.create_connection((host, 443), timeout=20) as sock:
        with context.wrap_socket(sock, server_hostname=host) as tls:
            expires = ssl.cert_time_to_seconds(tls.getpeercert()["notAfter"])
    return int((expires - time.time()) // 86400)


def checks(domain, club):
    made_up = f"check-{secrets.token_hex(4)}"
    return [
        ("The service's address answers /health/ over HTTPS", f"https://{domain}/health/", healthy),
        (f"A club's address ({club}) answers over HTTPS", f"https://{club}.{domain}/health/", healthy),
        (f"A made-up subdomain ({made_up}) has a valid certificate too",
         f"https://{made_up}.{domain}/health/", healthy),
        ("Plain HTTP redirects to HTTPS", f"http://{domain}/", redirects_to(f"https://{domain}/")),
        ("www redirects to the service's address", f"https://www.{domain}/", redirects_to(f"https://{domain}/")),
        ("A club's page sends HSTS, frame and referrer headers", f"https://{club}.{domain}/", secure_headers),
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("domain", nargs="?", default="racetimes.co.uk")
    parser.add_argument("--club", default="demo", help="a club's subdomain that exists (default: demo)")
    args = parser.parse_args(argv)

    failed = 0
    for label, url, expected in checks(args.domain, args.club):
        try:
            answer = fetch(url)
            ok, note = expected(*answer), f"{answer[0]}"
        except (urllib.error.URLError, OSError) as error:  # includes an invalid certificate
            ok, note = False, str(getattr(error, "reason", error))
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {label}  ({url}: {note})")
    for host in (args.domain, f"{args.club}.{args.domain}"):
        try:
            left = days_left(host)
            ok, note = left >= CERTIFICATE_DAYS_LEFT, f"{left} days left"
        except OSError as error:
            ok, note = False, str(error)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  The certificate for {host} is valid  ({note})")
    print(f"\n{'All checks passed.' if not failed else f'{failed} check(s) failed.'}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
