# Changelog

All notable changes to trackerkeeper are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/) and **the git tag is the version** (setuptools-scm).

Cutting a release moves the `[Unreleased]` section below into a dated
`[X.Y.Z]` heading, then `git tag vX.Y.Z`. `release.yml` lifts that section verbatim
into the GitHub release notes (falling back to auto-generated notes if the tag has
no matching section). See `docs/RELEASING.md`.

## [Unreleased]

### Added
- The baking phase: a single metadata source (`[tool.trackerkeeper.metadata]`), the
  `trackerkeeper bake` renderer, and the first channels — PyPI, a loose `.deb`, and an
  AppImage — generated from one source and verified against drift.

<!-- release-notes-end -->
