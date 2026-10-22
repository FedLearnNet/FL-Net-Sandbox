#!/bin/sh

# Removes the test platform and all clients (every directory in clients/ that
# has a docker-compose.yml) including their volumes, in parallel using
# `docker compose down -v`.

cd "$(dirname "$0")" || exit 1


# Space separated, so deployment directory names must not contain whitespace.
DEPLOYMENTS="platforms/test"
for dir in clients/*/; do
    [ -f "$dir/docker-compose.yml" ] && DEPLOYMENTS="$DEPLOYMENTS ${dir%/}"
done

JOBS=""
for dir in $DEPLOYMENTS; do
    # Run from within the directory so compose finds its docker-compose.yml and .env.
    # Output is prefixed with the directory to keep the parallel logs readable.
    # The exit code of compose (not sed) is passed out of the pipe via fd 3.
    (
        cd "$dir" || exit 1
        status=$( { { docker compose down -v 2>&1; echo $? >&3; } | sed -u "s|^|[$dir] |" >&4; } 3>&1 ) 4>&1
        exit "$status"
    ) &
    JOBS="$JOBS $!:$dir"
done

FAILED=""
for job in $JOBS; do
    wait "${job%%:*}" || FAILED="$FAILED ${job#*:}"
done

if [ -n "$FAILED" ]; then
    echo "Failed to remove:$FAILED" >&2
    exit 1
fi

echo "Removed: $DEPLOYMENTS"
