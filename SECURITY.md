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
- **Saved graphs:** graph files are uploaded by anonymous users and are untrusted. Enforce a
  size limit and validate JSON with Pydantic against the schema before use. Node
  `type_id`s resolve only through the registry — **never** `eval`, `exec`, `pickle`, or
  dynamic imports from graph data.
- **User-provided code nodes** are not supported (see FUTURE.md); if ever added they need
  a real sandbox.
- **Rendering:** do not use `unsafe_allow_html=True` with user-supplied strings (node
  titles, labels, SVG icons). Sanitize custom SVG icons.

## Resource exhaustion
- Feedback loops always bounded by `max_iterations` **and** `timeout_seconds`, with
  server-side hard caps that user settings cannot exceed.
- Limit node count / edge count per graph and captured snapshot memory.

## Dependencies
- Pin versions in `pyproject.toml`/lock file; enable Dependabot alerts.
