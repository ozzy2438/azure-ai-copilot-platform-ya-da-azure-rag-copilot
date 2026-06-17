import argparse
import json
import os
from pathlib import Path
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CHUNKS_PATH = (
    PROJECT_ROOT
    / "ingestion"
    / "data"
    / "rg271_agentic_chunks.json"
)

EMBEDDING_DIMENSIONS = 1536
EMBEDDING_BATCH_SIZE = 16


def normalise_openai_endpoint(endpoint: str) -> str:
    """
    Converts the Azure OpenAI resource endpoint into a v1 API base URL.
    """

    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/openai/v1"):
        return endpoint + "/"

    return endpoint + "/openai/v1/"


def load_configuration() -> dict[str, str]:
    """
    Loads secrets and service settings from the local .env file.
    """

    load_dotenv(PROJECT_ROOT / ".env")

    required_values = {
        "AOAI_ENDPOINT": os.getenv("AOAI_ENDPOINT"),
        "AOAI_KEY": os.getenv("AOAI_KEY"),
        "EMBEDDING_DEPLOYMENT": os.getenv(
            "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
        ),
        "SEARCH_ENDPOINT": os.getenv("SEARCH_ENDPOINT"),
        "SEARCH_KEY": os.getenv("SEARCH_KEY"),
        "SEARCH_INDEX_NAME": os.getenv(
            "SEARCH_INDEX_NAME",
            "reg-index",
        ),
    }

    missing = [
        name
        for name, value in required_values.items()
        if not value
    ]

    if missing:
        raise EnvironmentError(
            "Missing environment values: "
            + ", ".join(missing)
        )

    return {
        name: str(value)
        for name, value in required_values.items()
    }


def create_search_index(
    config: dict[str, str],
) -> None:
    """
    Creates or updates the Azure AI Search vector index.
    """

    credential = AzureKeyCredential(
        config["SEARCH_KEY"]
    )

    index_client = SearchIndexClient(
        endpoint=config["SEARCH_ENDPOINT"],
        credential=credential,
    )

    fields = [
        SimpleField(
            name="id",
            type=SearchFieldDataType.String,
            key=True,
            filterable=True,
        ),
        SearchableField(
            name="title",
            type=SearchFieldDataType.String,
        ),
        SearchableField(
            name="topic",
            type=SearchFieldDataType.String,
            filterable=True,
            facetable=True,
        ),
        SearchableField(
            name="summary",
            type=SearchFieldDataType.String,
        ),
        SearchableField(
            name="content",
            type=SearchFieldDataType.String,
        ),
        SimpleField(
            name="page_start",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="page_end",
            type=SearchFieldDataType.Int32,
            filterable=True,
            sortable=True,
        ),
        SimpleField(
            name="source",
            type=SearchFieldDataType.String,
            filterable=True,
        ),
        SimpleField(
            name="source_unit_ids",
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.String
            ),
            filterable=True,
        ),
        SearchField(
            name="content_vector",
            type=SearchFieldDataType.Collection(
                SearchFieldDataType.Single
            ),
            searchable=True,
            vector_search_dimensions=EMBEDDING_DIMENSIONS,
            vector_search_profile_name="regdesk-vector-profile",
        ),
    ]

    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="regdesk-hnsw",
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="regdesk-vector-profile",
                algorithm_configuration_name="regdesk-hnsw",
            )
        ],
    )

    index = SearchIndex(
        name=config["SEARCH_INDEX_NAME"],
        fields=fields,
        vector_search=vector_search,
    )

    result = index_client.create_or_update_index(
        index
    )

    print(f"Search index ready: {result.name}")


def create_openai_client(
    config: dict[str, str],
) -> OpenAI:
    """
    Creates the Azure OpenAI v1 client used for embeddings.
    """

    return OpenAI(
        api_key=config["AOAI_KEY"],
        base_url=normalise_openai_endpoint(
            config["AOAI_ENDPOINT"]
        ),
    )


def create_embeddings(
    client: OpenAI,
    deployment_name: str,
    texts: list[str],
) -> list[list[float]]:
    """
    Converts text into 1,536-dimensional embedding vectors.
    """

    response = client.embeddings.create(
        model=deployment_name,
        input=texts,
    )

    ordered_items = sorted(
        response.data,
        key=lambda item: item.index,
    )

    return [
        item.embedding
        for item in ordered_items
    ]


