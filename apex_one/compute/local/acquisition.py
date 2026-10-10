"""Explicit, verified acquisition of open-weight GGUF models from an OCI registry (Docker Hub `ai/` catalogue).

Never automatic: called only by `apex-one local acquire <key>`. Checks disk space first, downloads each layer with
resume support, verifies the sha256 digest of every blob, and records provenance (registry, digest, licence files
shipped with the artifact) in `var/models/<key>/apex_manifest.json`.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml

from apex_one.settings import get_settings

ACCEPT = "application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"


@dataclass
class LocalModelSpec:
    key: str
    registry_model: str
    repository: str
    tag: str
    port: int
    ctx: int = 8192
    vision: bool = False
    approx_gb: float = 0.0
    min_ram_gb: float = 0.0
    registry: str = "registry-1.docker.io"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def dir(self) -> Path:
        return models_dir() / self.key


def load_catalogue() -> tuple[dict[str, Any], dict[str, LocalModelSpec]]:
    data = yaml.safe_load((get_settings().config_dir / "local_models.yaml").read_text(encoding="utf-8"))
    specs = {}
    for m in data["models"]:
        src = m["source"]
        specs[m["key"]] = LocalModelSpec(key=m["key"], registry_model=m["registry_model"], repository=src["repository"],
                                         tag=src["tag"], port=m["port"], ctx=m.get("ctx", 8192),
                                         vision=m.get("vision", False), approx_gb=m.get("approx_gb", 0),
                                         min_ram_gb=m.get("min_ram_gb", 0), registry=src.get("registry", "registry-1.docker.io"),
                                         extra={k: v for k, v in m.items() if k == "chat_template_kwargs"})
    return data["runtime"], specs


def models_dir() -> Path:
    runtime, _ = load_catalogue()
    p = Path(runtime["models_dir"])
    return p if p.is_absolute() else get_settings().home / p


def _token(client: httpx.Client, repository: str) -> str:
    r = client.get("https://auth.docker.io/token",
                   params={"service": "registry.docker.io", "scope": f"repository:{repository}:pull"})
    r.raise_for_status()
    return r.json()["token"]


def fetch_manifest(spec: LocalModelSpec, client: httpx.Client | None = None, *, max_wait_s: float = 4500,
                   progress: Callable[[str], None] = print) -> dict[str, Any]:
    """Manifest GETs count against the registry pull quota: cache them, and WAIT (never bypass) on HTTP 429."""
    cache = spec.dir / "oci_manifest.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    import time

    waited = 0.0
    while True:
        try:
            m = _fetch_manifest_once(spec, client)
            spec.dir.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(m, indent=2), encoding="utf-8")
            return m
        except httpx.HTTPStatusError as e:
            if e.response.status_code != 429 or waited >= max_wait_s:
                raise
            progress(f"{spec.key}: registry pull quota exhausted (429); waiting 300 s (waited {waited:.0f} s)")
            time.sleep(300)
            waited += 300


def _fetch_manifest_once(spec: LocalModelSpec, client: httpx.Client | None = None) -> dict[str, Any]:
    own = client is None
    client = client or httpx.Client(timeout=30, follow_redirects=True)
    try:
        h = {"Authorization": f"Bearer {_token(client, spec.repository)}", "Accept": ACCEPT}
        r = client.get(f"https://{spec.registry}/v2/{spec.repository}/manifests/{spec.tag}", headers=h)
        r.raise_for_status()
        m = r.json()
        if "manifests" in m:  # index -> first manifest
            r = client.get(f"https://{spec.registry}/v2/{spec.repository}/manifests/{m['manifests'][0]['digest']}",
                           headers=h)
            r.raise_for_status()
            m = r.json()
        return m
    finally:
        if own:
            client.close()


def _download_blob(client: httpx.Client, spec: LocalModelSpec, digest: str, size: int, dest: Path,
                   progress: Callable[[str], None]) -> None:
    algo, _, expected = digest.partition(":")
    if dest.exists() and dest.stat().st_size == size and _sha256(dest) == expected:
        progress(f"{dest.name}: already present and verified")
        return
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(6):
        have = part.stat().st_size if part.exists() else 0
        if have >= size:
            break
        h = {"Authorization": f"Bearer {_token(client, spec.repository)}"}
        if have:
            h["Range"] = f"bytes={have}-"
        try:
            with client.stream("GET", f"https://{spec.registry}/v2/{spec.repository}/blobs/{digest}", headers=h) as r:
                if r.status_code not in (200, 206):
                    raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                mode = "ab" if (have and r.status_code == 206) else "wb"
                with part.open(mode) as fh:
                    for chunk in r.iter_bytes(1 << 20):
                        fh.write(chunk)
        except (httpx.HTTPError, OSError) as e:
            progress(f"{dest.name}: attempt {attempt + 1} interrupted ({type(e).__name__}); resuming")
    if part.stat().st_size != size:
        raise RuntimeError(f"{dest.name}: size mismatch {part.stat().st_size} != {size}")
    if algo != "sha256" or _sha256(part) != expected:
        part.unlink()
        raise RuntimeError(f"{dest.name}: digest verification FAILED (file deleted)")
    part.rename(dest)
    progress(f"{dest.name}: {size / 1e9:.2f} GB downloaded, sha256 verified")


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            h.update(chunk)
    return h.hexdigest()


def acquire(spec: LocalModelSpec, progress: Callable[[str], None] = print, reserve_gb: float = 3.0) -> dict[str, Any]:
    spec.dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=httpx.Timeout(60, read=300), follow_redirects=True) as client:
        m = fetch_manifest(spec, client, progress=progress)
        layers = m.get("layers", [])
        need = sum(l["size"] for l in layers if not (spec.dir / _fname(l)).exists())
        free = shutil.disk_usage(spec.dir).free
        if need + reserve_gb * 1e9 > free:
            raise RuntimeError(f"not enough disk: need {need / 1e9:.1f} GB + {reserve_gb} GB reserve, free {free / 1e9:.1f} GB")
        files = []
        for layer in layers:
            name = _fname(layer)
            _download_blob(client, spec, layer["digest"], layer["size"], spec.dir / name, progress)
            files.append({"file": name, "digest": layer["digest"], "size": layer["size"],
                          "media_type": layer["mediaType"]})
        cfg = {}
        if m.get("config", {}).get("digest"):
            h = {"Authorization": f"Bearer {_token(client, spec.repository)}"}
            r = client.get(f"https://{spec.registry}/v2/{spec.repository}/blobs/{m['config']['digest']}", headers=h)
            if r.status_code == 200:
                try:
                    cfg = r.json()
                except ValueError:
                    cfg = {}
    record = {"key": spec.key, "registry_model": spec.registry_model, "source": f"{spec.registry}/{spec.repository}:{spec.tag}",
              "artifact_type": m.get("artifactType"), "files": files, "config": cfg,
              "licence_files": [f["file"] for f in files if "licen" in f["file"].lower()]}
    (spec.dir / "apex_manifest.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def _fname(layer: dict[str, Any]) -> str:
    return Path(layer.get("annotations", {}).get("org.cncf.model.filepath") or layer["digest"].replace(":", "_")).name


def local_status() -> list[dict[str, Any]]:
    _, specs = load_catalogue()
    out = []
    for s in specs.values():
        man = s.dir / "apex_manifest.json"
        ggufs = sorted(p.name for p in s.dir.glob("*.gguf")) if s.dir.exists() else []
        out.append({"key": s.key, "registry_model": s.registry_model, "acquired": man.exists(), "files": ggufs,
                    "port": s.port, "vision": s.vision, "approx_gb": s.approx_gb})
    return out
