# Publishing

This project is configured for PyPI Trusted Publishing through GitHub Actions.
No long-lived PyPI token is required.

## Before the first release

1. Choose a license, add a `LICENSE` file, and add its SPDX identifier to
   `pyproject.toml`.
2. Create the GitHub repository and push this directory as its root.
3. Add the repository URLs to `pyproject.toml`, for example:

   ```toml
   [project.urls]
   Homepage = "https://github.com/OWNER/pdf-figure-table-extractor"
   Issues = "https://github.com/OWNER/pdf-figure-table-extractor/issues"
   Source = "https://github.com/OWNER/pdf-figure-table-extractor"
   ```

4. On PyPI, create a pending trusted publisher for:
   - PyPI project: `pdf-figure-table-extractor`
   - GitHub owner and repository: the repository created above
   - Workflow filename: `publish.yml`
   - Environment name: `pypi`
5. In the GitHub repository, create an environment named `pypi` and optionally
   require manual approval for deployments.

## Validate locally

```bash
uv sync --locked --all-groups
uv run ruff check .
uv run pytest
uv build
uvx --from twine twine check dist/*
```

## Release

1. Update `version` in `pyproject.toml` and run `uv lock`.
2. Commit the version change and create a matching tag such as `v0.1.0`.
3. Create a GitHub Release from that tag.
4. The `Publish to PyPI` workflow builds the distributions and runs:

   ```bash
   uv publish --trusted-publishing always
   ```

The package name is not reserved until the first successful PyPI upload.
