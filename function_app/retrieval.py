import os
from dataclasses import dataclass

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient


@dataclass(frozen=True)
class RetrievedDocument:
    id: str
    content: str
    source: str
    score: float


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _search_client() -> SearchClient:
    endpoint = _required_env("AZURE_SEARCH_ENDPOINT")
    index_name = os.getenv("AZURE_SEARCH_INDEX_NAME") or _required_env(
        "AZURE_SEARCH_INDEX"
    )
    key = os.getenv("AZURE_SEARCH_KEY") or os.getenv("AZURE_SEARCH_API_KEY")
    credential = AzureKeyCredential(key) if key else DefaultAzureCredential()
    return SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)


def retrieve_documents(query: str, top_k: int = 5) -> list[RetrievedDocument]:
    client = _search_client()
    results = client.search(
        search_text=query,
        top=top_k,
        select=["id", "content", "source"],
    )

    documents: list[RetrievedDocument] = []
    for result in results:
        documents.append(
            RetrievedDocument(
                id=str(result.get("id", "")),
                content=str(result.get("content", "")),
                source=str(result.get("source", "")),
                score=float(result.get("@search.score", 0.0)),
            )
        )
    return documents
