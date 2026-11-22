"""Small RGB image consumer; decoding and effects stay outside the framework."""

from collections.abc import Mapping
from io import BytesIO
from typing import Literal

import numpy as np
from numpy.typing import NDArray
from PIL import Image, ImageFilter, ImageOps
from pydantic import BaseModel, ConfigDict, Field, JsonValue

from igomgo_nodes.core import (
    BaseNode,
    Edge,
    Graph,
    GraphPolicy,
    LoopPolicy,
    NodeInstance,
    NodeRegistry,
    NodeSpec,
    PortSpec,
    Position,
)

from .common import chain

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 512 * 512
FEEDBACK_IMAGE_SIZE = 64
FEEDBACK_EDGE_ID = "blur-feedback"


def decode_image(data: bytes) -> NDArray[np.uint8]:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("Image upload exceeds 5 MiB")
    with Image.open(BytesIO(data)) as image:
        if image.format not in ("PNG", "JPEG"):
            raise ValueError("Only PNG and JPEG images are supported")
        if image.width * image.height > MAX_PIXELS:
            raise ValueError("Image exceeds 262,144 pixels (512 x 512 equivalent)")
        return np.asarray(ImageOps.exif_transpose(image).convert("RGB")).copy()


def encode_png(pixels: NDArray[np.uint8]) -> bytes:
    stream = BytesIO()
    Image.fromarray(pixels).save(stream, format="PNG")
    return stream.getvalue()


def sample_png() -> bytes:
    y, x = np.indices((96, 128))
    pixels = np.stack((x * 2, y * 2, (x + y) % 256), axis=-1).astype(np.uint8)
    return encode_png(pixels)


def feedback_sample_png() -> bytes:
    y, x = np.indices((FEEDBACK_IMAGE_SIZE, FEEDBACK_IMAGE_SIZE))
    checker = ((x // 8 + y // 8) % 2 * 255).astype(np.uint8)
    pixels = np.stack((checker, 255 - checker, checker), axis=-1)
    return encode_png(pixels)


def feedback_image(data: bytes) -> NDArray[np.uint8]:
    image = Image.fromarray(decode_image(data))
    image.thumbnail((FEEDBACK_IMAGE_SIZE, FEEDBACK_IMAGE_SIZE), Image.Resampling.LANCZOS)
    return np.asarray(image).copy()


def _image(inputs: Mapping[str, object]) -> NDArray[np.uint8]:
    value = inputs["data"]
    if not isinstance(value, np.ndarray) or value.dtype != np.uint8 or value.ndim != 3:
        raise ValueError("Connect an RGB uint8 image to the data input")
    if value.shape[2] != 3:
        raise ValueError("The image must have three RGB channels")
    return value


def _spec(name: str, title: str, *, optional_input: bool = False, icon: str = "") -> NodeSpec:
    return NodeSpec(
        type_id=f"image.{name}",
        title=title,
        icon=icon,
        category="Image",
        inputs=(PortSpec(name="data", dtype="image", min_connections=0 if optional_input else 1),),
        outputs=(PortSpec(name="data", dtype="image"),),
    )


class ImageInput(BaseNode):
    spec = _spec("input", "Image input", optional_input=True, icon="image-input")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": _image(inputs)}


class Grayscale(BaseNode):
    spec = _spec("grayscale", "Grayscale")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        image = ImageOps.grayscale(Image.fromarray(_image(inputs))).convert("RGB")
        return {"data": np.asarray(image).copy()}


class BlurParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    radius: float = Field(default=1.5, ge=0, le=10, allow_inf_nan=False)


class Blur(BaseNode):
    spec = _spec("blur", "Blur")
    parameter_model = BlurParams

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        params = BlurParams.model_validate(self.params)
        image = Image.fromarray(_image(inputs)).filter(ImageFilter.GaussianBlur(params.radius))
        return {"data": np.asarray(image).copy()}


class FeedbackBlur(Blur):
    spec = NodeSpec(
        type_id="image.feedback_blur",
        title="Feedback blur",
        icon="feedback-blur",
        category="Image",
        inputs=(
            PortSpec(name="data", dtype="image", min_connections=1),
            PortSpec(name="feedback", dtype="image"),
        ),
        outputs=(PortSpec(name="data", dtype="image", max_connections=2),),
    )

    @classmethod
    def direct_loopback_mode(cls, params: Mapping[str, JsonValue]) -> Literal["replace"]:
        return "replace"

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        current = inputs["feedback"] if inputs["feedback"] is not None else inputs["data"]
        return super().process({"data": current})


class Invert(BaseNode):
    spec = _spec("invert", "Invert")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": 255 - _image(inputs)}


class ImageOutput(BaseNode):
    spec = _spec("output", "PNG output", icon="image-output")

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        return {"data": _image(inputs)}


def demo() -> tuple[Graph, NodeRegistry]:
    return chain((ImageInput, Grayscale, Blur, Invert, ImageOutput))


def feedback_demo() -> tuple[Graph, NodeRegistry]:
    _, registry = demo()
    registry.register(FeedbackBlur)
    return (
        Graph(
            nodes=(
                NodeInstance(node_id="input", type_id="image.input"),
                NodeInstance(
                    node_id="blur", type_id="image.feedback_blur", position=Position(x=300)
                ),
                NodeInstance(node_id="output", type_id="image.output", position=Position(x=650)),
            ),
            edges=(
                Edge(
                    edge_id="input-blur",
                    src_node="input",
                    src_port="data",
                    dst_node="blur",
                    dst_port="data",
                ),
                Edge(
                    edge_id=FEEDBACK_EDGE_ID,
                    src_node="blur",
                    src_port="data",
                    dst_node="blur",
                    dst_port="feedback",
                ),
                Edge(
                    edge_id="blur-output",
                    src_node="blur",
                    src_port="data",
                    dst_node="output",
                    dst_port="data",
                ),
            ),
            policy=GraphPolicy(
                allow_feedback=True, loop=LoopPolicy(max_iterations=32, timeout_seconds=10)
            ),
        ),
        registry,
    )
