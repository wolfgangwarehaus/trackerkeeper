# dough — the baking phase

dough has two halves. The first is the **creation medium** — the rise: a uniform
window chrome, design system, themes, the platform scaffolding, so a new app is
mostly its own idea on a frosted base. The second is the **baking phase** — the
oven: the way one uniform product is *released across every platform and channel*,
productizing what jellytoast proved in the field. dough rises, then bakes, then
ships to the stores.

This document is the design for that second half. It's a spec, not yet code —
captured from the `baking-phase-research` sweep (2026-06-21) over jellytoast's
real release stack plus each channel's canonical schema.

---

## 1. The problem it actually solves

The baking phase is *not* "write some packaging scripts." jellytoast already has
the scripts — a `.deb` build, an AppImage build, an Inno installer, winget
manifests, a 366-line `release.yml`, the works. The thing it does **not** have is
a single place the app's identity lives. App identity is re-literalised across
**~13 files, and it has measurably drifted**: six different wordings of the
one-line summary, three publisher strings for one person (`august` /
`wolfgangwarehaus` / `wolfgang warehaus`), four divergent keyword lists, the
version hardcoded in three places. jellytoast can only *lint* that drift after the
fact (`test_version_consistency.py` covers 5 of ~8 version sites).

So the baking phase is one idea applied ruthlessly:

> **One metadata source → generate every manifest → verify nothing drifted.**

Everything below is downstream of that sentence. dough already proved the pattern
on the *design* side — `color_tokens` exports the palette to JSON so the app and
the landing page share one source of truth. The baking phase is the same move for
*identity and packaging metadata*.

---

## 2. Principles

1. **One metadata source.** A single schema-versioned table — `[tool.dough.metadata]`
   in `pyproject.toml`, co-located with `[project]` — holds the union field set
   once. Every manifest is rendered from it; none is hand-authored.

2. **Generate-then-verify, never hand-edit-then-test.** A `dough bake` render step
   reads the metadata + the identity-seam projections and *emits* the metainfo,
   `.desktop`, winget YAMLs, PKGBUILD, `.iss`, AppxManifest, deb control, the
   landing page, `palette.json`. A CI gate re-renders and diffs the committed files
   against a fresh render — any drift fails the build. (jellytoast lints; dough
   regenerates.)

3. **Dormancy is the default.** Every secret-bearing channel is guarded by
   `HAVE_X = secrets.X != ''`: absent its secret, the leg *skips* with a one-line
   activation pointer, present it *wakes up*. A freshly-baked app **builds green
   from day one with zero secrets**, and each channel lights up when its account is
   provisioned. This is what makes "full scope" honest for fork-and-own — most new
   apps won't have Azure/AUR/Apple set up, and they shouldn't need to.

4. **The tag is the version.** Dynamic versioning (`setuptools-scm`): the single
   version action is `git tag vX.Y.Z`. There is nothing to stamp and no
   consistency gate to need, because version divergence is made *structurally
   impossible* rather than caught afterward. `__version__` is read from a generated
   `dough/_version.py`; CI resolves the version from the tag and injects it into
   the version-bearing manifest fields at release time.

5. **OIDC-first; manual-first where the platform demands it.** Prefer tokenless
   auth wherever it exists (PyPI Trusted Publishing, Sigstore provenance). The two
   channels whose *first* submission is irreducibly human — the Microsoft Store
   cert review and a Flathub PR — are modeled as "manual-first, CI-after," not
   pretended-automatable.

---

## 3. The metadata core

### 3.1 The sidecar

`[tool.dough.metadata]` in `pyproject.toml` holds the union field set once,
version-free (version is referenced from `[project]`, never duplicated), and
schema-versioned with a `metadata_version` key the way `color_tokens` carries a
`PALETTE_VERSION`. The render engine reads this plus the seam's id projections and
the tag-resolved version.

About nine inputs drive everything; the rest are **derived**:

```
app_slug          dough
org_slug          wolfgangwarehaus
github_owner      wolfgangwarehaus
repo_name         dough
display_name      dough
summary           A frosted, cross-platform PySide6 app base
long_description  <one source, rendered to AppStream <p>/<ul>, deb body, store listing…>
license_spdx      GPL-2.0-or-later
# + version, from [project] / the tag
```

