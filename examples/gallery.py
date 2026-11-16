"""Streamlit-only previews and delivery for the small consumer examples."""

import base64
import hashlib
import json

import numpy as np
import plotly.graph_objects as go
import soundfile as sf
import streamlit as st
from numpy.typing import NDArray
from PIL import Image
from streamlit.components.v2 import component as component_v2

from igomgo_nodes.core import (
    ExecutionError,
    Executor,
    Graph,
    NodeRegistry,
    RunResult,
    dumps_graph,
    loads_graph,
)
from igomgo_nodes.storage import BrowserFileStore
from igomgo_nodes.ui import EditorAdapter, render_editor

from . import audio_poc, electronics_poc, image_poc
from .editor_demo import demo_graph, demo_registry

BROWSER_STORE = BrowserFileStore()

_FRAME_PLAYER = component_v2(
    "igomgo_image_feedback_player",
    html="""
        <div>
          <img id="frame" width="320" alt="Feedback iteration image">
          <p id="status" role="status">Loading feedback frames...</p>
          <button id="previous" type="button" disabled>Previous</button>
          <button id="play" type="button" disabled>Play</button>
          <button id="next" type="button" disabled>Next</button>
          <label>Playback speed (frames per second)
            <input id="fps" type="number" min="1" max="60" step="1" value="32">
          </label>
          <p><label>Choose iteration
            <input id="position" type="range" min="0" value="0" disabled>
          </label></p>
        </div>
    """,
    js="""
        const players = new WeakMap();
        export default function({data, parentElement}) {
          const previousPlayer = players.get(parentElement);
          if (previousPlayer) previousPlayer();
          const image = parentElement.querySelector("#frame");
          const status = parentElement.querySelector("#status");
          const previous = parentElement.querySelector("#previous");
          const next = parentElement.querySelector("#next");
          const play = parentElement.querySelector("#play");
          const fps = parentElement.querySelector("#fps");
          const position = parentElement.querySelector("#position");
          const frames = data.frames;
          previous.disabled = next.disabled = play.disabled = position.disabled = true;
          status.textContent = "Loading feedback frames...";
          let index = -1;
          let timer = null;
          let active = true;
          let started = null;
          let startIndex = 0;

          function show(i) {
            const target = Math.max(0, Math.min(i, frames.length - 1));
            if (target === index) return;
            index = target;
            image.src = frames[index].src;
            image.alt = `Feedback iteration ${frames[index].iteration}`;
            status.textContent =
              `Iteration ${frames[index].iteration} (${index + 1}/${frames.length})`;
            position.value = String(index);
          }
          function stop() {
            if (timer !== null) cancelAnimationFrame(timer);
            timer = null;
            play.textContent = "Play";
          }
          function tick(now) {
            if (!fps.checkValidity()) { stop(); fps.reportValidity(); return; }
            if (started === null) started = now;
            const nextIndex = startIndex + Math.floor((now - started) * fps.valueAsNumber / 1000);
            show(nextIndex);
            if (nextIndex >= frames.length) { stop(); return; }
            timer = requestAnimationFrame(tick);
          }
          previous.onclick = () => { stop(); show(index - 1); };
          next.onclick = () => { stop(); show(index + 1); };
          position.oninput = () => { stop(); show(Number(position.value)); };
          fps.onchange = () => { if (timer !== null) stop(); };
          play.onclick = () => {
            if (timer !== null) { stop(); return; }
            if (!fps.checkValidity()) { fps.reportValidity(); return; }
            if (index === frames.length - 1) show(0);
            startIndex = index;
            started = null;
            play.textContent = "Pause";
            timer = requestAnimationFrame(tick);
          };
          position.max = String(frames.length - 1);
          const images = frames.map(() => new Image());
          const loaded = images.map((preload, i) => new Promise((resolve, reject) => {
            preload.onload = resolve;
            preload.onerror = reject;
            preload.src = frames[i].src;
          }));
          Promise.all(loaded).then(() => {
            if (!active) return;
            previous.disabled = false;
            next.disabled = false;
            play.disabled = false;
            position.disabled = false;
            show(0);
          }).catch(() => {
            if (active) status.textContent = "Unable to load feedback frames.";
          });
          const dispose = () => { active = false; stop(); };
          players.set(parentElement, dispose);
          return () => {
            if (players.get(parentElement) === dispose) {
              dispose();
              players.delete(parentElement);
            }
          };
        }
    """,
)


def example_graph(name: str) -> tuple[Graph, NodeRegistry]:
    if name == "Logic":
        return demo_graph(), demo_registry()
    if name == "Audio":
        return audio_poc.demo()
    if name == "Image":
        return image_poc.demo()
    if name == "Image feedback":
        return image_poc.feedback_demo()
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
def feedback_image_input(data: bytes) -> NDArray[np.uint8]:
    return image_poc.feedback_image(data)


