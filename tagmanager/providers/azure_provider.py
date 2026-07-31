"""
Purpose: Azure provider — bulk inventory via one Resource Graph query per
subscription, service-principal credentials from the environment.
Author(s): John Reed
"""

import logging

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.azure_provider")
LOG.setLevel(logging.INFO)

QUERY = "Resources | project id, name, type, location, tags, subscriptionId"


def _default_client_builder(scope):  # pylint: disable=unused-argument
    """Resource Graph client using DefaultAzureCredential (env-driven SP)."""
    # Lazy imports: tests bypass this with a mock; production gets real SDK.
    from azure.identity import DefaultAzureCredential  # pylint: disable=import-outside-toplevel
    from azure.mgmt.resourcegraph import ResourceGraphClient  # pylint: disable=import-outside-toplevel
    return ResourceGraphClient(DefaultAzureCredential())


class AzureProvider(Provider):
    """Reads every resource + tags in a subscription via Resource Graph."""

    cloud_name = "azure"

    def __init__(self, client_builder=_default_client_builder):
        """
        Initialize AzureProvider with a client builder.

        :param client_builder: callable(scope) -> ResourceGraphClient
        """
        self._client_builder = client_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every resource in the subscription.

        :param scope: ScopeConfig (scope_id = subscription id)
        :yields: NormalizedResource
        """
        # pylint: disable=import-outside-toplevel
        from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions
        client = self._client_builder(scope)
        LOG.info("scanning azure subscription %s...", scope.scope_id)
        skip_token = None
        while True:
            request = QueryRequest(
                subscriptions=[scope.scope_id], query=QUERY,
                options=QueryRequestOptions(skip_token=skip_token))
            response = client.resources(request)
            for row in response.data:
                yield NormalizedResource(
                    cloud="azure", scope_id=scope.scope_id,
                    region=row.get("location", ""), rtype=row.get("type", ""),
                    resource_id=row.get("id", ""), name=row.get("name", ""),
                    tags=row.get("tags") or {})
            skip_token = getattr(response, "skip_token", None)
            if not skip_token:
                break

    def capabilities(self):
        """
        Declare provider capabilities.

        Azure supports direct tag writes (Tags API) in sub-project 2.

        :returns: ProviderCapabilities
        """
        return ProviderCapabilities(supports_direct_write=True)
