"""Pytest fixtures for querying a live Kubernetes cluster."""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import Any, Callable

import pytest
from kubernetes import client as kubernetes_client
from kubernetes import config, dynamic
from kubernetes.config.config_exception import ConfigException

from kube import KubernetesClient


@pytest.fixture
def has_condition() -> Callable[[Any, str, str], bool]:
    """Return whether a resource has a status condition with the given type/status."""

    def check(resource: Any, condition_type: str, expected_status: str) -> bool:
        conditions = resource.get("status", {}).get("conditions", []) or []
        return any(
            condition.get("type") == condition_type
            and condition.get("status") == expected_status
            for condition in conditions
        )

    return check


@pytest.fixture(scope="session")
def client() -> Iterator[KubernetesClient]:
    """Connect using in-cluster credentials or the current kubeconfig context."""
    configuration = kubernetes_client.Configuration()
    try:
        if os.environ.get("KUBERNETES_SERVICE_HOST"):
            config.load_incluster_config(client_configuration=configuration)
        else:
            config.load_kube_config(client_configuration=configuration)
    except ConfigException as error:
        pytest.fail(
            "Could not load Kubernetes credentials. Set KUBECONFIG or run this "
            f"test in a cluster with a service account: {error}",
            pytrace=False,
        )

    api_client = kubernetes_client.ApiClient(configuration=configuration)
    try:
        yield KubernetesClient(dynamic.DynamicClient(api_client))
    finally:
        api_client.close()
