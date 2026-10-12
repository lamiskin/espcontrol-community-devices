#!/usr/bin/env python3
"""Fail-closed OTA updater for one community ESPHome device.

Usage: python3 community/scripts/update_device.py [--dry-run] <IP>

Requires Linux ``avahi-browse``, Python 3, and ``curl`` for actual updates.
Upload uses the firmware's HTTP ``/update`` handler and therefore requires a
device firmware that exposes the ESPHome web-server OTA endpoint. The request
uses plain HTTP on the trusted LAN; this script does not set authentication.
Endpoint availability is not guaranteed for every device or release.
Discovery only browses ESPHome's DNS-SD service and accepts
records whose resolved address exactly matches the requested IP. A device
must publish its official ``package_import_url`` and ``project_version`` TXT
records. Dry-run resolves the device, fetches and validates the small release
manifest, and shows the plan. It does not download firmware, verify firmware
checksums, or connect to the device's OTA/API endpoint.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

from generate_manifest import chip_family

REPOSITORY_NAME = "espcontrol-community-devices"
TIMEOUT = 12
DISCOVERY_TIMEOUT = 18
PREFIX = "[update_device]"


class UpdateError(Exception):
    pass


def parse_origin_remote(remote_url):
    """Return (owner, repo) for a canonical GitHub origin URL."""
    value = remote_url.strip()
    scp = re.fullmatch(r"(?:[^@/:]+@)?github\.com:([^/]+)/([^/]+?)(?:\.git)?/?", value, re.IGNORECASE)
    if scp:
        owner, repository = scp.groups()
    else:
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme not in ("https", "ssh") or (parsed.hostname or "").lower() != "github.com":
            raise UpdateError("Origin remote must be a GitHub HTTPS or SSH repository URL.")
        path_parts = parsed.path.strip("/").split("/")
        if len(path_parts) != 2:
            raise UpdateError("Origin remote must identify exactly one GitHub owner and repository.")
        owner, repository = path_parts
        if repository.endswith(".git"):
            repository = repository[:-4]
    if (not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?", owner)
            or repository != REPOSITORY_NAME):
        raise UpdateError(f"Origin remote must be a GitHub repository named {REPOSITORY_NAME}.")
    return owner, repository


def repository_coordinates(repo_root=None):
    root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    try:
        result = subprocess.run(
            ["git", "-C", root, "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"Could not read the local Git origin remote: {exc}") from exc
    if result.returncode:
        raise UpdateError("Could not read the local Git origin remote; configure origin to the canonical GitHub repository.")
    return parse_origin_remote(result.stdout)


def github_base(coordinates):
    owner, repository = coordinates
    return f"https://github.com/{owner}/{repository}"


def require_same_identity(expected, observed, require_version=False):
    if canonical_mac(observed["mac"]) != canonical_mac(expected["mac"]) or observed["slug"] != expected["slug"]:
        raise UpdateError("Device identity changed at the target IP; aborting.")
    if require_version and observed["version"] != expected["version"]:
        raise UpdateError("Installed version changed at the target IP; aborting.")


def canonical_mac(value):
    compact = re.sub(r"[:-]", "", value.strip())
    if not re.fullmatch(r"[0-9a-fA-F]{12}", compact):
        raise UpdateError("ESPHome record has an invalid MAC address.")
    return compact.lower()


def device_registry(repo_root=None):
    root = repo_root or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    devices = os.path.join(root, "devices")
    registry = {}
    for slug in sorted(os.listdir(devices)):
        device_file = os.path.join(devices, slug, "device", "device.yaml")
        config_file = os.path.join(devices, slug, "esphome.yaml")
        if not (os.path.isfile(device_file) and os.path.isfile(config_file)):
            continue
        with open(device_file, encoding="utf-8") as f:
            first_lines = f.read(1024).splitlines()
        title = next((line.lstrip("# ").strip() for line in first_lines
                      if line.startswith("# DEVICE - ")), slug)
        registry[slug] = title.removeprefix("DEVICE - ").removesuffix(" hardware definition")
    return registry


def _split_avahi_fields(line):
    """Split Avahi parsable fields without consuming TXT quoting/escapes."""
    fields, part, escaped, quoted = [], [], False, False
    for char in line.rstrip("\n"):
        if escaped:
            part.append("\\")
            part.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            quoted = not quoted
            part.append(char)
        elif char == ";" and not quoted:
            fields.append("".join(part))
            part = []
        else:
            part.append(char)
    if escaped:
        part.append("\\")
    fields.append("".join(part))
    return fields


def parse_txt_fields(fields):
    records = {}
    for field in fields:
        try:
            entries = shlex.split(field)
        except ValueError as exc:
            raise UpdateError("Malformed quoted TXT fields in DNS-SD response.") from exc
        for entry in entries:
            if "=" in entry:
                key, value = entry.split("=", 1)
                key, value = key.strip(), value.strip().replace(r"\;", ";")
                if key in records and records[key] != value:
                    raise UpdateError(f"Conflicting duplicate DNS-SD TXT key: {key}.")
                records[key] = value
    return records


def parse_discovery(output, target_ip, registry, coordinates):
    candidates = {}
    target_records = 0
    for line in output.splitlines():
        fields = _split_avahi_fields(line)
        # Avahi -p -r: state, interface, protocol, name, type, domain,
        # hostname, address, port, then TXT records.
        if len(fields) < 10 or fields[0] != "=":
            continue
        if fields[4] != "_esphomelib._tcp" or fields[7] != target_ip:
            continue
        target_records += 1
        txt = parse_txt_fields(fields[9:])
        url = txt.get("package_import_url", "")
        match = re.fullmatch(
            rf"github://{re.escape(coordinates[0])}/{re.escape(coordinates[1])}/devices/([a-z0-9][a-z0-9-]*)/esphome\.yaml@([^/\s]+)",
            url,
        )
        if not match or match.group(1) not in registry:
            raise UpdateError("Unsupported or missing package_import_url on an ESPHome record at the requested IP.")
        version = txt.get("project_version", "").strip()
        mac = txt.get("mac", "").strip()
        if not version or not mac:
            raise UpdateError("ESPHome record at the requested IP is missing project_version or MAC TXT metadata.")
        mac_key = canonical_mac(mac)
        identity = (match.group(1), match.group(2), mac_key, version)
        candidates.setdefault(identity, {"slug": match.group(1), "ref": match.group(2),
                                         "model": registry[match.group(1)], "version": version,
                                         "mac": mac, "name": fields[3]})
    if not candidates or not target_records:
        raise UpdateError("No uniquely verifiable supported device at that IP (requires official package_import_url, project_version, and MAC TXT records).")
    if len(candidates) != 1:
        raise UpdateError(f"Ambiguous discovery: {len(candidates)} supported ESPHome records resolved to {target_ip}.")
    return next(iter(candidates.values()))


def discover(ip, registry, coordinates, runner=subprocess.run):
    if not shutil_which("avahi-browse"):
        raise UpdateError("avahi-browse is required for DNS-SD discovery on Linux.")
    try:
        result = runner(["avahi-browse", "--resolve", "--terminate", "--parsable", "_esphomelib._tcp"],
                        capture_output=True, text=True, timeout=DISCOVERY_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError(f"DNS-SD discovery failed: {exc}") from exc
    if result.returncode not in (0, 1):
        raise UpdateError(f"avahi-browse failed with status {result.returncode}: {result.stderr.strip()}")
    return parse_discovery(result.stdout, ip, registry, coordinates)


def shutil_which(command):
    # Keep the script dependency-free while honoring PATH exactly as exec does.
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(directory or ".", command)
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def request_json(url):
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "espcontrol-community-device-updater"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            if response.geturl().split("/", 3)[2].lower() not in ("api.github.com",):
                raise UpdateError("GitHub API redirected away from the official API host.")
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(f"GitHub API request failed: {exc}") from exc


def published_releases(coordinates, fetch=request_json):
    releases, page = [], 1
    while True:
        url = f"https://api.github.com/repos/{coordinates[0]}/{coordinates[1]}/releases?per_page=100&page={page}"
        batch = fetch(url)
        if not isinstance(batch, list):
            raise UpdateError("Malformed GitHub releases response.")
        releases.extend(r for r in batch if isinstance(r, dict) and not r.get("draft") and r.get("published_at"))
        if len(batch) < 100:
            break
        page += 1
        if page > 100:
            raise UpdateError("GitHub releases pagination exceeded safety limit.")
    try:
        return sorted(releases, key=lambda r: (r["published_at"], int(r["id"])), reverse=True)
    except (KeyError, TypeError, ValueError) as exc:
        raise UpdateError("Published release has malformed timestamp or ID.") from exc


def _trusted_asset_url(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname != "github.com" or parts.username or parts.password:
        raise UpdateError(f"Refusing non-official or unsafe release asset URL: {url}")
    return url


def _expected_asset_url(tag, filename, coordinates):
    return f"{github_base(coordinates)}/releases/download/{urllib.parse.quote(tag, safe='')}/{filename}"


def release_artifact(slug, release, coordinates):
    tag = release.get("tag_name")
    if not isinstance(tag, str) or not tag or "/" in tag:
        raise UpdateError("Release has an invalid tag.")
    assets = release.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Release assets are missing or malformed.")
    by_name = {}
    for asset in assets:
        if isinstance(asset, dict) and isinstance(asset.get("name"), str):
            by_name.setdefault(asset["name"], []).append(asset)
    manifest_name, ota_name = f"{slug}-manifest.json", f"{slug}.ota.bin"
    if len(by_name.get(manifest_name, [])) != 1 or len(by_name.get(ota_name, [])) != 1:
        raise UpdateError(f"Release {tag} must contain exactly one {manifest_name} and one {ota_name}; refusing fallback.")
    manifest_asset, ota_asset = by_name[manifest_name][0], by_name[ota_name][0]
    manifest_url = _trusted_asset_url(manifest_asset.get("browser_download_url", ""))
    ota_url = _trusted_asset_url(ota_asset.get("browser_download_url", ""))
    if manifest_url != _expected_asset_url(tag, manifest_name, coordinates) or ota_url != _expected_asset_url(tag, ota_name, coordinates):
        raise UpdateError("Release asset URLs do not match the exact repository, tag, and expected filenames.")
    return {"tag": tag, "manifest_name": manifest_name, "ota_name": ota_name,
            "manifest_asset": manifest_asset, "ota_asset": ota_asset,
            "manifest_url": manifest_url, "ota_url": ota_url}


def validate_manifest(raw, slug, tag, coordinates):
    try:
        manifest = json.loads(raw)
        if not isinstance(manifest, dict):
            raise TypeError("manifest must be an object")
        version = manifest["version"]
        builds = manifest["builds"]
        if not isinstance(builds, list) or not builds or not isinstance(builds[0], dict):
            raise TypeError("builds must be a nonempty object list")
        build = builds[0]
        ota = build["ota"]
        if not isinstance(ota, dict):
            raise TypeError("ota must be an object")
        family = chip_family(slug)
    except (ValueError, TypeError, KeyError, IndexError, OSError) as exc:
        raise UpdateError("Device release manifest is malformed or does not define OTA firmware.") from exc
    expected_version = tag.removeprefix("community-")
    repo_url = github_base(coordinates)
    expected_path = _expected_asset_url(tag, f"{slug}.ota.bin", coordinates)
    if (not isinstance(version, str) or version != expected_version
            or ota.get("path") != expected_path
            or ota.get("release_url") != f"{repo_url}/releases/tag/{tag}"
            or build.get("chipFamily") != family):
        raise UpdateError("Manifest version/tag/OTA path is inconsistent with selected release.")
    md5 = ota.get("md5")
    if not isinstance(md5, str) or not re.fullmatch(r"[a-fA-F0-9]{32}", md5):
        raise UpdateError("Manifest is missing the required valid OTA MD5 checksum.")
    return version, md5.lower()


TRUSTED_DOWNLOAD_HOSTS = {"github.com", "githubusercontent.com", "release-assets.githubusercontent.com"}


def _is_trusted_download_url(url):
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").lower()
    return (parts.scheme == "https" and not parts.username and not parts.password
            and (host in TRUSTED_DOWNLOAD_HOSTS or host.endswith(".githubusercontent.com")))


class TrustedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not _is_trusted_download_url(newurl):
            raise UpdateError("Release asset redirect left HTTPS or GitHub's trusted download domains.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url):
    # Deliberately no Authorization or other credentials on asset downloads.
    if not _is_trusted_download_url(url):
        raise UpdateError("Refusing download URL outside HTTPS and GitHub's trusted domains.")
    request = urllib.request.Request(url, headers={"User-Agent": "espcontrol-community-device-updater"})
    try:
        opener = urllib.request.build_opener(TrustedRedirectHandler())
        with opener.open(request, timeout=TIMEOUT) as response:
            if not _is_trusted_download_url(response.geturl()):
                raise UpdateError("Firmware download did not remain on HTTPS and a trusted GitHub domain.")
            return response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise UpdateError(f"Release asset download failed: {exc}") from exc


def verify_firmware(data, asset, manifest_md5):
    if not data:
        raise UpdateError("OTA firmware asset is empty.")
    digest = hashlib.sha256(data).hexdigest()
    api_digest = asset.get("digest")
    if api_digest:
        if not isinstance(api_digest, str) or not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", api_digest) or api_digest.split(":", 1)[1].lower() != digest:
            raise UpdateError("OTA firmware does not match GitHub API SHA-256 digest.")
    if manifest_md5 and hashlib.md5(data).hexdigest() != manifest_md5:  # noqa: S324 - upstream manifest contract
        raise UpdateError("OTA firmware does not match release manifest MD5.")
    return digest


def run_update(device, release, artifact, version, ip, coordinates, runner=subprocess.run):
    curl = shutil_which("curl")
    if not curl:
        raise UpdateError("curl is required for the device HTTP OTA upload but was not found on PATH.")
    print(f"Starting OTA upload of {artifact['ota_name']} to {ip} ({device['slug']}).")
    with tempfile.NamedTemporaryFile(prefix="espcontrol-ota-", suffix=".bin", delete=False) as firmware:
        firmware.write(release)
        firmware_path = firmware.name
    try:
        try:
            result = runner([curl, "--disable", "--noproxy", "*", "--fail", "--silent",
                             "--show-error", "--form", f"file=@{firmware_path}",
                             "--write-out", "\n%{http_code}", f"http://{ip}/update"],
                            timeout=900, check=False, capture_output=True, text=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise UpdateError(f"HTTP OTA upload failed or timed out: {exc}") from exc
        if result.returncode:
            raise UpdateError(f"curl HTTP OTA upload failed with status {result.returncode}; no retry attempted.")
        if not isinstance(result.stdout, str) or "\n" not in result.stdout:
            raise UpdateError("curl did not return an HTTP status; no retry attempted.")
        body, http_status = result.stdout.rsplit("\n", 1)
        body = body.rstrip("\r\n")
        if not re.fullmatch(r"2[0-9]{2}", http_status.strip()):
            raise UpdateError("Device HTTP OTA endpoint did not return a 2xx status; no retry attempted.")
        if body != "Update Successful!":
            raise UpdateError("Device did not return the expected 'Update Successful!' response; no retry attempted.")
    finally:
        try:
            os.unlink(firmware_path)
        except OSError:
            pass
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            after = discover(ip, device_registry(), coordinates, runner=runner)
            try:
                require_same_identity(device, after)
            except UpdateError as exc:
                raise UpdateError(f"Post-update verification failed: {exc}") from exc
            if after["version"] == version:
                print(f"Verified installed version {version} on {ip}.")
                return
        except UpdateError as exc:
            if "Post-update verification failed" in str(exc):
                raise
        time.sleep(3)
    raise UpdateError(f"OTA command returned, but {ip} did not rediscover with version {version}; no retry or rollback attempted.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="resolve target/release/artifact without downloading or uploading")
    parser.add_argument("ip", help="single target device IPv4 address (IPv6 is not supported)")
    args = parser.parse_args(argv)
    try:
        parsed_ip = ipaddress.ip_address(args.ip)
        if not isinstance(parsed_ip, ipaddress.IPv4Address):
            raise UpdateError("Only IPv4 target addresses are supported; IPv6 is not supported by this updater.")
        ip = str(parsed_ip)
        coordinates = repository_coordinates()
        registry = device_registry()
        device = discover(ip, registry, coordinates)
        releases = published_releases(coordinates)
        if not releases:
            raise UpdateError("No published GitHub releases were found.")
        release = releases[0]
        artifact = release_artifact(device["slug"], release, coordinates)
        print(f"Target: {ip} | {device['slug']} ({device['model']}) | MAC {device['mac']}")
        print(f"Installed: {device['version']} | Release: {release['tag_name']} ({release['published_at']})")
        if release.get("prerelease"):
            print("WARNING: selected release is a PREVIEW/prerelease.")
        manifest_raw = _download(artifact["manifest_url"])
        version, md5 = validate_manifest(manifest_raw, device["slug"], artifact["tag"], coordinates)
        print(f"Selected version: {version} | OTA artifact: {artifact['ota_name']}")
        if args.dry_run:
            print("Dry run: manifest validated; firmware checksums not verified; no firmware binary downloaded or uploaded.")
            return 0
        if version == device["version"]:
            raise UpdateError(f"Device already reports release version {version}; no update is needed.")
        firmware = _download(artifact["ota_url"])
        sha256 = verify_firmware(firmware, artifact["ota_asset"], md5)
        print(f"Manifest version: {version} | SHA-256: {sha256}")
        answer = input("Type 'yes' to upload this OTA firmware: ").strip().lower()
        if answer != "yes":
            print("Cancelled; no device write performed.")
            return 0
        before = discover(ip, registry, coordinates)
        require_same_identity(device, before, require_version=True)
        run_update(device, firmware, artifact, version, ip, coordinates)
        return 0
    except (UpdateError, ValueError) as exc:
        print(f"{PREFIX} ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
