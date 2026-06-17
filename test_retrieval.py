from function_app.retrieval import retrieve


query = (
    "The customer says they complained three weeks ago "
    "but the firm has not responded."
)

results = retrieve(
    query=query,
    top_k=5,
)

print(f"QUERY:\n{query}\n")

for index, item in enumerate(
    results,
    start=1,
):
    print("=" * 80)
    print(f"RESULT {index}")
    print(f"ID: {item['id']}")
    print(f"TITLE: {item['title']}")
    print(f"TOPIC: {item['topic']}")
    print(
        f"PAGES: "
        f"{item['page_start']}–{item['page_end']}"
    )
    print(f"AZURE SCORE: {item['score']}")
    print(f"DOMAIN BOOST: {item.get('domain_boost', 0.0)}")
    print(f"FINAL SCORE: {item.get('final_score', item['score'])}")
    print("\nSUMMARY:")
    print(item["summary"])
    print()