### 3.2 The projection engine — one id, many forms

A single logical identity projects into every channel's required shape. These are
*computed*, never re-literalised:

| Projection | Value (dough) | Consumed by |
|---|---|---|
| `windows_aumid` = `{org}.{app}` | `wolfgangwarehaus.dough` | Win AUMID **and** winget `PackageIdentifier` seed **and** MSIX `Identity Name` |
| `app_id_base` = `io.github.{owner}.{app}` | `io.github.wolfgangwarehaus.dough` | Flatpak manifest/metainfo/`.desktop`/icon names, deb+AppImage+AUR install paths, Wayland app_id, single-instance prefix |
| `cf_bundle_id` = `com.{org}.{app}` | `com.wolfgangwarehaus.dough` | macOS `CFBundleIdentifier`, cask `zap` |
| `homepage_url` = `github.com/{owner}/{repo}` | …/wolfgangwarehaus/dough | issues/releases/changelog/download URLs all derive |

The crux: `windows_aumid` is *already hardcoded* at `windows_shortcut.py:48`
(`APP_USER_MODEL_ID = "wolfgangwarehaus.dough"`) and is exactly `{org}.{app}` — the
same string winget and MSIX need. `app_id_base` is the single most load-bearing
value in the whole system (it's the immutable application identity, frozen once
published). The baking phase doesn't invent these — it computes them from the same
`org`/`app` the **P0 identity seam** already centralizes (see §4).

### 3.3 Field reference (the ~26-field union)

| Field | Derived? | Needed by |
|---|---|---|
| `app_slug` | input | ~everything (Qt name, all package ids, paths) |
| `org_slug` | input | winget, MSIX, Inno, AUMID, Qt org |
| `github_owner` / `repo_name` | input | deb, AppImage, winget, AUR, MSIX, pages, pipeline |
| `app_id_base` | ✓ | Flatpak, freedesktop, deb, AppImage, AUR, macOS, blur app_id, single_instance |
| `windows_aumid` | ✓ | Win AUMID, winget id, MSIX Identity Name |
| `cf_bundle_id` | ✓ | macOS bundle, cask |
| `display_name` | input | freedesktop, MSIX, Inno, winget, macOS, Qt, landing h1 |
| `generic_name` | input | `.desktop` GenericName |
| `version` | from tag | every channel + metainfo `<releases>` + landing (live-fetched) |
| `summary` | input | PyPI, metainfo, MSIX, winget ShortDescription, deb synopsis, AUR pkgdesc, cask, landing |
| `long_description` | input | PyPI long, metainfo description, winget, deb body, store listing, Flatpak, landing |
| `feature_cards[]` | input | landing 2×2 grid + metainfo `<ul>` |
| `license_spdx` | input | PyPI, metainfo project_license, AUR, deb DEP-5, winget, Flatpak, MSIX, cask |
| `license_url` | ✓ | winget, MSIX |
| `homepage_url` | ✓ | PyPI, metainfo, AUR, deb, winget, Inno, macOS, MSIX, landing |
| `maintainer_name` / `maintainer_email` | input | deb, AUR header, PyPI, Flatpak update_contact, deploy commits |
| `publisher_display_name` | input | MSIX, Inno, winget, macOS signing identity (note the space: `wolfgang warehaus`) |
| `categories[]` | input | freedesktop, deb Section, MSIX, macOS `LSApplicationCategoryType` |
| `keywords[]` | input | PyPI, freedesktop, winget Tags, MSIX |
| `icon_svg_source` | input | freedesktop, AppImage, MSIX asset matrix, Inno `.ico`, PyPI, landing, Qt icon |
| `screenshots[]` (path+caption+alt+w+h) | input | metainfo (≥1, first `type=default`), MSIX, landing, Flatpak |
| `requires_python` | input | PyPI, CI interpreter floor, Flatpak runtime |
| `entry_point` | input | PyPI gui-scripts, PyInstaller, Inno Run, MSIX, AppImage Exec |
| `runtime_deps` | input | PyPI; projected to AUR depends, deb shlib closure, Flatpak pip sources, AppImage bundling |
| `client_identity` = `{app}/{version} (+{homepage})` | ✓ | runtime User-Agent / API client strings |
| `store_secrets_of_record` | input/tracked | Inno AppId GUID (immutable), MSIX Publisher CN / PFN / Store ID — **threaded, never regenerated** |
| `kofi_handle` | input | landing tip box + metainfo `url type=donation` |

