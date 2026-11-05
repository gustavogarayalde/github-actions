"""Exercise the actual coverage action script without contacting GitHub."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_npm_release import steps


class NpmCoverageTests(unittest.TestCase):
    def run_report(self, event="pull_request", previous=False, summary=None, missing=False):
        step = next(s for s in steps("actions/build/npm") if s.get("name") == "Report test coverage")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "coverage").mkdir()
            if not missing:
                if summary is None:
                    summary = {"total": {metric: {"pct": 75, "covered": 3, "total": 4}
                                         for metric in ["statements", "branches", "functions", "lines"]}}
                (root / "coverage/coverage-summary.json").write_text(json.dumps(summary))
            script = root / "report.js"
            script.write_text('''
const calls = [];
const context = { eventName: process.env.EVENT, repo: {owner: 'test', repo: 'fixture'}, issue: {number: 42} };
const core = {summary: {addRaw(body) {calls.push(['summary', body]); return this}, async write() {}}};
const github = {
  paginate: async (_, params) => {
    calls.push(['list', params]);
    return process.env.PREVIOUS === 'true'
      ? [{id: 1, body: 'unrelated'}, {id: 2, body: '<!-- npm-test-coverage -->\\nold report'}]
      : [{id: 1, body: 'unrelated'}];
  },
  rest: {issues: {
    listComments() {},
    async updateComment(params) {calls.push(['update', params])},
    async createComment(params) {calls.push(['create', params])},
  }},
};
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
new AsyncFunction('require', 'core', 'github', 'context', process.env.SCRIPT)(require, core, github, context)
  .then(() => console.log(JSON.stringify(calls)))
  .catch(error => {console.error(error.message); process.exitCode = 1});
''')
            return subprocess.run(["node", str(script)], cwd=root, capture_output=True, text=True,
                                  env={**os.environ, "EVENT": event, "PREVIOUS": str(previous).lower(), "SCRIPT": step["with"]["script"]})

    def test_creates_comment_from_shared_jest_and_vitest_summary(self):
        result = self.run_report()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = json.loads(result.stdout)
        self.assertEqual([call[0] for call in calls], ["summary", "list", "create"])
        self.assertEqual(calls[-1][1]["issue_number"], 42)
        for metric in ["statements", "branches", "functions", "lines"]:
            self.assertIn(f"| {metric} | 75% | 3/4 |", calls[0][1])
        self.assertEqual(calls[0][1], calls[-1][1]["body"])

    def test_updates_only_the_marked_comment(self):
        result = self.run_report(previous=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = json.loads(result.stdout)
        self.assertEqual([call[0] for call in calls], ["summary", "list", "update"])
        self.assertEqual(calls[-1][1]["comment_id"], 2)

    def test_push_writes_summary_without_calling_github(self):
        result = self.run_report(event="push")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([call[0] for call in json.loads(result.stdout)], ["summary"])

    def test_missing_and_invalid_reports_fail(self):
        for kwargs in [{"missing": True}, {"summary": {}},
                       {"summary": {"total": {"statements": {"pct": "75", "covered": 3, "total": 4}}}}]:
            with self.subTest(kwargs=kwargs):
                result = self.run_report(**kwargs)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")

    def test_skipping_tests_also_skips_reporting_and_badges(self):
        action = steps("actions/build/npm")
        for name in ["Run Tests", "Generate Test Coverage Badges", "Push the coverage badges and summary file", "Report test coverage"]:
            step = next(s for s in action if s.get("name") == name)
            self.assertIn("inputs.skip-tests != 'true'", step["if"])
        self.assertFalse(any("jest-coverage-report-action" in s.get("uses", "") for s in action))

    def test_sentry_uses_next_output_only_for_next_apps(self):
        sentry = next(s for s in steps("actions/build/npm") if s.get("name") == "Create Sentry release")
        self.assertEqual(sentry["with"]["sourcemaps"], "${{ inputs.app-type == 'next-js' && '.next' || 'dist' }}")
