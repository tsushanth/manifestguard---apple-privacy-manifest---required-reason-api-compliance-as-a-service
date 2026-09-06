import plistlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import manifestguard as mg

FIXTURE_ROOT = Path(__file__).resolve().parent.parent / "fixtures" / "sample_app"


class TestScanner(unittest.TestCase):
    def setUp(self):
        self.rules = mg.load_rules()

    def test_detects_expected_categories_per_file(self):
        app_delegate = FIXTURE_ROOT / "App" / "Sources" / "AppDelegate.swift"
        ads_sdk = FIXTURE_ROOT / "Vendor" / "AwesomeAdsSDK" / "AwesomeAdsSDK.m"
        analytics = FIXTURE_ROOT / "Vendor" / "AnalyticsKit" / "AnalyticsKit.swift"

        self.assertEqual(mg.scan_file(app_delegate, self.rules), {"UserDefaults"})
        self.assertEqual(
            mg.scan_file(ads_sdk, self.rules), {"UserDefaults", "FileTimestamp"}
        )
        self.assertEqual(mg.scan_file(analytics, self.rules), {"DiskSpace"})

    def test_build_modules_groups_by_nearest_manifest(self):
        modules = mg.build_modules(FIXTURE_ROOT, self.rules)
        keyed = {mg.relpath(k, FIXTURE_ROOT): v for k, v in modules.items()}

        self.assertIn("App", keyed)
        self.assertEqual(keyed["App"]["detected"], {"UserDefaults"})
        self.assertIsNotNone(keyed["App"]["manifest_path"])

        ads_key = str(Path("Vendor") / "AwesomeAdsSDK")
        self.assertIn(ads_key, keyed)
        self.assertEqual(keyed[ads_key]["detected"], {"UserDefaults", "FileTimestamp"})
        self.assertIsNone(keyed[ads_key]["manifest_path"])

        analytics_key = str(Path("Vendor") / "AnalyticsKit")
        self.assertIn(analytics_key, keyed)
        self.assertEqual(keyed[analytics_key]["detected"], {"DiskSpace"})
        self.assertIsNotNone(keyed[analytics_key]["manifest_path"])

    def test_scan_flags_awesome_ads_and_analytics_kit_but_not_app(self):
        modules = mg.build_modules(FIXTURE_ROOT, self.rules)
        gaps_by_module = {}
        for module_dir, module in modules.items():
            declared = (
                mg.parse_manifest(module["manifest_path"]) if module["manifest_path"] else {}
            )
            gaps = mg.compute_gaps(module["detected"], declared, self.rules)
            gaps_by_module[mg.relpath(module_dir, FIXTURE_ROOT)] = gaps

        self.assertEqual(gaps_by_module["App"], [])

        ads_key = str(Path("Vendor") / "AwesomeAdsSDK")
        ads_categories = {g["category"] for g in gaps_by_module[ads_key]}
        self.assertEqual(ads_categories, {"UserDefaults", "FileTimestamp"})
        self.assertTrue(all(g["status"] == "undeclared" for g in gaps_by_module[ads_key]))

        analytics_key = str(Path("Vendor") / "AnalyticsKit")
        self.assertEqual(len(gaps_by_module[analytics_key]), 1)
        self.assertEqual(gaps_by_module[analytics_key][0]["category"], "DiskSpace")
        self.assertEqual(gaps_by_module[analytics_key][0]["status"], "missing_reason")

    def test_generate_produces_valid_plist_with_expected_categories(self):
        ads_sdk_dir = FIXTURE_ROOT / "Vendor" / "AwesomeAdsSDK"
        categories = mg.scan_tree_categories(ads_sdk_dir, self.rules)
        plist = mg.build_manifest_plist(categories, self.rules)

        with tempfile.NamedTemporaryFile(suffix=".xcprivacy") as tmp:
            with open(tmp.name, "wb") as f:
                plistlib.dump(plist, f)
            with open(tmp.name, "rb") as f:
                loaded = plistlib.load(f)

        api_types = {
            entry["NSPrivacyAccessedAPIType"] for entry in loaded["NSPrivacyAccessedAPITypes"]
        }
        self.assertEqual(
            api_types,
            {
                "NSPrivacyAccessedAPICategoryUserDefaults",
                "NSPrivacyAccessedAPICategoryFileTimestamp",
            },
        )
        for entry in loaded["NSPrivacyAccessedAPITypes"]:
            self.assertTrue(len(entry["NSPrivacyAccessedAPITypeReasons"]) >= 1)

    def test_validate_reports_missing_reason_for_analytics_kit(self):
        manifest_path = FIXTURE_ROOT / "Vendor" / "AnalyticsKit" / "PrivacyInfo.xcprivacy"
        path = FIXTURE_ROOT / "Vendor" / "AnalyticsKit"

        declared = mg.parse_manifest(manifest_path)
        detected = mg.scan_tree_categories(path, self.rules)
        gaps = mg.compute_gaps(detected, declared, self.rules)

        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["category"], "DiskSpace")
        self.assertEqual(gaps[0]["status"], "missing_reason")
        self.assertEqual(gaps[0]["declared_reasons"], [])


if __name__ == "__main__":
    unittest.main()
