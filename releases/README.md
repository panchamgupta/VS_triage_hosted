# Hosted Release Root

This directory is the default local development release root for the hosted portal scaffold.

Expected layout:

```text
releases/
  RELEASE_TAG/
    manifest.json
    data/
    poses/
    exports/
    static_payload/
```

Use the `HOSTED_PORTAL_RELEASE_ROOT` environment variable to point the Flask app at a cluster-mounted production release root.