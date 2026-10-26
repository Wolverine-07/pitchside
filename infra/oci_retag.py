"""Re-tag an image in Azure Container Registry with OCI media types.

Azure Container Apps rejects Docker v2 layer media types from some local Docker
setups ("unsupported MIME type for compression"). The layers themselves are
identical, so this rewrites only the manifest and pushes it under a new tag.

    python infra/oci_retag.py <registry>.azurecr.io pitchside v1 v1-oci
"""

import json
import os
import sys

import httpx

DOCKER_TO_OCI = {
    "application/vnd.docker.distribution.manifest.v2+json": "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json": "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.container.image.v1+json": "application/vnd.oci.image.config.v1+json",
    "application/vnd.docker.image.rootfs.diff.tar.gzip": "application/vnd.oci.image.layer.v1.tar+gzip",
}
ACCEPT = ",".join([*DOCKER_TO_OCI, *DOCKER_TO_OCI.values()])


def token(registry: str, repo: str, user: str, password: str) -> str:
    r = httpx.get(
        f"https://{registry}/oauth2/token",
        params={"service": registry, "scope": f"repository:{repo}:pull,push"},
        auth=(user, password),
    )
    r.raise_for_status()
    return r.json()["access_token"]


def convert(manifest: dict) -> dict:
    m = json.loads(json.dumps(manifest))
    m["mediaType"] = DOCKER_TO_OCI.get(m.get("mediaType"), m.get("mediaType"))
    if "config" in m:
        m["config"]["mediaType"] = DOCKER_TO_OCI.get(m["config"]["mediaType"], m["config"]["mediaType"])
    for layer in m.get("layers", []):
        layer["mediaType"] = DOCKER_TO_OCI.get(layer["mediaType"], layer["mediaType"])
    return m


def main() -> None:
    registry, repo, src, dst = sys.argv[1:5]
    user, password = os.environ["ACR_USER"], os.environ["ACR_PASSWORD"]
    h = {"Authorization": f"Bearer {token(registry, repo, user, password)}"}
    with httpx.Client(headers=h, timeout=60) as c:
        r = c.get(f"https://{registry}/v2/{repo}/manifests/{src}", headers={"Accept": ACCEPT})
        r.raise_for_status()
        manifest = r.json()
        if manifest.get("manifests"):  # an index: pick the linux/amd64 image
            entry = next(m for m in manifest["manifests"] if m.get("platform", {}).get("architecture") == "amd64")
            r = c.get(f"https://{registry}/v2/{repo}/manifests/{entry['digest']}", headers={"Accept": ACCEPT})
            r.raise_for_status()
            manifest = r.json()
        print("source:", manifest.get("mediaType"), "layers:", len(manifest.get("layers", [])))
        oci = convert(manifest)
        body = json.dumps(oci, separators=(",", ":")).encode()
        r = c.put(
            f"https://{registry}/v2/{repo}/manifests/{dst}",
            content=body,
            headers={"Content-Type": oci["mediaType"]},
        )
        r.raise_for_status()
        print("pushed", f"{registry}/{repo}:{dst}", r.headers.get("Docker-Content-Digest"))


if __name__ == "__main__":
    main()
