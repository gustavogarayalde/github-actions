#!/usr/bin/env bash

set -Eeuo pipefail

remote_directory="${1:?Remote directory is required}"
stage_directory="${2:?Stage directory is required}"
incoming_environment="${stage_directory}/environment.env"
incoming_compose="${stage_directory}/docker-compose.yml"
target_environment="${remote_directory}/.env"
target_compose="${remote_directory}/docker-compose.yml"
merged_environment="${stage_directory}/merged.env"

if [[ ! "$stage_directory" =~ ^/tmp/github-deploy\.[A-Za-z0-9]+$ ]]; then
  echo "Unexpected staging directory." >&2
  exit 1
fi

cleanup() {
  rm -rf -- "$stage_directory"
}
trap cleanup EXIT

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not installed on the server." >&2
  exit 1
}

docker compose version >/dev/null 2>&1 || {
  echo "Docker Compose v2 is not available on the server." >&2
  exit 1
}

[[ -f "$incoming_environment" ]] || {
  echo "The staged environment file is missing." >&2
  exit 1
}

[[ -f "$incoming_compose" ]] || {
  echo "The staged Docker Compose file is missing." >&2
  exit 1
}

# Reject malformed and duplicate declarations instead of applying an ambiguous update.
awk '
  {
    line = $0
    sub(/\r$/, "", line)
    trimmed = line
    sub(/^[ \t]*/, "", trimmed)

    if (trimmed == "" || substr(trimmed, 1, 1) == "#") {
      next
    }

    separator = index(trimmed, "=")
    name = substr(trimmed, 1, separator - 1)
    gsub(/[ \t]/, "", name)

    if (separator == 0 || name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
      printf "Invalid dotenv declaration on line %d. Expected KEY=value.\n", FNR > "/dev/stderr"
      invalid = 1
      next
    }

    if (seen[name]++) {
      printf "Duplicate variable %s in the incoming environment file.\n", name > "/dev/stderr"
      invalid = 1
    }
    count++
  }
  END {
    if (count == 0) {
      print "The incoming environment file has no variable declarations." > "/dev/stderr"
      invalid = 1
    }
    exit invalid
  }
' "$incoming_environment"

mkdir -p -- "$remote_directory"

if [[ -f "$target_environment" ]]; then
  awk '
    function variable_name(raw, normalized, separator, name) {
      normalized = raw
      sub(/\r$/, "", normalized)
      sub(/^[ \t]*/, "", normalized)

      if (normalized == "" || substr(normalized, 1, 1) == "#") {
        return ""
      }

      separator = index(normalized, "=")
      if (separator == 0) {
        return ""
      }

      name = substr(normalized, 1, separator - 1)
      gsub(/[ \t]/, "", name)
      if (name !~ /^[A-Za-z_][A-Za-z0-9_]*$/) {
        return ""
      }
      return name
    }

    FILENAME == ARGV[1] {
      raw = $0
      sub(/\r$/, "", raw)
      name = variable_name(raw)
      if (name == "") {
        next
      }
      updates[name] = raw
      order[++update_count] = name
      next
    }

    {
      name = variable_name($0)
      if (name != "" && name in updates) {
        print updates[name]
        replaced[name] = 1
      } else {
        sub(/\r$/, "")
        print
      }
    }

    END {
      for (position = 1; position <= update_count; position++) {
        name = order[position]
        if (!(name in replaced)) {
          print updates[name]
        }
      }
    }
  ' "$incoming_environment" "$target_environment" >"$merged_environment"
else
  awk '{ sub(/\r$/, ""); print }' "$incoming_environment" >"$merged_environment"
fi

# Resolve interpolation before changing either server file.
docker compose \
  --project-directory "$remote_directory" \
  --env-file "$merged_environment" \
  -f "$incoming_compose" \
  config --quiet

environment_changed=true
compose_changed=true

if [[ -f "$target_environment" ]] && cmp -s "$merged_environment" "$target_environment"; then
  environment_changed=false
fi

if [[ -f "$target_compose" ]] && cmp -s "$incoming_compose" "$target_compose"; then
  compose_changed=false
fi

if [[ "$environment_changed" == true ]]; then
  temporary_environment="$(mktemp "${remote_directory}/.env.github.XXXXXXXXXX")"
  cp -- "$merged_environment" "$temporary_environment"
  if [[ -f "$target_environment" ]]; then
    chmod --reference="$target_environment" "$temporary_environment"
  else
    chmod 600 "$temporary_environment"
  fi
  mv -f -- "$temporary_environment" "$target_environment"
  echo "Updated ${target_environment}."
else
  echo "No environment changes detected."
fi

if [[ "$compose_changed" == true ]]; then
  temporary_compose="$(mktemp "${remote_directory}/docker-compose.yml.github.XXXXXXXXXX")"
  cp -- "$incoming_compose" "$temporary_compose"
  if [[ -f "$target_compose" ]]; then
    chmod --reference="$target_compose" "$temporary_compose"
  else
    chmod 644 "$temporary_compose"
  fi
  mv -f -- "$temporary_compose" "$target_compose"
  echo "Updated ${target_compose}."
else
  echo "No Docker Compose changes detected."
fi

cd "$remote_directory"
docker compose up -d --remove-orphans
