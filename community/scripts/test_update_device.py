import hashlib
import json
import unittest
import urllib.request
from unittest import mock

import update_device as updater


SLUG = "guition-esp32-s3-jc3248w535"
COORDINATES = ("example-org", "espcontrol-community-devices")
URL = f"github://{COORDINATES[0]}/{COORDINATES[1]}/devices/{SLUG}/esphome.yaml@main"
REGISTRY = {SLUG: "Guition ESP32-S3-JC3248W535"}
IP = "192.0.2.10"
MAC = "02:00:00:00:00:01"
TXT = f'"package_import_url={URL}" "project_version=v0.13.0-upstream.v2.11.0" "mac={MAC}"'
LINE = (f"=;eth0;IPv4;espcontrol-device;_esphomelib._tcp;local;host.local;"
        f"{IP};6053;{TXT}")
ESCAPED_LINE = (f'=;eth0;IPv4;espcontrol-device;_esphomelib._tcp;local;host.local;{IP};6053;'
                f'"package_import_url={URL}" "project_version=v0.13.0-upstream.v2.11.0" '
                f'"mac={MAC}" "friendly_name=Hall\\; \\\"Panel\\\""')


class DiscoveryTests(unittest.TestCase):
    def test_origin_parsing_supports_https_and_ssh_and_rejects_other_repo(self):
        for remote in (
            "https://github.com/example-org/espcontrol-community-devices.git",
            "git@github.com:example-org/espcontrol-community-devices.git",
            "ssh://git@github.com/example-org/espcontrol-community-devices",
        ):
            self.assertEqual(updater.parse_origin_remote(remote), COORDINATES)
        for remote in ("https://github.com/example-org/other-repo.git", "https://example.invalid/example-org/espcontrol-community-devices.git"):
            with self.subTest(remote=remote), self.assertRaises(updater.UpdateError):
                updater.parse_origin_remote(remote)

    def test_exact_allowlisted_txt_resolves_device(self):
        device = updater.parse_discovery(LINE, IP, REGISTRY, COORDINATES)
        self.assertEqual(device["slug"], SLUG)
        self.assertEqual(device["version"], "v0.13.0-upstream.v2.11.0")

    def test_wrong_repo_and_unregistered_slug_fail_closed(self):
        for url in (URL.replace("example-org/", "other-org/"), URL.replace(SLUG, "unknown-model")):
            with self.subTest(url=url), self.assertRaises(updater.UpdateError):
                updater.parse_discovery(LINE.replace(URL, url), IP, REGISTRY, COORDINATES)

    def test_missing_or_ambiguous_txt_records_fail_closed(self):
        with self.assertRaises(updater.UpdateError):
            updater.parse_discovery(LINE.replace(f'"package_import_url={URL}"', '"unrelated=yes"'), IP, REGISTRY, COORDINATES)
        with self.assertRaises(updater.UpdateError):
            updater.parse_discovery(LINE + "\n" + LINE.replace("project_version=v0.13.0-upstream.v2.11.0", "project_version=v9"), IP, REGISTRY, COORDINATES)

    def test_duplicate_interfaces_deduplicate_but_conflicting_identity_fails(self):
        self.assertEqual(updater.parse_discovery(LINE + "\n" + LINE.replace("eth0", "wlan0"), IP, REGISTRY, COORDINATES)["mac"], MAC)
        conflicting = LINE.replace("project_version=v0.13.0-upstream.v2.11.0", "project_version=v9")
        with self.assertRaises(updater.UpdateError):
            updater.parse_discovery(LINE + "\n" + conflicting, IP, REGISTRY, COORDINATES)

    def test_quoted_txt_handles_escaped_semicolon_quotes_and_conflicting_duplicates(self):
        device = updater.parse_discovery(ESCAPED_LINE, IP, REGISTRY, COORDINATES)
        txt = updater.parse_txt_fields(updater._split_avahi_fields(ESCAPED_LINE)[9:])
        self.assertEqual(txt["friendly_name"], 'Hall; "Panel"')
        self.assertEqual(device["mac"], MAC)
        self.assertEqual(updater.parse_txt_fields(['"key=ok" "key=ok"'])["key"], "ok")
        with self.assertRaises(updater.UpdateError):
            updater.parse_txt_fields(['"key=first" "key=second"'])


