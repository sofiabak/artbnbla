#!/usr/bin/env python3
"""
Fetches every listing's Airbnb iCal feed and writes availability.json
with the set of booked (unavailable) dates per listing.

Reads the URLs from the AIRBNB_ICAL_URLS environment variable (a JSON
object mapping listing id -> iCal URL), which is populated from a GitHub
Actions repository secret. The URLs themselves are never written to disk
or committed to the repo -- only the resulting booked-dates list is.
"""
import json, os, re, sys, urllib.request, pathlib
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT / "availability.json"


def fetch_ics(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_booked_dates(ics_text):
    """Extract all booked calendar dates (YYYY-MM-DD) from an Airbnb iCal feed."""
    dates = set()
    events = re.findall(r"BEGIN:VEVENT(.*?)END:VEVENT", ics_text, re.S)
    for ev in events:
        start_m = re.search(r"DTSTART(?:;VALUE=DATE)?:(\d{8})", ev)
        end_m = re.search(r"DTEND(?:;VALUE=DATE)?:(\d{8})", ev)
        if not start_m or not end_m:
            continue
        start = datetime.strptime(start_m.group(1), "%Y%m%d")
        end = datetime.strptime(end_m.group(1), "%Y%m%d")  # exclusive end
        d = start
        while d < end:
            dates.add(d.strftime("%Y-%m-%d"))
            d += timedelta(days=1)
    return sorted(dates)


def main():
    raw = os.environ.get("AIRBNB_ICAL_URLS", "").strip()
    if not raw:
        print("AIRBNB_ICAL_URLS secret is not set yet -- skipping sync. "
              "The site will keep showing demo availability until it's configured.")
        sys.exit(0)

    try:
        urls = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: AIRBNB_ICAL_URLS is not valid JSON: {e}")
        sys.exit(1)

    old = {}
    if OUTPUT_FILE.exists():
        try:
            old = json.loads(OUTPUT_FILE.read_text())
        except Exception:
            pass

    result = {}
    had_error = False
    for listing_id, url in urls.items():
        if not url:
            continue
        try:
            ics = fetch_ics(url)
            booked = parse_booked_dates(ics)
            result[listing_id] = booked
            print(f"{listing_id}: {len(booked)} booked dates")
        except Exception as e:
            had_error = True
            print(f"ERROR fetching {listing_id}: {e}")
            if listing_id in old:
                print(f"  -> keeping last known data for {listing_id}")
                result[listing_id] = old[listing_id]

    result["_synced_at"] = datetime.utcnow().isoformat() + "Z"
    OUTPUT_FILE.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {OUTPUT_FILE}")

    if had_error and not result:
        sys.exit(1)


if __name__ == "__main__":
    main()
