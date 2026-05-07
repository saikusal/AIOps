from ..base import BaseAdapter
from ..registry import IntegrationRegistry


class AWSAdapter(BaseAdapter):
    def test_connection(self) -> bool:
        # Implementation placeholder: boto3 STS get-caller-identity
        return True


IntegrationRegistry.register("aws", AWSAdapter)
