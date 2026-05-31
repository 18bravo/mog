"""ComfyUI API client for the Mechanics of Government asset pipeline.

Talks to a local ComfyUI instance over its HTTP (`/prompt`, `/history`, `/view`)
and WebSocket (`/ws`) API. Loads an "API format" workflow JSON, lets you override
nodes by their `_meta.title` (POSITIVE / NEGATIVE / SAMPLER / LATENT / SAVE / ...),
queues it, waits for completion and downloads the resulting images.

Usage (library):
    from comfy_client import ComfyClient, load_workflow
    wf = load_workflow("workflows/terrain_tile_seamless.json")
    client = ComfyClient("127.0.0.1:8188")
    client.set_text(wf, "POSITIVE", "seamless snow tile ...")
    client.set_seed(wf, 42)
    paths = client.generate(wf, out_dir="assets/terrain", basename="snow__flat")

Usage (CLI smoke test / dry run, no server needed):
    python comfy_client.py --workflow workflows/terrain_tile_seamless.json \
        --positive "seamless snow tile" --seed 7 --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Workflow helpers (no network) — these are unit-testable on any machine.
# ---------------------------------------------------------------------------
def load_workflow(path: str | os.PathLike) -> Dict[str, Any]:
    """Load an API-format ComfyUI workflow JSON into a dict."""
    with open(path, "r", encoding="utf-8") as fh:
        wf = json.load(fh)
    if not isinstance(wf, dict) or not wf:
        raise ValueError(f"{path}: not a non-empty API-format workflow object")
    return wf


def find_node(wf: Dict[str, Any], title: str) -> Optional[str]:
    """Return the node id whose `_meta.title` matches `title` (case-insensitive)."""
    for node_id, node in wf.items():
        meta = node.get("_meta", {}) if isinstance(node, dict) else {}
        if str(meta.get("title", "")).strip().lower() == title.strip().lower():
            return node_id
    return None


def _require(wf: Dict[str, Any], title: str) -> str:
    node_id = find_node(wf, title)
    if node_id is None:
        raise KeyError(f"workflow has no node titled {title!r}")
    return node_id


def set_input(wf: Dict[str, Any], title: str, key: str, value: Any) -> None:
    wf[_require(wf, title)]["inputs"][key] = value


class _Mixin:
    """Shared convenience setters used by the client (kept stateless)."""

    @staticmethod
    def set_text(wf, title: str, text: str) -> None:
        set_input(wf, title, "text", text)

    @staticmethod
    def set_seed(wf, seed: int) -> None:
        set_input(wf, "SAMPLER", "seed", int(seed))

    @staticmethod
    def set_size(wf, width: int, height: int) -> None:
        set_input(wf, "LATENT", "width", int(width))
        set_input(wf, "LATENT", "height", int(height))

    @staticmethod
    def set_prefix(wf, prefix: str) -> None:
        set_input(wf, "SAVE", "filename_prefix", prefix)


# ---------------------------------------------------------------------------
# Networked client. Imports of requests/websocket are lazy so --dry-run and the
# validators run with zero third-party deps.
# ---------------------------------------------------------------------------
class ComfyClient(_Mixin):
    def __init__(self, server_address: str = "127.0.0.1:8188", timeout: int = 600):
        self.server = server_address.replace("http://", "").rstrip("/")
        self.client_id = str(uuid.uuid4())
        self.timeout = timeout

    # -- low level ---------------------------------------------------------
    def queue_prompt(self, wf: Dict[str, Any]) -> str:
        import requests

        payload = {"prompt": wf, "client_id": self.client_id}
        resp = requests.post(f"http://{self.server}/prompt", json=payload, timeout=30)
        if resp.status_code >= 400:
            # ComfyUI returns a JSON body explaining *why* a workflow was rejected
            # (missing node, bad ckpt_name, etc). Surface it instead of a bare 400.
            detail = resp.text
            try:
                err = resp.json()
                parts = []
                if err.get("error"):
                    e = err["error"]
                    parts.append(f"{e.get('type', '')}: {e.get('message', '')} {e.get('details', '')}".strip())
                for node_id, ne in (err.get("node_errors") or {}).items():
                    for d in ne.get("errors", []):
                        parts.append(
                            f"node {node_id} ({ne.get('class_type', '?')}): "
                            f"{d.get('message', '')} {d.get('details', '')}".strip()
                        )
                if parts:
                    detail = "\n  - " + "\n  - ".join(parts)
            except ValueError:
                pass
            raise RuntimeError(f"ComfyUI rejected the workflow (HTTP {resp.status_code}):{detail}")
        return resp.json()["prompt_id"]

    def upload_image(self, path: str | os.PathLike, subfolder: str = "mog_poses") -> str:
        """Upload an image to ComfyUI's input dir so a LoadImage node can use it.
        Returns the server-side reference ('subfolder/name') for the image widget."""
        import requests

        path = Path(path)
        with open(path, "rb") as fh:
            files = {"image": (path.name, fh, "image/png")}
            data = {"subfolder": subfolder, "overwrite": "true"}
            resp = requests.post(f"http://{self.server}/upload/image", files=files, data=data, timeout=30)
        resp.raise_for_status()
        j = resp.json()
        sub = j.get("subfolder", "")
        return f"{sub}/{j['name']}" if sub else j["name"]

    def _wait(self, prompt_id: str) -> None:
        from websocket import create_connection

        ws = create_connection(
            f"ws://{self.server}/ws?clientId={self.client_id}", timeout=self.timeout
        )
        try:
            while True:
                msg = ws.recv()
                if not isinstance(msg, str):
                    continue  # binary preview frame
                data = json.loads(msg)
                if data.get("type") == "executing":
                    d = data["data"]
                    if d.get("node") is None and d.get("prompt_id") == prompt_id:
                        return  # finished
        finally:
            ws.close()

    def _history(self, prompt_id: str) -> Dict[str, Any]:
        import requests

        resp = requests.get(f"http://{self.server}/history/{prompt_id}", timeout=30)
        resp.raise_for_status()
        return resp.json().get(prompt_id, {})

    def _download(self, image: Dict[str, str], dest: Path) -> None:
        import requests

        params = {
            "filename": image["filename"],
            "subfolder": image.get("subfolder", ""),
            "type": image.get("type", "output"),
        }
        resp = requests.get(f"http://{self.server}/view", params=params, timeout=60)
        resp.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)

    # -- high level --------------------------------------------------------
    def generate(
        self, wf: Dict[str, Any], out_dir: str, basename: str
    ) -> List[Path]:
        """Queue `wf`, wait, and save every output image as `<basename>__NNN.png`."""
        prompt_id = self.queue_prompt(wf)
        self._wait(prompt_id)
        history = self._history(prompt_id)

        saved: List[Path] = []
        idx = 1
        for node_out in history.get("outputs", {}).values():
            for image in node_out.get("images", []):
                dest = Path(out_dir) / f"{basename}__{idx:03d}.png"
                self._download(image, dest)
                saved.append(dest)
                idx += 1
        return saved


# ---------------------------------------------------------------------------
# CLI — primarily a dry-run validator usable in CI without a GPU/server.
# ---------------------------------------------------------------------------
def _main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="ComfyUI workflow runner / dry-run")
    p.add_argument("--workflow", required=True)
    p.add_argument("--positive")
    p.add_argument("--negative")
    p.add_argument("--seed", type=int)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--server", default="127.0.0.1:8188")
    p.add_argument("--out-dir", default="assets/_scratch")
    p.add_argument("--basename", default="test")
    p.add_argument("--dry-run", action="store_true", help="build the request, do not call ComfyUI")
    args = p.parse_args(argv)

    wf = load_workflow(args.workflow)
    if args.positive is not None:
        _Mixin.set_text(wf, "POSITIVE", args.positive)
    if args.negative is not None:
        _Mixin.set_text(wf, "NEGATIVE", args.negative)
    if args.seed is not None:
        _Mixin.set_seed(wf, args.seed)
    if args.width and args.height:
        _Mixin.set_size(wf, args.width, args.height)

    if args.dry_run:
        print("[dry-run] resolved workflow request:")
        print(json.dumps(wf, indent=2))
        for t in ("POSITIVE", "NEGATIVE", "SAMPLER", "LATENT", "SAVE"):
            nid = find_node(wf, t)
            print(f"  node {t:9} -> id {nid}")
        return 0

    client = ComfyClient(args.server)
    paths = client.generate(wf, args.out_dir, args.basename)
    print(f"Saved {len(paths)} image(s):")
    for path in paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
