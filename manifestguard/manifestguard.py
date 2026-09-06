#!/usr/bin/env python3
"""ManifestGuard: detect Apple "required reason API" usage in iOS source
trees and cross-reference it against PrivacyInfo.xcprivacy manifests.

Commands:
    scan <path>                          walk a tree, report undeclared usage
    generate <path> [--out FILE]         emit a starter manifest for a tree
    validate <manifest> <path>           check a manifest against a tree
"""

import argparse
import json
import plistlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RULES_PATH = ROOT / "rules" / "required_reason_apis.json"
MANIFEST_NAME = "PrivacyInfo.xcprivacy"
SOURCE_EXTENSIONS = {".swift", ".m", ".h"}


def load_rules(path=RULES_PATH):
    """Load the required-reason API rule table and compile its symbol regexes."""
    with open(path, "r") as f:
        raw = json.load(f)
    rules = {}
    for category, spec in raw.items():
        rules[category] = {
            "api_type": spec["api_type"],
            "patterns": [re.compile(p) for p in spec["symbols"]],
            "allowed_reasons": spec["allowed_reasons"],
        }
    return rules


def iter_source_files(root):
    for path in sorted(root.rglob("*")):
        if path.is_file() and path.suffix in SOURCE_EXTENSIONS:
            yield path


def categories_in_text(text, rules):
    found = set()
    for category, spec in rules.items():
        if any(p.search(text) for p in spec["patterns"]):
            found.add(category)
    return found


def scan_file(path, rules):
    text = path.read_text(encoding="utf-8", errors="ignore")
    return categories_in_text(text, rules)


def scan_tree_categories(root, rules):
    """All required-reason categories detected anywhere under root."""
    categories = set()
    for path in iter_source_files(root):
        categories |= scan_file(path, rules)
    return categories


def nearest_manifest_dir(file_path, root):
    """Nearest ancestor of file_path (down to root, inclusive) containing a manifest."""
    d = file_path.parent
    while True:
        if (d / MANIFEST_NAME).is_file():
            return d
        if d == root:
            return None
        d = d.parent


def build_modules(root, rules):
    """Group source files under root into modules keyed by the manifest that
    applies to them (nearest enclosing PrivacyInfo.xcprivacy), falling back
    to the file's own directory when no manifest applies anywhere above it.
    Returns {module_dir: {"detected": set(categories), "manifest_path": Path|None}}.
    """
    modules = {}
    for path in iter_source_files(root):
        manifest_dir = nearest_manifest_dir(path, root)
        module_key = manifest_dir if manifest_dir is not None else path.parent
        module = modules.setdefault(
            module_key,
            {
                "detected": set(),
                "manifest_path": (module_key / MANIFEST_NAME) if manifest_dir else None,
            },
        )
        module["detected"] |= scan_file(path, rules)
    return modules


def parse_manifest(manifest_path):
    """Return {api_type: [reasons]} declared in a PrivacyInfo.xcprivacy file."""
    with open(manifest_path, "rb") as f:
        plist = plistlib.load(f)
    declared = {}
    for entry in plist.get("NSPrivacyAccessedAPITypes", []):
        api_type = entry.get("NSPrivacyAccessedAPIType")
        reasons = entry.get("NSPrivacyAccessedAPITypeReasons", [])
        if api_type:
            declared[api_type] = list(reasons)
    return declared


def compute_gaps(detected_categories, declared, rules):
    """Compare detected categories against a declared {api_type: [reasons]} map.

    Returns a list of gap dicts, each either:
      {"category": ..., "status": "undeclared"}
      {"category": ..., "status": "missing_reason", "declared_reasons": [...]}
    """
    gaps = []
    for category in sorted(detected_categories):
        spec = rules[category]
        api_type = spec["api_type"]
        allowed = set(spec["allowed_reasons"])
        if api_type not in declared:
            gaps.append({"category": category, "status": "undeclared"})
            continue
        declared_reasons = set(declared[api_type])
        if not declared_reasons & allowed:
            gaps.append(
                {
                    "category": category,
                    "status": "missing_reason",
                    "declared_reasons": sorted(declared_reasons),
                }
            )
    return gaps


