import os
from typing import Any
import re
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

AOAI_ENDPOINT = os.environ["AOAI_ENDPOINT"]
AOAI_KEY = os.environ["AOAI_KEY"]

CHAT_DEPLOYMENT = os.getenv(
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "gpt-4o-mini",
)
MAX_GENERATION_REPAIR_ATTEMPTS = 2


def normalise_openai_endpoint(endpoint: str) -> str:
    """
    Converts the Azure OpenAI resource endpoint
    into the v1 API base URL.
    """

    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/openai/v1"):
        return endpoint + "/"

    return endpoint + "/openai/v1/"


client = OpenAI(
    api_key=AOAI_KEY,
    base_url=normalise_openai_endpoint(
        AOAI_ENDPOINT
    ),
)


SYSTEM_PROMPT = """
You are a compliance support assistant for an Australian financial
services complaints team.

Your task is to draft a concise internal handling note using only the
regulatory context supplied to you.

Mandatory rules:

1. Use only the supplied ASIC RG 271 context.
2. Do not invent legal requirements, deadlines or remedies.
3. Cite the relevant chunk ID after each important guidance point,
   using the exact format [rg271-XXXX].
   Use only the CHUNK ID values supplied in the retrieved context.
   Do not shorten citation IDs such as [rg271-0024] to [rg271-24].
4. Clearly separate confirmed regulatory guidance from operational
   suggestions.
5. Do not give legal advice.
6. Do not make a final legal or customer-outcome decision.
7. Do not instruct staff to take irreversible action.
8. If the context is insufficient or conflicting, explicitly state
   that human review is required.
9. Keep the note concise, practical and suitable for an internal
   complaints-handling team.
10. Do not expose or repeat unnecessary personal information.

11. Do not assume that a general 30-day timeframe applies unless the
    complaint type is known and the supplied context supports that
    timeframe.

12. If different complaint types have different timeframes, state that
    the applicable timeframe must first be identified.

13. Distinguish between:
    - enforceable requirements;
    - ASIC expectations or good-practice guidance; and
    - internal operational suggestions.

14. Do not cite RG paragraph numbers unless those exact paragraph
    numbers appear in the supplied context.

15. Every regulatory statement in both "Relevant RG 271 guidance" and
    "Suggested handling steps" must include at least one supplied chunk
    ID citation.

16. Use cautious language such as "confirm", "assess", "consider" and
    "subject to the applicable complaint type". Do not state that a
    deadline has been breached unless the complaint type, receipt date
    and applicable timeframe are confirmed.
17. The complaint type in the user input is UNKNOWN unless it is
    explicitly stated.

18. When the complaint type is unknown, never begin by stating that
    the 30-calendar-day timeframe definitely applies.

19. In that situation, use this form:
    "For complaint types subject to the general timeframe, the supplied
    context indicates a maximum of 30 calendar days. The applicable
    timeframe must be confirmed based on the complaint type."

20. Do not say that the complaint is overdue, breached, non-compliant,
    or outside the maximum timeframe unless the complaint type and
    receipt date are confirmed.

Use this structure:

Issue:
Relevant RG 271 guidance:
Suggested handling steps:
Human review:
""".strip()


def build_context(
    retrieved_items: list[dict[str, Any]],
) -> str:
    """
    Formats retrieved Azure AI Search results
    into source-labelled regulatory context.
    """

    context_sections: list[str] = []

    for item in retrieved_items:
        context_sections.append(
            "\n".join(
                [
                    f"CHUNK ID: {item['id']}",
                    f"TITLE: {item['title']}",
                    (
                        f"PAGES: {item['page_start']}"
                        f"–{item['page_end']}"
                    ),
                    "SOURCE CONTENT:",
                    item["content"],
                ]
            )
        )

    return "\n\n---\n\n".join(
        context_sections
    )

