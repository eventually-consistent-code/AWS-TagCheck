"""
Purpose: GCP provider — bulk inventory via Cloud Asset Inventory; labels
normalize to tags. Read-only in sub-project 1 (write shim lands in SP2).
Author(s): John Reed
"""

import logging

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.gcp_provider")
LOG.setLevel(logging.INFO)


def _default_client_builder(scope):  # pylint: disable=unused-argument
    """Asset client using application-default credentials."""
    # Lazy imports: tests bypass this with a mock; production gets real SDK.
    from google.cloud import asset_v1  # pylint: disable=import-outside-toplevel
    return asset_v1.AssetServiceClient()


class GcpProvider(Provider):
    """Reads every asset + labels in a project via Cloud Asset Inventory."""

    cloud_name = "gcp"

    def __init__(self, client_builder=_default_client_builder):
        """
        :param client_builder: callable(scope) -> AssetServiceClient
        """
        self._client_builder = client_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every asset in the project.

        :param scope: ScopeConfig (scope_id = project id)
        :yields: NormalizedResource
        """
        client = self._client_builder(scope)
        LOG.info("scanning gcp project %s...", scope.scope_id)
        assets = client.list_assets(request={
            "parent": f"projects/{scope.scope_id}",
            "content_type": "RESOURCE",
        })
        for asset in assets:
            data = asset.resource.data or {}
            yield NormalizedResource(
                cloud="gcp", scope_id=scope.scope_id,
                region=getattr(asset.resource, "location", "") or "global",
                rtype=asset.asset_type, resource_id=asset.name,
                name=data.get("name", ""), tags=dict(data.get("labels", {})))

    def capabilities(self):
        """GCP label writes are per-service — read-only until the SP2 shim."""
        return ProviderCapabilities(supports_direct_write=False)
