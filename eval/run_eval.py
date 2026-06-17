import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error, request


def post_complaint(endpoint: str, complaint: str) -> dict:
    payload = json.dumps({"complaint": complaint}).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def contains_all(text: str, terms: list[str]) -> bool:
    normalized = text.lower()
    return all(
        term.lower() in normalized
        for term in terms
    )


def evaluate_case(case: dict, payload: dict) -> list[str]:
    failures: list[str] = []

    expected_category = case.get("expected_category")
    if (
        expected_category is not None
        and payload.get("category") != expected_category
    ):
        failures.append(
            "category "
            f"expected={expected_category!r} "
            f"actual={payload.get('category')!r}"
        )

    if "expected_needs_human_review" in case:
        expected_review = case["expected_needs_human_review"]
        if payload.get("needs_human_review") is not expected_review:
            failures.append(
                "needs_human_review "
                f"expected={expected_review!r} "
                f"actual={payload.get('needs_human_review')!r}"
            )

    expected_stage = case.get("expected_processing_stage")
    if (
        expected_stage is not None
        and payload.get("processing_stage") != expected_stage
    ):
        failures.append(
            "processing_stage "
            f"expected={expected_stage!r} "
            f"actual={payload.get('processing_stage')!r}"
        )

    redacted_complaint = str(
        payload.get("redacted_complaint", "")
    )
    for term in case.get("expected_redacted_contains", []):
        if term not in redacted_complaint:
            failures.append(
                f"redacted_complaint missing {term!r}"
            )

    citation_ids = {
        item.get("id")
        for item in payload.get("citations", [])
    }
    expected_any = set(
        case.get("expected_citation_ids_any", [])
    )
    if expected_any and citation_ids.isdisjoint(expected_any):
        failures.append(
            "citations missing any of "
            f"{sorted(expected_any)!r}; "
            f"actual={sorted(citation_ids)!r}"
        )

    note_terms = case.get("expected_handling_note_terms", [])
    handling_note = str(payload.get("handling_note", ""))
    if note_terms and not contains_all(handling_note, note_terms):
        failures.append(
            "handling_note missing expected terms "
            f"{note_terms!r}"
        )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a lightweight triage golden eval."
    )
    parser.add_argument(
        "--endpoint",
        default=os.getenv(
            "COPILOT_TRIAGE_ENDPOINT",
            "http://localhost:7071/api/triage",
        ),
        help="Triage endpoint URL.",
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
            payload = post_complaint(
                args.endpoint,
                case["complaint"],
            )
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(
                f"{case['id']}: request failed: "
                f"{exc.code} {body}",
                file=sys.stderr,
            )
            return 2
        except error.URLError as exc:
            print(
                f"{case['id']}: request failed: {exc}",
                file=sys.stderr,
            )
            return 2

        case_failures = evaluate_case(case, payload)
        if case_failures:
            failures += 1
            print(f"{case['id']}: fail")
            for failure in case_failures:
                print(f"  - {failure}")
        else:
            print(f"{case['id']}: pass")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
