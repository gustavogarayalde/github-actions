#!/bin/sh
set -eu

# Only explicitly public variables belong in the browser runtime configuration.
environment_file="${1:-/usr/share/nginx/html/environment.json}"
jq -n 'env | with_entries(select(.key | startswith("NEXT_PUBLIC_") or startswith("VITE_")))' > "$environment_file"
