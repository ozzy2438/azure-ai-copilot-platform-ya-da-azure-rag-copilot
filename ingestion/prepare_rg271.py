from pathlib import Path

from pypdf import PdfReader


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_PATH = PROJECT_ROOT / "ingestion" / "data" / "rg271.pdf"
TEXT_PATH = PROJECT_ROOT / "ingestion" / "data" / "rg271.txt"


def extract_pdf_text(pdf_path: Path) -> str:
    """
    Extracts text from every page of the RG 271 PDF.
    """

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Source PDF was not found: {pdf_path}"
        )

    reader = PdfReader(str(pdf_path))
    extracted_pages: list[str] = []

    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_text = page_text.strip()

        if page_text:
            extracted_pages.append(
                f"\n\n--- PAGE {page_number} ---\n\n{page_text}"
            )

    if not extracted_pages:
        raise ValueError(
            "No text could be extracted from the PDF."
        )

    return "".join(extracted_pages).strip()


def main() -> None:
    text = extract_pdf_text(PDF_PATH)

    TEXT_PATH.write_text(
        text,
        encoding="utf-8",
    )

    page_count = text.count("--- PAGE ")

    print("RG 271 text extraction completed.")
    print(f"Source PDF: {PDF_PATH}")
    print(f"Output text: {TEXT_PATH}")
    print(f"Pages extracted: {page_count}")
    print(f"Characters extracted: {len(text):,}")


if __name__ == "__main__":
    main()