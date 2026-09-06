# ManifestGuard — Local MVP Scaffold Plan

## Goal of this MVP

Prove the core value with zero infra: **given a directory tree representing an
iOS app + its vendored/third-party SDK source, detect "required reason API"
usage, compare it against any existing `PrivacyInfo.xcprivacy` manifest(s),
report what's undeclared, and auto-generate a starter manifest for the gaps.**

Everything else in the pitch (SaaS dashboard, CI bot, App Store Connect
polling, continuous re-scan on SDK bumps, auth, billing, hosting) is
downstream of this detection engine working correctly. If the detector and
manifest generator/validator are correct on a local sample project, the rest
is plumbing, not risk.

## 1. Stack choice

**Python 3, standard library only.** No npm/pip install step, no build,
single-file-friendly, and critically: `plistlib` (stdlib) reads/writes
`.xcprivacy` files natively since they're just XML property lists — this
removes the one piece of the problem that would otherwise need a third-party
dependency (Node would need an npm plist package; Go would need a plist
library too). `re`, `pathlib`, `argparse`, `json`, `unittest` cover everything
else needed for a static text/source scanner and a CLI.

Rejected alternatives:
- Node/TS CLI — viable, but adds a plist dependency and a build/install step
  for no added capability at MVP stage.
- Go single binary — nice for distribution later, but no stdlib plist
  support and slower to iterate on regex/rule tweaks during MVP.

## 2. Explicitly out of scope for this local MVP

- **No real Mach-O binary / compiled framework scanning.** Real ManifestGuard
  would eventually run `strings`/symbol-table analysis on compiled
  `.xcframework`/`.a` binaries. That's a distinct, higher-effort capability
  (binary parsing, symbol demangling) and isn't needed to prove the
  detection/reporting/generation logic. MVP scans **source text** (`.swift`,
  `.m`, `.h`) in a sample fixture tree instead. This is the single biggest
  scope cut — flagged clearly so it's not mistaken for "done."
- **No SaaS dashboard / web server / database.** CLI output (human table +
  `--json`) is the entire interface.
- **No auth, accounts, or billing.** Not needed to demonstrate scanning value.
- **No hosting/deploy.** Runs from a local checkout.
- **No CI integration** (GitHub Actions, Bitrise plugin, etc.) — just the CLI
  invoked manually. A CI wrapper is a thin shell around the same CLI later.
- **No App Store Connect API integration** (upload-rejection polling).
- **No CocoaPods/SPM/Carthage dependency-graph resolution.** MVP scans
  whatever directory tree it's pointed at (a fixture simulating app +
  vendored SDKs); real dependency resolution is a separate, later feature.
- **No "continuous re-scan on SDK version bump."** That's a scheduler/webhook
  feature on top of a single-shot scan — single-shot scan is what's being
  proven here.

None of these cuts block demonstrating the core value: detect undeclared
required-reason API usage and produce/validate a manifest.

## 3. File / directory layout

```
manifestguard/
  manifestguard.py              # CLI entry point (argparse: scan, generate, validate)
  rules/
    required_reason_apis.json   # symbol -> Apple required-reason category mapping
  fixtures/
    sample_app/
      App/
        Sources/AppDelegate.swift        # uses one required-reason API directly
        PrivacyInfo.xcprivacy             # main app's existing manifest (incomplete on purpose)
      Vendor/
        AwesomeAdsSDK/
          AwesomeAdsSDK.m                 # uses UserDefaults + file timestamp APIs
          # (no PrivacyInfo.xcprivacy here — simulates an undeclared vendored SDK)
        AnalyticsKit/
          AnalyticsKit.swift              # uses disk-space API
          PrivacyInfo.xcprivacy           # present but missing one required reason
  tests/
    test_scanner.py              # unit tests over the fixture, run via unittest
plan.md
```

- `manifestguard.py` commands:
  - `scan <path>` — walk the tree, flag required-reason API usage per
    file/module, cross-reference existing manifests, print a table (or
    `--json`) of undeclared usages.
  - `generate <path> [--out FILE]` — emit a starter `PrivacyInfo.xcprivacy`
    covering the APIs detected under `<path>`.
  - `validate <manifest> <path>` — check an existing manifest's declared
    reasons against what's actually detected in `<path>`, report gaps.
- `rules/required_reason_apis.json` — small hand-curated table (symbol regex
  → API category → allowed reason codes), sourced from Apple's published
  required-reason API categories (UserDefaults, File timestamp, Disk space,
  System boot time, Active keyboard).

## 4. Verification plan

No test infra beyond stdlib `unittest` — no separate test runner to install.

Manual run-through:
```
python manifestguard.py scan fixtures/sample_app
python manifestguard.py scan fixtures/sample_app --json
python manifestguard.py generate fixtures/sample_app/Vendor/AwesomeAdsSDK \
    --out /tmp/PrivacyInfo.generated.xcprivacy
python manifestguard.py validate fixtures/sample_app/Vendor/AnalyticsKit/PrivacyInfo.xcprivacy \
    fixtures/sample_app/Vendor/AnalyticsKit
```
Expected observable results:
- `scan` flags `AwesomeAdsSDK` (UserDefaults + file timestamp usage, no
  manifest at all) and flags `AnalyticsKit` (disk-space usage present in code
  but missing from its existing manifest's declared reasons).
- `generate` produces a file that `plistlib.load()` can parse without error
  and that contains an `NSPrivacyAccessedAPITypes` entry for each API
  category actually detected in that subtree.
- `validate` exits non-zero and lists the specific missing reason(s) for
  `AnalyticsKit`.

Automated:
```
python -m unittest discover tests
```
- `test_scanner.py` asserts the scanner returns the exact expected set of
  (file, API category) tuples for the fixture tree — this is the golden-file
  check that the detection logic itself is correct, independent of CLI
  formatting.
- A second test round-trips `generate`'s output through `plistlib.load()` and
  asserts the expected categories are present, proving the generator emits a
  structurally valid, Apple-schema-shaped manifest.
