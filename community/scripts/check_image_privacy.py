#!/usr/bin/env python3
"""
check_image_privacy.py – Refuse to ship images carrying location metadata.

Usage:
    python3 community/scripts/check_image_privacy.py
    python3 community/scripts/check_image_privacy.py --strip [paths...]
    python3 community/scripts/check_image_privacy.py --self-test

Why this exists
---------------
Hardware verification is the most valuable contribution here, and it arrives
as a photo of someone's panel — taken at home, on a phone, with location
services on. Those photos go into docs/public/images/ and are published on the
Pages site and kept in git history forever.

A verification photo attached to a PR carried GPS coordinates precise to a few
metres: latitude, longitude, altitude, bearing and a timestamp. Copying it
straight into the repo would have published a contributor's home address as a
side effect of them helping out. Nothing in the pipeline would have noticed.

So this fails the build on any tracked image carrying location EXIF, rather
than relying on whoever commits it to remember. `--strip` rewrites the
offending files in place: EXIF removed entirely, orientation applied first so
portrait photos do not end up sideways.

Non-location EXIF (ColorSpace, dimensions) is left alone — it is harmless and
some existing images carry it.
"""

import argparse
import glob
import os
import subprocess
import sys

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")

# EXIF tag 34853 is GPSInfo. Anything under it is location data.
GPS_IFD_TAG = 34853

# Other tags worth refusing: they can carry a place name or a device serial.
SENSITIVE_TAGS = {
    GPS_IFD_TAG: "GPSInfo",
    0xA430: "CameraOwnerName",
    0xA431: "BodySerialNumber",
    0x9286: "UserComment",
    0x010E: "ImageDescription",
}

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def tracked_images():
    """Every image git tracks, so an untracked scratch file is not scanned."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not a git checkout — fall back to the docs image directory.
        return sorted(glob.glob(os.path.join(
            REPO_ROOT, "docs", "public", "images", "*")))
    return [os.path.join(REPO_ROOT, line) for line in out.splitlines()
            if line.lower().endswith(IMAGE_EXTS)]


def sensitive_tags_in(path):
    """Names of sensitive EXIF tags present in the image, or []."""
    try:
        from PIL import Image
    except ImportError:
        return None  # caller decides whether that is fatal
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            if not exif:
                return []
            found = []
            for tag, name in SENSITIVE_TAGS.items():
                value = exif.get(tag)
                if tag == GPS_IFD_TAG:
                    # Pillow exposes GPS as a sub-IFD; an empty one is fine.
                    try:
                        gps = exif.get_ifd(GPS_IFD_TAG)
                    except Exception:
                        gps = value
                    if gps:
                        found.append(name)
                elif value not in (None, "", b""):
                    found.append(name)
            return found
    except Exception as exc:            # unreadable/corrupt is worth surfacing
        return [f"unreadable ({exc.__class__.__name__})"]


def strip(path):
    """Remove all EXIF, preserving visual orientation. Returns True if changed."""
    from PIL import Image, ImageOps
    with Image.open(path) as im:
        fmt = im.format
        im = ImageOps.exif_transpose(im)
        clean = Image.new(im.mode, im.size)
        clean.putdata(list(im.getdata()))
        if fmt == "JPEG":
            clean.save(path, "JPEG", quality=85, optimize=True)
        else:
            clean.save(path, fmt)
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Fail on images carrying location metadata")
    parser.add_argument("--strip", nargs="*", metavar="PATH",
                        help="strip EXIF from the given images "
                             "(or every offending tracked image)")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return

    try:
        import PIL  # noqa: F401
    except ImportError:
        print("Pillow is required: pip install Pillow", file=sys.stderr)
        sys.exit(1)

    if args.strip is not None:
        targets = args.strip or [
            p for p in tracked_images() if sensitive_tags_in(p)]
        if not targets:
            print("Nothing to strip.")
            return
        for p in targets:
            strip(p)
            print(f"  stripped {os.path.relpath(p, REPO_ROOT)}")
        print(f"Stripped {len(targets)} image(s). Re-run without --strip.")
        return

    images = tracked_images()
    if not images:
        print("No tracked images. Nothing to check.")
        return

    offenders = []
    for path in images:
        found = sensitive_tags_in(path)
        if found:
            offenders.append((os.path.relpath(path, REPO_ROOT), found))

    if offenders:
        print(f"\nImages carrying sensitive metadata ({len(offenders)}):",
              file=sys.stderr)
        for rel, tags in offenders:
            print(f"  ✗ {rel}: {', '.join(tags)}", file=sys.stderr)
        print("\nA verification photo is taken at someone's home. Publishing "
              "its GPS tags exposes their address, permanently and in git "
              "history.\nFix: python3 community/scripts/check_image_privacy.py "
              "--strip", file=sys.stderr)
        sys.exit(1)

    print(f"Image privacy check passed ({len(images)} image(s), "
          f"no location metadata).")


# =============================================================================
# Self-test
# =============================================================================


def self_test():
    print("Running check_image_privacy self-test...")
    try:
        from PIL import Image
    except ImportError:
        print("  ! Pillow unavailable, skipping"); return

    import tempfile, shutil
    tmp = tempfile.mkdtemp(prefix="img_privacy_test_")
    try:
        clean_path = os.path.join(tmp, "clean.jpg")
        Image.new("RGB", (24, 18), (10, 20, 30)).save(clean_path, "JPEG")
        assert sensitive_tags_in(clean_path) == [], sensitive_tags_in(clean_path)
        print("  ✓ Image with no EXIF passes")

        # Build one carrying GPS, the way a phone would.
        gps_path = os.path.join(tmp, "gps.jpg")
        im = Image.new("RGB", (24, 18), (30, 20, 10))
        exif = im.getexif()
        gps_ifd = exif.get_ifd(GPS_IFD_TAG)
        gps_ifd[1] = "N"
        gps_ifd[2] = (57.0, 44.0, 54.0)
        gps_ifd[3] = "E"
        gps_ifd[4] = (14.0, 9.0, 6.0)
        im.save(gps_path, "JPEG", exif=exif)
        found = sensitive_tags_in(gps_path)
        assert "GPSInfo" in found, f"GPS not detected: {found}"
        print("  ✓ Image with GPS EXIF is flagged")

        # Stripping clears it and keeps the pixels.
        before = Image.open(gps_path).size
        strip(gps_path)
        assert sensitive_tags_in(gps_path) == [], sensitive_tags_in(gps_path)
        assert Image.open(gps_path).size == before
        print("  ✓ --strip removes it and preserves the image")

        # Benign EXIF is not treated as sensitive.
        benign_path = os.path.join(tmp, "benign.jpg")
        im2 = Image.new("RGB", (24, 18), (0, 0, 0))
        ex2 = im2.getexif()
        ex2[0xA001] = 1          # ColorSpace
        im2.save(benign_path, "JPEG", exif=ex2)
        assert sensitive_tags_in(benign_path) == [], \
            sensitive_tags_in(benign_path)
        print("  ✓ Benign EXIF (ColorSpace) is allowed")

        # A description/comment tag is refused — it can name a place.
        desc_path = os.path.join(tmp, "desc.jpg")
        im3 = Image.new("RGB", (24, 18), (5, 5, 5))
        ex3 = im3.getexif()
        ex3[0x010E] = "Taken at home, Example Street"
        im3.save(desc_path, "JPEG", exif=ex3)
        assert "ImageDescription" in sensitive_tags_in(desc_path)
        print("  ✓ ImageDescription is flagged")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("\nAll check_image_privacy self-tests passed! ✓")


if __name__ == "__main__":
    main()