def validate_citations(
    note: str,
    allowed_chunk_ids: list[str],
) -> None:
    """
    Rejects missing, malformed, or unsupported chunk citations.
    """

    # Find anything that resembles an RG 271 chunk citation.
    citation_like_values = re.findall(
        r"\[(rg271-[^\]]+)\]",
        note,
        flags=re.IGNORECASE,
    )

    if not citation_like_values:
        raise RuntimeError(
            "The generated note contains no RG 271 chunk citations."
        )

    malformed_ids = [
        citation
        for citation in citation_like_values
        if not re.fullmatch(
            r"rg271-\d{4}",
            citation,
            flags=re.IGNORECASE,
        )
    ]

    if malformed_ids:
        raise RuntimeError(
            "The generated note contains malformed citations: "
            + ", ".join(sorted(set(malformed_ids)))
        )

    cited_ids = {
        citation.lower()
        for citation in citation_like_values
    }

    allowed_ids = {
        chunk_id.lower()
        for chunk_id in allowed_chunk_ids
    }

    invalid_ids = cited_ids - allowed_ids

    if invalid_ids:
        raise RuntimeError(
            "The generated note cited chunks that were not "
            "supplied in the retrieved context: "
            + ", ".join(sorted(invalid_ids))
        )


def request_handling_note(
    complaint: str,
    regulatory_context: str,
    validation_error: str | None = None,
    previous_note: str | None = None,
) -> tuple[str, int]:
    """
    Requests a handling note and optionally asks the model to repair citations.
    """

    repair_instruction = ""

    if validation_error:
        repair_instruction = f"""

CITATION VALIDATION FAILED:

{validation_error}

Rewrite the handling note using only the exact CHUNK ID values supplied
in the retrieved context. Keep the required structure. Do not cite RG
paragraph numbers as chunk citations. Do not use shortened IDs such as
[rg271-51] or [rg271-66].

PREVIOUS NOTE TO REPAIR:

{previous_note or ""}
""".rstrip()

    user_prompt = f"""
CASE STATUS:

- Complaint type confirmed: NO
- Exact receipt date confirmed: NO
- Applicable statutory or regulatory timeframe confirmed: NO
- Do not conclude that a breach has occurred.

COMPLAINT:

{complaint}

RETRIEVED ASIC RG 271 CONTEXT:

{regulatory_context}
{repair_instruction}

Draft the internal handling note now.
""".strip()

    response = client.chat.completions.create(
        model=CHAT_DEPLOYMENT,
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": user_prompt,
            },
        ],
        temperature=0.1,
        max_tokens=700,
    )

    note = response.choices[0].message.content

    if not note:
        raise RuntimeError(
            "The model returned an empty handling note."
        )

    tokens_used = (
        response.usage.total_tokens
        if response.usage
        else 0
    )

    return note.strip(), tokens_used


def generate_handling_note(
    complaint: str,
    retrieved_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Generates a source-grounded internal handling note.
    """

    if not isinstance(complaint, str) or not complaint.strip():
        raise ValueError(
            "complaint must be a non-empty string"
        )

    if not retrieved_items:
        return {
            "handling_note": (
                "No sufficiently relevant RG 271 context "
                "was retrieved. Human review is required."
            ),
            "tokens_used": 0,
            "model": None,
            "context_chunk_ids": [],
            "generation_completed": False,
        }

    regulatory_context = build_context(
        retrieved_items
    )
    allowed_chunk_ids = [
        item["id"]
        for item in retrieved_items
    ]

    note = ""
    total_tokens = 0
    validation_error: str | None = None

    for attempt in range(MAX_GENERATION_REPAIR_ATTEMPTS + 1):
        note, tokens_used = request_handling_note(
            complaint=complaint,
            regulatory_context=regulatory_context,
            validation_error=validation_error,
            previous_note=note,
        )
        total_tokens += tokens_used

        try:
            validate_citations(
                note=note,
                allowed_chunk_ids=allowed_chunk_ids,
            )
            break
        except RuntimeError as exc:
            validation_error = str(exc)

            if attempt >= MAX_GENERATION_REPAIR_ATTEMPTS:
                raise

            print(
                "Generated note failed citation validation; "
                "requesting corrected note "
                f"({attempt + 1}/{MAX_GENERATION_REPAIR_ATTEMPTS})..."
            )

    return {
        "handling_note": note,
        "tokens_used": total_tokens,
        "model": CHAT_DEPLOYMENT,
        "context_chunk_ids": [
            item["id"]
            for item in retrieved_items
        ],
        "generation_completed": True,
    }
