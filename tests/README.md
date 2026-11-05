# NPM release regressions

Install `python3 -m pip install -r tests/requirements.txt`, then run `python3 -m unittest discover -s tests -v`.

The tests run local lifecycle hooks with a local devDependency, under NODE_ENV=production and npm_config_omit=dev, verify the prerelease version and packaged build output, check that npm ci preserves the lockfile, and validate shell syntax and nested action references. They do not publish, push, or use production services.

The source and all nested action references are prepared for v0.0.35. Publish that actions release before enabling its consumer references. Release v0.0.33 mixed v0.0.33 orchestration with v0.0.32 release implementations, so its NPM release did not check occupied remote versions. Normal release preparation must keep all nested references on the same tag. Run the full suite before publishing the tag; `test_nested_action_references_use_the_prepared_release` rejects mixed versions and already runs in Action checks CI. Rerunning an older workflow keeps its pinned action version.

Build and npm publication use npm ci --include=dev. Consumers must commit an up-to-date package-lock.json; peer policy is taken from their npm configuration. The action no longer forces legacy-peer-deps or rewrites their lockfile during CI. Tagging reuses the checked-out validated commit and its artifacts instead of running a second checkout.


NPM coverage reporting supports Jest and Vitest through the shared Istanbul
`coverage/coverage-summary.json` format (`coverageReporters: ['json-summary']`
for Jest; `coverage.reporter: ['json-summary']` for Vitest). `test:ci` remains
responsible for running tests and generating coverage; its nonzero exit status
stops the build. The action writes coverage to the job summary and updates one
marked PR comment, without requiring a runner-specific JSON test report or
claiming a comparison with the base branch. Existing coverage badges consume
the same summary file. `skip-tests` skips all coverage steps.

Node 22.x resolves to the latest Node 22 release, meeting Vite 8 and Vitest 5's
22.12 minimum. Sentry uses `.next` for Next.js and `dist` for Vite and UI libraries.
Build, package publishing and Storybook still use the consumer's npm scripts.
These changes are included in the prepared v0.0.35 release. Publish that release
before updating po-ui-lib's `tag-release@v0.0.32` reference to `v0.0.35`.
