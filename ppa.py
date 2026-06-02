#!/usr/bin/env python3
"""Launchpad PPA helpers: normalize a PPA reference and list its packages.

Accepts either form:
  - ppa short spec:  ppa:OWNER/ARCHIVE          e.g. ppa:fheimes/test
  - launchpad URL:   https://launchpad.net/~OWNER/+archive/ubuntu/ARCHIVE

CLI:
  python3 ppa.py <ppa-ref>            # list published sources
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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: python3 ppa.py <ppa-ref>")
    owner, archive = normalize(sys.argv[1])
    print(f"PPA: {ppa_web_url(owner, archive)}  (ppa:{owner}/{archive})")
    rows = list_sources(owner, archive)
    print(f"{len(rows)} published source(s):")
    for r in rows:
        print(f"  - {r['name']:<28} {r['version']:<32} {r['series']:<10} {r['status']}")
