"""
Purpose: AWS provider — bulk inventory via the Resource Groups Tagging API,
assume-role per account, ARN-derived resource types.
Author(s): John Reed
"""

import logging

import boto3

from tagmanager.providers.base import NormalizedResource, Provider, ProviderCapabilities

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
LOG = logging.getLogger("root.aws_provider")
LOG.setLevel(logging.INFO)


def _default_session_builder(scope, region):
    """Assume the scope's role when configured; default chain otherwise."""
    role_arn = scope.credentials.get("role_arn")
    if not role_arn:
        return boto3.Session(region_name=region)
    sts = boto3.client("sts")
    creds = sts.assume_role(RoleArn=role_arn, RoleSessionName="tagmanager")["Credentials"]
    return boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=region,
    )


def _rtype_from_arn(arn):
    """arn:aws:ec2:region:acct:instance/i-abc -> ec2:instance."""
    parts = arn.split(":", 5)
    service = parts[2] if len(parts) > 2 else "unknown"
    rest = parts[5] if len(parts) > 5 else ""
    kind = rest.split("/", 1)[0].split(":", 1)[0] or "resource"
    return f"{service}:{kind}"


class AwsProvider(Provider):
    """Reads every taggable resource in an account via the Tagging API."""

    cloud_name = "aws"

    def __init__(self, session_builder=_default_session_builder):
        """
        Initialize AwsProvider with a session builder.

        :param session_builder: callable(scope, region) -> boto3.Session
        """
        self._session_builder = session_builder

    def list_resources(self, scope):
        """
        Yield NormalizedResource for every tagged/taggable resource.

        :param scope: ScopeConfig with regions list set
        :yields: NormalizedResource
        """
        for region in scope.regions or []:
            LOG.info("scanning aws %s %s...", scope.scope_id, region)
            session = self._session_builder(scope, region)
            client = session.client("resourcegroupstaggingapi")
            paginator = client.get_paginator("get_resources")
            for page in paginator.paginate():
                for item in page.get("ResourceTagMappingList", []):
                    arn = item["ResourceARN"]
                    tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
                    yield NormalizedResource(
                        cloud="aws", scope_id=scope.scope_id, region=region,
                        rtype=_rtype_from_arn(arn), resource_id=arn,
                        name=tags.get("Name", ""), tags=tags)

    def capabilities(self):
        """
        Declare provider capabilities.

        AWS supports direct tag writes (TagResources) in sub-project 2.

        :returns: ProviderCapabilities
        """
        return ProviderCapabilities(supports_direct_write=True)
