import pickle
from io import BytesIO

import numpy as np
import plotly.graph_objects as go
import pytest
import soundfile as sf
from PIL import Image
from pydantic import ValidationError

from examples import audio_poc, electronics_poc, image_poc
from examples.editor_demo import demo_graph, demo_registry
from examples.gallery import waveform
from igomgo_nodes.core import Executor, GraphPolicy, LoopPolicy
from igomgo_nodes.core.executor import MAX_CAPTURE_BYTES


def test_audio_chain_runs_and_exports_matching_wav_shape() -> None:
    audio = audio_poc.decode_wav(audio_poc.sample_wav())
    graph, registry = audio_poc.demo()
    result = Executor().run(graph, registry, inputs={"input": {"data": audio}})
    assert not result.timed_out
    output = result.outputs["output"]["data"]
    assert isinstance(output, audio_poc.AudioBuffer)
    assert output.samples.shape == audio.samples.shape == (16000, 1)
    assert output.samples.dtype == np.float32
    assert output.sample_rate == audio.sample_rate
    assert not np.array_equal(output.samples, audio.samples)
    exported = audio_poc.decode_wav(audio_poc.encode_wav(output))
    assert exported.samples.shape == audio.samples.shape


@pytest.mark.parametrize(("delay", "expected"), [(1, [1, 2.5, 4.25, 6.125]), (2, [1, 2, 3.5, 5])])
def test_audio_feedback_adds_to_the_next_sample_without_replacing_it(
    delay: int, expected: list[float]
) -> None:
    samples = np.array([[1, 0], [2, 0], [3, 0], [4, 0]], dtype=np.float32)
    audio = audio_poc.AudioBuffer(samples, 16000)
    output = audio_poc.Delay("delay", {"delay_samples": delay, "feedback": 0.5}).process(
        {"data": audio}
    )["data"]
    assert isinstance(output, audio_poc.AudioBuffer)
    np.testing.assert_allclose(output.samples[:, 0], expected)
    np.testing.assert_array_equal(output.samples[:, 1], 0)
    np.testing.assert_array_equal(audio.samples[:, 0], [1, 2, 3, 4])


@pytest.mark.parametrize(
    ("seconds", "channels", "sample_rate"),
    [(3, 1, 8000), (5, 2, 48000), (0.1, 2, 8000)],
)
def test_direct_audio_feedback_adds_delayed_decaying_echoes_within_input_length(
    seconds: float, channels: int, sample_rate: int
) -> None:
    samples = np.zeros((int(seconds * sample_rate), channels), dtype=np.float32)
    samples[0] = np.arange(1, channels + 1, dtype=np.float32) * 0.25
    audio = audio_poc.AudioBuffer(samples, sample_rate)
    graph, registry = audio_poc.feedback_demo()
    result = Executor().run(
        graph,
        registry,
        inputs={"input": {"data": audio}},
        feedback_edge_ids=frozenset({audio_poc.FEEDBACK_EDGE_ID}),
    )
    assert not result.timed_out
    output = result.outputs["output"]["data"]
    assert isinstance(output, audio_poc.AudioBuffer)
    assert output.samples.shape == samples.shape
    expected = samples.copy()
    delay = round(sample_rate * 0.3)
    for iteration in range(1, 8):
        if iteration * delay < len(samples):
            expected[iteration * delay] = samples[0] * 0.5**iteration
    np.testing.assert_allclose(output.samples, expected)
    np.testing.assert_array_equal(samples[1:], 0)
    assert len(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)) < MAX_CAPTURE_BYTES


def test_direct_audio_feedback_rejects_mismatched_buffers() -> None:
    echo = audio_poc.FeedbackEcho("echo")
    original = audio_poc.AudioBuffer(np.zeros((10, 1), dtype=np.float32), 8000)
    feedback = audio_poc.AudioBuffer(np.zeros((10, 2), dtype=np.float32), 8000)
    with pytest.raises(ValueError, match="match the original"):
        echo.combine_loopback("data", [original], feedback)


def test_direct_audio_feedback_uses_configured_delay_and_gain() -> None:
    samples = np.zeros((5000, 1), dtype=np.float32)
    samples[0, 0] = 0.4
    audio = audio_poc.AudioBuffer(samples, 8000)
    graph, registry = audio_poc.feedback_demo()
    echo = graph.nodes[1].model_copy(update={"params": {"delay_ms": 100, "feedback": 0.25}})
    graph = graph.model_copy(update={"nodes": (graph.nodes[0], echo, graph.nodes[2])})
    result = Executor().run(
        graph,
        registry,
        inputs={"input": {"data": audio}},
        feedback_edge_ids=frozenset({audio_poc.FEEDBACK_EDGE_ID}),
    )
    output = result.outputs["output"]["data"]
    assert isinstance(output, audio_poc.AudioBuffer)
    np.testing.assert_allclose(output.samples[::800, 0], [0.4 * 0.25**i for i in range(7)])


