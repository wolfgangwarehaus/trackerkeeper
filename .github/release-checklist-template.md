# Release ${TAG} — propagation checklist

Auto-opened by `release-checklist.yml` on the `${TAG}` tag. Tick each channel as
it propagates. See `docs/RELEASING.md`.

## Automated — verify
- [ ] **GitHub release** drafted by `release.yml` — `.deb`, AppImage + `.zsync`, sdist/wheel, `SHA256SUMS`, Sigstore attestations
- [ ] Cross-distro **smoke tests** green (deb + AppImage self-containment)
- [ ] **Review the draft** and click **Publish** ← the one human gate
- [ ] **PyPI** — `pypi-publish.yml` uploaded `${V}`: https://pypi.org/project/dough/${V}/
- [ ] Provenance verifies: `gh attestation verify <asset> --repo wolfgangwarehaus/dough`

## Dormant / deferred — light up when configured (docs/TODO.md)
- [ ] **AUR** — `aur.yml` pushed `dough ${V}` (needs `AUR_SSH_PRIVATE_KEY` + AUR registration)
- [ ] **winget / MSIX / Windows Inno** — deferred (no Windows channel yet)
- [ ] **macOS cask** — deferred (needs an Apple Developer account)

## Housekeeping
- [ ] `docs/CHANGELOG.md`: the `[${V}]` section is dated + accurate
- [ ] `[Unreleased]` reset to empty for the next cycle
