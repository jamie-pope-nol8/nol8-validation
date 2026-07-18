#!/usr/bin/env bash

set -Eeuo pipefail

APPLY=false
BASELINE_NAME="initial-functional-baseline"

usage() {
    cat <<'EOF'
Usage:
  ./scripts/restructure-framework.sh
  ./scripts/restructure-framework.sh --apply

Without --apply, the script prints the proposed migration without
changing the repository.

Options:
  --apply    Perform the migration
  --help     Show this help
EOF
}

for argument in "$@"; do
    case "$argument" in
        --apply)
            APPLY=true
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            printf 'Unknown argument: %s\n\n' "$argument" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ ! -d ".git" ]]; then
    printf 'Error: run this script from the nol8-validation repository root.\n' >&2
    exit 1
fi

run() {
    if [[ "$APPLY" == true ]]; then
        "$@"
    else
        printf '[dry-run]'
        printf ' %q' "$@"
        printf '\n'
    fi
}

create_directory() {
    local directory="$1"

    if [[ -d "$directory" ]]; then
        return
    fi

    run mkdir -p "$directory"
}

create_empty_file() {
    local file="$1"

    if [[ -e "$file" ]]; then
        return
    fi

    create_directory "$(dirname "$file")"
    run touch "$file"
}

move_path() {
    local source="$1"
    local destination="$2"

    if [[ ! -e "$source" ]]; then
        printf '[skip] source does not exist: %s\n' "$source"
        return
    fi

    if [[ -e "$destination" ]]; then
        printf 'Error: destination already exists: %s\n' "$destination" >&2
        exit 1
    fi

    create_directory "$(dirname "$destination")"

    if git ls-files --error-unmatch "$source" >/dev/null 2>&1; then
        run git mv "$source" "$destination"
    else
        run mv "$source" "$destination"
    fi
}

move_directory_contents() {
    local source_directory="$1"
    local destination_directory="$2"
    local file
    local relative_path

    if [[ ! -d "$source_directory" ]]; then
        printf '[skip] directory does not exist: %s\n' "$source_directory"
        return
    fi

    create_directory "$destination_directory"

    while IFS= read -r -d '' file; do
        relative_path="${file#"$source_directory"/}"
        move_path "$file" "$destination_directory/$relative_path"
    done < <(
        find "$source_directory" \
            -mindepth 1 \
            -type f \
            -print0 |
            sort -z
    )
}

remove_directory_if_empty() {
    local directory="$1"

    if [[ ! -d "$directory" ]]; then
        return
    fi

    if find "$directory" -mindepth 1 -print -quit | grep -q .; then
        printf '[keep] directory is not empty: %s\n' "$directory"
        return
    fi

    run rmdir "$directory"
}

printf '\nNol8 Validation Framework migration\n'
printf 'Mode: %s\n\n' "$(
    if [[ "$APPLY" == true ]]; then
        printf 'apply'
    else
        printf 'dry-run'
    fi
)"

printf 'Creating target directories...\n'

directories=(
    "artifacts"
    "artifacts/$BASELINE_NAME"
    "artifacts/$BASELINE_NAME/generated"
    "artifacts/$BASELINE_NAME/output"
    "artifacts/$BASELINE_NAME/reports"
    "config"
    "config/profiles"
    "config/workloads"
    "docs"
    "framework"
    "framework/cli"
    "framework/document"
    "framework/execution"
    "framework/policy"
    "framework/reporting"
    "framework/scenarios"
    "framework/serializers"
    "framework/validation"
    "framework/workload"
    "samples"
    "scripts"
    "tests"
)

for directory in "${directories[@]}"; do
    create_directory "$directory"
done

printf '\nMoving authored configuration...\n'

move_path \
    "scale-test/config/workloads/enterprise-dlp.yaml" \
    "config/workloads/enterprise-dlp.yaml"

move_path \
    "scale-test/config/test-cases.yaml" \
    "config/test-cases.yaml"

printf '\nMoving existing Python implementations into the framework package...\n'

move_path \
    "scale-test/scripts/generate-functional-test.py" \
    "framework/policy/generate_functional_test.py"

move_path \
    "scale-test/scripts/generate-workload.py" \
    "framework/workload/generate_workload.py"

move_path \
    "scale-test/scripts/run-functional-test.py" \
    "framework/execution/run_functional_test.py"

printf '\nArchiving existing generated artifacts...\n'

move_directory_contents \
    "scale-test/generated" \
    "artifacts/$BASELINE_NAME/generated"

move_directory_contents \
    "scale-test/reports" \
    "artifacts/$BASELINE_NAME/reports"

move_directory_contents \
    "output" \
    "artifacts/$BASELINE_NAME/output"

printf '\nNormalizing documentation names...\n'

move_path \
    "known_behaviors.md" \
    "KNOWN_BEHAVIORS.md"

printf '\nCreating Python package markers...\n'

package_files=(
    "framework/__init__.py"
    "framework/cli/__init__.py"
    "framework/document/__init__.py"
    "framework/execution/__init__.py"
    "framework/policy/__init__.py"
    "framework/reporting/__init__.py"
    "framework/scenarios/__init__.py"
    "framework/serializers/__init__.py"
    "framework/validation/__init__.py"
    "framework/workload/__init__.py"
    "tests/__init__.py"
)

for file in "${package_files[@]}"; do
    create_empty_file "$file"
done

printf '\nCreating documentation placeholders...\n'

documentation_files=(
    "docs/ARCHITECTURE.md"
    "docs/REPORTS.md"
)

for file in "${documentation_files[@]}"; do
    create_empty_file "$file"
done

printf '\nRemoving empty legacy directories...\n'

legacy_directories=(
    "scale-test/config/workloads"
    "scale-test/config"
    "scale-test/generated"
    "scale-test/reports"
    "scale-test/scripts"
    "scale-test"
    "output"
)

for directory in "${legacy_directories[@]}"; do
    remove_directory_if_empty "$directory"
done

printf '\n'

if [[ "$APPLY" == true ]]; then
    printf 'Migration completed.\n\n'
    printf 'Review the repository with:\n\n'
    printf '  tree -L 5\n'
    printf '  git status --short\n'
else
    printf 'Dry run completed. No files were changed.\n\n'
    printf 'Apply the migration with:\n\n'
    printf '  ./scripts/restructure-framework.sh --apply\n'
fi