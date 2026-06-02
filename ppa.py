#!/usr/bin/env python3
"""Launchpad PPA helpers: normalize a PPA reference and list its packages.

Accepts either form:
  - ppa short spec:  ppa:OWNER/ARCHIVE          e.g. ppa:fheimes/test
  - launchpad URL:   https://launchpad.net/~OWNER/+archive/ubuntu/ARCHIVE

CLI:
  python3 ppa.py <ppa-ref>                     # list published sources
  python3 ppa.py builds <ppa-ref> <pkg> [series]  # list per-arch build status
"""
import json
import re
import sys
import urllib.request

API = "https://api.launchpad.net/devel"


def normalize(ref: str):
    """Return (owner, archive) from a ppa: spec or a launchpad.net URL."""
    ref = ref.strip()
    m = re.fullmatch(r"ppa:([^/]+)/(.+)", ref)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r"~([^/]+)/\+archive/(?:ubuntu/)?([^/?#]+)", ref)
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


if __name__ == "__main__":
    if len(sys.argv) >= 4 and sys.argv[1] == "builds":
        owner, archive = normalize(sys.argv[2])
        package = sys.argv[3]
        series = sys.argv[4] if len(sys.argv) > 4 else None
        builds = list_builds(owner, archive, package, series)
        failed = [b for b in builds if b["state"] != "Successfully built"]
        print(f"builds for {package} in ppa:{owner}/{archive}"
              + (f" ({series})" if series else "") + ":")
        for b in builds:
            print(f"  - {b['arch']:<10} {b['state']}")
            if b["state"] != "Successfully built" and b["build_log_url"]:
                print(f"      log: {b['build_log_url']}")
                print(f"      page: {b['web_link']}")
        sys.exit(1 if failed else 0)
    if len(sys.argv) != 2:
        sys.exit("usage: python3 ppa.py <ppa-ref>\n"
                 "       python3 ppa.py builds <ppa-ref> <pkg> [series]")
    owner, archive = normalize(sys.argv[1])
    print(f"PPA: {ppa_web_url(owner, archive)}  (ppa:{owner}/{archive})")
    rows = list_sources(owner, archive)
    print(f"{len(rows)} published source(s):")
    for r in rows:
        print(f"  - {r['name']:<28} {r['version']:<32} {r['series']:<10} {r['status']}")
