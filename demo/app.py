import os

import requests
import streamlit as st


st.set_page_config(page_title="Azure RAG Copilot", page_icon=":material/search:")
st.title("Azure RAG Copilot")

endpoint = st.sidebar.text_input(
    "Chat endpoint",
    os.getenv("COPILOT_CHAT_ENDPOINT", "http://localhost:7071/api/chat"),
)
question = st.text_area("Question", height=120)

if st.button("Ask", type="primary", disabled=not question.strip()):
    with st.spinner("Searching knowledge base"):
        response = requests.post(endpoint, json={"question": question}, timeout=60)
    if response.ok:
        payload = response.json()
        st.write(payload.get("answer", ""))
        citations = payload.get("citations", [])
        if citations:
            st.subheader("Citations")
            st.dataframe(citations, use_container_width=True)
    else:
        st.error(f"Request failed: {response.status_code} {response.text}")
