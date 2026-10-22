# Releasing trackerkeeper

**The tag is the version.** setuptools-scm derives the version from the latest
`git tag vX.Y.Z`; there is nothing to bump in N files. Manifests are *generated*
from `[tool.trackerkeeper.metadata]` by `trackerkeeper bake`, never hand-edited (docs/BAKING.md).

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

## Channels at a glance (2026-10-22)

| Channel | Ships from | State |
| --- | --- | --- |
| GitHub: `.deb`, AppImage (+ `.zsync`), sdist + wheel | `release.yml` | **live** |
| GitHub: Flatpak bundle (`trackerkeeper-X.Y.Z.flatpak`) | `release.yml` `build-linux-flatpak` | **live** — the phone-shell channel (KDE runtime brings Qt Quick) |
| GitHub: Windows x64 installer + x64 / Arm64 portable zips | `release.yml` `build-windows` (matrix) | **live**, unsigned until Azure signing |
| PyPI | `pypi-publish.yml` on publish | **live** (Trusted Publisher registered) |
| macOS `.dmg` (signed, notarized) + Homebrew cask | `macos.yml` on release | dormant — needs the Apple secrets (below) |
| winget | `winget.yml` on release | dormant — needs `WINGET_TOKEN` |
| AUR | `aur.yml` on release | dormant — needs `AUR_SSH_PRIVATE_KEY` + registering the package |
| Microsoft Store (MSIX) | manual first submission | dormant — reserve the name in Partner Center |
| Mac App Store | — | not started (jellytoast has the jobs to port once an App Store Connect record exists) |

**The phone interface ships in the Linux bundles.** The PyInstaller spec keeps
Qt Quick on Linux (pruned to the QML modules `trackerkeeper/quick` imports) and
the `.deb` job boots the frozen bundle with `TRACKERKEEPER_UI=quick`, failing
the release if the phone interface falls back. Windows / macOS still prune Qt
Quick: no phone shell there.

**One Apple account, two apps.** `wolfgangwarehaus` is a personal account, so
secrets can't be shared at org level — add the same values jellytoast has to
this repo: `APPLE_CERTIFICATE`, `APPLE_CERTIFICATE_PWD`, `APPLE_KEYCHAIN_PWD`,
`APPLE_SIGNING_IDENTITY`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER`,
`APPLE_API_KEY_B64`. `macos.yml` reads jellytoast's names first.

## One-time setup

- **PyPI Trusted Publishing** *(configured 2026-07-25)* — add a pending publisher at
  <https://pypi.org/manage/account/publishing/>. The project name must match
  `[project] name` in `pyproject.toml`, which for this loaf is **`trackerkeeper`**
  — NOT the dough base's own PyPI project. Register exactly these, which are the
  claims GitHub actually presented on the v0.1.0 run:

  | field | value |
  | --- | --- |
  | PyPI project name | `trackerkeeper` |
  | Owner | `wolfgangwarehaus` |
  | Repository name | `trackerkeeper` |
  | Workflow name | `pypi-publish.yml` |
  | Environment name | `pypi` |

  Until it exists, publishing a release fails that one leg with
  `invalid-publisher: valid token, but no corresponding publisher` — the GitHub
  release itself still publishes with every artifact, so only PyPI is missing.
  After registering, re-run the failed job (`gh run rerun <id>`) or dispatch
  `pypi-publish.yml` with the tag; nothing needs re-tagging.
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
  the Homebrew cask on `release: released`; the whole job skips until
  `APPLE_SIGNING_IDENTITY` (or the older `APPLE_TEAM_ID`) exists. Use the same
  secrets as jellytoast (listed above); `HOMEBREW_TAP_TOKEN` is optional.
- **MSIX / Microsoft Store** *(manual-first)* — the toolkit ships
  (`packaging/msix/`: `AppxManifest.xml`, `make-assets.sh`) but the first
  submission is **manual** via Partner Center — follow
  `packaging/msix/STORE-SUBMISSION.md` (fill `msix_publisher_cn` after registering,
  re-bake, validate locally with WACK, then upload).
- Otherwise nothing: the `.deb` / AppImage / `.exe` / attestations / checklist use
  the built-in `GITHUB_TOKEN` + OIDC.

## Verify an artifact

```sh
gh attestation verify <file> --repo wolfgangwarehaus/trackerkeeper
sha256sum -c SHA256SUMS
```

## Not yet wired (see docs/TODO.md)

A hosted apt/PPA repo, the landing page, and Flathub (policy-blocked — skipped).
Everything else — PyPI, `.deb`, AppImage, AUR, Windows (Inno + winget), macOS, and
MSIX — is wired (dormant channels light up when their account/secret is provisioned).
