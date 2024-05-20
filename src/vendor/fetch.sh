#!/usr/bin/env bash

set -eEuo pipefail

log() { printf '%b\n' -- "$*" >&2; }
print() { printf '%b\n' -- "$*"; }

git_fetch() {
  local url="${1:?"Missing URL"}"; shift
  local branch="${1:?"Missing Branch"}"; shift
  local dir="${1:?"Missing Dir"}"; shift

  if [[ -d "${dir}" ]]; then
    (
      cd "${dir}" || exit
      git fetch --depth 1 origin "${branch}"
    )
  else
    install -dm0755 "${dir}"
    git clone --depth 1 --branch "${branch}" --single-branch "${url}" "${dir}"
  fi
}

declare os; os="$(uname -s)"
declare vendor_dir="${CI_PROJECT_DIR:?"Missing CI_PROJECT_DIR Env Var"}/src/vendor"

### Pyusb

declare -A pyusb=(
  [path]="pyusb/pyusb"
  [giturl]="git@github.com:pyusb/pyusb.git"
  [branch]="v1.2.1"
)
git_fetch "${pyusb[giturl]}" "${pyusb[branch]}" "${vendor_dir}/${pyusb[path]}/${pyusb[branch]}"

case "${os}" in
  "Darwin")
    brew install libusb
    ;;
  *)
    log "Please install libusb"
    ;;
esac

### Openant

declare -A openant=(
  [path]="Tigge/openant"
  [giturl]="git@github.com:Tigge/openant.git"
  [branch]="v1.3.1"
)
git_fetch "${openant[giturl]}" "${openant[branch]}" "${vendor_dir}/${openant[path]}/${openant[branch]}"

###

log 'fin'
