# Security

## Reporting
Report vulnerabilities privately via GitHub Security Advisories on this repository
(Security → Report a vulnerability). Do not open public issues for security problems.

## Secrets
- Supabase URL and **anon/publishable** key go in `.streamlit/secrets.toml` locally and in
  the Streamlit Community Cloud secrets manager when deployed. Never commit them.
- The Supabase **service-role** key must **never** be used in the Streamlit app or shipped
  in the package. Admin tasks run from migrations/CI only.
- `.streamlit/secrets.toml` and `.env` are git-ignored; enable GitHub secret scanning and
  push protection.

## Supabase
- Row Level Security **enabled on every table**; policies restrict rows to
  `auth.uid() = owner_id`.
- Storage buckets are **private**; object paths prefixed `{owner_id}/…`, with policies
  enforcing that prefix. Serve files via short-lived signed URLs.
- Run Supabase security advisors after each migration.

## Untrusted input
- **Uploads:** enforce size limits (`server.maxUploadSize`) and an allow-list of types
  (WAV, PNG, JPEG). Decode with established libraries (`soundfile`, Pillow); cap image
  pixel count (Pillow `MAX_IMAGE_PIXELS`) and audio duration/sample rate.
- The example gallery enforces 5 MiB per media upload before decoding. WAV metadata
  must describe nonempty audio no longer than 5 seconds, 8–48 kHz, and one or two
  channels; non-finite decoded samples are rejected. Image headers must identify
  PNG/JPEG with at most 262,144 pixels before full RGB decoding. Corrupt media raises
  visible errors. The transport's 25 MB cap does not replace these smaller demo limits.
- **Saved graphs:** graph files are uploaded by anonymous users and are untrusted. Enforce a
  size limit and validate JSON with Pydantic against the schema before use. Node
  `type_id`s resolve only through the registry — **never** `eval`, `exec`, `pickle`, or
  dynamic imports from graph data.
- Use `loads_graph`/`dumps_graph` at graph-file boundaries: maximum 25 MiB UTF-8,
  10,000 nodes and 100,000 edges, with an explicit supported schema version.
  Imports reject duplicate JSON keys and non-finite numeric values. Imported node types
  must already be registered; full connection/feedback checks still run before execution.
- Editor documents are capped at 25 MiB and include the core graph plus feedback-edge
  selections. The loader also accepts core graph JSON and resolves every type through the
  supplied registry. Upload failures are reported without replacing the active editor.
- `LocalJsonStore` is for trusted local application deployments only. It restricts names
  to simple `.igomgo.json` filenames under its configured directory, rejects symlinks,
  reads at most 25 MiB, and uses atomic replacement. Do not expose server-local storage as
  per-user persistence on a shared host; use browser download/upload or an explicitly
  isolated authenticated store instead.
- **User-provided code nodes** are not supported (see FUTURE.md); if ever added they need
  a real sandbox.
- **Rendering:** do not use `unsafe_allow_html=True` with user-supplied strings (node
  titles, labels, SVG icons). Sanitize custom SVG icons.

## Resource exhaustion
- Feedback loops always bounded by `max_iterations` **and** `timeout_seconds`, with
  server-side hard caps that user settings cannot exceed.
- Limit node count / edge count per graph and captured snapshot memory.
- Virtual-spiral expansion rejects results above 10,000 nodes or 100,000 edges before
  creating copies. Expansion itself does not run processing; execution must separately
  enforce the original timeout and capture limits.
- The executor uses a spawned worker and terminates/joins it at timeout (maximum
  60 seconds). Snapshot schedules above 1,000 and result transfers/retention above
  16 MiB raise explicit errors. These do not constrain all consumer allocations:
  workers are resource-isolation helpers, not sandboxes for untrusted code.
- Multiprocessing uses pickle only for locally registered, trusted classes and worker
  messages. Never accept pickled files, network messages, or class definitions from users.
  Uploaded graph files remain validated JSON with registry-only type resolution.
- Decoded demo uploads and complete run results use Streamlit server-memory caches with
  at most four entries each. They are not durable storage; keep sensitive material out of
  shared demo deployments. Consumers hosting private data should define their own cache
  isolation and retention policy.

## Dependencies
- Pin versions in `pyproject.toml`/lock file; enable Dependabot alerts.
