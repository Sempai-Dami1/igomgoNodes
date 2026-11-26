# igomgo-ImageLab handoff

## Adopt per-node feedback limits

1. Update the ImageLab framework pin below and reinstall it in the ImageLab environment.
2. Open **Feedback blur**, enable graph feedback, and set **Maximum iterations** in
   Setup to at least 3. Select the blur node with its direct loopback active.
3. In the node inspector, clear **Use graph default**, set **Loop maximum iterations**
   to **3**, and apply. Run with capture frequency **1** and confirm that iteration
   3 is the final capture and the output comes from that pass.
4. Download and reopen the graph. Confirm the override and feedback boundary persist.
   Open an older graph file and confirm the loop inherits the graph maximum.

The graph setting supplies both the default and the ceiling. Independent direct
self-loops can have different counts. Blur strength remains an ImageLab parameter.
ImageLab should use the framework-provided inspector control for the iteration count.

## Purpose and project boundary

Build **igomgo-ImageLab** as a separate consumer application that lets a user
configure and run an image-effect chain with a node graph. The integration reference
below applies to the existing ImageLab app and future image consumers.

igomgoNodes supplies the graph model, port and connection rules, execution,
bounded feedback, editor, and graph-file serialization. ImageLab owns its
image node classes, decoding, effects, previews, export, domain-specific
validation, and product experience. Keep image-processing dependencies and code
in ImageLab, not in igomgoNodes core.

ImageLab and later consumer apps are expected to reveal new framework needs.
Implement domain-specific features in the consumer; when a need is reusable,
document the use case and propose a change to igomgoNodes. Record deferred
framework ideas in [FUTURE.md](../FUTURE.md), promote agreed work in
[PROGRESS.md](../PROGRESS.md), and preserve existing consumers and graph files.
Do not assume planned features exist or add speculative framework abstractions.

## Current starting point

- The repository's [image example](../examples/image_poc.py) contains a small
  `image.input` → `image.grayscale` → `image.blur` → `image.invert` →
  `image.output` chain. The gallery connects it to upload, preview, execution,
  and PNG download; see [gallery.py](../examples/gallery.py).
- These are proof-of-concept **consumer** classes, not built-in image nodes
  distributed by the wheel. ImageLab should define and register its own nodes.
  The example is a reference for conventions and can be adapted.
- The example passes RGB `uint8` NumPy arrays on ports with `dtype="image"`.
  This is a useful initial contract, but the consumer must validate actual
  shape, channels, and dtype; the framework's dtype string is not pixel validation.
- The example's separate feedback demo runs a replacement blur loop, captures
  iterations, and previews them. It is not a video encoder or a resumable
  step-by-step execution engine.
- The package supports Python 3.11+. The latest existing tag, `v0.1.0`, predates
  the feedback demo, focus-mode improvements, and hosted selection fix. Do not
  assume the tag contains features added since it.

## Install and version

Pin this framework revision in ImageLab's dependency manifest to adopt per-node
feedback limits and schema-v1 import migration:

```text
igomgonodes[ui] @ git+https://github.com/Sempai-Dami1/igomgoNodes.git@d35d5941aa1cdc1fe45907350829be6dd65f4f13
```

Install NumPy and Pillow separately in ImageLab if following the existing image
example. Declare and test ImageLab's own dependencies; `ui` supplies the editor,
not the example processing libraries. The repository is private, so local and
deployment environments need authorized Git access. Do not embed credentials in
dependency URLs or commit secrets. For local development, an editable install of
a checked-out igomgoNodes repository is also possible; pin an immutable revision
or a later verified release for deployments. Coordinate a new release tag when
ready rather than silently relying on mutable `main`.

## Consumer developer integration

### 1. Define and register image nodes

Place node classes in importable ImageLab modules, not inside a function or only
in the Streamlit entry script. The executor starts a spawned worker, including on
Windows, and must be able to import the registered classes. CLI entry points
that launch execution need the `if __name__ == "__main__":` guard.

For each type, subclass `BaseNode`, give it a stable `NodeSpec.type_id`, declare
named input/output `PortSpec`s, and return a dictionary with exactly the declared
output names from `process`. A single-capacity input receives a value or `None`;
a multi-connection input receives an ordered list. Set `min_connections=1`
where a graph edge is required. An external input must be an unconnected,
optional, single-capacity input port.

For example, the following node follows the demo's RGB contract:

