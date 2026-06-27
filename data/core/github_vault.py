from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import requests


@dataclass
class GitHubVaultConfig:
    token: str
    repo: str
    branch: str = "main"
    root: str = ""

    @property
    def is_ready(self) -> bool:
        return bool(self.token and self.repo)


def _get_secret(secrets, key: str, default=None):
    try:
        if secrets is not None and key in secrets:
            return secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


def load_github_config(secrets=None) -> GitHubVaultConfig:
    secrets = secrets or {}
    return GitHubVaultConfig(
        token=_get_secret(secrets, "GITHUB_TOKEN", "") or "",
        repo=_get_secret(secrets, "GITHUB_REPO", "") or "",
        branch=_get_secret(secrets, "GITHUB_BRANCH", "main") or "main",
        root=(_get_secret(secrets, "GITHUB_VAULT_ROOT", "") or "").strip("/"),
    )


def _join_root(root: str, path: str) -> str:
    path = (path or "").strip("/")
    root = (root or "").strip("/")
    return f"{root}/{path}" if root else path


def _strip_root(root: str, path: str) -> str:
    path = (path or "").strip("/")
    root = (root or "").strip("/")
    if root and path.startswith(root + "/"):
        return path[len(root) + 1:]
    return path


class GitHubVaultClient:
    def __init__(self, config: GitHubVaultConfig):
        self.config = config
        self.base_url = f"https://api.github.com/repos/{config.repo}/contents"
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {config.token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path}"

    def _remote_path(self, relative_path: str) -> str:
        return _join_root(self.config.root, relative_path)

    def get_item(self, relative_path: str) -> Optional[dict]:
        path = self._remote_path(relative_path)
        params = {"ref": self.config.branch}
        response = requests.get(self._url(path), headers=self.headers, params=params, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else None

    def get_sha(self, relative_path: str) -> Optional[str]:
        item = self.get_item(relative_path)
        if item:
            return item.get("sha")
        return None

    def read_text(self, relative_path: str) -> Tuple[Optional[str], Optional[str]]:
        item = self.get_item(relative_path)
        if not item:
            return None, None
        content = item.get("content")
        if content is None:
            return None, item.get("sha")
        decoded = base64.b64decode(content.encode("ascii")).decode("utf-8")
        return decoded, item.get("sha")

    def list_files(self, relative_dir: str = "") -> List[dict]:
        """Recursively list files under relative_dir. Returned paths are relative to vault root."""
        start = self._remote_path(relative_dir)
        collected: List[dict] = []

        def walk(remote_path: str):
            params = {"ref": self.config.branch}
            response = requests.get(self._url(remote_path), headers=self.headers, params=params, timeout=30)
            if response.status_code == 404:
                return
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                if data.get("type") == "file":
                    collected.append({
                        "path": _strip_root(self.config.root, data.get("path", "")),
                        "sha": data.get("sha"),
                        "name": data.get("name"),
                        "type": data.get("type"),
                    })
                return
            for item in data:
                if item.get("type") == "dir":
                    walk(item.get("path", ""))
                elif item.get("type") == "file":
                    collected.append({
                        "path": _strip_root(self.config.root, item.get("path", "")),
                        "sha": item.get("sha"),
                        "name": item.get("name"),
                        "type": item.get("type"),
                    })

        walk(start)
        return collected

    def upsert_file(self, relative_path: str, content: str, message: str, expected_sha: Optional[str] = None, force: bool = False) -> Tuple[bool, str, Optional[str]]:
        path = self._remote_path(relative_path)
        current_sha = self.get_sha(relative_path)
        if expected_sha and current_sha and current_sha != expected_sha and not force:
            return False, f"{relative_path}: conflict — remote file changed since last sync", current_sha

        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload = {
            "message": message,
            "content": encoded,
            "branch": self.config.branch,
        }
        if current_sha:
            payload["sha"] = current_sha

        response = requests.put(self._url(path), headers=self.headers, json=payload, timeout=60)
        if response.status_code not in (200, 201):
            return False, f"{relative_path}: HTTP {response.status_code} — {response.text[:300]}", current_sha
        data = response.json()
        new_sha = None
        try:
            new_sha = data.get("content", {}).get("sha")
        except Exception:
            new_sha = None
        action = "updated" if current_sha else "created"
        return True, f"{relative_path}: {action}", new_sha or current_sha

    def sync_files(self, files: Dict[str, str], message_prefix: str = "LifeOS sync", expected_shas: Optional[Dict[str, str]] = None, force: bool = False) -> Dict[str, List[str] | Dict[str, str]]:
        results: Dict[str, List[str] | Dict[str, str]] = {"ok": [], "failed": [], "conflicts": [], "shas": {}}
        expected_shas = expected_shas or {}
        for path, content in files.items():
            ok, msg, sha = self.upsert_file(
                path,
                content,
                f"{message_prefix}: {path}",
                expected_sha=expected_shas.get(path),
                force=force,
            )
            if ok:
                results["ok"].append(msg)
                if sha:
                    results["shas"][path] = sha
            elif "conflict" in msg.lower():
                results["conflicts"].append(msg)
                if sha:
                    results["shas"][path] = sha
            else:
                results["failed"].append(msg)
        return results
