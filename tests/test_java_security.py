from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class JavaSecurityTests(unittest.TestCase):
    def test_docker_pulls_latest_base(self):
        steps = yaml.safe_load((ROOT / "actions/publish/docker/action.yml").read_text())["runs"]["steps"]
        build = next(s for s in steps if "docker/build-push-action@" in s.get("uses", ""))
        self.assertTrue(build["with"]["pull"])
