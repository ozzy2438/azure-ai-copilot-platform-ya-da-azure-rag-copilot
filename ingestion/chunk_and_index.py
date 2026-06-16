import argparse
import hashlib
import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchableField,
    SearchFieldDataType,
    SearchIndex,
    SimpleField,
)
from dotenv import load_dotenv


def required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def credential() -> AzureKeyCredential | DefaultAzureCredential:
    key = os.getenv("AZURE_SEARCH_KEY") or os.getenv("AZURE_SEARCH_API_KEY")
    return AzureKeyCredential(key) if key else DefaultAzureCredential()


def ensure_index(endpoint: str, index_name: str) -> None:
    client = SearchIndexClient(endpoint=endpoint, credential=credential())
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SimpleField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
    ]
    client.create_or_update_index(SearchIndex(name=index_name, fields=fields))


def chunk_text(text: str, size: int = 1800, overlap: int = 200) -> list[str]:
    cleaned = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not cleaned:
        return []

    chunks = []
    start = 0
    while start < len(cleaned):
        end = min(start + size, len(cleaned))
        chunks.append(cleaned[start:end])
        if end == len(cleaned):
            break
        start = max(0, end - overlap)
    return chunks


def document_id(source: str, chunk_index: int, content: str) -> str:
    digest = hashlib.sha256(f"{source}:{chunk_index}:{content}".encode()).hexdigest()
    return digest[:32]


def load_documents(input_dir: Path) -> list[dict]:
    records = []
    for path in sorted(input_dir.rglob("*")):
        if path.suffix.lower() not in {".md", ".txt"}:
            continue

        text = path.read_text(encoding="utf-8")
        for chunk_index, chunk in enumerate(chunk_text(text), start=1):
            source = str(path.relative_to(input_dir))
            records.append(
                {
                    "id": document_id(source, chunk_index, chunk),
                    "content": chunk,
                    "source": source,
                }
            )
    return records


def upload_documents(endpoint: str, index_name: str, records: list[dict]) -> None:
    if not records:
        print("No documents found to upload.")
        return

    client = SearchClient(
        endpoint=endpoint,
        index_name=index_name,
        credential=credential(),
    )
    result = client.merge_or_upload_documents(records)
    succeeded = sum(1 for item in result if item.succeeded)
    print(f"Uploaded {succeeded}/{len(records)} chunks to {index_name}.")


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Chunk and index local documents.")
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).parent / "data",
        help="Directory containing .txt or .md files.",
    )
    args = parser.parse_args()

    endpoint = required_env("AZURE_SEARCH_ENDPOINT")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME") or required_env(
        "AZURE_SEARCH_INDEX"
    )

    ensure_index(endpoint, index_name)
    upload_documents(endpoint, index_name, load_documents(args.input_dir))


if __name__ == "__main__":
    main()
