#!/usr/bin/env python3
"""
check_image_privacy.py – Refuse to ship images or videos carrying location
metadata.

Usage:
    python3 community/scripts/check_image_privacy.py
    python3 community/scripts/check_image_privacy.py --strip [paths...]
    python3 community/scripts/check_image_privacy.py --self-test

Why this exists
---------------
Hardware verification is the most valuable contribution here, and it arrives
as a photo (or video) of someone's panel — taken at home, on a phone, with
location services on. That media goes into docs/public/images/ and is
published on the Pages site and kept in git history forever.

A verification photo attached to a PR carried GPS coordinates precise to a few
metres: latitude, longitude, altitude, bearing and a timestamp. Copying it
straight into the repo would have published a contributor's home address as a
side effect of them helping out. Nothing in the pipeline would have noticed.

So this fails the build on any tracked image carrying location EXIF, or video
carrying a location container tag, rather than relying on whoever commits it
to remember. `--strip` rewrites the offending files in place: for an image,
EXIF removed entirely (orientation applied first so portrait photos do not
end up sideways); for a video, remuxed with all container/stream metadata
stripped and the audio/video streams copied untouched (no re-encode, so no
quality loss).

Non-location EXIF (ColorSpace, dimensions) is left alone — it is harmless and
some existing images carry it.

Video scanning needs ffprobe/ffmpeg (present on GitHub's ubuntu-latest
runners by default). If no video is tracked, that dependency is never
checked, so this stays a no-op addition for a repo with only photos.
"""

import argparse
import glob
import json
import os
import subprocess
import sys

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff")
VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".webm")

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

# Container/stream metadata keys phones and editors use for a location —
# QuickTime's ISO 6709 point string (iPhone), and the generic tags a few
# other tools (and Matroska/WebM) use for the same thing.
LOCATION_TAG_KEYS = {
    "com.apple.quicktime.location.iso6709",
    "location",
    "location-eng",
    "gps",
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


def tracked_videos():
    """Every video git tracks, so an untracked scratch file is not scanned."""
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return sorted(glob.glob(os.path.join(
            REPO_ROOT, "docs", "public", "images", "*")))
    return [os.path.join(REPO_ROOT, line) for line in out.splitlines()
            if line.lower().endswith(VIDEO_EXTS)]


def video_location_tags_in(path):
    """Names of location-carrying container/stream tags in a video, or None
    if ffprobe is unavailable (caller decides whether that is fatal)."""
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", "-show_streams", path],
            capture_output=True, text=True)
    except FileNotFoundError:
        return None
    if result.returncode != 0:
        return [f"unreadable (ffprobe exit {result.returncode})"]
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return ["unreadable (bad ffprobe output)"]

    found = set()
    tag_dicts = [data.get("format", {}).get("tags", {}) or {}]
    tag_dicts += [s.get("tags", {}) or {} for s in data.get("streams", [])]
    for tags in tag_dicts:
        for key, value in tags.items():
            if key.lower() in LOCATION_TAG_KEYS and value:
                found.add(key)
    return sorted(found)


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


def strip_video(path):
    """Remux with all container/stream metadata removed; streams are copied,
    never re-encoded, so this cannot touch quality. Returns True if changed."""
    import tempfile

    fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(path)[1])
    os.close(fd)
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", path, "-map_metadata", "-1",
             "-c", "copy", tmp_path],
            check=True, capture_output=True)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return True


def location_tags_in(path):
    """Dispatch to the image or video scanner by extension."""
    if path.lower().endswith(VIDEO_EXTS):
        return video_location_tags_in(path)
    return sensitive_tags_in(path)


def strip_target(path):
    """Dispatch to the image or video stripper by extension."""
    if path.lower().endswith(VIDEO_EXTS):
        return strip_video(path)
    return strip(path)


def main():
    parser = argparse.ArgumentParser(
        description="Fail on images or videos carrying location metadata")
    parser.add_argument("--strip", nargs="*", metavar="PATH",
                        help="strip metadata from the given images/videos "
                             "(or every offending tracked file)")
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

    videos = tracked_videos()
    # ffprobe/ffmpeg is only required when there is actually a video to
    # scan, so a repo with only photos never needs it installed.
    if videos and video_location_tags_in(videos[0]) is None:
        print("ffprobe (part of ffmpeg) is required to scan tracked videos",
              file=sys.stderr)
        sys.exit(1)

    if args.strip is not None:
        targets = args.strip or [
            p for p in tracked_images() + videos if location_tags_in(p)]
        if not targets:
            print("Nothing to strip.")
            return
        for p in targets:
            strip_target(p)
            print(f"  stripped {os.path.relpath(p, REPO_ROOT)}")
        print(f"Stripped {len(targets)} file(s). Re-run without --strip.")
        return

    images = tracked_images()
    media = images + videos
    if not media:
        print("No tracked images or videos. Nothing to check.")
        return

    offenders = []
    for path in media:
        found = location_tags_in(path)
        if found:
            offenders.append((os.path.relpath(path, REPO_ROOT), found))

    if offenders:
        print(f"\nFiles carrying sensitive metadata ({len(offenders)}):",
              file=sys.stderr)
        for rel, tags in offenders:
            print(f"  ✗ {rel}: {', '.join(tags)}", file=sys.stderr)
        print("\nA verification photo or video is taken at someone's home. "
              "Publishing its location metadata exposes their address, "
              "permanently and in git history.\nFix: "
              "python3 community/scripts/check_image_privacy.py --strip",
              file=sys.stderr)
        sys.exit(1)

    print(f"Image privacy check passed ({len(images)} image(s), "
          f"{len(videos)} video(s), no location metadata).")


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

    self_test_video()

    print("\nAll check_image_privacy self-tests passed! ✓")


def self_test_video():
    import tempfile, shutil

    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("  ! ffmpeg/ffprobe unavailable, skipping video tests")
        return

    tmp = tempfile.mkdtemp(prefix="img_privacy_video_test_")
    try:
        clean_path = os.path.join(tmp, "clean.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=blue:s=32x24:d=1",
             clean_path],
            check=True, capture_output=True)
        assert video_location_tags_in(clean_path) == [], \
            video_location_tags_in(clean_path)
        print("  ✓ Video with no location tag passes")

        # Build one carrying a location, the way a phone/editor would tag it
        # (ffmpeg's mov muxer round-trips the generic "location" key; real
        # device footage more commonly carries Apple's ISO6709 variant, also
        # in LOCATION_TAG_KEYS, but that key doesn't survive an ffmpeg remux
        # so it isn't practical to synthesize here).
        gps_path = os.path.join(tmp, "gps.mp4")
        subprocess.run(
            ["ffmpeg", "-y", "-i", clean_path,
             "-metadata", "location=+57.4321-014.2109+010.000/",
             "-c", "copy", gps_path],
            check=True, capture_output=True)
        found = video_location_tags_in(gps_path)
        assert found == ["location", "location-eng"], found
        print("  ✓ Video with a location tag is flagged")

        # Stripping clears it and keeps the video playable (same duration).
        import json as _json

        def duration(p):
            out = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", p],
                capture_output=True, text=True, check=True).stdout
            return float(_json.loads(out)["format"]["duration"])

        before = duration(gps_path)
        strip_video(gps_path)
        assert video_location_tags_in(gps_path) == [], \
            video_location_tags_in(gps_path)
        assert abs(duration(gps_path) - before) < 0.05
        print("  ✓ --strip removes it and preserves the video")

        # The dispatch helpers route by extension to the right scanner/stripper.
        assert location_tags_in(gps_path) == []
        assert location_tags_in(clean_path) == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