```python
from collections.abc import Mapping

import numpy as np

from igomgo_nodes.core import BaseNode, NodeSpec, PortSpec


class Invert(BaseNode):
    spec = NodeSpec(
        type_id="imagelab.invert",
        title="Invert",
        category="Image",
        icon="image-invert",
        inputs=(PortSpec(name="data", dtype="image", min_connections=1),),
        outputs=(PortSpec(name="data", dtype="image"),),
    )

    def process(self, inputs: Mapping[str, object]) -> dict[str, object]:
        pixels = inputs["data"]
        if (
            not isinstance(pixels, np.ndarray)
            or pixels.dtype != np.uint8
            or pixels.ndim != 3
            or pixels.shape[2] != 3
        ):
            raise ValueError("Expected an RGB uint8 image")
        return {"data": 255 - pixels}
```

Create a `NodeRegistry()` and explicitly `register()` every input, effect, and
output class. Give adjustable effects a Pydantic v2 `parameter_model` with
defaults and bounds; the editor builds parameter fields from it and node
construction validates it. Keep parameters JSON-compatible. The
[consumer guide](./consumer-guide.md) covers connection limits, parameter models,
and registry usage.

Pick a stable ImageLab type-ID namespace and version its parameter semantics.
Type IDs are persisted in graph files: renaming or changing their meaning can
break saved work. Imported files resolve only types already in the registry;
never load code or dynamically import classes based on a graph file.

### 2. Build the initial graph and editor

Construct a `Graph` containing `NodeInstance`s and `Edge`s with declared port
names. Provide an input node with an optional, unconnected `data` port for the
uploaded image, at least one effect, and an output node. Keep source and output
node IDs stable if ImageLab's preview and export code looks them up by ID.
Decide how to handle users deleting or replacing them; the demo explicitly
requires its original `input` and `output` nodes when running.

Create one `EditorAdapter(graph, registry)` per user session and render it with
`render_editor(editor)`. Use `editor.graph` and `editor.feedback_edge_ids` as
the current graph and selected feedback boundaries. Avoid a module-global editor
shared across users. For a custom layout, `render_editor` accepts `section="setup"`,
`section="draft"`, and `section="node"`; the API still calls the canvas section
`"draft"`, even though the demo's visible tab is **Canvas**. The gallery shows
how to compose these sections and an application-owned Graph/output section.

The editor permits incomplete graphs while editing. Before running, check
connections and feedback with `graph.validate_connections(registry)` and
`graph.validate_feedback()`, and report errors to the user. The executor also
validates execution readiness, including feedback boundaries.

### 3. Pass image data and run

Decode and validate the uploaded image in ImageLab. Keep pixels out of graph
parameters and graph JSON. Once the source and output IDs and port names exist in
the consumer graph, the integration looks like this:

```python
result = Executor().run(
    editor.graph,
    registry,
    inputs={"input": {"data": pixels}},
    feedback_edge_ids=editor.feedback_edge_ids,
)
if result.timed_out:
    # Report the timeout; completed passes do not guarantee a final output.
    ...
else:
    output_pixels = result.outputs["output"]["data"]
```

This is an integration fragment: import `Executor`, create the registered nodes
and graph, and bind `pixels` to the validated decoded image first. Handle
`ExecutionError` and validation/decode errors visibly; check that the expected
output exists and meets the ImageLab pixel contract before preview or export.
Consumer classes and payloads must be transferable to the spawned process.

Execution retains outputs from nodes, not just the final image. Worker messages
and retained results are limited to 16 MiB, with up to 1,000 snapshots and a
maximum 60-second run. Copies and feedback snapshots can make image chains hit
these limits sooner than an individual input image would suggest. Choose and
test ImageLab-specific image, graph, and capture limits; expose explicit errors
instead of silently truncating or claiming success.

Run on an explicit user action and invalidate displayed results when the graph,
parameters, feedback boundaries, or input change. The gallery fingerprints these
inputs before showing a cached result. Cache expensive work only with appropriate
entry limits, isolation, and retention for the sensitivity of uploaded images;
the demo's server-memory caches are not private durable storage.

### 4. Save, restore, and export

Use `BrowserFileStore.serialize(editor.graph, editor.feedback_edge_ids)` for
downloadable editor bytes. On upload, use `deserialize(data, registry)`, then
`editor.replace_graph(document.graph, frozenset(document.feedback_edge_ids))`
only after validation succeeds. Surface failures and leave the current graph
untouched. This document preserves selected feedback boundaries; plain
`dumps_graph`/`loads_graph` files contain only the core graph.

