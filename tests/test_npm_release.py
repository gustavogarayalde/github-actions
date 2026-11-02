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
    def test_push_only_the_new_tag_despite_conflicting_old_local_tags(self):
        tagging = steps("actions/tag")
        snapshot = next(s["run"] for s in tagging if s.get("name") == "Record existing tags")
        push = next(s["run"] for s in tagging if s.get("name") == "Push tag")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            checkout = root / "checkout"
            checkout.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=checkout, check=True, capture_output=True, text=True)
            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            git("commit", "--allow-empty", "-m", "initial")
            git("remote", "add", "origin", str(remote))
            git("tag", "v0.8.590")
            git("push", "origin", "refs/tags/v0.8.590")
            git("commit", "--allow-empty", "-m", "next")
            git("tag", "-f", "v0.8.590")
            git("tag", "unrelated-local-tag")
            env_file = root / "env"
            env = {**os.environ, "GITHUB_ENV": str(env_file), "GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"}
            subprocess.run(["bash", "-e", "-c", snapshot], cwd=checkout, env=env, check=True, capture_output=True)
            snapshot_path = env_file.read_text().strip().split("=", 1)[1]
            self.addCleanup(Path(snapshot_path).unlink, missing_ok=True)
            env["TAGS_BEFORE_FILE"] = snapshot_path
            # No new tag must fail instead of choosing an unrelated tag.
            result = subprocess.run(["bash", "-e", "-c", push], cwd=checkout, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            git("tag", "v0.8.594")
            subprocess.run(["bash", "-e", "-c", push], cwd=checkout, env=env, check=True, capture_output=True)
            self.assertIn("LATEST_TAG=v0.8.594", env_file.read_text())
            self.assertEqual(git("ls-remote", "origin", "refs/heads/main").stdout.split()[0], git("rev-parse", "HEAD").stdout.strip())
            remote_tags = git("ls-remote", "--tags", "origin").stdout
            self.assertIn("refs/tags/v0.8.594", remote_tags)
            self.assertNotIn("unrelated-local-tag", remote_tags)
            self.assertNotEqual(git("rev-parse", "v0.8.590").stdout.strip(), remote_tags.split("\trefs/tags/v0.8.590")[0])
            # Multiple new tags are ambiguous and must not be published.
            git("tag", "another-new-tag")
            result = subprocess.run(["bash", "-e", "-c", push], cwd=checkout, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("another-new-tag", git("ls-remote", "--tags", "origin").stdout)

    def test_release_versions_only_a_clean_checkout(self):
        release = next(s["run"] for s in steps("actions/release/npm") if s.get("name") == "NPM Release")
        for initial, expected, dirty, occupied in [
            ("1.2.3", "1.2.4", False, []),
            ("1.2.3-pr.42", "1.2.3", False, []),
            ("1.2.3", "1.2.3", True, []),
            ("0.8.595", "0.8.598", False, ["v0.8.596", "v0.8.597"]),
            ("1.2.3-pr.42", "1.2.4", False, ["v1.2.3"]),
            ("1.2.3", "1.2.3", False, None),
        ]:
            with self.subTest(initial=initial, dirty=dirty), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                def run(*args):
                    return subprocess.run(args, cwd=root, check=True, capture_output=True, text=True)
                run("git", "init")
                run("git", "config", "user.email", "test@example.com")
                run("git", "config", "user.name", "Test")
                manifest = root / "package.json"
                manifest.write_text(json.dumps({"name": "release-fixture", "version": initial}))
                run("git", "add", "package.json")
                run("git", "commit", "-m", "fixture")
                remote = root / "remote.git"
                run("git", "init", "--bare", str(remote))
                run("git", "remote", "add", "origin", str(remote if occupied is not None else root / "missing-remote.git"))
                for tag in occupied or []:
                    run("git", "tag", tag)
                    run("git", "push", "origin", f"refs/tags/{tag}")
                    # Reproduce shallow checkout: the conflicting tags exist
                    # only on the remote when the release starts.
                    run("git", "tag", "-d", tag)
                if dirty:
                    manifest.write_text(json.dumps({"name": "changed-by-install", "version": initial}))
                result = subprocess.run(["bash", "-e", "-c", release], cwd=root, capture_output=True, text=True)
                failed = dirty or occupied is None
                if failed:
                    self.assertNotEqual(result.returncode, 0)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(manifest.read_text())["version"], expected)
                self.assertEqual(run("git", "tag").stdout.strip(), "" if failed else f"v{expected}")
                if dirty:
                    self.assertIn("package.json", result.stdout)
                    self.assertIn("::error::", result.stdout)

    def test_atomic_release_does_not_push_branch_when_new_tag_conflicts(self):
        push = next(s["run"] for s in steps("actions/tag") if s.get("name") == "Push tag")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "remote.git"
            checkout = root / "checkout"
            checkout.mkdir()
            def git(*args):
                return subprocess.run(["git", *args], cwd=checkout, check=True, capture_output=True, text=True)
            git("init", "--bare", str(remote))
            git("init")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            git("commit", "--allow-empty", "-m", "initial")
            initial = git("rev-parse", "HEAD").stdout.strip()
            git("remote", "add", "origin", str(remote))
            git("push", "origin", "HEAD:refs/heads/main")
            git("tag", "v0.8.596")
            git("push", "origin", "refs/tags/v0.8.596")
            git("commit", "--allow-empty", "-m", "release")
            git("tag", "-f", "v0.8.596")
            snapshot = root / "before"
            snapshot.write_text("")
            env_file = root / "env"
            env = {**os.environ, "GITHUB_ENV": str(env_file), "TAGS_BEFORE_FILE": str(snapshot), "GITHUB_EVENT_NAME": "push", "GITHUB_REF_NAME": "main"}
            result = subprocess.run(["bash", "-e", "-c", push], cwd=checkout, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(git("ls-remote", "origin", "refs/heads/main").stdout.split()[0], initial)
            self.assertEqual(git("ls-remote", "--tags", "origin", "refs/tags/v0.8.596").stdout.split()[0], initial)
            self.assertFalse(env_file.exists())

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
