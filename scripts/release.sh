#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

need_command() {
    command -v "$1" >/dev/null 2>&1 || die "missing required command: $1"
}

need_command git
need_command gh

gh auth status >/dev/null 2>&1 || die "GitHub CLI is not authenticated, run: gh auth login"

python_cmd=""
if command -v python3 >/dev/null 2>&1
then
    python_cmd="python3"
elif command -v python >/dev/null 2>&1
then
    python_cmd="python"
else
    die "missing required command: python3"
fi

version="$("$python_cmd" - <<'PY'
import tomllib

with open("pyproject.toml", "rb") as f:
    print(tomllib.load(f)["project"]["version"])
PY
)"

if [[ ! "$version" =~ ^[0-9]+[.][0-9]+[.][0-9]+$ ]]
then
    die "pyproject.toml version is not a simple release version: $version"
fi

tag="v$version"
branch="$(git branch --show-current)"

if [ "$branch" != "main" ]
then
    die "release must be run from main, current branch is $branch"
fi

if [ -n "$(git status --porcelain --untracked-files=all)" ]
then
    die "working tree is not clean"
fi

local_head="$(git rev-parse HEAD)"
remote_main="$(git ls-remote origin refs/heads/main | awk '{print $1}')"

if [ -z "$remote_main" ]
then
    die "could not read origin/main"
fi

if [ "$local_head" != "$remote_main" ]
then
    die "local HEAD is not pushed to origin/main"
fi

if git rev-parse -q --verify "refs/tags/$tag" >/dev/null 2>&1
then
    die "local tag already exists: $tag"
fi

if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1
then
    die "remote tag already exists: $tag"
fi

if gh release view "$tag" >/dev/null 2>&1
then
    die "GitHub Release already exists: $tag"
fi

printf 'Preparing release %s from %s\n' "$tag" "$local_head"
printf 'This will create and push tag %s, then publish the GitHub Release.\n' "$tag"
printf 'Continue? [y/N] '
read -r answer

if [ "$answer" != "y" ] &&
    [ "$answer" != "Y" ] &&
    [ "$answer" != "yes" ] &&
    [ "$answer" != "YES" ]
then
    die "release cancelled"
fi

git tag -a "$tag" -m "Release $tag"
git push origin "$tag"

gh release create "$tag" \
    --title "$tag" \
    --generate-notes \
    --verify-tag

printf 'Published GitHub Release %s\n' "$tag"
printf 'Watch the release workflow, then test pip install bundesrecht from PyPI.\n'
