import unittest

from sources import parse_rss_xml


class SourceTests(unittest.TestCase):
    def test_rss_parser(self):
        xml = """<?xml version='1.0'?>
        <rss version='2.0'><channel><item>
          <title>Postdoctoral Researcher in Molecular Simulation</title>
          <link>https://example.org/job/1</link>
          <description><![CDATA[<p>Use molecular dynamics and DFT.</p>]]></description>
        </item></channel></rss>"""
        jobs = parse_rss_xml(xml, "Example University")
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]["company"], "Example University")
        self.assertIn("molecular dynamics", jobs[0]["description"].lower())


if __name__ == "__main__":
    unittest.main()
