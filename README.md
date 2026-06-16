# Azure AI Copilot Platform

This repository contains a minimal Azure RAG copilot platform:

- Azure Functions HTTP endpoints for health and chat
- Azure AI Search retrieval over indexed knowledge chunks
- Azure OpenAI answer generation with citations
- Local document ingestion into Azure AI Search
- A lightweight golden-set evaluator
- A Streamlit demo client

## Layout

- `function_app/`: Azure Functions app and copilot runtime
- `ingestion/`: local document chunking and indexing
- `eval/`: golden-set regression checks
- `demo/`: Streamlit client for manual testing
- `infra/`: Azure CLI setup helper

## Configuration

Create local environment values outside git, for example in
`function_app/local.settings.json` or `.env`:

```bash
AZURE_SEARCH_ENDPOINT=https://<search-name>.search.windows.net
AZURE_SEARCH_INDEX=rag-copilot
AZURE_SEARCH_KEY=<optional-search-key>
AZURE_OPENAI_ENDPOINT=https://<openai-name>.openai.azure.com
AZURE_OPENAI_API_KEY=<openai-key>
AZURE_OPENAI_DEPLOYMENT=<chat-deployment-name>
```

If `AZURE_SEARCH_KEY` is not set, the app uses `DefaultAzureCredential`.

## Run Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r function_app/requirements.txt
python ingestion/chunk_and_index.py
func start --script-root function_app
```

In another shell:

```bash
pip install -r demo/requirements.txt
streamlit run demo/app.py
```

Run the golden-set check against the local function app:

```bash
python eval/run_eval.py
```
