import argparse
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_BLOCKS_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271_source_blocks.json"
)

AGENTIC_UNITS_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271_agentic_units.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271_agentic_chunks.json"
)

CHECKPOINT_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "agentic_checkpoint.json"
)


# Maximum approximate input size sent in one agent request.
# This keeps requests smaller, cheaper and easier to inspect.
MAX_BATCH_CHARS = 9_000
MIN_BATCH_CHARS = 6_000
MAX_FINAL_CHUNK_CHARS = 4_000
# These are not final chunks.
# They are small, immutable evidence units that the agent groups.
TARGET_UNIT_CHARS = 700
MAX_UNIT_CHARS = 1_100
# Pages 1–3 contain the cover, document metadata and table of contents.
# The substantive regulatory guidance begins on page 4.
MIN_SOURCE_PAGE = 4


KNOWN_HEADINGS = (
    "A Overview",
    "Key points",
    "Financial services dispute resolution framework",
    "ASIC’s role in internal dispute resolution",
    "Application of the IDR requirements",
    "Requirements for IDR processes",
    "Transition period",
    "B Application of IDR requirements",
    "Definition of ‘complaint’",
    "Definition of ‘complainant’",
    "Outsourcing IDR processes",
    "C Maximum IDR timeframes and IDR responses",
    "Acknowledgement of complaint",
    "What an IDR response must contain",
    "Maximum timeframes for an IDR response",
    "IDR response requirements for multi-tier IDR processes",
    "The role of customer advocates",
    "Links between the IDR process and AFCA",
    "D Systemic issues",
    "Examples of systemic issues",
    "How to manage systemic issues",
    "E IDR standards",
    "Basis for the IDR standards",
    "Commitment and culture",
    "Enabling complaints",
    "Resourcing",
    "Responsiveness",
    "Objectivity and fairness",
    "Policy and procedures",
    "Data collection, analysis and internal reporting",
    "Continuous improvement",
    "Key terms",
    "Related information",
)

class PlannedChunk(BaseModel):
    """
    A semantic grouping decision made by the agent.
    """

    title: str = Field(
        description="Short descriptive title for the chunk."
    )

    topic: str = Field(
        description="Short snake_case topic label."
    )

    summary: str = Field(
        description=(
            "A short metadata summary. "
            "It must not add rules or legal conclusions."
        )
    )

    unit_ids: list[str] = Field(
        description=(
            "Adjacent source unit IDs included in this chunk, "
            "in their original order."
        )
    )

    rationale: str = Field(
        description=(
            "Brief reason these adjacent units belong together."
        )
    )


class BatchChunkPlan(BaseModel):
    """
    Structured response required from the agent.
    """

    chunks: list[PlannedChunk]


SYSTEM_PROMPT = """
You are an expert information architect working with ASIC Regulatory Guide 271.

Your task is to identify semantically coherent chunk boundaries.

Important rules:

1. You receive numbered source units.
2. Every source unit must be assigned to exactly one chunk.
3. Preserve the original order.
4. A chunk may contain only adjacent source units.
5. Do not omit, duplicate or reorder any source unit.
6. Do not rewrite the regulatory source text.
7. Do not create legal rules, obligations or interpretations.
8. Keep closely related headings, requirements, notes and examples together.
9. Start a new chunk when the legal topic, requirement or operational purpose changes.
10. Avoid chunks containing only an isolated heading where possible.
11. The title, topic, summary and rationale are metadata only.
12. The actual final chunk content will be reconstructed from the original source units by Python.
13. Aim for final chunks between approximately 500 and 3,000 characters.
14. Do not create a chunk larger than 4,000 characters unless preserving an inseparable table makes it unavoidable.
15. Do not combine different firm types merely because they appear in the same table.
16. Do not attach a new section heading to the preceding section.

Return only the structured chunk plan.
""".strip()


def normalise_endpoint(endpoint: str) -> str:
    """
    Converts an Azure OpenAI resource endpoint into a v1 base URL.
    """

    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/openai/v1"):
        return endpoint + "/"

    return endpoint + "/openai/v1/"