def test_lowpass_attenuates_high_frequency_and_rejects_invalid_cutoff() -> None:
    time = np.arange(16000) / 16000
    samples = np.sin(2 * np.pi * 4000 * time).astype(np.float32)[:, None]
    audio = audio_poc.AudioBuffer(samples, 16000)
    output = audio_poc.LowPass("low").process({"data": audio})["data"]
    assert isinstance(output, audio_poc.AudioBuffer)
    assert np.std(output.samples[100:]) < np.std(samples[100:]) * 0.2
    with pytest.raises(ValueError, match="half the sample rate"):
        audio_poc.LowPass("low", {"cutoff_hz": 10000}).process({"data": audio})


def test_waveform_sampling_and_wav_clipping_are_bounded() -> None:
    samples = np.array([[2.0, -2.0]] * 10001, dtype=np.float32)
    audio = audio_poc.AudioBuffer(samples, 16000)
    figure = waveform(audio)
    traces = tuple(figure.select_traces())
    assert len(traces) == 2
    for trace in traces:
        assert isinstance(trace, go.Scatter)
        x = trace.x
        assert isinstance(x, (tuple, list, np.ndarray))
        assert len(x) <= 2000
    decoded = audio_poc.decode_wav(audio_poc.encode_wav(audio))
    assert np.max(decoded.samples) <= 1
    assert np.min(decoded.samples) >= -1
    assert decoded.samples[0, 0] > 0.99


def test_image_chain_runs_and_exports_rgb_grayscale_inverted_pixels() -> None:
    pixels = np.full((8, 12, 3), [20, 40, 60], dtype=np.uint8)
    graph, registry = image_poc.demo()
    result = Executor().run(graph, registry, inputs={"input": {"data": pixels}})
    assert not result.timed_out
    output = result.outputs["output"]["data"]
    assert isinstance(output, np.ndarray)
    assert output.shape == pixels.shape
    assert output.dtype == np.uint8
    expected_gray = round(0.299 * 20 + 0.587 * 40 + 0.114 * 60)
    np.testing.assert_array_equal(output, 255 - expected_gray)
    np.testing.assert_array_equal(image_poc.decode_image(image_poc.encode_png(output)), output)
    np.testing.assert_array_equal(pixels[0, 0], [20, 40, 60])


def test_image_blur_changes_impulse_without_changing_shape() -> None:
    pixels = np.zeros((9, 9, 3), dtype=np.uint8)
    pixels[4, 4] = 255
    output = image_poc.Blur("blur").process({"data": pixels})["data"]
    assert isinstance(output, np.ndarray)
    assert output.shape == pixels.shape
    assert 0 < output[4, 4, 0] < 255
    assert output[4, 3, 0] > 0


def test_image_feedback_runs_32_successive_blurs_and_exports_final_png() -> None:
    pixels = image_poc.feedback_image(image_poc.feedback_sample_png())
    assert pixels.shape == (64, 64, 3)
    graph, registry = image_poc.feedback_demo()
    result = Executor().run(
        graph,
        registry,
        inputs={"input": {"data": pixels}},
        feedback_edge_ids=frozenset({image_poc.FEEDBACK_EDGE_ID}),
    )
    assert not result.timed_out
    assert [snapshot.iteration for snapshot in result.snapshots] == list(range(1, 33))
    expected = pixels
    blur = image_poc.Blur("expected")
    for snapshot in result.snapshots:
        expected = blur.process({"data": expected})["data"]
        np.testing.assert_array_equal(snapshot.outputs["blur"]["data"], expected)
    final = result.outputs["output"]["data"]
    assert isinstance(final, np.ndarray)
    np.testing.assert_array_equal(final, expected)
    assert np.std(final) < np.std(pixels)
    np.testing.assert_array_equal(image_poc.decode_image(image_poc.encode_png(final)), final)
    assert len(pickle.dumps(result, protocol=pickle.HIGHEST_PROTOCOL)) < MAX_CAPTURE_BYTES


def test_feedback_image_limits_uploaded_dimensions_without_upscaling() -> None:
    large = image_poc.encode_png(np.zeros((40, 128, 3), dtype=np.uint8))
    small = image_poc.encode_png(np.zeros((4, 8, 3), dtype=np.uint8))
    assert image_poc.feedback_image(large).shape == (20, 64, 3)
    assert image_poc.feedback_image(small).shape == (4, 8, 3)


