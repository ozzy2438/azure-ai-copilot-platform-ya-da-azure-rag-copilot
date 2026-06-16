import json

import azure.functions as func

from pii import redact

from classifier import classify
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
def triage_complaint(req: func.HttpRequest) -> func.HttpResponse:
    """
    Redacts PII, classifies the complaint, and decides whether
    human review is required.
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

    category, confidence = classify(cleaned_complaint)

    needs_human_review = confidence < 0.50

    response = {
        "redacted_complaint": cleaned_complaint,
        "category": category,
        "classification_confidence": confidence,
        "needs_human_review": needs_human_review,
        "processing_stage": "local_rule_based_baseline",
    }

    return func.HttpResponse(
        json.dumps(response, indent=2),
        status_code=200,
        mimetype="application/json",
    )