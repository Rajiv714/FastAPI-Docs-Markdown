"""Streamlit UI: FastAPI OpenAPI -> Markdown converter.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from openapi_md import endpoint_rows, openapi_to_markdown, spec_stats, validate_spec
from sources import SpecFetchError, docs_to_openapi_url, fetch_openapi

st.set_page_config(page_title="OpenAPI → Markdown", page_icon="📝", layout="wide")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2rem;}
      [data-testid="stSidebar"][aria-expanded="true"] {
          width: 440px !important; min-width: 440px !important; max-width: 440px !important;
      }
      [data-testid="stSidebar"][aria-expanded="true"] > div:first-child {width: 440px !important;}
      div[data-testid="stMetric"] {
          background: rgba(128,128,128,0.08); padding: 12px 16px; border-radius: 10px;
      }
    </style>
    """,
    unsafe_allow_html=True,
)


def set_spec(spec: object, source: str) -> bool:
    error = validate_spec(spec)
    if error:
        st.sidebar.error(error)
        return False
    st.session_state["spec"] = spec
    st.session_state["source"] = source
    return True


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.header("📥 Load API spec")
    mode = st.radio("Source", ["FastAPI /docs URL", "Upload JSON"], horizontal=True,
                    label_visibility="collapsed")

    if mode == "FastAPI /docs URL":
        url = st.text_input("Docs URL", placeholder="https://your-api.com/docs",
                            help="The /docs link is converted to /openapi.json automatically.")
        if url.strip():
            try:
                st.caption(f"Will fetch: `{docs_to_openapi_url(url)}`")
            except ValueError as e:
                st.caption(f"⚠️ {e}")

        if st.button("Fetch & convert", type="primary", width="stretch"):
            try:
                with st.spinner("Fetching spec…"):
                    spec, resolved = fetch_openapi(url)
                if set_spec(spec, resolved):
                    st.success("Spec loaded.")
            except (ValueError, SpecFetchError) as e:
                st.error(str(e))

    else:
        file = st.file_uploader("openapi.json", type=["json"])
        if file is not None and st.session_state.get("loaded_file_id") != file.file_id:
            try:
                if set_spec(json.loads(file.getvalue().decode("utf-8")), file.name):
                    st.session_state["loaded_file_id"] = file.file_id
                    st.success("Spec loaded.")
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                st.error(f"Invalid JSON file: {e}")

    if "spec" in st.session_state:
        st.divider()
        if st.button("🗑️ Clear", width="stretch"):
            st.session_state.pop("spec", None)
            st.session_state.pop("source", None)
            st.rerun()

# --------------------------------------------------------------------------- #
# Main area
# --------------------------------------------------------------------------- #
st.title("📝 OpenAPI → Markdown")
st.caption("Turn a FastAPI `openapi.json` into clean, shareable documentation.")

spec = st.session_state.get("spec")
if not spec:
    st.info("👈 Paste your FastAPI `/docs` URL or upload an `openapi.json` file to get started.")
    st.markdown(
        """
        **What you get**
        - Endpoints grouped by tag, with parameters, request bodies and responses
        - Auto-generated example JSON payloads
        - Schema tables with types, constraints, enums, defaults and nested fields
        - Authentication schemes, webhooks and deprecation notices
        """
    )
    st.stop()

markdown_output = openapi_to_markdown(spec)
stats = spec_stats(spec)
st.caption(f"Source: `{st.session_state.get('source', '-')}`")

c1, c2, c3, c4 = st.columns(4)
c1.metric("API", stats["title"])
c2.metric("Version", stats["version"])
c3.metric("Endpoints", stats["endpoints"])
c4.metric("Schemas", stats["schemas"])

d1, d2, _ = st.columns([1, 1, 2])
d1.download_button("📥 Download Markdown", data=markdown_output, file_name="API_DOCUMENTATION.md",
                   mime="text/markdown", type="primary", width="stretch")
d2.download_button("📄 Download spec (JSON)", data=json.dumps(spec, indent=2),
                   file_name="openapi.json", mime="application/json", width="stretch")

tab_preview, tab_source, tab_endpoints = st.tabs(["📖 Preview", "🧾 Markdown source", "🔌 Endpoints"])
with tab_preview:
    with st.container(border=True):
        st.markdown(markdown_output)
with tab_source:
    st.code(markdown_output, language="markdown", line_numbers=True)
with tab_endpoints:
    st.dataframe(pd.DataFrame(endpoint_rows(spec)), width="stretch", hide_index=True)
