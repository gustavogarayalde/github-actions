# NPM release regressions

Install `python3 -m pip install -r tests/requirements.txt`, then run `python3 -m unittest discover -s tests -v`.

The tests run local lifecycle hooks with a local devDependency, under NODE_ENV=production and npm_config_omit=dev, verify the prerelease version and packaged build output, check that npm ci preserves the lockfile, and validate shell syntax and nested action references. They do not publish, push, or use production services.

The source and nested action references are prepared for v0.0.32 (the previous local release is v0.0.31). Publish that actions release before enabling its consumer references. po-ui-lib is prepared to use actions/tag-release@v0.0.32; rerunning its older workflow still executes v0.0.25. Normal release preparation must keep all nested references on the same tag; the test checks that every nested reference uses the orchestrator's release tag.

Build and npm publication use npm ci --include=dev. Consumers must commit an up-to-date package-lock.json; peer policy is taken from their npm configuration. The action no longer forces legacy-peer-deps or rewrites their lockfile during CI. Tagging reuses the checked-out validated commit and its artifacts instead of running a second checkout.
