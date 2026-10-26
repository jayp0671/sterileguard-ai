#!/usr/bin/env bash
# Stage the Hugging Face Space build context (SG-16): the Space README (YAML header), the API
# Dockerfile at the root, and only the workspace members the API image needs. No .env, data,
# runs or reports are ever copied.
set -euo pipefail
out="${1:?usage: stage.sh <out-dir> [git-sha]}"
sha="${2:-}"
root="$(cd "$(dirname "$0")/../../.." && pwd)"

rm -rf "$out"
mkdir -p "$out"
cp "$root/ops/deploy/space/README.md" "$out/README.md"
# The Space builds ./Dockerfile; GIT_SHA is baked in so /health reports the deployed commit.
sed "s/^ARG GIT_SHA=\"\"/ARG GIT_SHA=\"$sha\"/" "$root/apps/api/Dockerfile" > "$out/Dockerfile"
cp "$root/pyproject.toml" "$root/uv.lock" "$out/"
for member in apps/api packages/data packages/sim packages/ml packages/agents ops/scripts; do
  mkdir -p "$out/$member"
  (cd "$root/$member" && tar --exclude='__pycache__' --exclude='.pytest_cache' --exclude='tests' \
    --exclude='notebooks' --exclude='reports' -cf - .) | (cd "$out/$member" && tar -xf -)
done
echo "staged $(find "$out" -type f | wc -l) files in $out"
