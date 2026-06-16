import json
import logging

import azure.functions as func

from audit import log_event
from generation import generate_answer
from pii import redact_text
from retrieval import retrieve_documents


app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


def _json_response(payload: dict, status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


@app.route(route="health", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def health(req: func.HttpRequest) -> func.HttpResponse:
    return _json_response({"status": "ok"})


@app.route(route="chat", methods=["POST"])
def chat(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json()
    except ValueError:
        return _json_response({"error": "Request body must be valid JSON."}, 400)

    question = str(body.get("question", "")).strip()
    if not question:
        return _json_response({"error": "Field 'question' is required."}, 400)

    top_k = int(body.get("top_k", 5))
    top_k = max(1, min(top_k, 10))

    redacted_question = redact_text(question)
    try:
        documents = retrieve_documents(question, top_k=top_k)
        answer = generate_answer(question, documents)
    except Exception as exc:
        logging.exception("Chat request failed")
        log_event(
            "chat.failed",
            {"question": redacted_question, "error": type(exc).__name__},
        )
        return _json_response({"error": "Chat request failed."}, 500)

    log_event(
        "chat.completed",
        {"question": redacted_question, "document_count": len(documents)},
    )

    citations = [
        {
            "id": document.id,
            "source": document.source,
            "score": document.score,
        }
        for document in documents
    ]
    return _json_response({"answer": answer, "citations": citations})
