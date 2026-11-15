"""Bounded WAV consumer: gain, low-pass and additive delayed sample feedback."""

from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO

import numpy as np
import soundfile as sf
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from scipy.signal import butter, sosfilt

from igomgo_nodes.core import BaseNode, Graph, NodeRegistry, NodeSpec, PortSpec

from .common import chain

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SECONDS = 5


@dataclass(frozen=True)
class AudioBuffer:
    samples: NDArray[np.float32]
    sample_rate: int


def decode_wav(data: bytes) -> AudioBuffer:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("WAV upload exceeds 5 MiB")
    info = sf.info(BytesIO(data))
    if info.format not in ("WAV", "WAVEX"):
        raise ValueError("Only WAV audio is supported")
    if not 8000 <= info.samplerate <= 48000 or info.channels not in (1, 2):
        raise ValueError("Use mono/stereo WAV at 8,000 to 48,000 Hz")
    if info.frames < 1 or info.frames > MAX_SECONDS * info.samplerate:
        raise ValueError("Use a nonempty WAV no longer than 5 seconds")
    samples, sample_rate = sf.read(BytesIO(data), dtype="float32", always_2d=True)
    if not np.isfinite(samples).all():
        raise ValueError("WAV contains non-finite samples")
    return AudioBuffer(np.asarray(samples, dtype=np.float32), sample_rate)


def encode_wav(audio: AudioBuffer) -> bytes:
    stream = BytesIO()
    sf.write(
        stream, np.clip(audio.samples, -1, 1), audio.sample_rate, format="WAV", subtype="PCM_16"
    )
    return stream.getvalue()


def sample_wav() -> bytes:
    sample_rate = 16000
    time = np.arange(sample_rate, dtype=np.float32) / sample_rate
    samples = 0.25 * np.sin(2 * np.pi * 440 * time) + 0.1 * np.sin(2 * np.pi * 4000 * time)
    return encode_wav(AudioBuffer(samples[:, None].astype(np.float32), sample_rate))


def _audio(inputs: Mapping[str, object]) -> AudioBuffer:
    value = inputs["data"]
    if not isinstance(value, AudioBuffer):
        raise ValueError("Connect an audio buffer to the data input")
    return value


def _spec(name: str, title: str, *, optional_input: bool = False) -> NodeSpec:
    return NodeSpec(
        type_id=f"audio.{name}",
        title=title,
        category="Audio",
        inputs=(PortSpec(name="data", dtype="audio", min_connections=0 if optional_input else 1),),
        outputs=(PortSpec(name="data", dtype="audio"),),
    )


class AudioInput(BaseNode):
    spec = _spec("input", "WAV input", optional_input=True)

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": _audio(inputs)}


class GainParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    gain: float = Field(default=0.8, ge=0, le=2, allow_inf_nan=False)


class Gain(BaseNode):
    spec = _spec("gain", "Gain")
    parameter_model = GainParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        audio = _audio(inputs)
        params = GainParams.model_validate(self.params)
        return {"data": AudioBuffer(audio.samples * params.gain, audio.sample_rate)}


class LowPassParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cutoff_hz: float = Field(default=1000, ge=20, le=20000, allow_inf_nan=False)


class LowPass(BaseNode):
    spec = _spec("lowpass", "Low-pass")
    parameter_model = LowPassParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        audio = _audio(inputs)
        params = LowPassParams.model_validate(self.params)
        if params.cutoff_hz >= audio.sample_rate / 2:
            raise ValueError("Low-pass cutoff must be below half the sample rate")
        coefficients = butter(2, params.cutoff_hz, fs=audio.sample_rate, output="sos")
        filtered = np.asarray(sosfilt(coefficients, audio.samples, axis=0), dtype=np.float32)
        return {"data": AudioBuffer(filtered, audio.sample_rate)}


class DelayParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    delay_samples: int = Field(default=1, ge=1, le=12000)
    feedback: float = Field(default=0.25, ge=0, le=0.9, allow_inf_nan=False)


class Delay(BaseNode):
    spec = _spec("delay", "Additive feedback delay")
    parameter_model = DelayParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        audio = _audio(inputs)
        params = DelayParams.model_validate(self.params)
        samples = audio.samples.copy()
        for index in range(params.delay_samples, len(samples)):
            samples[index] += params.feedback * samples[index - params.delay_samples]
        return {"data": AudioBuffer(samples, audio.sample_rate)}


class AudioOutput(BaseNode):
    spec = _spec("output", "WAV output")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": _audio(inputs)}


def demo() -> tuple[Graph, NodeRegistry]:
    return chain((AudioInput, Gain, LowPass, Delay, AudioOutput))
