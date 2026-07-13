#!/bin/bash
# Hook: Block git hook bypass in commit/push commands
# Type: PreToolUse, Matcher: Bash
# Exit code 2 = block
set -euo pipefail

SEPARATOR="__CLAUDE_BOOTSTRAP_COMMAND_SEPARATOR__"

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

if [ -z "$COMMAND" ]; then
  exit 0
fi

TOKENS=()

add_token() {
  local token=$1
  if [[ -n "$token" ]]; then
    TOKENS+=("$token")
  fi
}

add_separator() {
  add_token "$1"
  TOKENS+=("$SEPARATOR")
}

tokenize_command() {
  local input=$1
  local token=""
  local quote=""
  local escaped=false
  local char next
  local length=${#input}
  local i

  for ((i = 0; i < length; i++)); do
    char=${input:i:1}

    if [[ "$escaped" == true ]]; then
      token+="$char"
      escaped=false
      continue
    fi

    if [[ "$quote" == "'" ]]; then
      if [[ "$char" == "'" ]]; then
        quote=""
      else
        token+="$char"
      fi
      continue
    fi

    if [[ "$quote" == '"' ]]; then
      if [[ "$char" == '"' ]]; then
        quote=""
      elif [[ "$char" == "\\" ]]; then
        ((i++)) || true
        if [[ $i -lt $length ]]; then
          next=${input:i:1}
          token+="$next"
        else
          token+="\\"
        fi
      else
        token+="$char"
      fi
      continue
    fi

    case "$char" in
      "\\")
        escaped=true
        ;;
      "'")
        quote="'"
        ;;
      '"')
        quote='"'
        ;;
      " " | $'\t' | $'\r')
        add_token "$token"
        token=""
        ;;
      $'\n' | ";")
        add_separator "$token"
        token=""
        ;;
      "&")
        add_token "$token"
        token=""
        if [[ $((i + 1)) -lt $length && "${input:i + 1:1}" == "&" ]]; then
          ((i++)) || true
        fi
        TOKENS+=("$SEPARATOR")
        ;;
      "|")
        add_token "$token"
        token=""
        if [[ $((i + 1)) -lt $length && "${input:i + 1:1}" == "|" ]]; then
          ((i++)) || true
        fi
        TOKENS+=("$SEPARATOR")
        ;;
      *)
        token+="$char"
        ;;
    esac
  done

  add_token "$token"
}

is_assignment() {
  [[ $1 =~ ^[A-Za-z_][A-Za-z0-9_]*= ]]
}

is_bypass_assignment() {
  [[ $1 == "HUSKY=0" || $1 == SKIP=* ]]
}

find_git_subcommand_index() {
  local i=$1
  shift
  local -a segment=("$@")
  local token
  i=$((i + 1))

  while [[ $i -lt ${#segment[@]} ]]; do
    token=${segment[i]}

    case "$token" in
      commit | push)
        echo "$i"
        return 0
        ;;
      --)
        return 1
        ;;
      -C | -c | --git-dir | --work-tree | --namespace)
        i=$((i + 2))
        continue
        ;;
      --git-dir=* | --work-tree=* | --namespace=* | --no-pager | --paginate | --bare)
        i=$((i + 1))
        continue
        ;;
      -*)
        i=$((i + 1))
        continue
        ;;
      *)
        return 1
        ;;
    esac
  done

  return 1
}

segment_blocks() {
  local -a segment=("$@")
  local i=0
  local env_bypass=false
  local subcommand_index subcommand token skip_next=false

  while [[ $i -lt ${#segment[@]} ]] && is_assignment "${segment[i]}"; do
    if is_bypass_assignment "${segment[i]}"; then
      env_bypass=true
    fi
    i=$((i + 1))
  done

  if [[ $i -ge ${#segment[@]} || "${segment[i]}" != "git" ]]; then
    return 1
  fi

  if ! subcommand_index=$(find_git_subcommand_index "$i" "${segment[@]}"); then
    return 1
  fi

  subcommand=${segment[subcommand_index]}

  if [[ "$env_bypass" == true ]]; then
    return 0
  fi

  for ((i = subcommand_index + 1; i < ${#segment[@]}; i++)); do
    token=${segment[i]}

    if [[ "$skip_next" == true ]]; then
      skip_next=false
      continue
    fi

    if [[ "$subcommand" == "commit" ]]; then
      case "$token" in
        -m | --message | -F | --file | -C | -c)
          skip_next=true
          continue
          ;;
      esac
    fi

    if [[ "$token" == "--no-verify" ]]; then
      return 0
    fi
  done

  return 1
}

tokenize_command "$COMMAND"

SEGMENT=()
for token in "${TOKENS[@]}"; do
  if [[ "$token" == "$SEPARATOR" ]]; then
    if [[ ${#SEGMENT[@]} -gt 0 ]] && segment_blocks "${SEGMENT[@]}"; then
      echo "BLOCKED: git hook bypass is not allowed."
      echo "If a hook is failing, fix the underlying issue instead of skipping it."
      exit 2
    fi
    SEGMENT=()
  else
    SEGMENT+=("$token")
  fi
done

if [[ ${#SEGMENT[@]} -gt 0 ]] && segment_blocks "${SEGMENT[@]}"; then
  echo "BLOCKED: git hook bypass is not allowed."
  echo "If a hook is failing, fix the underlying issue instead of skipping it."
  exit 2
fi

exit 0
