import os
import stat
import tempfile
import unittest
from pathlib import Path

from xray_interactive.model import new_config, parse_jsonish
from xray_interactive.xray import find_xray_binary


class ModelTests(unittest.TestCase):
    def test_top_level_keys(self):
        cfg = new_config()
        self.assertEqual(
            list(cfg),
            [
                "env", "log", "api", "dns", "routing", "policy", "inbounds",
                "outbounds", "stats", "fakedns", "metrics", "observatory",
                "burstObservatory", "geodata", "version",
            ],
        )

    def test_jsonish(self):
        self.assertEqual(parse_jsonish("443"), 443)
        self.assertEqual(parse_jsonish("true"), True)
        self.assertEqual(parse_jsonish('[1,2]'), [1, 2])
        self.assertEqual(parse_jsonish("example.com"), "example.com")

    def test_xray_must_be_in_cwd(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "xray"
            p.write_text("#!/bin/sh\nexit 0\n")
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
            self.assertEqual(find_xray_binary(Path(td)), p.resolve())


if __name__ == "__main__":
    unittest.main()
