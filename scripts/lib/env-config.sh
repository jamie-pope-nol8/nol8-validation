#!/usr/bin/env bash
#
# Safe loader for KEY=VALUE environment files.
#
# WHY THIS EXISTS
#
# The transports used to `source config/demo.env`. That file is committed, so
# sourcing it runs whatever it contains as shell code: a poisoned change to it
# would be arbitrary code execution inside the transport, with the bearer token
# loaded on the very next line (FW-4). Parsing the file instead means it can
# only ever set variables - it cannot run commands.
#
# Sourcing THIS file is fine: it is code we wrote and commit deliberately. The
# distinction is data versus code. A .env file is data and must not be executed.
#
# CALLER PRECEDENCE (FW-5)
#
# A variable already present in the environment is left untouched, so
#   THEMIS_ALLOW_INSECURE_TLS=0 ./scripts/load-policy.sh ...
# is respected instead of being silently overwritten by the file. The file
# supplies defaults; the caller wins.
#
# Written for bash 3.2 (the macOS system bash) as well as modern bash.

# _env_var_is_set NAME -> 0 if a variable of that name is set (even if empty).
# NAME is validated by the caller against [A-Za-z_][A-Za-z0-9_]*, so the eval
# carries no untrusted metacharacters.
_env_var_is_set() {
  eval "[ \"\${${1}+set}\" = set ]"
}

# load_env_file FILE [ALLOWED_KEY ...]
#
# Parse FILE as KEY=VALUE lines and export each assignment, unless the caller
# already set that variable. Comments (#...) and blank lines are ignored.
# Malformed lines are reported and skipped rather than executed.
#
# If any ALLOWED_KEY names are given, only those keys are honored; any other key
# is reported and skipped. Use this for the committed config, so a tampered file
# cannot smuggle in something like LD_PRELOAD. Omit it for the local secrets
# file, whose keys are the operator's own.
load_env_file() {
  local file="$1"
  shift
  local allowed_count=$#

  local line key value lineno=0 allowed matched
  while IFS= read -r line || [ -n "$line" ]; do
    lineno=$((lineno + 1))

    case "$line" in
      ''|[[:space:]]*'#'*|'#'*) continue ;;
    esac
    if [[ ! "$line" =~ ^[[:space:]]*(export[[:space:]]+)?([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      # A blank line already continued above; anything else that is not a plain
      # assignment is suspicious in a config file.
      case "$line" in
        *[![:space:]]*) echo "Ignoring malformed line $lineno in ${file##*/}" >&2 ;;
      esac
      continue
    fi
    key="${BASH_REMATCH[2]}"
    value="${BASH_REMATCH[3]}"

    # Strip one layer of matching surrounding quotes. The value is never
    # evaluated, so a literal $ or backtick inside it stays literal.
    if [[ "$value" =~ ^\"(.*)\"$ ]]; then
      value="${BASH_REMATCH[1]}"
    elif [[ "$value" =~ ^\'(.*)\'$ ]]; then
      value="${BASH_REMATCH[1]}"
    fi

    if [ "$allowed_count" -gt 0 ]; then
      matched=false
      for allowed in "$@"; do
        if [ "$allowed" = "$key" ]; then
          matched=true
          break
        fi
      done
      if [ "$matched" != true ]; then
        echo "Ignoring unexpected key '$key' in ${file##*/}" >&2
        continue
      fi
    fi

    if _env_var_is_set "$key"; then
      continue
    fi
    printf -v "$key" '%s' "$value"
    export "$key"
  done < "$file"

  return 0
}