def remove_repeated_page_header(text: str) -> str:
    """
    Removes recurring PDF headers and page labels.

    It does not alter regulatory wording in the body.
    """

    patterns = [
        (
            r"REGULATORY GUIDE 271:\s*"
            r"Internal dispute resolution\s*"
            r"© Australian Securities and Investments Commission\s*"
            r"September 2021\s*"
            r"Page\s+\d+\s*"
        ),
    ]

    cleaned = text

    for pattern in patterns:
        cleaned = re.sub(
            pattern,
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

    return re.sub(r"\s+", " ", cleaned).strip()


def split_at_regulatory_anchors(text: str) -> list[str]:
    """
    Separates source text at strong regulatory and document anchors.

    These pieces are immutable evidence units, not final RAG chunks.
    """

    heading_pattern = "|".join(
        re.escape(heading)
        for heading in sorted(
            KNOWN_HEADINGS,
            key=len,
            reverse=True,
        )
    )

    anchor_pattern = re.compile(
        rf"(?="
        rf"RG\s+271\.\d+\s+(?=(?-i:[A-Z]))"
        rf"|Note(?:\s+\d+)?:"
        rf"|Example\s+\d+:"
        rf"|Table\s+\d+:"
        rf"|{heading_pattern}"
        rf")",
        flags=re.IGNORECASE,
    )

    return [
        part.strip()
        for part in anchor_pattern.split(text)
        if part.strip()
    ]


def find_safe_cut_position(
    text: str,
    limit: int,
) -> int:
    """
    Finds the safest available boundary before the character limit.

    Preference order:
    1. Sentence or clause punctuation
    2. Bullet boundary
    3. Whitespace boundary

    It never cuts through the middle of a word.
    """

    window = text[: limit + 1]

    preferred_separators = (
        ". ",
        "; ",
        ": ",
        " • ",
        "  ",
    )

    candidate_positions = [
        window.rfind(separator)
        for separator in preferred_separators
    ]

    best_position = max(candidate_positions)

    if best_position >= int(limit * 0.60):
        return best_position + 1

    whitespace_position = window.rfind(" ")

    if whitespace_position > 0:
        return whitespace_position

    return limit

def split_long_piece(piece: str) -> list[str]:
    """
    Divides unusually long evidence pieces at safe boundaries.

    These are not final semantic chunks. The agent will later
    group adjacent evidence units according to meaning.
    """

    if len(piece) <= MAX_UNIT_CHARS:
        return [piece]

    candidate_segments = re.split(
        r"(?<=[.!?;:])\s+"
        r"(?="
        r"(?:[A-Z]"
        r"|RG\s+271\."
        r"|Note\b"
        r"|Example\b"
        r"|Table\b"
        r"|\([a-z0-9]+\)"
        r"|[•])"
        r")",
        piece,
    )

    output_units: list[str] = []
    buffer = ""

    def append_safely(value: str) -> None:
        remaining = value.strip()

        while len(remaining) > MAX_UNIT_CHARS:
            cut_position = find_safe_cut_position(
                remaining,
                MAX_UNIT_CHARS,
            )

            first_part = remaining[:cut_position].strip()

            if first_part:
                output_units.append(first_part)

            remaining = remaining[cut_position:].strip()

        if remaining:
            output_units.append(remaining)

    for segment in candidate_segments:
        segment = segment.strip()

        if not segment:
            continue

        candidate = (
            f"{buffer} {segment}".strip()
            if buffer
            else segment
        )

        if len(candidate) <= TARGET_UNIT_CHARS:
            buffer = candidate
            continue

        if buffer:
            append_safely(buffer)
            buffer = ""

        if len(segment) > MAX_UNIT_CHARS:
            append_safely(segment)
        else:
            buffer = segment

    if buffer:
        append_safely(buffer)

    return output_units


def build_source_units(
    page_blocks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Converts large page-level blocks into traceable evidence units.

    The units keep the original wording and page number.
    """

    units: list[dict[str, Any]] = []

    for page_block in page_blocks:
        page = int(page_block["page"])

        if page < MIN_SOURCE_PAGE:
            continue

        page_text = remove_repeated_page_header(
            page_block["text"]
        )

        anchored_pieces = split_at_regulatory_anchors(
            page_text
        )

        for piece in anchored_pieces:
            smaller_pieces = split_long_piece(piece)

            for smaller_piece in smaller_pieces:
                cleaned_piece = re.sub(
                    r"\s+",
                    " ",
                    smaller_piece,
                ).strip()

                if not cleaned_piece:
                    continue

                unit_id = f"U{len(units) + 1:05d}"

                units.append(
                    {
                        "unit_id": unit_id,
                        "page": page,
                        "text": cleaned_piece,
                        "character_count": len(cleaned_piece),
                        "source_block_id": page_block["block_id"],
                    }
                )

    return units


def is_section_heading(unit: dict[str, Any]) -> bool:
    """
    Detects short document headings so a new model batch can
    begin at a meaningful section boundary.
    """

    text = unit["text"].strip()

    return (
        text in KNOWN_HEADINGS
        or (
            len(text) <= 90
            and not text.endswith((".", ";", ":"))
            and not text.startswith(
                ("RG 271.", "Note", "Table", "Example")
            )
        )
    )


def create_batches(
    units: list[dict[str, Any]],
) -> list[list[dict[str, Any]]]:
    """
    Creates sequential batches and prefers starting a new batch
    at a document section heading.

    This prevents headings from being stranded at the end of
    the previous model request.
    """

    batches: list[list[dict[str, Any]]] = []
    current_batch: list[dict[str, Any]] = []
    current_chars = 0

    for unit in units:
        unit_size = len(unit["text"])

        starts_new_section = (
            current_batch
            and current_chars >= MIN_BATCH_CHARS
            and is_section_heading(unit)
        )

        exceeds_hard_limit = (
            current_batch
            and current_chars + unit_size > MAX_BATCH_CHARS
        )

        if starts_new_section or exceeds_hard_limit:
            batches.append(current_batch)
            current_batch = []
            current_chars = 0

        current_batch.append(unit)
        current_chars += unit_size

    if current_batch:
        batches.append(current_batch)

    return batches


def format_batch_for_agent(
    batch: list[dict[str, Any]],
) -> str:
    """
    Creates the numbered text shown to the agent.
    """

    sections = []

    for unit in batch:
        sections.append(
            f"[{unit['unit_id']}] "
            f"[Page {unit['page']}]\n"
            f"{unit['text']}"
        )

    return "\n\n".join(sections)


def validate_plan(
    plan: BatchChunkPlan,
    batch: list[dict[str, Any]],
) -> None:
    """
    Refuses output with missing, duplicated, invented,
    reordered or non-adjacent source units.
    """

    expected_ids = [
        unit["unit_id"]
        for unit in batch
    ]

    returned_ids = [
        unit_id
        for chunk in plan.chunks
        for unit_id in chunk.unit_ids
    ]

    if returned_ids != expected_ids:
        raise ValueError(
            "Agent plan failed source coverage validation.\n"
            f"Expected: {expected_ids}\n"
            f"Returned: {returned_ids}"
        )

    expected_positions = {
        unit_id: index
        for index, unit_id in enumerate(expected_ids)
    }

    for chunk in plan.chunks:
        if not chunk.unit_ids:
            raise ValueError(
                "Agent returned a chunk with no source units."
            )

        positions = [
            expected_positions[unit_id]
            for unit_id in chunk.unit_ids
        ]

        expected_sequence = list(
            range(
                positions[0],
                positions[0] + len(positions),
            )
        )

        if positions != expected_sequence:
            raise ValueError(
                "Agent attempted to group non-adjacent units: "
                f"{chunk.unit_ids}"
            )


def reconstruct_chunks(
    plan: BatchChunkPlan,
    batch: list[dict[str, Any]],
    starting_number: int,
    batch_number: int,
) -> list[dict[str, Any]]:
    """
    Reconstructs final content from original source units.

    The LLM never supplies the final regulatory wording.
    """

    unit_lookup = {
        unit["unit_id"]: unit
        for unit in batch
    }

    reconstructed: list[dict[str, Any]] = []

    for offset, planned_chunk in enumerate(
        plan.chunks
    ):
        selected_units = [
            unit_lookup[unit_id]
            for unit_id in planned_chunk.unit_ids
        ]

        content = "\n\n".join(
            unit["text"]
            for unit in selected_units
        )

        if len(content) > MAX_FINAL_CHUNK_CHARS:
            raise ValueError(
                "Agent created an oversized final chunk: "
                f"{planned_chunk.unit_ids} "
                f"({len(content):,} characters)"
            )

        pages = sorted(
            {
                unit["page"]
                for unit in selected_units
            }
        )

        chunk_number = starting_number + offset

        reconstructed.append(
            {
                "id": f"rg271-{chunk_number:04d}",
                "title": planned_chunk.title,
                "topic": planned_chunk.topic,
                "summary": planned_chunk.summary,
                "content": content,
                "page_start": min(pages),
                "page_end": max(pages),
                "source_unit_ids": planned_chunk.unit_ids,
                "source_block_ids": sorted(
                    {
                        unit["source_block_id"]
                        for unit in selected_units
                    }
                ),
                "agent_rationale": planned_chunk.rationale,
                "source": (
                    "ASIC Regulatory Guide 271: "
                    "Internal dispute resolution"
                ),
                "batch_number": batch_number,
                "character_count": len(content),
                "content_sha256": hashlib.sha256(
                    content.encode("utf-8")
                ).hexdigest(),
            }
        )

    return reconstructed


def create_client() -> tuple[OpenAI, str]:
    """
    Creates the Azure OpenAI v1 client.
    """

    load_dotenv()

    endpoint = (
        os.getenv("AOAI_ENDPOINT")
        or os.getenv("AZURE_OPENAI_ENDPOINT")
    )

    api_key = (
        os.getenv("AOAI_KEY")
        or os.getenv("AZURE_OPENAI_API_KEY")
    )

    deployment = os.getenv(
        "AZURE_OPENAI_CHAT_DEPLOYMENT",
        "gpt-4o-mini",
    )

    if not endpoint:
        raise EnvironmentError(
            "AOAI_ENDPOINT or AZURE_OPENAI_ENDPOINT "
            "is missing."
        )

    if not api_key:
        raise EnvironmentError(
            "AOAI_KEY or AZURE_OPENAI_API_KEY "
            "is missing."
        )

    client = OpenAI(
        api_key=api_key,
        base_url=normalise_endpoint(endpoint),
    )

    return client, deployment


def call_chunking_agent(
    client: OpenAI,
    deployment: str,
    batch: list[dict[str, Any]],
) -> tuple[BatchChunkPlan, int]:
    """
    Requests a validated structured chunk plan.
    """

    expected_ids = [
        unit["unit_id"]
        for unit in batch
    ]

    user_prompt = (
        "Group the following adjacent regulatory source units "
        "into semantically coherent chunks.\n\n"
        "Every ID in this exact sequence must appear once:\n"
        f"{expected_ids}\n\n"
        "SOURCE UNITS:\n\n"
        f"{format_batch_for_agent(batch)}"
    )

    completion = client.beta.chat.completions.parse(
        model=deployment,
        temperature=0,
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
        response_format=BatchChunkPlan,
    )

    message = completion.choices[0].message

    if message.refusal:
        raise RuntimeError(
            f"Model refused the request: {message.refusal}"
        )

    if message.parsed is None:
        raise RuntimeError(
            "The model returned no parsed chunk plan."
        )

    tokens_used = (
        completion.usage.total_tokens
        if completion.usage
        else 0
    )

    return message.parsed, tokens_used


def save_json(
    path: Path,
    value: Any,
) -> None:
    path.write_text(
        json.dumps(
            value,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def run_prepare_only() -> None:
    """
    Builds units and batches without making any paid model call.
    """

    page_blocks = json.loads(
        SOURCE_BLOCKS_PATH.read_text(
            encoding="utf-8"
        )
    )

    units = build_source_units(page_blocks)
    batches = create_batches(units)

    oversized_units = [
        unit
        for unit in units
        if unit["character_count"] > MAX_UNIT_CHARS
    ]

    invalid_pages = [
        unit
        for unit in units
        if unit["page"] < MIN_SOURCE_PAGE
    ]

    if oversized_units:
        raise ValueError(
            "Oversized source units remain: "
            f"{[unit['unit_id'] for unit in oversized_units]}"
        )

    if invalid_pages:
        raise ValueError(
            "Front-matter pages entered the agentic corpus."
        )

    save_json(
        AGENTIC_UNITS_PATH,
        units,
    )

    average_unit_size = (
        sum(unit["character_count"] for unit in units)
        / len(units)
    )

    print("Agentic source preparation completed.")
    print(f"Page blocks received: {len(page_blocks)}")
    print(f"Immutable source units created: {len(units)}")
    print(f"Planned model batches: {len(batches)}")
    print(
        f"Average unit size: "
        f"{average_unit_size:.0f} chars"
    )
    print(
        "Largest unit: "
        f"{max(unit['character_count'] for unit in units):,} chars"
    )
    print(f"Units written to: {AGENTIC_UNITS_PATH}")
    print("\nNo Azure OpenAI calls were made.")


def run_agentic_chunking(
    limit_batches: int | None,
) -> None:
    """
    Runs the complete agentic chunking pipeline.
    """

    page_blocks = json.loads(
        SOURCE_BLOCKS_PATH.read_text(
            encoding="utf-8"
        )
    )

    units = build_source_units(page_blocks)
    batches = create_batches(units)

    save_json(
        AGENTIC_UNITS_PATH,
        units,
    )

    if limit_batches is not None:
        batches = batches[:limit_batches]

    client, deployment = create_client()

    all_chunks: list[dict[str, Any]] = []
    total_tokens = 0

    for batch_index, batch in enumerate(
        batches,
        start=1,
    ):
        print(
            f"Processing batch {batch_index}/{len(batches)} "
            f"with {len(batch)} source units..."
        )

        plan, tokens_used = call_chunking_agent(
            client=client,
            deployment=deployment,
            batch=batch,
        )

        validate_plan(
            plan=plan,
            batch=batch,
        )

        reconstructed = reconstruct_chunks(
            plan=plan,
            batch=batch,
            starting_number=len(all_chunks) + 1,
            batch_number=batch_index,
        )

        all_chunks.extend(reconstructed)
        total_tokens += tokens_used

        checkpoint = {
            "completed_batches": batch_index,
            "chunks_created": len(all_chunks),
            "tokens_used": total_tokens,
            "chunks": all_chunks,
        }

        save_json(
            CHECKPOINT_PATH,
            checkpoint,
        )

        print(
            f"Batch {batch_index} passed validation. "
            f"Total chunks: {len(all_chunks)}"
        )

    save_json(
        OUTPUT_PATH,
        all_chunks,
    )

    print("\nAgentic chunking completed.")
    print(f"Final chunks created: {len(all_chunks)}")
    print(f"Total model tokens used: {total_tokens:,}")
    print(f"Output: {OUTPUT_PATH}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create source-faithful agentic chunks "
            "from ASIC RG 271."
        )
    )

    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help=(
            "Create immutable source units without "
            "calling Azure OpenAI."
        ),
    )

    parser.add_argument(
        "--limit-batches",
        type=int,
        default=None,
        help=(
            "Process only the first N model batches. "
            "Useful for a low-cost test."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    if not SOURCE_BLOCKS_PATH.exists():
        raise FileNotFoundError(
            f"Source blocks were not found: "
            f"{SOURCE_BLOCKS_PATH}"
        )

    if args.prepare_only:
        run_prepare_only()
        return

    run_agentic_chunking(
        limit_batches=args.limit_batches,
    )


if __name__ == "__main__":
    main()
