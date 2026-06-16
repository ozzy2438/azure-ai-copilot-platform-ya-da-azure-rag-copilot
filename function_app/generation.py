import os

from openai import AzureOpenAI

from retrieval import RetrievedDocument


SYSTEM_PROMPT = """You are an Azure AI copilot for internal knowledge.
Answer only from the supplied context. If the answer is not in the context,
say you do not know. Cite source names inline when useful."""


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        api_key=_required_env("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
    )


def _format_context(documents: list[RetrievedDocument]) -> str:
    chunks = []
    for idx, document in enumerate(documents, start=1):
        source = document.source or document.id
        chunks.append(f"[{idx}] Source: {source}\n{document.content}")
    return "\n\n".join(chunks)


def generate_answer(question: str, documents: list[RetrievedDocument]) -> str:
    if not documents:
        return "I do not know. No relevant documents were found."

    response = _client().chat.completions.create(
        model=_required_env("AZURE_OPENAI_DEPLOYMENT"),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Question:\n{question}\n\n"
                    f"Context:\n{_format_context(documents)}"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=700,
    )
    content = response.choices[0].message.content
    return (content or "").strip()
