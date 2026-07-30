import unittest

from config import ConfigError, validate_companies


class ConfigTests(unittest.TestCase):
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
