"""Runtime JSON and version-consistent Docker assets, without external services."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_npm_release import ROOT, steps


class ViteEnvironmentTests(unittest.TestCase):
    def generate(self, destination, values):
        return subprocess.run(
            ['sh', str(ROOT / 'dockerfiles/vite/start.sh'), str(destination)],
            env={'PATH': os.environ['PATH'], **values}, capture_output=True, text=True,
        )

    def test_exports_only_public_prefixes_and_escapes_json_values(self):
        public = {
            'NEXT_PUBLIC_API_BASE_URL': 'https://api.example.com',
            'VITE_MESSAGE': 'quotes " newline\nbackslash \\ Unicode ñ $HOME',
            'NEXT_PUBLIC_ENABLED': 'false',
            'VITE_CUSTOMER_ID': '42',
            'VITE_EMPTY': '',
        }
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'environment.json'
            result = self.generate(destination, {
                **public, 'SENTRY_AUTH_TOKEN': 'private',
                'PREFIX_NEXT_PUBLIC_BAD': 'private', 'PREFIX_VITE_BAD': 'private',
            })
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(destination.read_text()), public)
            self.assertEqual(result.stdout, '')

    def test_recreates_configuration_at_startup_without_stale_build_values(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / 'environment.json'
            destination.write_text('{"NEXT_PUBLIC_OLD":"build-value"}')
            first = self.generate(destination, {'NEXT_PUBLIC_API_BASE_URL': 'runtime'})
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(json.loads(destination.read_text()), {'NEXT_PUBLIC_API_BASE_URL': 'runtime'})
            second = self.generate(destination, {})
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(destination.read_text()), {})

    def test_fails_when_runtime_configuration_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.generate(Path(directory) / 'missing/environment.json', {})
            self.assertNotEqual(result.returncode, 0)

    def test_uses_nginx_startup_hook_and_uncached_json_endpoint(self):
        dockerfile = (ROOT / 'dockerfiles/vite/Dockerfile').read_text()
        self.assertIn('RUN apk add --no-cache jq', dockerfile)
        self.assertIn('COPY ./start.sh /docker-entrypoint.d/40-runtime-environment.sh', dockerfile)
        self.assertIn('RUN chmod +x /docker-entrypoint.d/40-runtime-environment.sh', dockerfile)
        self.assertIn('location = /environment.json', dockerfile)
        self.assertIn('default_type application/json;', dockerfile)
        self.assertIn('add_header Cache-Control "no-store" always;', dockerfile)
        self.assertIn('try_files $uri =404;', dockerfile)
        self.assertIn('try_files $uri $uri/ /index.html;', dockerfile)

    def prepare(self, app_type, directory):
        prepare = next(s for s in steps('actions/publish/docker') if s.get('name') == 'Prepare Docker runtime files')
        return subprocess.run(['bash', '-e', '-c', prepare['run']], cwd=directory,
                              env={**os.environ, 'APP_TYPE': app_type,
                                   'ACTION_DIRECTORY': str(ROOT / 'actions/publish/docker')},
                              capture_output=True, text=True)

    def test_copies_docker_assets_from_the_current_action_release_for_every_app_type(self):
        for app_type in ['next-js', 'vite', 'npm-ui-lib', 'spring-boot']:
            with self.subTest(app_type=app_type), tempfile.TemporaryDirectory() as directory:
                consumer = Path(directory)
                result = self.prepare(app_type, directory)
                self.assertEqual(result.returncode, 0, result.stderr)
                source = ROOT / 'dockerfiles' / app_type
                self.assertEqual((consumer / '.github-actions-docker/Dockerfile').read_bytes(), (source / 'Dockerfile').read_bytes())
                if app_type in ['next-js', 'vite']:
                    self.assertEqual((consumer / 'start.sh').read_bytes(), (source / 'start.sh').read_bytes())
                    self.assertTrue(os.access(consumer / 'start.sh', os.X_OK))
                else:
                    self.assertFalse((consumer / 'start.sh').exists())

    def test_rejects_unknown_app_types_before_writing_files(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.prepare('../../other', directory)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_builder_uses_prepared_assets_and_all_shell_blocks_parse(self):
        action = steps('actions/publish/docker')
        builder = next(s for s in action if s.get('name') == 'Build and push')
        self.assertEqual(builder['with']['file'], '.github-actions-docker/Dockerfile')
        self.assertNotIn('raw.githubusercontent.com', json.dumps(action))
        for step in action:
            if 'run' in step:
                subprocess.run(['bash', '-n', '-c', step['run']], check=True)
        subprocess.run(['sh', '-n', str(ROOT / 'dockerfiles/vite/start.sh')], check=True)


if __name__ == '__main__':
    unittest.main()
