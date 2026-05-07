from typing import Dict, Type
from .base import BaseAdapter


class IntegrationRegistry:
    """Registry to map integration_type to the appropriate Adapter class."""
    _adapters: Dict[str, Type[BaseAdapter]] = {}

    @classmethod
    def register(cls, integration_type: str, adapter_class: Type[BaseAdapter]):
        cls._adapters[integration_type] = adapter_class

    @classmethod
    def get_adapter(cls, integration_model) -> BaseAdapter:
        adapter_class = cls._adapters.get(integration_model.integration_type)
        if not adapter_class:
            raise ValueError(f"No adapter registered for integration type: {integration_model.integration_type}")
        return adapter_class(integration_model)

