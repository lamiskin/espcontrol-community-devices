#!/usr/bin/env python3
"""
prepare_c6_firmware.py – Download and verify the ESP32-C6 recovery firmware
build dependency (issue #98).

P4 panels in this repo use a separate ESP32-C6 chip for WiFi
(esp32_hosted). Upstream's C6 recovery build (jtenniswood/espcontrol,
common/device/esp32_c6_recovery.yaml) embeds a pinned, known-good C6
firmware blob into the compiled image so a USB-only reflash can repair a
desynced/corrupted C6 without needing a network connection. That blob is
not upstream-specific — it is ESPHome's own official ESP-Hosted
network_adapter firmware — so the version/hash pin and download URL here
are copied verbatim from upstream's scripts/prepare_c6_firmware.py.

The compiled esp32_c6_recovery.yaml component (`c6_recovery.path`, a
cv.file_) resolves its relative path against the file passed to `esphome
compile` — i.e. against builds/, not against wherever this file happens to
be fetched from — so the release workflow must place the verified blob at
exactly `<assembly>/.firmware-deps/esp32-c6/<version>/
network_adapter_esp32c6.bin` before compiling any *.recovery.yaml.

Usage:
    python3 community/scripts/prepare_c6_firmware.py --output <path>
    python3 community/scripts/prepare_c6_firmware.py --output <path> --check
    python3 community/scripts/prepare_c6_firmware.py --self-test
"""

import argparse
import hashlib
import os
import sys
import tempfile
import urllib.request

C6_VERSION = "2.12.12"
C6_SHA256 = "bad97ce81e7fcf5f3365898f633b80941ae863db9c754d87a78f89c8f61f2e94"
C6_URL = (
    "https://esphome.github.io/esp-hosted-firmware/"
    f"v{C6_VERSION}/network_adapter_esp32c6.bin"
)

PREFIX = "[prepare_c6_firmware]"


class C6FirmwareError(RuntimeError):
    pass


def error(msg):
    print(f"{PREFIX} ERROR: {msg}", file=sys.stderr)


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(path, expected_sha256=C6_SHA256):
    if not os.path.isfile(path):
        raise C6FirmwareError(f"C6 firmware not found: {path}")
    actual = sha256(path)
    if actual != expected_sha256:
        raise C6FirmwareError(
            f"C6 firmware checksum mismatch: expected {expected_sha256}, "
            f"got {actual}")


def download(url, destination):
    out_dir = os.path.dirname(destination) or "."
    os.makedirs(out_dir, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(destination)}.", suffix=".tmp",
        dir=out_dir)
    try:
        with os.fdopen(fd, "wb") as out:
            request = urllib.request.Request(
                url, headers={"User-Agent": "espcontrol-c6-recovery-build"})
            with urllib.request.urlopen(request, timeout=60) as response:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp_path, destination)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def prepare(output, url=C6_URL, expected_sha256=C6_SHA256):
    """Reuse an already-verified cached file; otherwise download and verify."""
    if os.path.isfile(output):
        try:
            verify(output, expected_sha256)
            print(f"{PREFIX} using verified ESP32-C6 firmware "
                  f"{C6_VERSION}: {output}")
            return output
        except C6FirmwareError:
            os.unlink(output)

    try:
        download(url, output)
        verify(output, expected_sha256)
    except Exception as exc:
        try:
            os.unlink(output)
        except OSError:
            pass
        raise C6FirmwareError(f"could not prepare ESP32-C6 firmware: {exc}") from exc

    print(f"{PREFIX} downloaded and verified ESP32-C6 firmware "
          f"{C6_VERSION}: {output}")
    return output


def self_test():
    import http.server
    import shutil
    import socketserver
    import tempfile as tf
    import threading

    failures = []

    def check(name, cond):
        if not cond:
            failures.append(name)

    payload = b"fake-c6-firmware-bytes-for-self-test"
    payload_sha256 = hashlib.sha256(payload).hexdigest()

    tmp = tf.mkdtemp(prefix="prepare_c6_firmware_test_")
    try:
        # Serve the fixture payload over a local HTTP server so download()
        # is exercised for real rather than mocked.
        serve_dir = os.path.join(tmp, "serve")
        os.makedirs(serve_dir)
        with open(os.path.join(serve_dir, "fw.bin"), "wb") as f:
            f.write(payload)

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=serve_dir, **kw)

            def log_message(self, *a):
                pass

        with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
            port = httpd.server_address[1]
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{port}/fw.bin"

                # Fresh download, verified.
                dest = os.path.join(tmp, "out", "fw.bin")
                prepare(dest, url=url, expected_sha256=payload_sha256)
                check("downloaded file missing", os.path.isfile(dest))
                with open(dest, "rb") as f:
                    check("downloaded content mismatch", f.read() == payload)

                # A wrong pin is rejected rather than silently accepted.
                try:
                    prepare(os.path.join(tmp, "out2", "fw.bin"), url=url,
                            expected_sha256="0" * 64)
                    failures.append("wrong sha256 did NOT raise")
                except C6FirmwareError:
                    pass

                # An already-verified cache is reused without re-downloading
                # — corrupt the server's copy and confirm prepare() still
                # succeeds from the cache alone.
                os.unlink(os.path.join(serve_dir, "fw.bin"))
                prepare(dest, url=url, expected_sha256=payload_sha256)
                check("valid cache was not reused",
                      sha256(dest) == payload_sha256)

                # A corrupted cache with the server unreachable fails loudly
                # instead of silently proceeding with bad firmware.
                with open(dest, "wb") as f:
                    f.write(b"corrupted")
                try:
                    prepare(dest, url=url, expected_sha256=payload_sha256)
                    failures.append(
                        "corrupted cache + unreachable source did NOT raise")
                except C6FirmwareError:
                    pass
            finally:
                httpd.shutdown()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # The real pin: confirm the constants agree with each other in shape
    # (this cannot hit the network in CI, but catches a bad edit).
    check("C6_SHA256 is not 64 hex chars",
          len(C6_SHA256) == 64 and all(c in "0123456789abcdef" for c in C6_SHA256))
    check("C6_URL does not carry C6_VERSION",
          f"v{C6_VERSION}" in C6_URL)

    if failures:
        for msg in failures:
            error(f"self-test: {msg}")
        return 1
    print(f"{PREFIX} self-test passed")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="path to write the verified firmware to")
    parser.add_argument("--check", action="store_true",
                        help="only verify the cached dependency; do not download it")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(self_test())

    if not args.output:
        parser.error("--output is required")

    try:
        if args.check:
            verify(args.output)
            print(f"{PREFIX} verified ESP32-C6 firmware {C6_VERSION}: {args.output}")
        else:
            prepare(args.output)
    except C6FirmwareError as exc:
        error(str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()