class ReleaseTests(unittest.TestCase):
    def test_release_pagination_and_prerelease_order(self):
        stable = {"id": 3, "published_at": "2026-01-01T00:00:00Z", "draft": False, "prerelease": False}
        preview = {"id": 4, "published_at": "2026-02-01T00:00:00Z", "draft": False, "prerelease": True}
        draft = {"id": 5, "published_at": None, "draft": True}
        fetch = mock.Mock(side_effect=[[stable] * 100, [draft, preview]])
        releases = updater.published_releases(COORDINATES, fetch)
        self.assertEqual(len(fetch.call_args_list), 2)
        self.assertIn("/repos/example-org/espcontrol-community-devices/releases?", fetch.call_args_list[0].args[0])
        self.assertEqual(releases, [preview] + [stable] * 100)

    def test_missing_release_assets_and_malformed_manifest_fail(self):
        with self.assertRaises(updater.UpdateError):
            updater.release_artifact(SLUG, {"tag_name": "v1", "assets": []}, COORDINATES)
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(b"{}", SLUG, "v1", COORDINATES)

    def test_manifest_must_match_release_and_ota_path(self):
        tag = "community-v1.0-preview.1"
        root = f"https://github.com/{COORDINATES[0]}/{COORDINATES[1]}/releases/download/{tag}"
        manifest = {"version": "v1.0-preview.1", "builds": [{"chipFamily": updater.chip_family(SLUG), "ota": {
            "path": f"{root}/{SLUG}.ota.bin", "release_url": f"https://github.com/{COORDINATES[0]}/{COORDINATES[1]}/releases/tag/{tag}", "md5": "0" * 32}}]}
        self.assertEqual(updater.validate_manifest(json.dumps(manifest).encode(), SLUG, tag, COORDINATES), ("v1.0-preview.1", "0" * 32))
        manifest["builds"][0]["ota"]["path"] = f"{root}/{SLUG}.factory.bin"
        with self.assertRaises(updater.UpdateError):
            updater.validate_manifest(json.dumps(manifest).encode(), SLUG, tag, COORDINATES)

    def test_manifest_requires_md5_and_matching_version_and_chip(self):
        tag = "community-v1.0.0"
        root = f"https://github.com/{COORDINATES[0]}/{COORDINATES[1]}/releases/download/{tag}"
        ota = {"path": f"{root}/{SLUG}.ota.bin", "release_url": f"https://github.com/{COORDINATES[0]}/{COORDINATES[1]}/releases/tag/{tag}", "md5": "a" * 32}
        manifest = {"version": "v1.0.0", "builds": [{"chipFamily": updater.chip_family(SLUG), "ota": ota}]}
        self.assertEqual(updater.validate_manifest(json.dumps(manifest), SLUG, tag, COORDINATES)[0], "v1.0.0")
        for change in (
            lambda m: m["builds"][0]["ota"].pop("md5"),
            lambda m: m.update(version="v2.0.0"),
            lambda m: m["builds"][0].update(chipFamily="ESP32-P4"),
        ):
            broken = json.loads(json.dumps(manifest))
            change(broken)
            with self.subTest(manifest=broken), self.assertRaises(updater.UpdateError):
                updater.validate_manifest(json.dumps(broken), SLUG, tag, COORDINATES)

    def test_checksum_validation(self):
        data = b"firmware"
        asset = {"digest": "sha256:" + hashlib.sha256(data).hexdigest()}
        self.assertEqual(updater.verify_firmware(data, asset, hashlib.md5(data).hexdigest()), asset["digest"].split(":")[1])
        with self.assertRaises(updater.UpdateError):
            updater.verify_firmware(data, {"digest": "sha256:" + "0" * 64}, None)
        with self.assertRaises(updater.UpdateError):
            updater.verify_firmware(data, {}, "0" * 32)