def test_logic_and_symbolic_consumers_build_and_run() -> None:
    result = Executor().run(demo_graph(), demo_registry())
    assert not result.timed_out
    assert result.outputs["out"] == {"value": False}
    graph, registry = electronics_poc.demo()
    result = Executor().run(graph, registry)
    assert not result.timed_out
    assert result.outputs["output"]["data"] == (
        "Supply (5 V) -> Resistor (1 kOhm) -> LED (symbol only, not simulated)"
    )


@pytest.mark.parametrize(("value", "expected"), [(9.0, 3.0), (0.0, 0.0), (16.0, 4.0), (0.01, 0.1)])
def test_square_root_feedback_runs_bounded_passes_and_returns_estimate(
    value: float, expected: float
) -> None:
    graph, registry = electronics_poc.feedback_demo()
    source = graph.nodes[0].model_copy(update={"params": {"value": value}})
    graph = graph.model_copy(update={"nodes": (source, *graph.nodes[1:])})
    result = Executor().run(
        graph, registry, feedback_edge_ids=frozenset({electronics_poc.FEEDBACK_EDGE_ID})
    )
    assert not result.timed_out
    assert [snapshot.iteration for snapshot in result.snapshots] == list(range(1, 9))
    states: list[electronics_poc.SquareRootState] = []
    for snapshot in result.snapshots:
        state = snapshot.outputs["sqrt"]["data"]
        assert isinstance(state, electronics_poc.SquareRootState)
        states.append(state)
    if value == 9:
        assert [state.estimate for state in states[:3]] == pytest.approx(
            [5.0, 3.4, 3.023529411764706]
        )
    assert result.outputs["output"]["estimate"] == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize("value", [-1, 10001, float("nan"), float("inf")])
def test_square_root_input_rejects_out_of_range_or_nonfinite_values(value: float) -> None:
    with pytest.raises(ValidationError):
        electronics_poc.NumberInput("input", {"value": value})


def test_square_root_rejects_a_zero_estimate_for_positive_input() -> None:
    state = electronics_poc.SquareRootState(9, 0)
    with pytest.raises(ValueError, match="nonnegative"):
        electronics_poc.SquareRoot("sqrt").process({"data": [state]})


def test_square_root_respects_iteration_limit_for_incomplete_estimates() -> None:
    graph, registry = electronics_poc.feedback_demo()
    graph = graph.model_copy(
        update={
            "policy": GraphPolicy(
                allow_feedback=True, loop=LoopPolicy(max_iterations=1, timeout_seconds=10)
            )
        }
    )
    result = Executor().run(
        graph, registry, feedback_edge_ids=frozenset({electronics_poc.FEEDBACK_EDGE_ID})
    )
    assert not result.timed_out
    assert len(result.snapshots) == 1
    assert result.outputs["output"]["estimate"] == 5


@pytest.mark.parametrize(
    ("sample_rate", "channels", "frames"),
    [(4000, 1, 16), (16000, 3, 16), (8000, 1, 40001), (8000, 1, 0)],
)
def test_audio_upload_resource_limits(sample_rate: int, channels: int, frames: int) -> None:
    stream = BytesIO()
    sf.write(stream, np.zeros((frames, channels), dtype=np.float32), sample_rate, format="WAV")
    with pytest.raises(ValueError):
        audio_poc.decode_wav(stream.getvalue())


def test_upload_byte_limits_are_checked_before_decoding() -> None:
    too_large = b" " * (5 * 1024 * 1024 + 1)
    for decoder in (audio_poc.decode_wav, image_poc.decode_image):
        with pytest.raises(ValueError, match="5 MiB"):
            decoder(too_large)


def test_image_pixel_limit_and_format_allowlist() -> None:
    stream = BytesIO()
    Image.new("RGB", (513, 512)).save(stream, format="PNG")
    with pytest.raises(ValueError, match="262,144 pixels"):
        image_poc.decode_image(stream.getvalue())
    stream = BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="BMP")
    with pytest.raises(ValueError, match="PNG and JPEG"):
        image_poc.decode_image(stream.getvalue())
    assert image_poc.decode_image(image_poc.sample_png()).shape == (96, 128, 3)


def test_audio_rejects_other_formats_nonfinite_samples_and_corrupt_data() -> None:
    stream = BytesIO()
    sf.write(stream, np.zeros(16, dtype=np.float32), 16000, format="FLAC")
    with pytest.raises(ValueError, match="Only WAV"):
        audio_poc.decode_wav(stream.getvalue())
    stream = BytesIO()
    sf.write(stream, np.array([np.nan], dtype=np.float32), 16000, format="WAV", subtype="FLOAT")
    with pytest.raises(ValueError, match="non-finite"):
        audio_poc.decode_wav(stream.getvalue())
    with pytest.raises(sf.LibsndfileError):
        audio_poc.decode_wav(b"not a WAV")
    with pytest.raises(OSError):
        image_poc.decode_image(b"not an image")
