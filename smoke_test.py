"""Lightweight local API smoke test. Start the app first, then run: python smoke_test.py"""
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000")
try:
    with urllib.request.urlopen(BASE_URL + "/health", timeout=10) as response:
        body = response.read().decode("utf-8")
        if response.status != 200 or '"status":"healthy"' not in body.replace(" ", ""):
            print("Unexpected health response:", response.status, body)
            sys.exit(1)
        print("Health check passed:", body)
except (urllib.error.URLError, TimeoutError) as exc:
    print("Health check failed:", exc)
    sys.exit(1)
