from function_app.generation import (
    generate_handling_note,
)
from function_app.retrieval import retrieve


complaint = (
    "The customer says they complained three weeks ago "
    "but the firm has not responded."
)

retrieved_items = retrieve(
    query=complaint,
    top_k=5,
)

result = generate_handling_note(
    complaint=complaint,
    retrieved_items=retrieved_items,
)

print("COMPLAINT:")
print(complaint)

print("\nRETRIEVED CHUNKS:")
for chunk_id in result["context_chunk_ids"]:
    print("-", chunk_id)

print("\nHANDLING NOTE:")
print(result["handling_note"])

print("\nTOKENS USED:")
print(result["tokens_used"])

print("\nMODEL:")
print(result["model"])