def build_manifest_plist(categories, rules):
    """Build a starter PrivacyInfo.xcprivacy plist dict for detected categories."""
    api_types = []
    for category in sorted(categories):
        spec = rules[category]
        api_types.append(
            {
                "NSPrivacyAccessedAPIType": spec["api_type"],
                "NSPrivacyAccessedAPITypeReasons": [spec["allowed_reasons"][0]],
            }
        )
    return {
        "NSPrivacyTracking": False,
        "NSPrivacyTrackingDomains": [],
        "NSPrivacyCollectedDataTypes": [],
        "NSPrivacyAccessedAPITypes": api_types,
    }


def relpath(path, root):
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def cmd_scan(args):
    rules = load_rules()
    root = Path(args.path).resolve()
    modules = build_modules(root, rules)

    rows = []
    for module_dir in sorted(modules, key=lambda p: relpath(p, root)):
        module = modules[module_dir]
        declared = parse_manifest(module["manifest_path"]) if module["manifest_path"] else {}
        gaps = compute_gaps(module["detected"], declared, rules)
        for gap in gaps:
            rows.append({"module": relpath(module_dir, root), **gap})

    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        if not rows:
            print("No gaps found.")
        else:
            header = f"{'MODULE':<30} {'CATEGORY':<16} {'STATUS':<15} DETAIL"
            print(header)
            print("-" * len(header))
            for row in rows:
                detail = ""
                if row["status"] == "undeclared":
                    detail = "no PrivacyInfo.xcprivacy declares this category"
                elif row["status"] == "missing_reason":
                    detail = f"declared reasons {row['declared_reasons']} don't include an allowed reason"
                print(f"{row['module']:<30} {row['category']:<16} {row['status']:<15} {detail}")
            print(f"\n{len(rows)} gap(s) found.")

    return 1 if rows else 0


def cmd_generate(args):
    rules = load_rules()
    path = Path(args.path).resolve()
    categories = scan_tree_categories(path, rules)
    plist = build_manifest_plist(categories, rules)

    out_path = Path(args.out) if args.out else path / f"{Path(MANIFEST_NAME).stem}.generated.xcprivacy"
    with open(out_path, "wb") as f:
        plistlib.dump(plist, f)

    print(f"Wrote {out_path} covering: {', '.join(sorted(categories)) or '(no required-reason APIs detected)'}")
    return 0


def cmd_validate(args):
    rules = load_rules()
    manifest_path = Path(args.manifest).resolve()
    path = Path(args.path).resolve()

    declared = parse_manifest(manifest_path)
    detected = scan_tree_categories(path, rules)
    gaps = compute_gaps(detected, declared, rules)

    if not gaps:
        print(f"OK: {manifest_path} covers all detected required-reason API usage under {path}")
        return 0

    print(f"{len(gaps)} gap(s) in {manifest_path}:")
    for gap in gaps:
        if gap["status"] == "undeclared":
            print(f"  - {gap['category']}: not declared at all")
        else:
            print(
                f"  - {gap['category']}: declared reasons {gap['declared_reasons']} "
                "don't include an allowed reason"
            )
    return 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scan iOS source trees for undeclared required-reason API usage.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Scan a tree and report undeclared required-reason API usage.")
    p_scan.add_argument("path")
    p_scan.add_argument("--json", action="store_true", help="Print results as JSON instead of a table.")
    p_scan.set_defaults(func=cmd_scan)

    p_generate = sub.add_parser("generate", help="Generate a starter PrivacyInfo.xcprivacy for a tree.")
    p_generate.add_argument("path")
    p_generate.add_argument("--out", help="Output file path (default: <path>/PrivacyInfo.generated.xcprivacy)")
    p_generate.set_defaults(func=cmd_generate)

    p_validate = sub.add_parser("validate", help="Validate an existing manifest against a tree.")
    p_validate.add_argument("manifest")
    p_validate.add_argument("path")
    p_validate.set_defaults(func=cmd_validate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
