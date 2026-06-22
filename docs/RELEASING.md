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
   AppImage (+ `.zsync`) + Windows `.exe` installer + portable `.zip` + sdist +
   wheel, **smoke-tests the `.deb`/AppImage in clean containers**
   (self-containment), attaches `SHA256SUMS` and Sigstore build-provenance
   attestations, and opens a **draft** GitHub release. `release-checklist.yml`
   opens a propagation-checklist issue at the same time.
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
- **AUR** *(dormant)* — `aur.yml` publishes the PKGBUILD on `release: released`,
  but skips until you add an `AUR_SSH_PRIVATE_KEY` secret (a dedicated AUR deploy
  keypair; the public half on your AUR account) **and** the AUR reopens
  new-package registration (frozen after the 2026 malware wave).
- **Windows code signing** *(dormant)* — the `.exe` builds + ships **unsigned**
  until you add the six Azure Trusted Signing secrets (`AZURE_TENANT_ID`,
  `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_SIGNING_ENDPOINT`,
  `AZURE_SIGNING_ACCOUNT`, `AZURE_SIGNING_PROFILE`). `build-windows` keys off
  `AZURE_CLIENT_ID` and skips both signing steps when it's empty.
- **winget** *(dormant)* — `winget.yml` submits to microsoft/winget-pkgs on
  `release: released`; needs a CLASSIC PAT (`public_repo`) as `WINGET_TOKEN` and a
  fork of microsoft/winget-pkgs under `wolfgangwarehaus`.
- **macOS** *(dormant)* — `macos.yml` builds, signs, notarizes the `.dmg` and bumps
  the Homebrew cask on `release: released`; the whole job skips until you add a
  $99/yr Apple Developer membership + the secrets `MACOS_CERTIFICATE` (base64
  `.p12`), `MACOS_CERTIFICATE_PWD`, `MACOS_KEYCHAIN_PWD`, `APPLE_ID`,
  `APPLE_APP_SPECIFIC_PASSWORD`, `APPLE_TEAM_ID`, and `HOMEBREW_TAP_TOKEN` (a PAT
  for a separate `homebrew-tap` repo). Keys off `APPLE_TEAM_ID`.
- **MSIX / Microsoft Store** *(manual-first)* — the toolkit ships
  (`packaging/msix/`: `AppxManifest.xml`, `make-assets.sh`) but the first
  submission is **manual** via Partner Center — follow
  `packaging/msix/STORE-SUBMISSION.md` (fill `msix_publisher_cn` after registering,
  re-bake, validate locally with WACK, then upload).
- Otherwise nothing: the `.deb` / AppImage / `.exe` / attestations / checklist use
  the built-in `GITHUB_TOKEN` + OIDC.

## Verify an artifact

```sh
gh attestation verify <file> --repo wolfgangwarehaus/dough
sha256sum -c SHA256SUMS
```

## Not yet wired (see docs/TODO.md)

A hosted apt/PPA repo, the landing page, and Flathub (policy-blocked — skipped).
Everything else — PyPI, `.deb`, AppImage, AUR, Windows (Inno + winget), macOS, and
MSIX — is wired (dormant channels light up when their account/secret is provisioned).
