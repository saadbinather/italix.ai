#!/bin/sh
set -eu

italix_script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
italix_env_file="$italix_script_dir/../../.env"
italix_unlock_secret=$(awk -F= '$1 == "ITALIX_OPERATOR_UNLOCK_SECRET" {sub(/^[^=]*=/, ""); print; exit}' "$italix_env_file")

if [ "${#italix_unlock_secret}" -lt 32 ]; then
  echo "ITALIX operator unlock secret is not configured." >&2
  exit 1
fi

printf '%s' "$italix_unlock_secret" | pbcopy
unset italix_unlock_secret
echo "ITALIX operator unlock secret copied to the local clipboard."