Graph files store configuration, not the uploaded image or processed output.
Make that distinction clear in ImageLab and provide separate image export.
The framework's graph/editor file limits are 25 MiB, 10,000 nodes, and 100,000
edges. Exports use schema v2, and imports migrate v1 files. Readers pinned to the
older framework require v1 files. All imports require registered types. Shared hosting should
use browser download/upload rather than `LocalJsonStore` as per-user server
storage. Supabase storage and account-based sharing are deferred.

### 5. Optional feedback

Start with a straightforward acyclic image chain. If ImageLab needs repeated
effects, enable graph feedback with a finite `LoopPolicy` and explicitly select
edges that break every cycle. The executor unrolls the graph into a bounded
virtual spiral: the external image enters the first pass, feedback is passed to
later passes, and downstream output comes from the final completed pass.
Use `result.snapshots` for captured complete passes and check `result.timed_out`.
Capture can quickly exceed memory limits.

See `FeedbackBlur` and `feedback_demo()` in the image example for the existing
replacement self-loop. Adding image frames, video export, background execution,
or manual global stepping requires additional consumer/framework work; these are
not implied by feedback support. Never implement an unbounded processing loop.

## Intended ImageLab user workflow

The following describes a recommended experience to implement in ImageLab;
the exact layout and features are not yet shipped in that app.

1. **Choose an image.** Upload a supported image; show the original and a clear
   message if the file is invalid or too large.
2. **Build the chain.** Add image nodes from the palette, connect compatible
   output and input ports in the desired order, and adjust effect parameters in
   the inspector. For example: image input → grayscale → blur → image output.
   The effect order changes the result.
3. **Edit safely.** Select a node or connection; the existing editor highlights
   the selection red. Use its on-screen delete controls. Deleting a node also
   removes its connections. Keyboard Delete is not supported. For multi-port
   nodes, use the named-port connection controls; the canvas supports dragging
   single-port connections.
4. **Validate and run.** Resolve missing or incompatible connections, then run
   the graph. Show processing errors or timeout explicitly. When the input or
   graph changes, mark old output stale until the user runs again.
5. **Preview and export.** Compare the input and final image, then download the
   processed image. Format and quality choices are ImageLab decisions.
6. **Save the configuration.** Download a graph file to keep the chain and
   settings; load it later and upload an image again. Graph files do not contain
   the user's image.
7. **Use feedback only when offered.** Enable feedback, set iteration and time
   limits, connect the loop, and select its feedback boundary. Explain that
   repeated passes are finite and may be limited by execution and memory caps.

The current igomgoNodes demo also offers an optional **Focus mode** with Setup,
Canvas, Node, and Graph tabs. ImageLab may reuse that arrangement or choose its
own; it is not automatically supplied by `render_editor()`.

## Security and verification checklist

- Follow [SECURITY.md](../SECURITY.md). Treat images and graph JSON as untrusted;
  limit upload bytes and decoded pixel count, allow-list formats, use established
  decoders, and report corrupt files. The demo limits images to 5 MiB and 262,144
  pixels; these are demo limits, not automatic framework limits.
- Keep secrets out of code and dependency URLs. Do not accept user code, pickle,
  dynamically imported node classes, or unsanitized user-provided SVG/HTML.
  Spawned workers are not a sandbox.
- Test each effect and its parameter bounds, RGB shape/dtype, invalid inputs, and
  expected output. Smoke-test a connected input → effect → output graph, a
  graph-file round trip, and UI selection, edits, run, errors, and export.
- Test from the actual pinned installation and in the intended hosting environment,
  including Git access, worker startup, upload limits, and memory/timeout behavior.
  If feedback is offered, test bounded iterations, boundary selection, timeout,
  and snapshot limits.
- Track consumer requests with a reproducible use case and expected behavior.
  Distinguish an ImageLab feature from a reusable framework change; add migrations
  and compatibility tests before breaking persisted graph formats or stable IDs.

## References

- [Consumer guide](./consumer-guide.md): package APIs, validation, feedback, and storage.
- [Image example](../examples/image_poc.py) and [gallery integration](../examples/gallery.py).
- [Project concept](../CONCEPT.md), [progress](../PROGRESS.md),
  [future ideas](../FUTURE.md), and [security](../SECURITY.md).