`runtime_deps` is the one genuinely app-specific block dough can't own — but the
*projections* of it (AUR depends, deb `Depends`, AppImage bundling) should be
auto-derived (`dpkg-shlibdeps`, a PyPI→Arch table, `linuxdeploy-plugin-qt`), not
hand-maintained the way jellytoast does in `XCB_DEPS_WORKLIST.md`.

---

## 4. The bridge to P0 — the identity seam

The baking phase is the *consumer* of P0 step 4's identity seam, and the research
**confirms the roadmap's "do NOT build a 7-field dataclass."** The split is clean:

- **`configure(org, app, display_name)`** carries only *runtime* identity + its
  deterministic id projections. Its one hard job is the import-time coupling:
  `design_tokens._load_font_scale` reads `QSettings("dough","dough")` at module
  import (`design_tokens.py:53`), *before* a QApplication exists — so identity
  cannot come from `applicationName()`. `configure()` routes that, plus
  `settings.py:18-19,36` and `app.py:30,89-93`, through one call, and exposes the
  lazy-read projections (`windows_aumid`, `app_id_base`, `desktop-id`) computed
  from `org`+`app`.

- **The sidecar** carries all *descriptive/store* metadata (summary, long
  description, license, categories, keywords, screenshots, publisher, the store
  GUIDs). These are static build-time fields the renderer reads — they never touch
  the running QApplication.

- **The overlap** is `org` / `app` / `display_name` / `version`: the seam exposes
  them at runtime, the sidecar/`[project]` holds them at build time, and a CI test
  (dough's analogue of `test_version_consistency.py`, extended to the id
  projections) asserts the seam's computed `app_id_base` / `windows_aumid` /
  `winget-id` / `desktop-id` match what the renderer stamped into every manifest —
  so a hand-edit that bypasses the seam fails CI.

Net: P0 step 4 and the baking phase share **one derivation, not a second config
surface.** Building the seam now, with these projections in mind, is what lets the
oven stamp every manifest from a single source later.

---

## 5. The channel matrix

| Channel | Artifact | State | Effort | Wakes on |
|---|---|---|---|---|
| **PyPI** | sdist + wheel | proven | low | OIDC (Trusted Publishing) — no secret |
| **Landing page** | static GH Pages site | proven | med | none (push to `site/**`) |
| **Loose `.deb`** | release-asset `.deb` | proven | med | none (`GITHUB_TOKEN`) |
| **AppImage** | `.AppImage` + `.zsync` | proven | med | none (`GITHUB_TOKEN`) |
| **Windows installer** | Inno setup `.exe` + portable `.zip` | proven | med | unsigned now; signs on Azure secrets |
| **winget** | 3 YAML manifests | proven (dormant) | med | `WINGET_TOKEN` + winget-pkgs fork |
| **AUR** | PKGBUILD (source) | proven (dormant) | med | `AUR_SSH_PRIVATE_KEY` (+ AUR reg reopen) |
| **MSIX / Store** | `.msix` | proven | high | manual first submit; then Store secrets |
| **Hosted apt / PPA** | signed Release/Packages | greenfield | high | `GPG_PRIVATE_KEY` + Pages |
| **macOS `.dmg` + cask** | notarized `.dmg` + tap | greenfield (**goal, dormant**) | high | Apple membership + 7 secrets + tap repo |
| **Flatpak** | flatpak-builder manifest | **policy-gated** | high | self-host remote, or skip |

### Per-channel notes

- **PyPI** — fully tokenless: `python -m build` → `twine check` →
  `gh-action-pypi-publish` on `release:[published]`, Sigstore/PEP 740 attestations
  for free. One-time pending-publisher config on the PyPI side.

- **Loose `.deb`** — `dpkg-deb` over a PyInstaller onedir under `/opt`, installs
  the `.desktop` + metainfo + hicolor icons. Templatize `control`/`copyright` (DEP-5)
  /`changelog`; auto-derive `Depends` via `dpkg-shlibdeps` instead of the hand-kept
  worklist. It's a release asset, **not** an apt channel (no `apt upgrade`/GPG trust).

