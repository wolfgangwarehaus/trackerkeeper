# Releasing dough

**The tag is the version.** setuptools-scm derives the version from the latest
`git tag vX.Y.Z`; there is nothing to bump in N files. Manifests are *generated*
from `[tool.dough.metadata]` by `dough bake`, never hand-edited (docs/BAKING.md).

## Cut a release

1. **Move the changelog.** In `docs/CHANGELOG.md`, rename `## [Unreleased]` to
   `## [X.Y.Z] — YYYY-MM-DD` (keep an empty `[Unreleased]` above for next time).
   `release.yml` lifts this section verbatim into the GitHub release notes.
2. **Tag and push.**
   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
3. **`release.yml` (Phase 1)** runs on the tag: renders the manifests with the
   release version injected, freezes the PyInstaller bundle, builds the `.deb` +
   AppImage (+ `.zsync`) + sdist + wheel, attaches `SHA256SUMS` and Sigstore
   build-provenance attestations, and opens a **draft** GitHub release.
4. **Review the draft** on GitHub. This is the one deliberate human gate.
5. **Publish.** Clicking Publish fires `release: published` →
   **`pypi-publish.yml`** uploads the sdist + wheel to PyPI via OIDC Trusted
   Publishing (no token).

A `git tag vX.Y.Z` re-push or a workflow re-run is idempotent (create-or-update +
`--clobber`). `workflow_dispatch` on `release.yml` is a dry run: it builds and
uploads workflow artifacts but creates no release.

## One-time setup

- **PyPI Trusted Publishing** — add a pending publisher at
  <https://pypi.org/manage/account/publishing/> matching `pypi-publish.yml`
  (project `dough`, owner `wolfgangwarehaus`, repo `dough`, workflow
  `pypi-publish.yml`, environment `pypi`). See the header of that workflow.
- Nothing else: the `.deb` / AppImage / attestations use the built-in
  `GITHUB_TOKEN` + OIDC.

## Verify an artifact

```sh
gh attestation verify <file> --repo wolfgangwarehaus/dough
sha256sum -c SHA256SUMS
```

## Not yet wired (see docs/TODO.md)

Windows (Inno installer + winget + MSIX), AUR, macOS (`.dmg` + cask), a hosted
apt repo, and the landing page. The metadata core already carries their fields;
they light up channel-by-channel as each is templatized.
