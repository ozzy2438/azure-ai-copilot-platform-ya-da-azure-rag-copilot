import json
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SOURCE_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271.txt"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271_source_blocks.json"
)


PAGE_MARKER_PATTERN = re.compile(
    r"--- PAGE\s+(\d+)\s+---"
)


def normalise_paragraph(text: str) -> str:
    """
    Cleans PDF line wrapping without changing the source wording.
    """

    text = text.replace("\r\n", "\n")

    # Join ordinary line wraps inside a paragraph.
    text = re.sub(r"(?<!\n)\n(?!\n)", " ", text)

    # Remove repeated spaces.
    text = re.sub(r"[ \t]+", " ", text)

    return text.strip()


def extract_source_blocks(text: str) -> list[dict]:
    """
    Converts page-marked text into numbered source paragraphs.

    This does not perform semantic chunking.
    It only creates traceable source units for the agent.
    """

    matches = list(
        PAGE_MARKER_PATTERN.finditer(text)
    )

    if not matches:
        raise ValueError(
            "No page markers were found. "
            "Expected markers such as --- PAGE 1 ---."
        )

    blocks: list[dict] = []

    for index, match in enumerate(matches):
        page_number = int(match.group(1))

        page_start = match.end()

        page_end = (
            matches[index + 1].start()
            if index + 1 < len(matches)
            else len(text)
        )

        page_text = text[page_start:page_end].strip()

        raw_paragraphs = re.split(
            r"\n\s*\n",
            page_text,
        )

        for paragraph in raw_paragraphs:
            cleaned = normalise_paragraph(paragraph)

            if not cleaned:
                continue

            block_id = f"B{len(blocks) + 1:05d}"

            blocks.append(
                {
                    "block_id": block_id,
                    "page": page_number,
                    "text": cleaned,
                    "character_count": len(cleaned),
                }
            )

    return blocks


def main() -> None:
    if not SOURCE_PATH.exists():
        raise FileNotFoundError(
            f"RG 271 text file was not found: "
            f"{SOURCE_PATH}"
        )

    source_text = SOURCE_PATH.read_text(
        encoding="utf-8"
    )

    blocks = extract_source_blocks(source_text)

    OUTPUT_PATH.write_text(
        json.dumps(
            blocks,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Source block preparation completed.")
    print(f"Blocks created: {len(blocks)}")
    print(f"Output file: {OUTPUT_PATH}")

    if blocks:
        print("\nFirst block:")
        print(
            json.dumps(
                blocks[0],
                indent=2,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()