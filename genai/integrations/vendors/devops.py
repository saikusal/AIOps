import requests

from ..base import BaseAdapter
from ..registry import IntegrationRegistry
from .common import credential_metadata, credential_secret


class GitHubAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/') or 'https://api.github.com'}/user",
                headers={"Authorization": f"Bearer {credential_secret(self.integration)}"} if credential_secret(self.integration) else {},
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False


class GitLabAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/') or 'https://gitlab.com'}/api/v4/user",
                headers={"PRIVATE-TOKEN": credential_secret(self.integration)} if credential_secret(self.integration) else {},
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False


class BitbucketAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            metadata = credential_metadata(self.integration)
            username = str(metadata.get("username") or "")
            auth = (username, credential_secret(self.integration)) if username and credential_secret(self.integration) else None
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/') or 'https://api.bitbucket.org'}/2.0/user",
                auth=auth,
                timeout=8,
            )
            return response.status_code == 200
        except Exception:
            return False


class JenkinsAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            metadata = credential_metadata(self.integration)
            username = str(metadata.get("username") or "")
            auth = (username, credential_secret(self.integration)) if username and credential_secret(self.integration) else None
            response = requests.get(f"{self.integration.endpoint_url.rstrip('/')}/api/json", auth=auth, timeout=8)
            return response.status_code == 200
        except Exception:
            return False


class ArgoCDAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/')}/api/v1/session/userinfo",
                headers={"Authorization": f"Bearer {credential_secret(self.integration)}"} if credential_secret(self.integration) else {},
                timeout=8,
                verify=False,
            )
            return response.status_code == 200
        except Exception:
            return False


class FluxCDAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        return bool(self.integration.endpoint_url or credential_metadata(self.integration).get("kube_context"))


class KubernetesAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        try:
            response = requests.get(
                f"{self.integration.endpoint_url.rstrip('/')}/version",
                headers={"Authorization": f"Bearer {credential_secret(self.integration)}"} if credential_secret(self.integration) else {},
                timeout=8,
                verify=False,
            )
            return response.status_code == 200
        except Exception:
            return False


IntegrationRegistry.register("github", GitHubAdapter)
IntegrationRegistry.register("gitlab", GitLabAdapter)
IntegrationRegistry.register("bitbucket", BitbucketAdapter)
IntegrationRegistry.register("jenkins", JenkinsAdapter)
IntegrationRegistry.register("argocd", ArgoCDAdapter)
IntegrationRegistry.register("fluxcd", FluxCDAdapter)
IntegrationRegistry.register("kubernetes", KubernetesAdapter)
