---
name: shared-file-drop
description: Publish human-facing HTML, images, video, PDF, JSON, CSV, or text files to a configured S3-compatible public drop and return a URL. Use it for temporary artifacts that someone needs to open outside the agent workspace.
---

# Shared file drop

Publish temporary artifacts with:

```bash
shared-file-upload <file-or-directory> [--name <name>] [--dir <subdirectory>]
```

The command prints a URL beneath
`<SHARE_PUBLIC_URL>/shared/<profile>/<yyyymmdd>/...`. Directory uploads return
their `index.html` URL when one exists.

The S3-compatible bucket must have a lifecycle rule that deletes objects under
the `shared/` prefix after 30 days. The uploader adds a `retention=30d` object
tag and a matching HTTP expiry timestamp, but provider lifecycle configuration
is what actually deletes the object.

Required environment variables:

- `SHARE_PUBLIC_URL`
- `S3_ENDPOINT`
- `S3_BUCKET`
- `S3_ACCESS_KEY_ID`
- `S3_SECRET_ACCESS_KEY`

Optional: `S3_REGION` (defaults to `auto`).

Never upload credentials, private database dumps, personal data, customer data,
or anything that should not be accessible to someone holding the URL.
