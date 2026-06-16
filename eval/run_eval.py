import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


def post_question(endpoint: str, question: str) -> str:
    payload = json.dumps({"question": question}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    return str(body.get("answer", ""))


def score_answer(answer: str, expected_terms: list[str]) -> tuple[int, int]:
    normalized = answer.lower()
    matched = sum(1 for term in expected_terms if term.lower() in normalized)
    return matched, len(expected_terms)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a lightweight golden eval.")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("COPILOT_CHAT_ENDPOINT", "http://localhost:7071/api/chat"),
        help="Chat endpoint URL.",
    )
    parser.add_argument(
        "--golden-set",
        type=Path,
        default=Path(__file__).with_name("golden_set.json"),
        help="Golden set JSON path.",
    )
    args = parser.parse_args()

    cases = json.loads(args.golden_set.read_text(encoding="utf-8"))
    failures = 0
    for case in cases:
        try:
            answer = post_question(args.endpoint, case["question"])
        except error.URLError as exc:
            print(f"{case['id']}: request failed: {exc}", file=sys.stderr)
            return 2

        matched, total = score_answer(answer, case.get("expected_terms", []))
        status = "pass" if matched == total else "fail"
        print(f"{case['id']}: {status} ({matched}/{total} expected terms)")
        if status == "fail":
            failures += 1

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
