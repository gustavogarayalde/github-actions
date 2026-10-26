"""Run with python3 -m unittest discover -s tests -v (requires requirements.txt)."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


def steps(action):
    return yaml.safe_load((ROOT / action / "action.yml").read_text())["runs"]["steps"]


class NpmReleaseTests(unittest.TestCase):
    def test_tagging_does_not_replace_the_validated_checkout(self):
        for action in ["actions/tag", "actions/tag/pr"]:
            with self.subTest(action=action):
                self.assertFalse(any("actions/checkout@" in s.get("uses", "") for s in steps(action)))

    def test_nested_action_references_use_the_prepared_release(self):
        orchestrator = steps("actions/tag-release")
        expected = next(s["uses"].rsplit("@", 1)[1] for s in orchestrator if s.get("uses", "").startswith("gustavogarayalde/github-actions/"))
        self.assertRegex(expected, r"^v[0-9]+\.[0-9]+\.[0-9]+$")
        for manifest in (ROOT / "actions").rglob("action.yml"):
            for step in yaml.safe_load(manifest.read_text())["runs"]["steps"]:
                reference = step.get("uses", "")
                if reference.startswith("gustavogarayalde/github-actions/"):
                    action, version = reference.split("@")
                    self.assertEqual(version, expected)
                    local = action.removeprefix("gustavogarayalde/github-actions/")
                    self.assertTrue((ROOT / local / "action.yml").exists())

    def test_build_uses_a_reproducible_install_including_dev_dependencies(self):
        install = next(s for s in steps("actions/build/npm") if s.get("name") == "Install Dependencies")
        self.assertEqual(install["run"], "npm ci --include=dev")

    def test_storybook_keeps_its_build_dependencies_and_registry_auth(self):
        storybook = next(s for s in steps("actions/publish") if s.get("name") == "Build Storybook")
        self.assertEqual(storybook["run"].splitlines(), ["npm ci --include=dev", "npm run build-storybook"])
        self.assertEqual(storybook["env"]["NODE_AUTH_TOKEN"], "${{ inputs.token }}")

    def test_publish_installs_before_executing_lifecycle_hooks(self):
        publication = steps("actions/publish/npm")
        self.assertEqual(publication[0]["run"], "npm ci --include=dev")
        self.assertEqual(publication[1]["run"], "npm publish")
        self.assertEqual(publication[0]["env"]["NODE_AUTH_TOKEN"], "${{ inputs.token }}")

    def test_all_npm_action_shell_blocks_parse(self):
        for action in ["actions/build/npm", "actions/publish/npm", "actions/tag", "actions/tag/pr"]:
            for step in steps(action):
                if "run" in step:
                    with self.subTest(action=action, step=step.get("name")):
                        subprocess.run(["bash", "-n", "-c", step["run"]], check=True)

    def test_publish_hooks_work_with_production_environment_and_keep_version(self):
        # No registry or publish: the fixture provides its own build tool as a local devDependency.
        with tempfile.TemporaryDirectory(prefix="npm-publish-regression-") as directory:
            root = Path(directory)
            tool = root / "build-tool"
            tool.mkdir()
            (tool / "package.json").write_text(json.dumps({"name": "fixture-build-tool", "version": "1.0.0", "bin": {"fixture-build": "build.js"}}))
            (tool / "build.js").write_text("#!/usr/bin/env node\nconst fs=require('node:fs');fs.mkdirSync('dist',{recursive:true});fs.writeFileSync('dist/version.txt',require(process.cwd()+'/package.json').version)\n")
            (tool / "build.js").chmod(0o755)
            (root / "package.json").write_text(json.dumps({"name": "npm-publication-fixture", "version": "1.0.0-pr.152.171", "private": True, "files": ["dist"], "scripts": {"build": "fixture-build", "prepublishOnly": "npm run build"}, "devDependencies": {"fixture-build-tool": "file:./build-tool"}}))
            env = {**os.environ, "NODE_ENV": "production", "npm_config_omit": "dev", "npm_config_audit": "false", "npm_config_fund": "false"}
            subprocess.run(["npm", "install", "--package-lock-only", "--ignore-scripts"], cwd=root, env=env, check=True, capture_output=True)
            before = (root / "package-lock.json").read_bytes()
            subprocess.run(["npm", "ci", "--omit=dev"], cwd=root, env=env, check=True, capture_output=True)
            missing = subprocess.run(["npm", "run", "prepublishOnly"], cwd=root, env=env, capture_output=True)
            self.assertNotEqual(missing.returncode, 0)
            install = steps("actions/publish/npm")[0]["run"]
            subprocess.run(["bash", "-e", "-c", install], cwd=root, env=env, check=True, capture_output=True)
            subprocess.run(["npm", "run", "prepublishOnly"], cwd=root, env=env, check=True, capture_output=True)
            self.assertEqual((root / "dist/version.txt").read_text(), "1.0.0-pr.152.171")
            self.assertEqual((root / "package-lock.json").read_bytes(), before)
            packed = subprocess.run(["npm", "pack", "--dry-run", "--json", "--ignore-scripts"], cwd=root, env=env, check=True, capture_output=True, text=True)
            metadata = json.loads(packed.stdout)[0]
            self.assertEqual(metadata["version"], "1.0.0-pr.152.171")
            self.assertIn("dist/version.txt", [f["path"] for f in metadata["files"]])


if __name__ == "__main__":
    unittest.main()
