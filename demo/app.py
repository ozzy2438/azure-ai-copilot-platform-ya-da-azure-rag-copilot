import os

import requests
import streamlit as st


st.set_page_config(page_title="RegDesk Triage Copilot", page_icon=":material/search:")
st.title("RegDesk Triage Copilot")

endpoint = st.sidebar.text_input(
    "Triage endpoint",
    os.getenv("COPILOT_TRIAGE_ENDPOINT", "http://localhost:7071/api/triage"),
)
complaint = st.text_area("Complaint", height=160)

if st.button("Triage", type="primary", disabled=not complaint.strip()):
    with st.spinner("Running triage workflow"):
        response = requests.post(
            endpoint,
            json={"complaint": complaint},
            timeout=90,
        )
    if response.ok:
        payload = response.json()

        st.metric("Category", payload.get("category", "unknown"))
        st.metric(
            "Needs human review",
            str(payload.get("needs_human_review", "unknown")),
        )

        st.subheader("Handling note")
        st.write(payload.get("handling_note", ""))

        citations = payload.get("citations", [])
        if citations:
            st.subheader("Citations")
            st.dataframe(citations, use_container_width=True)

        with st.expander("Raw response"):
            st.json(payload)
    else:
        st.error(f"Request failed: {response.status_code} {response.text}")
