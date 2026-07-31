"""
Purpose: Provider plugin contract — normalized resource model, scope config,
capability flags, and the abstract interface every cloud implements.
Author(s): John Reed
"""

import abc
from dataclasses import dataclass, field


@dataclass
class NormalizedResource:
    """One cloud resource in cross-cloud normal form (labels become tags)."""

    cloud: str
    scope_id: str
    region: str
    rtype: str
    resource_id: str
    name: str
    tags: dict = field(default_factory=dict)


@dataclass
class ScopeConfig:
    """One account/subscription/project plus how to reach it."""

    cloud: str
    scope_id: str
    credentials: dict
    regions: list = None


@dataclass
class ProviderCapabilities:
    """What a provider can do beyond reading."""

    supports_direct_write: bool


class Provider(abc.ABC):
    """Abstract cloud provider: read now, write methods land in sub-project 2."""

    cloud_name = "abstract"

    @abc.abstractmethod
    def list_resources(self, scope):
        """
        Yield NormalizedResource for every taggable resource in the scope.

        :param scope: ScopeConfig
        :yields: NormalizedResource
        """

    @abc.abstractmethod
    def capabilities(self):
        """
        Declare provider capabilities.

        :returns: ProviderCapabilities
        """

    def apply_tags(self, scope, resource_id, tags):
        """Direct tag write — implemented in sub-project 2."""
        raise NotImplementedError("sub-project 2")

    def export_changeset(self, changes):
        """Change-set export — implemented in sub-project 2."""
        raise NotImplementedError("sub-project 2")
