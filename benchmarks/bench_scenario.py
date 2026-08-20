"""Synthetic benchmark scenario: generates N workflow files + mocked GitHub API."""

import asyncio
import tempfile
from pathlib import Path

import httpx2
from pin_actions.client import GitHubClient
from pin_actions.config import Settings
from pin_actions.core import run
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class BenchSettings(BaseSettings):
    """CLI & environment configuration for benchmark scenario."""

    model_config = SettingsConfigDict(
        env_prefix="BENCH_",
        case_sensitive=False,
        populate_by_name=True,
    )

    files: int = Field(default=100, ge=1, description="Number of workflow files to generate")
    concurrency: int = Field(default=5, ge=1, description="GitHub client concurrency level")
    already_pinned_ratio: float = Field(
        default=0.3, ge=0.0, le=1.0, description="Fraction of actions that are already pinned with SHAs"
    )
    verbose: int = Field(default=0, ge=0, le=3, description="Verbosity level 0-3")


# Mock GitHub API responses
MOCK_TAGS = {
    "actions/checkout": [
        ("v4.0.0", "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b"),
        ("v3.6.0", "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c"),
        ("v3.5.3", "c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c2d"),
    ],
    "actions/setup-python": [
        ("v5.0.0", "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c2d3e"),
        ("v4.7.0", "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c2d3e4f"),
        ("v4.6.1", "f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c2d3e4f5a"),
    ],
    "actions/upload-artifact": [
        ("v4.0.0", "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0"),
        ("v3.1.3", "2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1"),
    ],
}

MOCK_REFS = {
    ("actions/checkout", "v4"): "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b",
    ("actions/checkout", "main"): "1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a1a",
    ("actions/setup-python", "v4"): "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b1c2d3e4f",
    ("actions/setup-python", "main"): "2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b",
    ("actions/upload-artifact", "v4"): "1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0",
}


def mock_transport_handler(request: httpx2.Request) -> httpx2.Response:
    """Mock GitHub API responses."""
    url = str(request.url)

    # Parse URL to determine response
    if "/tags" in url:
        for repo_name, tags in MOCK_TAGS.items():
            if repo_name in url:
                return httpx2.Response(
                    200,
                    json=[{"name": tag, "commit": {"sha": sha}} for tag, sha in tags],
                )
        return httpx2.Response(404, json={})

    if "/commits/" in url:
        parts = url.split("/")
        ref = parts[-1]
        return httpx2.Response(
            200,
            json={
                "sha": MOCK_REFS.get(("dummy", ref), "0" * 40),
                "commit": {"committer": {"date": "2024-08-01T12:00:00Z"}},
            },
        )

    return httpx2.Response(404, json={})


def generate_workflow_files(directory: Path, count: int, *, already_pinned_ratio: float = 0.3) -> None:
    """Generate synthetic workflow YAML files.

    Args:
        directory: Destination directory.
        count: Number of workflow files to generate.
        already_pinned_ratio: Fraction of actions that are already pinned with SHAs.
    """
    actions = [
        ("actions/checkout", "v4"),
        ("actions/setup-python", "v4"),
        ("actions/upload-artifact", "v4"),
    ]

    for i in range(count):
        content = f"""
name: Workflow {i}
on:
  push:
    branches: [main]

jobs:
  test-{i}:
    runs-on: ubuntu-latest
    steps:
"""
        for j, (action, ref) in enumerate(actions):
            if j < len(actions) * already_pinned_ratio:
                # Already pinned SHA (with comment preserving original tag)
                sha = MOCK_REFS.get((action, ref), "0" * 40)
                content += f"      - uses: {action}@{sha}  # {ref}\n"
            else:
                # Mutable ref needing resolution
                content += f"      - uses: {action}@{ref}\n"

        # Add a checkout with with.ref for some workflows
        if i % 3 == 0:
            content += """      - uses: actions/checkout@v4
        with:
          repository: example/repo
          ref: feature-branch
"""

        workflow_path = directory / f"workflow-{i:04d}.yml"
        workflow_path.write_text(content)


async def run_benchmark(settings: BenchSettings) -> None:
    """Run benchmark scenario.

    Args:
        settings: Benchmark configuration.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Generate workflows
        print(f"Generating {settings.files} workflow files...")
        generate_workflow_files(tmppath, settings.files, already_pinned_ratio=settings.already_pinned_ratio)

        # Build pin-actions settings
        pin_settings = Settings(
            path=tmppath,
            github_token=None,
            concurrency=settings.concurrency,
            dry_run=True,
            verbose=settings.verbose,
        )

        # Create client with mocked transport
        transport = httpx2.MockTransport(mock_transport_handler)
        async with GitHubClient(concurrency=settings.concurrency) as client:
            # Replace the HTTP client's transport with mock
            await client._get_http_client()
            if client._http_client:
                # Recreate with mocked transport
                await client._http_client.aclose()
                client._http_client = httpx2.AsyncClient(transport=transport)

            print(f"Running benchmark on {settings.files} files with concurrency={settings.concurrency}...")
            try:
                modified = await run(pin_settings, client=client)
                print(f"Benchmark complete: {len(modified)} files would be modified")
            except Exception as e:
                print(f"Benchmark failed: {e}")
                raise


def main() -> None:
    """CLI entry point."""
    settings = BenchSettings(
        _cli_parse_args=True,
        _cli_kebab_case=True,
        _cli_implicit_flags=True,
        _cli_prog_name="bench-scenario",
    )
    asyncio.run(run_benchmark(settings))


if __name__ == "__main__":
    main()
