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
        if key in secrets:
            return secrets[key]
    except Exception:
        pass
    return os.environ.get(key, default)


def load_github_config(secrets=None) -> GitHubVaultConfig:
    if secrets is None:
        secrets = {}
    return GitHubVaultConfig(
        token=_get_secret(secrets, "GITHUB_TOKEN", "") or "",
        repo=_get_secret(secrets, "GITHUB_REPO", "") or "",
        branch=_get_secret(secrets, "GITHUB_BRANCH", "main") or "main",
        root=(_get_secret(secrets, "GITHUB_VAULT_ROOT", "") or "").strip("/"),
    )


def _join_root(root: str, path: str) -> str:
    path = path.strip("/")
    root = (root or "").strip("/")
    return f"{root}/{path}" if root else path


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

    def get_sha(self, path: str) -> Optional[str]:
        params = {"ref": self.config.branch}
        response = requests.get(self._url(path), headers=self.headers, params=params, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict):
            return data.get("sha")
        return None

    def upsert_file(self, relative_path: str, content: str, message: str) -> Tuple[bool, str]:
        path = _join_root(self.config.root, relative_path)
        sha = self.get_sha(path)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        payload = {
            "message": message,
            "content": encoded,
            "branch": self.config.branch,
        }
        if sha:
            payload["sha"] = sha

        response = requests.put(self._url(path), headers=self.headers, json=payload, timeout=60)
        if response.status_code not in (200, 201):
            return False, f"{relative_path}: HTTP {response.status_code} — {response.text[:300]}"
        action = "updated" if sha else "created"
        return True, f"{relative_path}: {action}"

    def sync_files(self, files: Dict[str, str], message_prefix: str = "LifeOS sync") -> Dict[str, List[str]]:
        results = {"ok": [], "failed": []}
        for path, content in files.items():
            ok, msg = self.upsert_file(path, content, f"{message_prefix}: {path}")
            if ok:
                results["ok"].append(msg)
            else:
                results["failed"].append(msg)
        return results
