"""Streamlit-only previews and delivery for the small consumer examples."""

import hashlib
import json

import numpy as np
import plotly.graph_objects as go
import soundfile as sf
import streamlit as st
from numpy.typing import NDArray
from PIL import Image

from igomgo_nodes.core import (
    ExecutionError,
    Executor,
    Graph,
    NodeRegistry,
    RunResult,
    dumps_graph,
    loads_graph,
)
from igomgo_nodes.ui import EditorAdapter, render_editor

from . import audio_poc, electronics_poc, image_poc
from .editor_demo import demo_graph, demo_registry


def example_graph(name: str) -> tuple[Graph, NodeRegistry]:
    if name == "Logic":
        return demo_graph(), demo_registry()
    if name == "Audio":
        return audio_poc.demo()
    if name == "Image":
        return image_poc.demo()
    if name == "Electronics":
        return electronics_poc.demo()
    raise ValueError(f"Unknown example: {name}")


@st.cache_data(max_entries=4, show_spinner=False)
def audio_input(data: bytes) -> audio_poc.AudioBuffer:
    return audio_poc.decode_wav(data)


@st.cache_data(max_entries=4, show_spinner=False)
def image_input(data: bytes) -> NDArray[np.uint8]:
    return image_poc.decode_image(data)


@st.cache_data(max_entries=4, show_spinner=False)
def run_example(name: str, document: str, data: bytes, feedback: tuple[str, ...]) -> RunResult:
    _, registry = example_graph(name)
    graph = loads_graph(document, registry)
    inputs: dict[str, dict[str, object]] = {}
    if name in ("Audio", "Image"):
        types = {node.node_id: node.type_id for node in graph.nodes}
        domain = name.lower()
        if types.get("input") != f"{domain}.input" or types.get("output") != f"{domain}.output":
            raise ValueError(
                "Keep the demo's original input and output nodes to preview/export media"
            )
        payload = audio_input(data) if name == "Audio" else image_input(data)
        inputs["input"] = {"data": payload}
    return Executor().run(graph, registry, inputs=inputs, feedback_edge_ids=frozenset(feedback))


