# Pin Container Images

Resolve container image tags to immutable `sha256:` content digests.

A workflow carries more executable references than `uses:`.
A repository can be fully SHA-pinned on `uses:` and still pull `redis:7` fresh on every run.
Image pinning is **on by default**.

## Covered References

| Reference                        | Example                           |
| -------------------------------- | --------------------------------- |
| Step container                   | `uses: docker://alpine:3`         |
| Job container                    | `jobs.<id>.container.image`       |
| Job container (string shorthand) | `jobs.<id>.container: node:20`    |
| Service container                | `jobs.<id>.services.<name>.image` |

## Example

Before:

```yaml
jobs:
  test:
    container:
      image: python:3.14-slim
    services:
      redis:
        image: redis:7
    steps:
      - uses: docker://alpine:3
```

After:

```yaml
jobs:
  test:
    container:
      image: python@sha256:7d1e2c3b4a5f6e7d8c9b0a1f2e3d4c5b6a7f8e9d0c1b2a3f4e5d6c7b8a9f0e1d  # 3.14-slim
    services:
      redis:
        image: redis@sha256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b  # 7
    steps:
      - uses: docker://alpine@sha256:3f2e1d0c9b8a7f6e5d4c3b2a1f0e9d8c7b6a5f4e3d2c1b0a9f8e7d6c5b4a3f2e  # 3
```

The original tag is preserved in the trailing comment, exactly as with action refs.

## Disable Image Pinning

Pin only `uses:` refs and leave images alone:

```bash
pin-actions --no-image-pin --github-token $GITHUB_TOKEN
```

## Registry Support

Digests are resolved through the registry's Bearer-token challenge flow, anonymously for public registries
(Docker Hub, GHCR, Quay.io, and others).
GHCR receives the GitHub token when one is configured.

Registries that do not offer Bearer auth — notably Amazon ECR and Google GCR — raise `UnsupportedRegistryError`.
During a normal run that error is caught per image: the entry is left untouched and a warning is logged,
so one unsupported registry never aborts the batch.

The error only propagates if you call `ContainerRegistryClient.resolve_digest()` yourself.

## Cool-off Does Not Apply

`--exclude-newer` gates tag *selection* under `--update`.
Image pinning resolves the tag you already named, so there is nothing to select and no cutoff to apply.

## See Also

- [Architecture Overview](../explanation/architecture.md) — registry resolution and concurrency model
- [Reference: errors](../reference/errors.md) — `UnsupportedRegistryError` attributes
- [Comparing pin-actions to Similar Tools](../explanation/comparison.md) — which tools cover which image surfaces
