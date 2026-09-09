import json
import unittest
from pathlib import Path

from config import ConfigError, validate_companies, validate_profile


class ConfigTests(unittest.TestCase):
    def test_exclusion_settings_reject_non_booleans(self):
        profile = json.loads((Path(__file__).resolve().parents[1] / "profile.json").read_text())
        validate_profile(profile)
        for key in ("exclude_doctoral_training", "exclude_experimental_roles"):
            for value in ("false", 1, None):
                with self.subTest(key=key, value=value), self.assertRaises(ConfigError):
                    validate_profile(dict(profile, **{key: value}))

    def test_academic_source_is_valid(self):
        validate_companies(
            [
                {
                    "company": "CHARMM-GUI Jobs",
                    "source_type": "charmm_gui",
                    "url": "https://example.org/jobs",
                    "enabled": True,
                }
            ]
        )

    def test_restricted_source_must_be_disabled(self):
        with self.assertRaises(ConfigError):
            validate_companies(
                [
                    {
                        "company": "Restricted Board",
                        "source_type": "restricted",
                        "url": "https://example.org/jobs",
                        "enabled": True,
                    }
                ]
            )


if __name__ == "__main__":
    unittest.main()