def waveform(audio: audio_poc.AudioBuffer) -> go.Figure:
    stride = max(1, (len(audio.samples) + 1999) // 2000)
    indexes = np.arange(0, len(audio.samples), stride)
    figure = go.Figure()
    for channel in range(audio.samples.shape[1]):
        figure.add_scatter(
            x=indexes / audio.sample_rate,
            y=audio.samples[indexes, channel],
            mode="lines",
            name=f"Channel {channel + 1}",
        )
    figure.update_layout(
        xaxis_title="Seconds",
        yaxis_title="Amplitude",
        height=230,
        margin={"l": 10, "r": 10, "t": 10, "b": 10},
    )
    return figure


def _show_input(name: str, data: bytes) -> None:
    if name == "Audio":
        st.subheader("Input waveform")
        audio = audio_input(data)
        st.plotly_chart(waveform(audio), key="input_waveform", use_container_width=True)
        st.audio(audio_poc.encode_wav(audio), format="audio/wav")
        st.caption(
            "WAV: up to 5 seconds, mono/stereo, 8-48 kHz. "
            "Waveforms show at most 2,000 points/channel."
        )
    elif name == "Image":
        st.subheader("Input image")
        st.image(image_input(data), caption="Decoded RGB input", width=360)
        st.caption("PNG/JPEG: up to 262,144 pixels and 5 MiB. Effects use RGB.")
    elif name == "Electronics":
        st.info(
            "Symbolic labels only. No circuit simulation, current calculation "
            "or real-world design advice."
        )


def _show_result(name: str, result: RunResult) -> None:
    if result.timed_out:
        st.warning("Run stopped at timeout. Only completed passes are available.")
    else:
        st.success("Run complete.")
    if name == "Audio":
        value = result.outputs.get("output", {}).get("data")
        if value is None and result.timed_out:
            st.warning("No final WAV was completed.")
            return
        if not isinstance(value, audio_poc.AudioBuffer):
            raise ValueError("The output node did not produce audio")
        st.subheader("Output waveform")
        st.plotly_chart(waveform(value), key="output_waveform", use_container_width=True)
        if np.max(np.abs(value.samples)) > 1:
            st.warning(
                "Output exceeds full scale. Playback/export clips to [-1, 1]; reduce gain/feedback."
            )
        encoded = audio_poc.encode_wav(value)
        st.audio(encoded, format="audio/wav")
        st.download_button("Download output WAV", encoded, "igomgo-output.wav", mime="audio/wav")
    elif name == "Image":
        pixels = result.outputs.get("output", {}).get("data")
        if pixels is None and result.timed_out:
            st.warning("No final image was completed.")
            return
        if not isinstance(pixels, np.ndarray):
            raise ValueError("The output node did not produce an image")
        st.subheader("Final image")
        st.image(pixels, caption="Final chain output", width=360)
        st.download_button(
            "Download output PNG",
            image_poc.encode_png(pixels),
            "igomgo-output.png",
            mime="image/png",
        )
    elif name == "Electronics":
        st.subheader("Symbolic output")
        value = result.outputs.get("output", {}).get("data")
        if value is not None:
            st.code(str(value), language=None)
        elif not result.timed_out:
            raise ValueError("The symbolic output node is missing")
    else:
        st.subheader("Logic values")
        st.json(result.outputs)
    if result.snapshots:
        st.subheader("Captured feedback passes")
        st.caption("Review of completed runs, not manual execution stepping.")
        st.dataframe(
            [
                {"component": ", ".join(snapshot.component), "iteration": snapshot.iteration}
                for snapshot in result.snapshots
            ],
            hide_index=True,
        )


def render_gallery() -> None:
    name = st.sidebar.selectbox("Example", ("Logic", "Audio", "Image", "Electronics"))
    editor_key = "editor" if name == "Logic" else f"editor_{name.lower()}"
    if editor_key not in st.session_state:
        graph, registry = example_graph(name)
        st.session_state[editor_key] = EditorAdapter(graph, registry)
    editor: EditorAdapter = st.session_state[editor_key]
    data = b""
    if name in ("Audio", "Image"):
        upload = st.sidebar.file_uploader(
            "WAV input" if name == "Audio" else "Image input",
            type=["wav"] if name == "Audio" else ["png", "jpg", "jpeg"],
            key=f"{name}_upload",
        )
        data = (
            upload.getvalue()
            if upload is not None
            else audio_poc.sample_wav()
            if name == "Audio"
            else image_poc.sample_png()
        )
        if upload is None:
            st.caption("Using the generated sample. Upload a file to replace it.")
    render_editor(editor, key=editor_key)
    try:
        _show_input(name, data)
        document = dumps_graph(editor.graph)
        feedback = tuple(sorted(editor.feedback_edge_ids))
        fingerprint = hashlib.sha256(
            document.encode("utf-8") + json.dumps(feedback).encode("utf-8") + data
        ).hexdigest()
        request_key = f"{editor_key}_last_run"
        if st.button("Run graph", key=f"{editor_key}_run"):
            st.session_state[request_key] = fingerprint
        if request_key not in st.session_state:
            return
        if st.session_state[request_key] != fingerprint:
            st.info("Graph or input changed. Run again to refresh the output.")
            return
        with st.spinner("Processing the consumer graph..."):
            result = run_example(name, document, data, feedback)
        _show_result(name, result)
    except (
        ValueError,
        KeyError,
        OSError,
        sf.LibsndfileError,
        Image.DecompressionBombError,
        ExecutionError,
    ) as error:
        st.session_state.pop(f"{editor_key}_last_run", None)
        st.error(str(error))