@st.cache_data(max_entries=4, show_spinner=False)
def run_example(name: str, document: str, data: bytes, feedback: tuple[str, ...]) -> RunResult:
    _, registry = example_graph(name)
    graph = loads_graph(document, registry)
    inputs: dict[str, dict[str, object]] = {}
    if name in ("Audio", "Image", "Image feedback"):
        types = {node.node_id: node.type_id for node in graph.nodes}
        domain = "audio" if name == "Audio" else "image"
        if types.get("input") != f"{domain}.input" or types.get("output") != f"{domain}.output":
            raise ValueError(
                "Keep the demo's original input and output nodes to preview/export media"
            )
        if name == "Audio":
            payload = audio_input(data)
        elif name == "Image feedback":
            payload = feedback_image_input(data)
        else:
            payload = image_input(data)
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
        st.plotly_chart(
            waveform(audio),
            key="input_waveform",
            width="stretch",
            alt="Input audio waveform by channel",
        )
        st.audio(audio_poc.encode_wav(audio), format="audio/wav", alt="Input audio playback")
        st.caption(
            "WAV: up to 5 seconds, mono/stereo, 8-48 kHz. "
            "Waveforms show at most 2,000 points/channel."
        )
    elif name in ("Image", "Image feedback"):
        st.subheader("Input image")
        st.image(
            feedback_image_input(data) if name == "Image feedback" else image_input(data),
            caption="Decoded RGB input",
            width=360,
            alt="Input image before processing",
        )
        if name == "Image feedback":
            st.caption("Input is reduced to at most 64 × 64 pixels for feedback preview.")
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
        st.plotly_chart(
            waveform(value),
            key="output_waveform",
            width="stretch",
            alt="Processed audio waveform by channel",
        )
        if np.max(np.abs(value.samples)) > 1:
            st.warning(
                "Output exceeds full scale. Playback/export clips to [-1, 1]; reduce gain/feedback."
            )
        encoded = audio_poc.encode_wav(value)
        st.audio(encoded, format="audio/wav", alt="Processed audio playback")
        st.download_button("Download output WAV", encoded, "igomgo-output.wav", mime="audio/wav")
    elif name in ("Image", "Image feedback"):
        pixels = result.outputs.get("output", {}).get("data")
        if pixels is None and result.timed_out:
            st.warning("No final image was completed.")
        elif not isinstance(pixels, np.ndarray):
            raise ValueError("The output node did not produce an image")
        else:
            st.subheader("Final image")
            st.image(
                pixels,
                caption="Final chain output",
                width=360,
                alt="Final image after processing",
            )
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
        if name == "Image feedback":
            frames: list[dict[str, object]] = []
            for snapshot in result.snapshots:
                if "blur" not in snapshot.outputs:
                    continue
                pixels = snapshot.outputs["blur"].get("data")
                if not isinstance(pixels, np.ndarray):
                    raise ValueError("The feedback blur did not produce an image")
                encoded = base64.b64encode(image_poc.encode_png(pixels)).decode("ascii")
                frames.append(
                    {"iteration": snapshot.iteration, "src": f"data:image/png;base64,{encoded}"}
                )
            if frames:
                _FRAME_PLAYER(data={"frames": frames}, key="image_feedback_player")
            else:
                st.info("No feedback blur frames were captured in this run.")
        st.dataframe(
            [
                {"component": ", ".join(snapshot.component), "iteration": snapshot.iteration}
                for snapshot in result.snapshots
            ],
            hide_index=True,
        )


def render_gallery() -> None:
    name = st.sidebar.selectbox(
        "Example", ("Logic", "Audio", "Image", "Image feedback", "Electronics")
    )
    editor_key = "editor" if name == "Logic" else f"editor_{name.lower().replace(' ', '_')}"
    if editor_key not in st.session_state:
        graph, registry = example_graph(name)
        editor = EditorAdapter(graph, registry)
        if name == "Image feedback":
            editor.set_feedback_edges(frozenset({image_poc.FEEDBACK_EDGE_ID}))
        st.session_state[editor_key] = editor
    editor: EditorAdapter = st.session_state[editor_key]
    st.sidebar.subheader("Graph file")
    try:
        graph_file = BROWSER_STORE.serialize(editor.graph, editor.feedback_edge_ids)
    except (ValueError, KeyError) as error:
        graph_file = None
        st.sidebar.error(f"Cannot save this graph: {error}")
    if graph_file is not None:
        st.sidebar.download_button(
            "Download graph",
            data=graph_file,
            file_name=f"{name.lower()}-graph.igomgo.json",
            mime="application/json",
            key=f"{editor_key}_graph_download",
        )
    uploaded_graph = st.sidebar.file_uploader(
        "Load graph",
        type=["json"],
        key=f"{editor_key}_graph_upload",
    )
    loaded_hash_key = f"{editor_key}_loaded_graph_hash"
    if uploaded_graph is None:
        st.session_state.pop(loaded_hash_key, None)
    else:
        uploaded_bytes = uploaded_graph.getvalue()
        uploaded_hash = hashlib.sha256(uploaded_bytes).hexdigest()
        if st.session_state.get(loaded_hash_key) != uploaded_hash:
            try:
                document = BROWSER_STORE.deserialize(uploaded_bytes, editor.registry)
                editor.replace_graph(document.graph, frozenset(document.feedback_edge_ids))
                st.session_state[loaded_hash_key] = uploaded_hash
                st.session_state.pop(f"{editor_key}_last_run", None)
                st.sidebar.success("Graph loaded.")
            except (ValueError, KeyError, OSError) as error:
                st.sidebar.error(f"Graph not loaded: {error}")
    data = b""
    if name in ("Audio", "Image", "Image feedback"):
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
            else image_poc.feedback_sample_png()
            if name == "Image feedback"
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