def build_embedding_text(
    chunk: dict[str, Any],
) -> str:
    """
    Combines useful metadata with the original regulatory content.

    This improves retrieval without changing the source wording.
    """

    return (
        f"Title: {chunk['title']}\n"
        f"Topic: {chunk['topic']}\n"
        f"Summary: {chunk['summary']}\n\n"
        f"Regulatory content:\n{chunk['content']}"
    )


def build_search_document(
    chunk: dict[str, Any],
    vector: list[float],
) -> dict[str, Any]:
    """
    Converts one agentic chunk into an Azure Search document.
    """

    return {
        "id": chunk["id"],
        "title": chunk["title"],
        "topic": chunk["topic"],
        "summary": chunk["summary"],
        "content": chunk["content"],
        "page_start": chunk["page_start"],
        "page_end": chunk["page_end"],
        "source": chunk["source"],
        "source_unit_ids": chunk["source_unit_ids"],
        "content_vector": vector,
    }


def upload_chunks(
    config: dict[str, str],
) -> None:
    """
    Embeds and uploads all agentic chunks in small batches.
    """

    if not CHUNKS_PATH.exists():
        raise FileNotFoundError(
            f"Agentic chunk file not found: {CHUNKS_PATH}"
        )

    chunks = json.loads(
        CHUNKS_PATH.read_text(encoding="utf-8")
    )

    if not chunks:
        raise ValueError(
            "The agentic chunk file contains no chunks."
        )

    openai_client = create_openai_client(config)

    search_client = SearchClient(
        endpoint=config["SEARCH_ENDPOINT"],
        index_name=config["SEARCH_INDEX_NAME"],
        credential=AzureKeyCredential(
            config["SEARCH_KEY"]
        ),
    )

    uploaded_count = 0

    for start in range(
        0,
        len(chunks),
        EMBEDDING_BATCH_SIZE,
    ):
        batch = chunks[
            start:start + EMBEDDING_BATCH_SIZE
        ]

        texts = [
            build_embedding_text(chunk)
            for chunk in batch
        ]

        vectors = create_embeddings(
            client=openai_client,
            deployment_name=(
                config["EMBEDDING_DEPLOYMENT"]
            ),
            texts=texts,
        )

        if len(vectors) != len(batch):
            raise RuntimeError(
                "Embedding count does not match "
                "the number of source chunks."
            )

        documents = [
            build_search_document(
                chunk=chunk,
                vector=vector,
            )
            for chunk, vector in zip(
                batch,
                vectors,
                strict=True,
            )
        ]

        results = search_client.upload_documents(
            documents=documents
        )

        failures = [
            result
            for result in results
            if not result.succeeded
        ]

        if failures:
            messages = [
                (
                    f"{result.key}: "
                    f"{result.error_message}"
                )
                for result in failures
            ]

            raise RuntimeError(
                "Some documents failed to upload:\n"
                + "\n".join(messages)
            )

        uploaded_count += len(documents)

        print(
            f"Uploaded {uploaded_count}/{len(chunks)} "
            "documents."
        )

    print(
        f"\nCompleted: {uploaded_count} agentic chunks "
        f"uploaded to index "
        f"'{config['SEARCH_INDEX_NAME']}'."
    )


def verify_document_count(
    config: dict[str, str],
) -> None:
    """
    Confirms that documents can be retrieved from the index.
    """

    search_client = SearchClient(
        endpoint=config["SEARCH_ENDPOINT"],
        index_name=config["SEARCH_INDEX_NAME"],
        credential=AzureKeyCredential(
            config["SEARCH_KEY"]
        ),
    )

    count = search_client.get_document_count()

    print(f"Documents currently in index: {count}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create the RegDesk vector index and upload "
            "agentic RG 271 chunks."
        )
    )

    parser.add_argument(
        "--index-only",
        action="store_true",
        help=(
            "Create the Search index without generating "
            "embeddings or uploading documents."
        ),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    config = load_configuration()

    create_search_index(config)

    if args.index_only:
        print(
            "Index-only mode completed. "
            "No embedding calls were made."
        )
        return

    upload_chunks(config)
    verify_document_count(config)


if __name__ == "__main__":
    main()