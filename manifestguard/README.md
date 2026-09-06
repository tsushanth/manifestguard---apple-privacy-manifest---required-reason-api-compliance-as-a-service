# ManifestGuard (local MVP)

A CLI that scans an iOS app's source tree (app code + vendored/third-party
SDK source) for Apple "required reason API" usage — `UserDefaults`, file
timestamps, disk space, system boot time, active keyboard — and
cross-references it against `PrivacyInfo.xcprivacy` manifests, so you can
catch undeclared usage before an App Store Connect binary upload gets
rejected.

This is the local, zero-infra MVP described in `../plan.md`: a detection
engine, not the eventual SaaS/CI product. It scans **source text**
(`.swift`, `.m`, `.h`) rather than compiled binaries — see "Scope" below.

## Requirements

Python 3, standard library only. No install step.

## Commands

```
python3 manifestguard.py scan <path> [--json]
python3 manifestguard.py generate <path> [--out FILE]
python3 manifestguard.py validate <manifest> <path>
```

- **scan** — walks `<path>`, detects required-reason API usage per module
  (grouped by the nearest enclosing `PrivacyInfo.xcprivacy`, or by its own
  directory if no manifest covers it), and reports what's undeclared or
  declared without a valid reason code. Prints a table by default, or
  `--json` for machine-readable output. Exits `1` if any gaps are found,
  `0` if clean — so it's CI-friendly.
- **generate** — scans `<path>` as a single unit and writes a starter
  `PrivacyInfo.xcprivacy` covering every required-reason category detected
  in it. Defaults to `<path>/PrivacyInfo.generated.xcprivacy`.
- **validate** — checks an existing manifest's declared reasons against
  what's actually detected in `<path>`, lists specific gaps, and exits
  non-zero if any exist.

## Try it against the bundled fixture

`fixtures/sample_app` simulates an app with two vendored SDKs:
`AwesomeAdsSDK` (uses `UserDefaults` + a file-timestamp API, ships **no**
manifest at all) and `AnalyticsKit` (uses a disk-space API, ships a manifest
that declares the `DiskSpace` category but with no valid reason code).

```
python3 manifestguard.py scan fixtures/sample_app
python3 manifestguard.py scan fixtures/sample_app --json

python3 manifestguard.py generate fixtures/sample_app/Vendor/AwesomeAdsSDK \
    --out /tmp/PrivacyInfo.generated.xcprivacy

python3 manifestguard.py validate \
    fixtures/sample_app/Vendor/AnalyticsKit/PrivacyInfo.xcprivacy \
    fixtures/sample_app/Vendor/AnalyticsKit
```

`scan` should flag both `AwesomeAdsSDK` (fully undeclared) and
`AnalyticsKit` (declared category, missing a valid reason), and leave the
main `App` module clean. `generate` should write a manifest that
`plistlib.load()` can parse, containing one entry per detected category.
`validate` should exit non-zero and print the specific missing reason for
`AnalyticsKit`.

## Rules

`rules/required_reason_apis.json` is a small hand-curated table mapping
source-level symbols/APIs to Apple's required-reason API categories and
their allowed reason codes.

## Tests

```
python3 -m unittest discover tests
```

Asserts the scanner returns the exact expected categories per fixture file
and module, and that `generate`'s output round-trips through `plistlib`
with the expected categories present.

## Scope

This MVP proves the detection/reporting/generation logic on a source-text
fixture. It does **not** do compiled Mach-O/`.xcframework` binary scanning,
does not resolve CocoaPods/SPM/Carthage dependency trees, and has no
dashboard, CI integration, auth, or App Store Connect polling — see
`../plan.md` for what's explicitly out of scope and why.
