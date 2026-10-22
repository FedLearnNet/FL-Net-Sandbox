#!/usr/bin/env python3
"""Generates the testing bundle deployments (platforms/test, clients/c1, clients/c2) with the flnet CLI.

    python3 init_test_bundle.py          asks before deleting existing deployments
    python3 init_test_bundle.py --yes    no questions

The deployment directories are generated and not committed: do not edit them, put testing changes into
overrides/ (compose overrides, wrapper templates, images_used.env, realm-users/) or the settings below.
Environment: FLNET_BIN = flnet binary to use (e.g. a local CLI build), otherwise the release FLNET_VERSION
(default: staging) is installed into bin/.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent
OVERRIDES = BUNDLE / "overrides"
DATA = BUNDLE / "data"
INSTALL_SCRIPT = "https://raw.githubusercontent.com/FedLearnNet/FL-Net-CLI/main/install.sh"
# flnet keeps its instances in $FLNET_HOME/{platforms,clients}: the bundle directory itself, so instances in
# ~/fl-net with the same names don't collide
FLNET_ENV = {"FLNET_HOME": str(BUNDLE)}

IMAGE_TAG = "staging"
PLATFORM = {"name": "test", "port": 8250, "relay_port": 9150}
# the clients reach the platform through the docker host gateway
PLATFORM_URL_FOR_CLIENTS = f"http://host.docker.internal:{PLATFORM['port']}"
# Platform account the clients use for federated requests, see overrides/realm-users/platform-users.json
PLATFORM_USERNAME = "test"
PLATFORM_PASSWORD = "test"
# Client 2 is opened via 127.0.0.1 instead of localhost so the browser keeps separate login cookies (README).
# flnet treats --listen 127.0.0.1 as localhost, so its address is set as the client's domain.
CLIENTS = [
    {"name": "c1", "port": 8251, "domain": None, "csv": "clinic_001.csv"},
    {"name": "c2", "port": 8252, "domain": "http://127.0.0.1:8252", "csv": "clinic_002.csv"},
]


def step(message):
    print(f"\n==> {message}", flush=True)


def fail(message):
    sys.exit(f"ERROR: {message}")


def run(command, cwd=None, env=None):
    result = subprocess.run(command, cwd=cwd, env={**os.environ, **(env or {})})
    if result.returncode != 0:
        fail(f"'{' '.join(map(str, command))}' failed with exit code {result.returncode}")


def flnet_binary():
    if os.environ.get("FLNET_BIN"):
        flnet = Path(os.environ["FLNET_BIN"]).expanduser().resolve()
        step(f"Using flnet from FLNET_BIN: {flnet}")
    else:
        version = os.environ.get("FLNET_VERSION", "staging")
        step(f"Installing flnet {version} into {BUNDLE / 'bin'}")
        if not shutil.which("curl"):
            fail("curl is required to install flnet (or set FLNET_BIN)")
        (BUNDLE / "bin").mkdir(exist_ok=True)
        # install.sh verifies the SHA256SUMS of the release
        script = subprocess.run(["curl", "-fsSL", INSTALL_SCRIPT], capture_output=True, check=False)
        if script.returncode != 0:
            fail(f"downloading {INSTALL_SCRIPT} failed: {script.stderr.decode().strip()}")
        install = subprocess.run(["sh"], input=script.stdout,
                                 env={**os.environ, "FLNET_VERSION": version, "FLNET_INSTALL_DIR": str(BUNDLE / "bin")})
        if install.returncode != 0:
            fail("installing flnet failed")
        flnet = BUNDLE / "bin" / "flnet"
    run([flnet, "--version"])
    return flnet


def deployment_dirs():
    return [BUNDLE / "platforms" / PLATFORM["name"], *[BUNDLE / "clients" / c["name"] for c in CLIENTS]]


def remove_existing(assume_yes):
    existing = [d for d in (BUNDLE / "platforms", BUNDLE / "clients") if d.exists()]
    if not existing:
        return
    print("This DELETES the existing testing bundle deployments including ALL their data (docker volumes):")
    for d in existing:
        print(f"  {d}")
    if not assume_yes and input("Type 'yes' to continue: ").strip() != "yes":
        fail("aborted")
    step("Removing the existing deployments")
    for d in sorted(p for root in existing for p in root.iterdir() if (p / "docker-compose.yml").is_file()):
        print(f"docker compose down -v in {d}")
        result = subprocess.run(["docker", "compose", "down", "-v", "--remove-orphans"], cwd=d)
        if result.returncode != 0:
            print(f"WARNING: docker compose down failed in {d}, its containers/volumes may remain", file=sys.stderr)
    for d in existing:
        shutil.rmtree(d)


def init_platform(flnet):
    step(f"Generating platforms/{PLATFORM['name']}")
    run([flnet, "platform", "init", "--no-input", "--yes",
         "--name", PLATFORM["name"], "--dir", BUNDLE / "platforms" / PLATFORM["name"],
         "--domain", f"http://localhost:{PLATFORM['port']}",
         "--port", str(PLATFORM["port"]), "--relay-port", str(PLATFORM["relay_port"]),
         # self-signed localhost certificate; the relay generates its own (overrides/platform.override.yml)
         "--ssl-cert", DATA / "certs" / "fullchain.pem", "--ssl-key", DATA / "certs" / "privkey.pem",
         "--no-nginx-ssl",
         "--min-clients", "1",
         "--platform-aggregator",
         "--sapbert", "--sapbert-dir", DATA / "sapbert",
         "--image-tag", IMAGE_TAG],
        env=FLNET_ENV)


def init_client(flnet, client):
    step(f"Generating clients/{client['name']}")
    run([flnet, "client", "init", "--no-input", "--yes",
         "--name", client["name"], "--dir", BUNDLE / "clients" / client["name"],
         "--network", "custom",
         "--platform-url", PLATFORM_URL_FOR_CLIENTS,
         "--platform-relay-port", str(PLATFORM["relay_port"]),
         "--platform-username", PLATFORM_USERNAME,
         "--federation",
         "--listen", "localhost", "--port", str(client["port"]),
         "--domain", client["domain"] or "none",
         "--ssl", "none",
         "--default-permission",
         "--allow-auto-statistics", "--allow-auto-learning", "--allow-auto-metrics",
         "--auto-statistics", "all", "--auto-metrics", "all", "--auto-learning", "all",
         "--allow-queries", "--query-retry-time", "3", "--query-sample-threshold", "100",
         "--image-tag", IMAGE_TAG],
        env={**FLNET_ENV, "FLNET_PLATFORM_PASSWORD": PLATFORM_PASSWORD})


def apply_overrides(directory, kind):
    """Moves the generated compose file aside and adds the wrapper, which merges overrides/<kind>.override.yml."""
    (directory / "docker-compose.yml").rename(directory / "docker-compose.base.yml")
    shutil.copyfile(OVERRIDES / f"{kind}.compose.yml", directory / "docker-compose.yml")
    merge_users(directory / "keycloak-realms" / "realm-export.json", OVERRIDES / "realm-users" / f"{kind}-users.json")


def merge_users(realm_file, users_file):
    """Adds the users of users_file to the realm export, skipping existing usernames."""
    realm = json.loads(realm_file.read_text())
    users = realm.setdefault("users", [])
    names = {user["username"] for user in users}
    users.extend(user for user in json.loads(users_file.read_text()) if user["username"] not in names)
    # overwrite in place to keep the permissions flnet set
    realm_file.write_text(json.dumps(realm, indent=2) + "\n")
    print(f"Keycloak users in {realm_file.relative_to(BUNDLE)}: {', '.join(u['username'] for u in users)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-y", "--yes", action="store_true", help="delete existing deployments without asking")
    args = parser.parse_args()

    if not shutil.which("docker"):
        fail("docker is required")
    for file in (DATA / "certs" / "fullchain.pem", DATA / "certs" / "privkey.pem",
                 DATA / "sapbert" / "sapbert.onnx", DATA / "sapbert" / "tokenizer.json"):
        if not file.is_file():
            fail(f"{file} missing")

    flnet = flnet_binary()
    remove_existing(args.yes)

    init_platform(flnet)
    for client in CLIENTS:
        init_client(flnet, client)

    step("Applying the testing bundle changes (overrides/)")
    apply_overrides(BUNDLE / "platforms" / PLATFORM["name"], "platform")
    for client in CLIENTS:
        directory = BUNDLE / "clients" / client["name"]
        apply_overrides(directory, "client")
        with (directory / ".env").open("a") as env:
            env.write("# Testing bundle only: data file in import_data_handling/ the client imports on startup"
                      " (overrides/client.override.yml)\n"
                      f"TESTING_CLINIC_CSV={client['csv']}\n")
    for directory in deployment_dirs():
        run(["docker", "compose", "config", "--quiet"], cwd=directory)

    step("Done, start the bundle with: sh start_test_bundle.sh")


if __name__ == "__main__":
    main()
