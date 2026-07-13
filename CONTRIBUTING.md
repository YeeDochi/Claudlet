# Contributing to claudlet

**English** | [한국어](CONTRIBUTING.ko.md)

Thanks for considering it — fixes, docs, and platform reports are all welcome.
**Ongoing macOS testing** is especially valuable, since the maintainer has no
Mac (see below).

## Dev setup

```bash
git clone https://github.com/YeeDochi/Claudlet.git
cd Claudlet
pip install -e . pytest
# macOS only, for the window-integration bits:
pip install pyobjc-framework-Quartz
```

An editable install (`-e .`) means your changes take effect immediately. This
is different from `pipx install claudlet`, which copies the package into an
isolated venv that only updates on a fresh `pipx upgrade`/`pipx install
--force` — don't try to hand-edit that copy.

Run a pet from the checkout, and point your own Claude Code at it:
```bash
claudlet             # launch a standalone pet from this checkout
claudlet-install     # register hooks + the /claudlet skill, so a real session drives it
```

## Running tests

```bash
pytest
```
`tests/conftest.py` puts `src/` on `sys.path`, so this works straight from a
checkout, no install needed. There's no CI test workflow yet — the only
GitHub Action (`publish.yml`) builds and uploads to PyPI on a version tag — so
please run the suite locally before opening a PR.

## Code style

- No comments explaining *what* code does — only *why*, and only when it's
  not obvious from the code itself. `state_engine.py` is the house style to
  match: terse, why-not-what.
- `state_engine.py` is deliberately Qt-free and takes `now` as an explicit
  argument instead of reading the wall clock, so it stays pure and
  unit-testable without a display. Keep new engine logic in that shape.
- Platform-specific code stays isolated per OS (`windows_win32.py`,
  `windows_macos.py`, `focus.py` dispatching by host) — avoid scattering
  `sys.platform` checks through shared modules.

## Branches & commits

- `develop` is the working branch — PRs target `develop`, not `master`.
- `master` only ever holds released tags (`scripts/release.sh` fast-forwards
  it on release) — don't commit to it directly.
- Commit messages follow Conventional Commits: `type(scope): summary`
  (`feat`, `fix`, `docs`, `chore`, …) — see `git log` for real examples.
- Cutting a release (version bump, tag, publish) is maintainer-only, via
  `scripts/release.sh` — contributors don't need to touch versioning.

## What's most needed right now

**Ongoing macOS testing.** All three platforms are hardware-verified as of
v1.0.0, but the maintainer has no Mac — so the macOS window-integration path
(`src/claudlet/windows_macos.py`, wired into `pet.py`) is only checked on real
hardware by contributors, which means macOS-specific regressions tend to surface
after a release. Retesting on new macOS versions and reporting anything off
(perch offsets, occlusion, click-to-focus) stays especially valuable. See
**[macOS notes](docs/platform.md#macos-notes)** for the Screen Recording
permission gotcha and `claudlet-macos-diag` troubleshooting.

## Reporting bugs / requesting features

Open a GitHub issue. Please include your OS, the output of `claudlet-version`,
and — for pet-behavior bugs — which Claude Code hook events were involved if
you know them. There's no built-in event log yet, so precise repro steps help
a lot.

## License

By contributing you agree your changes are licensed under the project's
**MIT** license (code) — see [LICENSE](LICENSE). Creature artwork is **CC0**
([NOTICE](NOTICE)); new art contributions should be CC0 too.