- **AppImage** — build on the **oldest** runner (`ubuntu-22.04`, glibc 2.35; AppImage
  is forward- not backward-compatible), `linuxdeploy-plugin-qt` for bundling
  (replacing jellytoast's hand-rolled `ldd` walk), embed `gh-releases-zsync` update
  info, upload both files, `APPIMAGE_EXTRACT_AND_RUN=1` (no FUSE on CI).

- **Windows** — **sign order is load-bearing**: code-sign the frozen bundle (exe +
  every DLL, recursive) *first*, build the Inno installer from the already-signed
  bundle, sign the installer, then zip the portable. Azure Trusted Signing
  (~$10/mo, OV-class; EV no longer bypasses SmartScreen as of 2024), dormant until
  6 Azure secrets. **Generate the `VSVersionInfo`** the `.spec` is missing today —
  the single biggest canonical Windows gap. AppId GUID is immutable and brace-escaped.

- **winget** — treat the in-repo manifests as **disposable output**: let
  `winget-releaser`/`komac` emit the current schema (1.10) from the *published*
  asset (a draft 404s, hence `release:[released]`). No checked-in `InstallerSha256`.
  Dormant until `WINGET_TOKEN` (classic PAT, `public_repo`) + a winget-pkgs fork.

- **AUR** — source PKGBUILD built from the tag tarball (`updpkgsums` +
  regenerated `.SRCINFO`), pushed via `AUR_SSH_PRIVATE_KEY`. Add a `makepkg`+`namcap`
  CI gate. Dormant until the key exists *and* AUR new-package registration reopens
  (frozen post-2026 malware wave). depends/optdepends are table-driven PyPI→Arch.

- **MSIX / Store** — the first submission is **manual** via Partner Center (free
  individual account; `runFullTrust` cert review 1–5 days; pre-declare the
  PyInstaller-bootloader false positive). Updates automatable for *free* products.
  The Store *re-signs* at ingestion — that's the channel's value (the free
  SmartScreen fix). 4-part `pkgver` (first≠0, fourth=0), decoupled from the
  marketing version. Asset matrix is a **data-driven** size/scale/targetsize table
  rendered from `icon_svg_source` — not jellytoast's bespoke 24-file `make-assets`
  enumeration — plus the `makepri` step jellytoast omits. `is_msix_packaged()` and
  the StartupTask autostart backend are generic enough to live in dough's
  `platform_compat` / `autostart`, not per app.

- **Hosted apt / PPA** — greenfield, opt-in. `reprepro`/`aptly` → Pages with a
  GPG-signed `Release`/`InRelease` + keyring + a `signed-by=` sources line. A
  Launchpad PPA would need a *source* build (a PyInstaller bundle can't `dput`) —
  large rework, which is why jellytoast shipped the loose `.deb` instead.

- **macOS** *(a real goal — present but dormant)* — wired into the template now so
  dough is mac-ready, gated off until you have an Apple account. Full chain:
  PyInstaller `BUNDLE` (`Info.plist` `CFBundleIdentifier = com.{org}.{app}`,
  relaxed `library-validation` entitlement so PySide6 loads unsigned dylibs) → sign
  nested dylibs **bottom-up** → sign the `.app` → `create-dmg` → sign the dmg →
  `notarytool submit --wait` → `stapler staple` → compute the cask `sha256`
  *after* stapling → `action-homebrew-bump-cask` to a **separate** `homebrew-<tap>`
  repo (`HOMEBREW_TAP_TOKEN` — `GITHUB_TOKEN` can't cross-repo). Activation cost:
  $99/yr Apple Developer membership, a macOS runner, 7 secrets, the tap repo. The
  metadata core already carries the mac fields, so flipping it on needs no
  re-derivation.

- **Flatpak** *(policy-gated)* — **skip flathub.org.** Flathub's Generative-AI ban
  (effective 2026-05-29) makes a `Co-Authored-By: Claude` commit lineage
  presumptively disqualifying — the exact reason jellytoast retired the channel.
  We still *generate* the `metainfo.xml` / `.desktop` / icon set, because the deb
  and AppImage builds consume them; the full flatpak-builder manifest stays in the
  template but is **retargetable to a self-hosted flat-manager remote**
  (`flatpak remote-add wolfgangwarehaus …`), never aimed at Flathub. If a future
  app ships a clean, non-AI-lineage history, the same manifest can submit upstream.

---

## 6. The release pipeline

### 6.1 The two-phase model (lift verbatim from jellytoast)

The load-bearing design. Do **not** collapse it into one tag-triggered workflow —
the draft + human gate + wait-for-public-asset semantics are *why* it works.

```
PHASE 1  — on push, tags: v*
  release.yml: resolve version from the tag → dough bake (render manifests)
    → build every artifact family in parallel → smoke-test → Sigstore provenance
    → create a DRAFT GitHub Release (SHA256SUMS + CHANGELOG-curated notes)
  release-checklist.yml: open the propagation checklist issue

  ── a human reviews the draft and clicks Publish ──   ← the one deliberate gate

PHASE 2  — on the release event
  release:[published]  → OIDC/tokenless channels        (PyPI)
  release:[released]   → channels that DOWNLOAD the asset (winget, AUR)
                         (these must wait — a draft asset 404s)
```

### 6.2 Dynamic versioning

`pyproject.toml` declares `dynamic = ["version"]` with `setuptools-scm` writing
`dough/_version.py`; runtime `__version__` reads it. Cutting a release is
**`git tag vX.Y.Z && git push --tags`** — there is no version to stamp in N files
and therefore no version-drift class to gate against. CI resolves the version once
(`${GITHUB_REF_NAME#v}`, factored into a `resolve-version` composite action rather
than pasted into three jobs) and injects it into the version-bearing fields
(`winget InstallerUrl`, `metainfo <releases>`, the 4-part Windows/MSIX numbers) at
render time. The only human pre-tag step is moving the CHANGELOG `[Unreleased]`
section to the release — which the curated-notes extractor then reads.

### 6.3 Robustness machinery (templatize, don't reinvent)

CHANGELOG-driven curated notes (awk on `## [VERSION]`, a `<!-- release-notes-end -->`
sentinel, a UTF-8-safe length backstop, `--generate-notes` fallback for `-rc`/`-test`
tags); create-or-update + `--clobber` idempotency (re-runs and re-pushed tags never
fail with "already exists"); bare-version asset naming; `SHA256SUMS` over all assets;
the auto-opened propagation checklist via a narrow `envsubst`. `pages.yml` stays
**decoupled** (push to `main`, `paths: site/**`, *not* tags) so a docs edit deploys
without a release, and the landing page fetches the version live from
`/releases/latest`.

### 6.4 Secrets contract

A generated `docs/SECRETS.md` table, every workflow shipping with named
placeholders + skip-if-unset guards:

| Channel | Secrets | Auth model |
|---|---|---|
| PyPI, Sigstore | — | OIDC |
| Windows signing | `AZURE_TENANT_ID`,`CLIENT_ID`,`CLIENT_SECRET`,`SIGNING_ENDPOINT`,`SIGNING_ACCOUNT`,`SIGNING_PROFILE` | Azure Trusted Signing |
| AUR | `AUR_SSH_PRIVATE_KEY` | git-over-SSH |
| winget | `WINGET_TOKEN` (classic PAT) + fork | komac PR |
| MSIX updates | `AZURE_AD_TENANT_ID`,`CLIENT_ID`,`SECRET`,`SELLER_ID` + Store ID | msstore CLI |
| macOS | `MACOS_CERTIFICATE`,`_PWD`,`MACOS_KEYCHAIN_PWD`,`APPLE_ID`,`APPLE_APP_SPECIFIC_PASSWORD`,`APPLE_TEAM_ID` + `HOMEBREW_TAP_TOKEN` | Developer ID + notarytool |
| Hosted apt | `GPG_PRIVATE_KEY`,`GPG_PASSPHRASE` | GPG |

---

## 7. Templated `packaging/` layout

`dough bake <name>` walks every `*.j2`, substitutes from `[tool.dough.metadata]` +
the seam projections + the tag-resolved version, and writes a fully-wired tree —
one command from fork to installable.

> **As built (Beat 2):** the template tree mirrors the OUTPUT 1:1 — a `*.j2`
> renders (filename + body) to the same relative path under `packaging/`, minus
> `.j2`. So the freedesktop pair lives at `packaging/templates/{{app_id_base}}.*.j2`
> (→ `packaging/` root, where the build scripts read them), not under a
> `freedesktop/` group. The sketch below keeps the cosmetic grouping for reading;
> the renderer's rule is "templates/ mirrors packaging/", which makes the
> generate-then-verify diff trivial. PyPI is sdist/wheel from the dynamic version,
> so it has no template — only the publish workflow.

```
pyproject.toml                      # [tool.dough.metadata] — the one source
packaging/
  templates/
    freedesktop/  {{app_id_base}}.metainfo.xml.j2   {{app_id_base}}.desktop.j2
    flatpak/      {{app_id_base}}.yaml.j2            # self-host / reuse only
    deb/          build_deb.sh.j2  control.j2  copyright.j2  changelog.j2
    aur/          PKGBUILD.j2
    windows/      {{app_slug}}.iss.j2  {{app_slug}}.spec.j2  version_info.txt.j2
    msix/         AppxManifest.xml.j2  make-assets.j2  STORE-SUBMISSION.md.j2
    macos/        {{app_slug}}.spec.j2  entitlements.plist  {{app_slug}}.rb.j2
    site/         index.html.j2  privacy.html.j2  README.md.j2
  metadata.schema.toml              # schema-versioned validation
.github/
  workflows/  release.yml.j2  pypi-publish.yml.j2  aur.yml.j2  winget.yml.j2
              pages.yml.j2  release-checklist.yml.j2
  actions/resolve-version/
dev/cut_release.sh.j2               # thin: changelog + tag + push
docs/  RELEASING.md.j2  SECRETS.md.j2
tests/ test_identity_consistency.py.j2   # render-diff gate
```

---

## 8. Build sequencing

Three buckets, mapped onto the dough roadmap:

1. **Lift-and-templatize (proven in jellytoast — just parameterize the literals):**
   PyPI, loose `.deb`, AppImage, Windows Inno+PyInstaller, winget, MSIX, the landing
   page, and the whole orchestration spine. The fastest path to "installable on day
   one."

2. **Build fresh as a framework capability (jellytoast hand-rolled per-channel; dough
   makes it shared data):** the single metadata source, the id-projection engine,
   the generate-then-verify renderer, the data-driven icon/asset matrix, auto-derived
   deb `Depends` + table-driven AUR depends, `linuxdeploy-plugin-qt` bundling, and
   the missing Windows `VSVersionInfo`.

3. **Greenfield / dormant:** macOS (`.dmg` + cask — a stated goal, wired but gated on
   Apple secrets), a hosted signed apt repo, and the self-host/skip Flatpak branch.

**Prerequisite for all of it: P0 step 4 (the identity seam).** The oven can't stamp
a single manifest until `org`/`app`/`display_name` and their projections live in one
place. Finish P0 — including designing `configure()` against §4 — and the proven tier
(bucket 1) becomes mostly a templatize-the-literals exercise over code that already
ships in jellytoast.

---

## 9. Per-fork setup (what a new app fills in)

Most of a fork is `org`/`app`/`display_name` + the descriptive fields. A handful of
values are **single-instance identity that must be tracked, never regenerated**, and
never cross-contaminated between apps:

- **Inno `AppId` GUID** — `dough bake` generates a fresh `uuid4` for a new fork; it is
  immutable thereafter (changing it orphans installed users from upgrades).
- **MSIX `Publisher CN` / PFN / Store ID** — Partner-Center-issued; left as blank
  placeholders the forker fills after registration.
- **macOS `Team ID`** — from the Apple Developer account.
- **Publisher canonicalization** — one `maintainer_name`, one
  `publisher_display_name` (the spaced `wolfgang warehaus` is a *display variant*,
  not a third source). Resolve jellytoast's three-string drift at the source.

---

## 10. Status

Spec only — no code yet. Gated behind **P0** (the identity seam is the prerequisite).
When P0 lands, start bucket 1 (proven tier) behind the dormancy guards, keep macOS
present-but-dormant, and skip Flathub. See `docs/ROADMAP.md` for P0, and
`docs/PHILOSOPHY.md` "Batteries, templated" for the original promise this delivers.
