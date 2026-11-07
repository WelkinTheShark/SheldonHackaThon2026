"""Sends text from stdin to ZeroDog's Roast and prints the result. Standard library only."""
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    url = os.environ.get("ZERODOG_URL", "").rstrip("/")
    token = os.environ.get("ZERODOG_TOKEN", "")
    text = sys.stdin.read().strip()
    if not url or not token:
        print("Set ZERODOG_URL and ZERODOG_TOKEN. python -m app.devs add prints both.")
        return 1
    if not text:
        print("Nothing to roast. Add a prompt after /roast.")
        return 1

    request = urllib.request.Request(
        f"{url}/api/roast",
        data=json.dumps({"text": text}).encode(),
        headers={"content-type": "application/json", "x-api-key": token},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.load(response)
    except (urllib.error.URLError, ValueError) as error:
        print(f"ZeroDog couldn't roast this: {error}")
        return 1

    recommendation = result["recommendation"]
    print(f"Score: {result['score']} out of 100")
    for issue in result["issues"]:
        print(f"- {issue}")
    print(f"Fix: {result['fix']}")
    print(
        f"Recommended model: {recommendation['label']}. {recommendation['reason']} "
        f"Judged by {recommendation['decided_by']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
