import json
from audit import log_audit_event
import azure.functions as func

from classifier import classify
from generation import generate_handling_note
from pii import redact
from retrieval import retrieve


app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)


@app.route(route="health", methods=["GET"])
def health(req: func.HttpRequest) -> func.HttpResponse:
    """
    Simple health-check endpoint.

    It confirms that the local Azure Function is running.
    """

    return func.HttpResponse(
        json.dumps(
            {
                "status": "healthy",
                "service": "RegDesk Complaint Triage Copilot",
            }
        ),
        status_code=200,
        mimetype="application/json",
    )


@app.route(route="redact", methods=["POST"])
def redact_complaint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Accepts a complaint and removes basic personally identifiable information.
    """

    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps(
                {
                    "error": 'Send valid JSON such as {"complaint": "..."}'
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    complaint = body.get("complaint")

    if not isinstance(complaint, str) or not complaint.strip():
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "complaint must be a non-empty string"
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    cleaned_complaint = redact(complaint)

    return func.HttpResponse(
        json.dumps(
            {
                "redacted_complaint": cleaned_complaint,
                "pii_removed": cleaned_complaint != complaint,
            },
            indent=2,
        ),
        status_code=200,
        mimetype="application/json",
    )

@app.route(route="triage", methods=["POST"])
def triage_complaint(
    req: func.HttpRequest,
) -> func.HttpResponse:
    """
    Runs the complete RegDesk complaint-triage workflow.
    """
    try:
        body = req.get_json()
    except ValueError:
        return func.HttpResponse(
            json.dumps(
                {
                    "error": (
                        'Send valid JSON such as '
                        '{"complaint": "..."}'
                    )
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    complaint = body.get("complaint")

    if (
        not isinstance(complaint, str)
        or not complaint.strip()
    ):
        return func.HttpResponse(
            json.dumps(
                {
                    "error": (
                        "complaint must be a "
                        "non-empty string"
                    )
                }
            ),
            status_code=400,
            mimetype="application/json",
        )

    try:
        # 1. Remove basic personal information.
        cleaned_complaint = redact(complaint)
        # 2. Apply the explainable baseline classifier.
        category, confidence = classify(
            cleaned_complaint
        )
        # 3. Retrieve relevant RG 271 context.
        retrieved_items = retrieve(
            query=cleaned_complaint,
            top_k=5,
        )
        # 4. Generate a grounded handling note.
        generation_result = generate_handling_note(
            complaint=cleaned_complaint,
            retrieved_items=retrieved_items,
        )
        # 5. Apply workflow guardrails.
        handling_note_lower = generation_result[
            "handling_note"
        ].lower()
        review_phrases = [
            "human review is required",
            "further human review is required",
            "further review is required",
            "requires human review",
            "manual review is required",
            "must be confirmed",
        ]

        needs_human_review = (
            confidence < 0.50
            or not retrieved_items
            or not generation_result[
                "generation_completed"
            ]
            or any(
                phrase in handling_note_lower
                for phrase in review_phrases
            )
        )
        log_audit_event(
            complaint=cleaned_complaint,
            category=category,
            needs_human_review=needs_human_review,
            citation_ids=[
                item["id"]
                for item in retrieved_items
            ],
        )
        response = {
            "redacted_complaint": cleaned_complaint,
            "category": category,
            "classification_confidence": confidence,
            "needs_human_review": needs_human_review,
            "handling_note": generation_result[
                "handling_note"
            ],
            "citations": [
                {
                    "id": item["id"],
                    "title": item["title"],
                    "pages": (
                        f"{item['page_start']}"
                        f"-{item['page_end']}"
                    ),
                }
                for item in retrieved_items
            ],
            "tokens_used": generation_result[
                "tokens_used"
            ],
            "model": generation_result["model"],
            "processing_stage": (
                "azure_rag_with_guardrails"
            ),
        }
        return func.HttpResponse(
            json.dumps(
                response,
                indent=2,
                ensure_ascii=False,
            ),
            status_code=200,
            mimetype="application/json",
        )
    except Exception as exc:
        return func.HttpResponse(
            json.dumps(
                {
                    "error": "triage_processing_failed",
                    "detail": str(exc),
                    "needs_human_review": True,
                }
            ),
            status_code=500,
            mimetype="application/json",
        )
