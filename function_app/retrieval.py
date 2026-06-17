import os
from typing import Any

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery
from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

SEARCH_ENDPOINT = os.environ["SEARCH_ENDPOINT"]
SEARCH_KEY = os.getenv("SEARCH_KEY")
SEARCH_INDEX_NAME = os.getenv(
    "SEARCH_INDEX_NAME",
    "reg-index",
)

AOAI_ENDPOINT = os.environ["AOAI_ENDPOINT"]
AOAI_KEY = os.environ["AOAI_KEY"]
EMBEDDING_DEPLOYMENT = os.environ[
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT"
]


def normalise_openai_endpoint(endpoint: str) -> str:
    """
    Converts the Azure OpenAI resource endpoint
    into the v1 API base URL.
    """

    endpoint = endpoint.rstrip("/")

    if endpoint.endswith("/openai/v1"):
        return endpoint + "/"

    return endpoint + "/openai/v1/"


openai_client = OpenAI(
    api_key=AOAI_KEY,
    base_url=normalise_openai_endpoint(
        AOAI_ENDPOINT
    ),
)


def create_search_credential() -> AzureKeyCredential | DefaultAzureCredential:
    """
    Uses a Search admin/query key locally and managed identity in Azure.
    """

    if SEARCH_KEY:
        return AzureKeyCredential(SEARCH_KEY)

    return DefaultAzureCredential()


search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX_NAME,
    credential=create_search_credential(),
)


def embed_query(query: str) -> list[float]:
    """
    Converts the user's complaint into the same
    vector format used for the indexed chunks.
    """

    response = openai_client.embeddings.create(
        model=EMBEDDING_DEPLOYMENT,
        input=query,
    )

    return response.data[0].embedding


def expand_query(query: str) -> str:
    """
    Adds regulatory vocabulary to common complaint language.

    This is a transparent query-expansion baseline.
    It does not change the user's original complaint.
    """

    normalised = query.lower()
    additions: list[str] = []

    if any(
        phrase in normalised
        for phrase in [
            "not responded",
            "no response",
            "still waiting",
            "three weeks",
            "weeks ago",
            "delay",
            "delayed",
        ]
    ):
        additions.extend(
            [
                "maximum IDR timeframe",
                "IDR response delay",
                "written response",
                "notification of delay",
            ]
        )

    if any(
        phrase in normalised
        for phrase in [
            "complained",
            "complaint",
            "dissatisfied",
        ]
    ):
        additions.append("internal dispute resolution")

    if not additions:
        return query

    return query + "\nRegulatory concepts: " + "; ".join(
        dict.fromkeys(additions)
    )


def domain_rerank(
    query: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Applies small, explainable domain-specific ranking boosts.

    Azure Search remains the main retriever.
    This layer only resolves obvious complaint-domain ambiguities.
    """

    normalised = query.lower()

    for item in items:
        boost = 0.0

        searchable_text = " ".join(
            [
                item["title"],
                item["topic"],
                item["summary"],
                item["content"][:800],
            ]
        ).lower()

        if any(
            phrase in normalised
            for phrase in [
                "not responded",
                "no response",
                "still waiting",
                "delay",
                "weeks ago",
            ]
        ):
            if any(
                term in searchable_text
                for term in [
                    "timeframe",
                    "response delay",
                    "maximum idr",
                    "notification of delay",
                    "idr response",
                ]
            ):
                boost += 0.020

            if "what is not a complaint" in searchable_text:
                boost -= 0.015

        item["domain_boost"] = boost
        item["final_score"] = item["score"] + boost

    return sorted(
        items,
        key=lambda item: item["final_score"],
        reverse=True,
    )


def retrieve(
    query: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """
    Runs hybrid retrieval:
    keyword search + vector similarity search.
    """

    if not isinstance(query, str) or not query.strip():
        raise ValueError(
            "query must be a non-empty string"
        )

    expanded_query = expand_query(query)
    candidate_count = max(top_k * 3, 15)

    query_vector = embed_query(expanded_query)

    vector_query = VectorizedQuery(
        vector=query_vector,
        k_nearest_neighbors=max(top_k * 4, 20),
        fields="content_vector",
        kind="vector",
    )

    results = search_client.search(
        search_text=expanded_query,
        vector_queries=[vector_query],
        search_fields=[
            "title",
            "topic",
            "summary",
            "content",
        ],
        select=[
            "id",
            "title",
            "topic",
            "summary",
            "content",
            "page_start",
            "page_end",
            "source",
        ],
        top=candidate_count,
    )

    retrieved_items: list[dict[str, Any]] = []

    for result in results:
        retrieved_items.append(
            {
                "id": result["id"],
                "title": result["title"],
                "topic": result["topic"],
                "summary": result["summary"],
                "content": result["content"],
                "page_start": result["page_start"],
                "page_end": result["page_end"],
                "source": result["source"],
                "score": result["@search.score"],
            }
        )

    reranked = domain_rerank(
        query=query,
        items=retrieved_items,
    )

    return reranked[:top_k]
