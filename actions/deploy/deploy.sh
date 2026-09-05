#!/usr/bin/env bash

set -Eeuo pipefail

required_variables=(
  DEPLOY_ENVIRONMENT
  DEPLOY_LOCAL_DIRECTORY
  DEPLOY_REMOTE_DIRECTORY
  DEPLOY_SSH_HOST
  DEPLOY_SSH_USER
  DEPLOY_SSH_PRIVATE_KEY
  DEPLOY_SSH_PORT
)

for variable_name in "${required_variables[@]}"; do
  if [[ -z "${!variable_name:-}" ]]; then
    echo "::error::The ${variable_name} input is required."
    exit 1
  fi
done

if [[ ! "$DEPLOY_ENVIRONMENT" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  echo "::error::The environment name contains unsupported characters."
  exit 1
fi

if [[ ! "$DEPLOY_SSH_HOST" =~ ^[A-Za-z0-9][A-Za-z0-9.-]*$ ]]; then
  echo "::error::The SSH host must be a hostname or IPv4 address."
  exit 1
fi

if [[ ! "$DEPLOY_SSH_USER" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "::error::The SSH user contains unsupported characters."
  exit 1
fi

if [[ ! "$DEPLOY_SSH_PORT" =~ ^[0-9]+$ ]]; then
  echo "::error::The SSH port must be between 1 and 65535."
  exit 1
fi

ssh_port_number=$((10#$DEPLOY_SSH_PORT))
if ((ssh_port_number < 1 || ssh_port_number > 65535)); then
  echo "::error::The SSH port must be between 1 and 65535."
  exit 1
fi

DEPLOY_SSH_PORT="$ssh_port_number"

if [[ "$DEPLOY_REMOTE_DIRECTORY" != /* ]] ||
  [[ "$DEPLOY_REMOTE_DIRECTORY" == "/" ]] ||
  [[ "$DEPLOY_REMOTE_DIRECTORY" =~ (^|/)\.\.(/|$) ]] ||
  [[ ! "$DEPLOY_REMOTE_DIRECTORY" =~ ^/[A-Za-z0-9._/-]+$ ]]; then
  echo "::error::The remote directory must be a safe absolute path other than /."
  exit 1
fi

if [[ "$DEPLOY_LOCAL_DIRECTORY" == /* ]] ||
  [[ "$DEPLOY_LOCAL_DIRECTORY" == -* ]] ||
  [[ "$DEPLOY_LOCAL_DIRECTORY" =~ (^|/)\.\.(/|$) ]]; then
  echo "::error::The local directory must be a safe path relative to the repository."
  exit 1
fi

local_directory="${DEPLOY_LOCAL_DIRECTORY%/}"
environment_file="${local_directory}/.env.${DEPLOY_ENVIRONMENT}"
compose_file="${local_directory}/docker-compose.yml"

if [[ ! -d "$local_directory" ]]; then
  echo "::error::Local directory not found: ${local_directory}"
  exit 1
fi

if [[ ! -f "$environment_file" ]]; then
  echo "::error::Environment file not found: ${environment_file}"
  exit 1
fi

if [[ ! -f "$compose_file" ]]; then
  echo "::error::Docker Compose file not found: ${compose_file}"
  exit 1
fi

ssh_directory="$(mktemp -d "${RUNNER_TEMP:-/tmp}/deploy-ssh.XXXXXXXXXX")"
private_key_file="${ssh_directory}/private_key"
known_hosts_file="${ssh_directory}/known_hosts"
remote_stage=""
remote_target="${DEPLOY_SSH_USER}@${DEPLOY_SSH_HOST}"

printf '%s\n' "$DEPLOY_SSH_PRIVATE_KEY" >"$private_key_file"
chmod 600 "$private_key_file"

if [[ -n "${DEPLOY_SSH_KNOWN_HOSTS:-}" ]]; then
  printf '%s\n' "$DEPLOY_SSH_KNOWN_HOSTS" >"$known_hosts_file"
else
  echo "::warning::SSH_KNOWN_HOSTS is not configured; trusting the host key discovered during this run."
  ssh-keyscan -T 10 -p "$DEPLOY_SSH_PORT" "$DEPLOY_SSH_HOST" >"$known_hosts_file"
fi

ssh_options=(
  -i "$private_key_file"
  -p "$DEPLOY_SSH_PORT"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$known_hosts_file"
)

scp_options=(
  -i "$private_key_file"
  -P "$DEPLOY_SSH_PORT"
  -o BatchMode=yes
  -o IdentitiesOnly=yes
  -o StrictHostKeyChecking=yes
  -o UserKnownHostsFile="$known_hosts_file"
)

cleanup() {
  if [[ "$remote_stage" =~ ^/tmp/github-deploy\.[A-Za-z0-9]+$ ]]; then
    ssh "${ssh_options[@]}" "$remote_target" "rm -rf -- '$remote_stage'" >/dev/null 2>&1 || true
  fi
  rm -rf -- "$ssh_directory"
}
trap cleanup EXIT

remote_stage="$(
  ssh "${ssh_options[@]}" "$remote_target" \
    "mktemp -d /tmp/github-deploy.XXXXXXXXXX"
)"

if [[ ! "$remote_stage" =~ ^/tmp/github-deploy\.[A-Za-z0-9]+$ ]]; then
  echo "::error::The server returned an unexpected temporary directory."
  exit 1
fi

scp "${scp_options[@]}" \
  "$environment_file" \
  "${remote_target}:${remote_stage}/environment.env"

scp "${scp_options[@]}" \
  "$compose_file" \
  "${remote_target}:${remote_stage}/docker-compose.yml"

scp "${scp_options[@]}" \
  "$GITHUB_ACTION_PATH/remote-deploy.sh" \
  "${remote_target}:${remote_stage}/remote-deploy.sh"

ssh "${ssh_options[@]}" "$remote_target" \
  "bash '${remote_stage}/remote-deploy.sh' '$DEPLOY_REMOTE_DIRECTORY' '$remote_stage'"
