#!/bin/sh

# Builds a base image with your Tool API changes, builds the US-130 Tool on top of
# it and replaces the Tool image the Platform built in the sandbox registry.
#
# Usage: sh build_and_push_custom_toolapi.sh [tag]
# The tag of the image to replace is only needed if the registry holds several.

set -eu

cd "$(dirname "$0")"

REGISTRY="localhost:8250"
TOOL="us130-hospital-readmission-federated-nn"
TOOL_REPO_URL="https://github.com/FedLearnNet/FL-Net-Tool-US-130-FL-NN.git"
TOOL_REPO_DIR="../FL-Net-Tool-US-130-FL-NN"
TOOL_API_REPO_URL="https://github.com/FedLearnNet/Python-Tool-API"
PARENT_DIR="$(cd .. && pwd)"

echo "WARNING: This clones $TOOL_REPO_URL as a sibling of this folder into $PARENT_DIR/ (skipped if it already exists)."

# The Tool API repo is cloned under either of these names
TOOL_API_DIR=""
for dir in ../Python-Tool-API ../local-global-tool-api; do
    if [ -f "$dir/dev_scripts/build_local_docker_image.sh" ]; then
        TOOL_API_DIR="$dir"
        break
    fi
done

if [ -z "$TOOL_API_DIR" ]; then
    echo "ERROR: Tool API repo not found. Clone $TOOL_API_REPO_URL into $PARENT_DIR/ first." >&2
    exit 1
fi

echo "Your Tool API changes must be in $PARENT_DIR/${TOOL_API_DIR#../}, this is the folder that gets built."

TOOL_API_BRANCH="$(git -C "$TOOL_API_DIR" branch --show-current)"
if [ "$TOOL_API_BRANCH" = "develop" ] || [ "$TOOL_API_BRANCH" = "main" ]; then
    echo "WARNING: The Tool API repo is on branch $TOOL_API_BRANCH, your changes are probably on another branch."
fi

# Looked up first to fail before the builds if the Platform didn't build the Tool yet
if [ $# -gt 0 ]; then
    TAG="$1"
else
    TAGS_RESPONSE="$(curl -fs "$REGISTRY/v2/tools/$TOOL/tags/list")" || {
        echo "ERROR: Tool $TOOL not found in the registry at $REGISTRY. Is the Platform running and did it build the Tool?" >&2
        exit 1
    }
    TAGS="$(printf '%s' "$TAGS_RESPONSE" | python3 -c 'import json, sys; print("\n".join(json.load(sys.stdin)["tags"] or []))')"
    if [ -z "$TAGS" ]; then
        echo "ERROR: The registry has no image of Tool $TOOL yet, wait until the Platform built it." >&2
        exit 1
    fi
    if [ "$(printf '%s\n' "$TAGS" | wc -l)" -ne 1 ]; then
        echo "ERROR: The registry has several images of Tool $TOOL, pass the tag to replace as argument:" >&2
        echo "$TAGS" >&2
        exit 1
    fi
    TAG="$TAGS"
fi
IMG="$REGISTRY/tools/$TOOL:$TAG"

if [ ! -d "$TOOL_REPO_DIR" ]; then
    git clone "$TOOL_REPO_URL" "$TOOL_REPO_DIR"
fi

# Base image with your Tool API changes -> base-python-dep:testingtag
sh "$TOOL_API_DIR/dev_scripts/build_local_docker_image.sh"

# Build the Tool on your base image under that name (FROM replaced on the fly, nothing to commit)
sed 's#^FROM .*#FROM base-python-dep:testingtag#' "$TOOL_REPO_DIR/Dockerfile" \
    | docker build -t "$IMG" -f - "$TOOL_REPO_DIR"

# Push it (pipeline credentials of the sandbox; REGISTRY_PUSH_BASIC_AUTH = base64 of pipeline:<password>)
grep '^REGISTRY_PUSH_BASIC_AUTH=' platforms/test/env/registry-secrets.env | cut -d= -f2- \
    | base64 -d | cut -d: -f2- | docker login "$REGISTRY" -u pipeline --password-stdin
docker push "$IMG"

echo "Pushed: $IMG"
