#!/usr/bin/env python3
"""Launchpad PPA helpers: normalize a PPA reference and list its packages.

Accepts either form:
  - ppa short spec:  ppa:OWNER/ARCHIVE          e.g. ppa:fheimes/test
  - launchpad URL:   https://launchpad.net/~OWNER/+archive/ubuntu/ARCHIVE

CLI:
  python3 ppa.py <ppa-ref>                          # list published sources
  python3 ppa.py builds <ppa-ref> <pkg> [series]    # list per-arch build status
  python3 ppa.py fetch [<ppa-ref> <pkg> [series]]   # pull & unpack source
  python3 ppa.py binaries [<ppa-ref> <pkg> [series]]# build status + download debs
  python3 ppa.py current                            # show the recorded pick

For fetch/binaries/current, a missing target is read from .ppa-request (the pick
recorded by the web form).
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

API = "https://api.launchpad.net/devel"
DIR = os.path.dirname(os.path.abspath(__file__))
REQUEST_FILE = os.path.join(DIR, ".ppa-request")
WORK = "/tmp/opencode/ppa-review"


def normalize(ref: str):
    """Return (owner, archive) from a ppa: spec, owner/archive, or LP URL."""
    ref = ref.strip()
    m = re.search(r"~([^/]+)/\+archive/(?:ubuntu/)?([^/?#]+)", ref)
    if m:
        return m.group(1), m.group(2)
    m = re.fullmatch(r"(?:ppa:)?([^/:]+)/([^/]+)", ref)
    if m:
        return m.group(1), m.group(2)
    raise ValueError(f"unrecognized PPA reference: {ref!r}")


def api_archive_url(owner: str, archive: str) -> str:
    return f"{API}/~{owner}/+archive/ubuntu/{archive}"


def ppa_web_url(owner: str, archive: str) -> str:
    return f"https://launchpad.net/~{owner}/+archive/ubuntu/{archive}"


def list_sources(owner: str, archive: str, status: str = "Published"):
    """Return a list of dicts: name, version, series, status."""
    url = (f"{api_archive_url(owner, archive)}"
           f"?ws.op=getPublishedSources&status={status}")
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    out = []
    for e in data.get("entries", []):
        out.append({
            "name": e["source_package_name"],
            "version": e["source_package_version"],
            "series": e["distro_series_link"].rstrip("/").split("/")[-1],
            "status": e["status"],
        })
    out.sort(key=lambda x: (x["name"], x["version"]))
    return out


def _published_source(owner, archive, package, series=None):
    """Return the newest matching published-source entry (with self_link)."""
    url = (f"{api_archive_url(owner, archive)}?ws.op=getPublishedSources"
           f"&source_name={package}&exact_match=true")
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    entries = data.get("entries", [])
    if series:
        entries = [e for e in entries
                   if e["distro_series_link"].rstrip("/").split("/")[-1] == series]
    if not entries:
        raise LookupError(f"no published source {package!r} in ppa:{owner}/{archive}"
                          + (f" for {series}" if series else ""))
    return entries[0]


def list_builds(owner: str, archive: str, package: str, series=None):
    """Return per-arch build records: arch, state, build_log_url, web_link."""
    src = _published_source(owner, archive, package, series)
    url = src["self_link"] + "?ws.op=getBuilds"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    out = []
    for b in data.get("entries", []):
        out.append({
            "arch": b.get("arch_tag"),
            "state": b.get("buildstate"),
            "build_log_url": b.get("build_log_url"),
            "web_link": b.get("web_link"),
        })
    out.sort(key=lambda x: x["arch"] or "")
    return out


def read_request():
    """Parse the newest line of .ppa-request into a dict, or return None.

    Line format: <ts>\tppa:owner/archive\t<url>\t<package>\t<series>
    """
    try:
        text = open(REQUEST_FILE, encoding="utf-8").read()
    except FileNotFoundError:
        return None
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    parts = (lines[-1].split("\t") + [""] * 5)[:5]
    owner, archive = normalize(parts[1]) if parts[1] else ("", "")
    return {"owner": owner, "archive": archive,
            "package": parts[3], "series": parts[4]}


def resolve_target(args):
    """(owner, archive, package, series) from CLI args, else from .ppa-request."""
    if len(args) >= 2:
        owner, archive = normalize(args[0])
        return owner, archive, args[1], (args[2] if len(args) > 2 else "")
    req = read_request()
    if not req or not req["package"]:
        sys.exit("no package given and no pick recorded in .ppa-request\n"
                 "pick one on the PPA page, or pass: <ppa-ref> <pkg> [series]")
    return req["owner"], req["archive"], req["package"], req["series"]


def fetch(owner, archive, package, series=""):
    """Pull and unpack a PPA source package into WORK; return an exit code.

    pull-lp-source has no real PPA support, so we use pull-ppa-source with the
    PPA as OWNER/ARCHIVE and always pass the series. The target dir is cleaned
    first because pull-ppa-source aborts ("Source unpack failed") if it exists.
    --no-verify-signature: PPA keys aren't imported here; fine for a read-only
    review and must not abort the fetch.
    """
    owner_archive = f"{owner}/{archive}"
    print(f"PPA:     ppa:{owner_archive}\nPackage: {package}\n"
          f"Series:  {series or '<auto>'}")
    os.makedirs(WORK, exist_ok=True)
    for p in glob.glob(os.path.join(WORK, package + "*")):
        if os.path.isdir(p):
            shutil.rmtree(p, ignore_errors=True)
    cmd = ["pull-ppa-source", "--no-verify-signature", "--ppa",
           owner_archive, package] + ([series] if series else [])
    print("+ " + " ".join(cmd))
    rc = subprocess.run(cmd, cwd=WORK).returncode
    if rc != 0:
        print(f"pull-ppa-source failed (exit {rc})", file=sys.stderr)
        return rc
    trees = [t for t in sorted(glob.glob(os.path.join(WORK, package + "-*")))
             if os.path.isfile(os.path.join(t, "debian", "changelog"))]
    if not trees:
        print("fetch completed but no extracted source tree with debian/ found",
              file=sys.stderr)
        return 1
    tree = trees[-1]
    print(f"OK: source extracted to {tree}")
    with open(os.path.join(WORK, ".last-source"), "w", encoding="utf-8") as fh:
        fh.write(tree + "\n")
    return 0


def binaries(owner, archive, package, series=""):
    """Report per-arch build status and download binary .debs into WORK."""
    print(f"PPA:     ppa:{owner}/{archive}\nPackage: {package}   "
          f"Series: {series or '<auto>'}\n")
    print("== Build status (Launchpad) ==")
    builds = list_builds(owner, archive, package, series or None)
    failed = [b for b in builds if b["state"] != "Successfully built"]
    for b in builds:
        print(f"  - {b['arch']:<10} {b['state']}")
        if b in failed and b["build_log_url"]:
            print(f"      log: {b['build_log_url']}")
    if failed:
        print(">> One or more architectures FAILED to build (see log URL above).")
    print("\n== Downloading binary .deb packages ==")
    os.makedirs(WORK, exist_ok=True)
    for d in glob.glob(os.path.join(WORK, "*.deb")):
        os.remove(d)
    cmd = ["pull-ppa-source", "--no-verify-signature", "-p", "debs", "--ppa",
           f"{owner}/{archive}", package] + ([series] if series else [])
    subprocess.run(cmd, cwd=WORK)
    debs = sorted(glob.glob(os.path.join(WORK, "*.deb")))
    if debs:
        print(f"Downloaded {len(debs)} .deb(s):")
        for d in debs:
            print(f"   {d}")
    else:
        print("No .deb packages downloaded.")
    return 1 if failed else 0


if __name__ == "__main__":
    args = sys.argv[1:]
    cmd = args[0] if args else ""
    if cmd == "builds" and len(args) >= 3:
        owner, archive = normalize(args[1])
        builds = list_builds(owner, archive, args[2],
                             args[3] if len(args) > 3 else None)
        failed = [b for b in builds if b["state"] != "Successfully built"]
        print(f"builds for {args[2]} in ppa:{owner}/{archive}"
              + (f" ({args[3]})" if len(args) > 3 else "") + ":")
        for b in builds:
            print(f"  - {b['arch']:<10} {b['state']}")
            if b["state"] != "Successfully built" and b["build_log_url"]:
                print(f"      log: {b['build_log_url']}")
                print(f"      page: {b['web_link']}")
        sys.exit(1 if failed else 0)
    if cmd == "fetch":
        sys.exit(fetch(*resolve_target(args[1:])))
    if cmd == "binaries":
        sys.exit(binaries(*resolve_target(args[1:])))
    if cmd == "current":
        req = read_request()
        if not req:
            sys.exit("no .ppa-request recorded yet")
        print(f"ppa:{req['owner']}/{req['archive']}\t{req['package']}"
              f"\t{req['series']}")
        sys.exit(0)
    if len(args) != 1:
        sys.exit(__doc__)
    owner, archive = normalize(args[0])
    print(f"PPA: {ppa_web_url(owner, archive)}  (ppa:{owner}/{archive})")
    rows = list_sources(owner, archive)
    print(f"{len(rows)} published source(s):")
    for r in rows:
        print(f"  - {r['name']:<28} {r['version']:<32} {r['series']:<10} {r['status']}")
