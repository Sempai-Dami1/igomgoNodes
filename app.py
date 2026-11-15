"""Streamlit entry point for the small consumer-driven editor demo."""

import streamlit as st

import igomgo_nodes
from examples.gallery import render_gallery

st.set_page_config(page_title="igomgoNodes", page_icon="🧩", layout="wide")
st.title("🧩 igomgoNodes")
st.caption(f"v{igomgo_nodes.__version__} · drag nodes, tap to select, or use inspector movement")

render_gallery()
