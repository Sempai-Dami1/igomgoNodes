"""Streamlit entry point for the small consumer-driven editor demo."""

import qrcode
import streamlit as st
from qrcode.exceptions import DataOverflowError

import igomgo_nodes
from examples.gallery import render_gallery

st.set_page_config(page_title="igomgoNodes", page_icon="🧩", layout="wide")
with st.container(horizontal=True, vertical_alignment="center"):
    with st.container(width="content"):
        st.title("🧩 igomgoNodes")
    with st.container(width="content"):
        url = st.context.url
        if url is None:
            st.caption("App URL unavailable")
        else:
            try:
                qr = qrcode.make(url)
                st.image(qr.get_image(), width=128, alt="QR code for the current app address")
            except (DataOverflowError, ValueError) as error:
                st.warning(f"Cannot generate a QR code for the app URL: {error}")
    with st.container(width="content"):
        focus = st.toggle("Focus mode", key="focus_mode")
st.caption(f"v{igomgo_nodes.__version__} · drag nodes, tap to select, or use inspector movement")

render_gallery(focus=focus)
