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

with st.container(horizontal=True):
    with st.popover("About", icon=":material/info:"):
        st.markdown(
            "igomgoNodes is a framework for building node-based editors. "
            "This gallery demonstrates logic, audio, image, and electronics examples."
        )
        st.markdown(
            "**Data:** graphs can be downloaded and uploaded as JSON. "
            "Session data is temporary, and media and results may be cached in server memory. "
            "Avoid uploading sensitive data."
        )
        st.markdown(f"**Version:** {igomgo_nodes.__version__} · [iGOMGO.com](https://igomgo.com)")
    with st.popover("Help", icon=":material/help:"):
        st.markdown(
            "Choose an example, add nodes from the palette, and drag nodes or use the "
            "inspector to move them. Connect single-port nodes on the canvas or use "
            "Connections for named ports."
        )
        st.markdown(
            "Enable graph feedback in the policy before creating a cycle, then select "
            "the feedback boundaries. Validate the graph and select **Run graph** to "
            "view the output."
        )
        st.markdown(
            "**Focus mode** separates Setup, Draft, Node, and Graph into tabs. "
            "Download your graph before ending the session to keep it."
        )
    with st.popover("Feedback", icon=":material/feedback:"):
        st.markdown("Share a suggestion or report an issue using the hosted form.")
        st.link_button(
            "Open feedback form",
            "https://docs.google.com/forms/d/e/"
            "1FAIpQLSf6Ixq_xBFYUaL8hd5lduzqHdtV32SD3RVRPb3vqGsHkwNxqg/"
            "viewform?usp=publish-editor",
            width="stretch",
        )

render_gallery(focus=focus)