class SafetyTests(unittest.TestCase):
    def test_cancel_and_dry_run_do_not_invoke_upload(self):
        with mock.patch.object(updater, "repository_coordinates", return_value=COORDINATES), \
             mock.patch.object(updater, "discover", return_value={"slug": SLUG, "model": "Model", "mac": MAC, "version": "old"}), \
             mock.patch.object(updater, "published_releases", return_value=[{"tag_name": "v2", "published_at": "now", "prerelease": True, "assets": []}]), \
             mock.patch.object(updater, "release_artifact", return_value={"tag": "v2", "ota_name": SLUG + ".ota.bin", "manifest_url": "https://github.com/manifest", "ota_url": "https://github.com/ota", "ota_asset": {}}), \
             mock.patch.object(updater, "_download", side_effect=[b"manifest", b"manifest", b"firmware"]) as download, \
             mock.patch.object(updater, "validate_manifest", return_value=("new", None)), \
             mock.patch.object(updater, "verify_firmware", return_value="digest"), \
             mock.patch.object(updater, "run_update") as upload, \
             mock.patch("builtins.input", return_value="no"):
            self.assertEqual(updater.main(["--dry-run", IP]), 0)
            self.assertEqual(updater.main([IP]), 0)
        self.assertEqual(download.call_count, 3)  # Manifest for both plans, firmware only for actual mode.
        self.assertEqual(download.call_args_list[0].args, ("https://github.com/manifest",))
        self.assertEqual(download.call_args_list[1].args, ("https://github.com/manifest",))
        self.assertEqual(download.call_args_list[2].args, ("https://github.com/ota",))
        upload.assert_not_called()

    def test_upload_uses_ota_file_and_explicit_ip(self):
        device = {"slug": SLUG}
        artifact = {"ota_name": SLUG + ".ota.bin"}
        calls = []

        def fake_runner(args, **kwargs):
            calls.append((args, kwargs))
            return mock.Mock(returncode=0, stdout="Update Successful!\n200", stderr="")

        with mock.patch.object(updater, "shutil_which", return_value="/usr/bin/curl"), \
             mock.patch.object(updater, "discover", return_value={"slug": SLUG, "mac": MAC, "version": "v2"}):
            updater.run_update({**device, "mac": MAC, "version": "old"}, b"firmware", artifact, "v2", IP, COORDINATES, runner=fake_runner)
        args, kwargs = calls[0]
        self.assertEqual(args[0:2], ["/usr/bin/curl", "--disable"])
        self.assertEqual(args[1:4], ["--disable", "--noproxy", "*"])
        self.assertIn("--fail", args)
        self.assertIn("--silent", args)
        self.assertIn("--show-error", args)
        self.assertIn("--form", args)
        form_arg = args[args.index("--form") + 1]
        self.assertTrue(form_arg.startswith("file=@"))
        self.assertTrue(form_arg.endswith(".bin"))
        self.assertEqual(args[args.index("--write-out") + 1], "\n%{http_code}")
        self.assertEqual(args[-1], f"http://{IP}/update")
        self.assertNotIn("--location", args)
        self.assertNotIn("shell", kwargs)
        self.assertTrue(kwargs["capture_output"])

    def test_http_or_curl_failure_and_unexpected_response_abort(self):
        device = {"slug": SLUG, "mac": MAC, "version": "old"}
        artifact = {"ota_name": SLUG + ".ota.bin"}
        outcomes = (
            (mock.Mock(returncode=22, stdout="HTTP failure\n500", stderr="HTTP failure"), "curl HTTP OTA upload failed"),
            (mock.Mock(returncode=0, stdout="Update Failed!\n200", stderr=""), "expected 'Update Successful!'"),
            (mock.Mock(returncode=0, stdout="Update Successful!\n302", stderr=""), "did not return a 2xx status"),
        )
        for result, message in outcomes:
            with self.subTest(result=result), \
                 mock.patch.object(updater, "shutil_which", return_value="/usr/bin/curl"), \
                 self.assertRaisesRegex(updater.UpdateError, message):
                updater.run_update(device, b"firmware", artifact, "v2", IP, COORDINATES,
                                   runner=mock.Mock(return_value=result))

    def test_successful_upload_rediscovery_verifies_target_version(self):
        device = {"slug": SLUG, "mac": MAC, "version": "old"}
        artifact = {"ota_name": SLUG + ".ota.bin"}
        runner = mock.Mock(return_value=mock.Mock(returncode=0))
        verified = {"slug": SLUG, "mac": MAC, "version": "new"}
        runner.return_value.stdout = "Update Successful!\n200"
        with mock.patch.object(updater, "shutil_which", return_value="/usr/bin/curl"), \
             mock.patch.object(updater, "discover", return_value=verified):
            updater.run_update(device, b"firmware", artifact, "new", IP, COORDINATES, runner=runner)
        runner.assert_called_once()
        self.assertEqual(runner.call_args.args[0][0:2], ["/usr/bin/curl", "--disable"])
        self.assertEqual(runner.call_args.args[0][-1], f"http://{IP}/update")
        self.assertTrue(runner.call_args.kwargs["capture_output"])

    def test_post_upload_slug_or_mac_mismatch_fails_immediately(self):
        device = {"slug": SLUG, "mac": MAC, "version": "old"}
        artifact = {"ota_name": SLUG + ".ota.bin"}
        for changed in (
            {"slug": "other-model", "mac": MAC, "version": "new"},
            {"slug": SLUG, "mac": "02:00:00:00:00:02", "version": "new"},
        ):
            runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout="Update Successful!\n200", stderr=""))
            with self.subTest(changed=changed), \
                 mock.patch.object(updater, "shutil_which", return_value="/usr/bin/curl"), \
                 mock.patch.object(updater, "discover", return_value=changed), \
                 self.assertRaises(updater.UpdateError):
                 updater.run_update(device, b"firmware", artifact, "new", IP, COORDINATES, runner=runner)
            runner.assert_called_once()

    def test_unchanged_version_times_out_without_upload_retry(self):
        device = {"slug": SLUG, "mac": MAC, "version": "old"}
        artifact = {"ota_name": SLUG + ".ota.bin"}
        runner = mock.Mock(return_value=mock.Mock(returncode=0, stdout="Update Successful!\n200", stderr=""))
        unchanged = {"slug": SLUG, "mac": MAC, "version": "old"}
        with mock.patch.object(updater, "shutil_which", return_value="/usr/bin/curl"), \
             mock.patch.object(updater, "discover", return_value=unchanged), \
             mock.patch.object(updater.time, "monotonic", side_effect=[0, 0, 91]), \
             mock.patch.object(updater.time, "sleep") as sleep, \
             self.assertRaisesRegex(updater.UpdateError, "no retry or rollback"):
            updater.run_update(device, b"firmware", artifact, "new", IP, COORDINATES, runner=runner)
        runner.assert_called_once()
        sleep.assert_called_once_with(3)

    def test_redirect_to_untrusted_or_http_url_is_rejected(self):
        handler = updater.TrustedRedirectHandler()
        request = urllib.request.Request("https://github.com/example")
        for destination in ("http://github.com/file", "https://evil.invalid/file"):
            with self.subTest(destination=destination), self.assertRaises(updater.UpdateError):
                handler.redirect_request(request, None, 302, "Found", {}, destination)

    def test_ipv6_target_is_rejected_before_discovery(self):
        with mock.patch.object(updater, "repository_coordinates", return_value=COORDINATES), \
             mock.patch.object(updater, "discover") as discover:
            self.assertEqual(updater.main(["2001:db8::1"]), 1)
        discover.assert_not_called()

    def test_identity_changes_preupload_and_wrong_postupdate_slug_fail(self):
        target = {"slug": SLUG, "mac": MAC, "version": "current"}
        with self.assertRaises(updater.UpdateError):
            updater.require_same_identity(target, {"slug": SLUG, "mac": "02:00:00:00:00:02", "version": "current"}, require_version=True)
        with self.assertRaises(updater.UpdateError):
            updater.require_same_identity(target, {"slug": "other-model", "mac": MAC, "version": "new"})

    def test_main_aborts_without_upload_when_target_changes_before_upload(self):
        original = {"slug": SLUG, "model": "Model", "mac": MAC, "version": "old"}
        changed = {**original, "mac": "02:00:00:00:00:02"}
        artifact = {"tag": "community-v2", "ota_name": SLUG + ".ota.bin", "manifest_url": "https://github.com/manifest", "ota_url": "https://github.com/ota", "ota_asset": {}}
        with mock.patch.object(updater, "repository_coordinates", return_value=COORDINATES), \
             mock.patch.object(updater, "device_registry", return_value=REGISTRY), \
             mock.patch.object(updater, "discover", side_effect=[original, changed]), \
             mock.patch.object(updater, "published_releases", return_value=[{"tag_name": "community-v2", "published_at": "now", "prerelease": False}]), \
             mock.patch.object(updater, "release_artifact", return_value=artifact), \
             mock.patch.object(updater, "_download", side_effect=[b"manifest", b"firmware"]), \
             mock.patch.object(updater, "validate_manifest", return_value=("v2", "a" * 32)), \
             mock.patch.object(updater, "verify_firmware", return_value="digest"), \
             mock.patch.object(updater, "run_update") as upload, \
             mock.patch("builtins.input", return_value="yes"):
            self.assertEqual(updater.main([IP]), 1)
        upload.assert_not_called()

    def test_asset_url_requires_exact_expected_basename(self):
        tag = "v1.0.0"
        assets = []
        for name in (SLUG + "-manifest.json", SLUG + ".ota.bin"):
            assets.append({"name": name, "browser_download_url": f"https://github.com/{COORDINATES[0]}/{COORDINATES[1]}/releases/download/{tag}/{name}"})
        assets[1]["browser_download_url"] = assets[1]["browser_download_url"].replace(SLUG + ".ota.bin", SLUG + ".factory.bin")
        with self.assertRaises(updater.UpdateError):
            updater.release_artifact(SLUG, {"tag_name": tag, "assets": assets}, COORDINATES)


if __name__ == "__main__":
    unittest.main()
