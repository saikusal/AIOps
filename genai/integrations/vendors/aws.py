from ..base import BaseAdapter
from ..registry import IntegrationRegistry
from .common import credential_metadata, credential_secret


class AWSAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        metadata = credential_metadata(self.integration)
        return bool(
            metadata.get("role_arn")
            or metadata.get("access_key_id") and credential_secret(self.integration)
            or metadata.get("profile_name")
        )


IntegrationRegistry.register("aws", AWSAdapter)
