"""Small, read-only helpers for querying arbitrary Kubernetes resources."""

from __future__ import annotations

from typing import Any

from kubernetes import dynamic


class KubernetesClient:
    """Query Kubernetes resources by kind, with optional API version selection.

    ``get`` returns one resource. ``list`` returns the resource instances in a
    Kubernetes list response. Namespaced resources are listed cluster-wide
    when ``namespace`` is omitted.
    """

    def __init__(self, client: dynamic.DynamicClient) -> None:
        self._client = client

    def get(
        self,
        kind: str,
        name: str,
        namespace: str | None = None,
        *,
        api_version: str | None = None,
    ) -> Any:
        """Get a resource by kind, name, and (for namespaced kinds) namespace.

        ``api_version`` can be supplied to disambiguate kinds provided by
        multiple API groups or versions, for example ``operators.coreos.com/v1``.
        """
        resource = self._resource(kind, api_version)
        request: dict[str, str] = {"name": name}

        if resource.namespaced:
            if namespace is None:
                raise ValueError(
                    f"namespace is required to get namespaced resource {kind} {name}"
                )
            request["namespace"] = namespace
        elif namespace is not None:
            raise ValueError(
                f"{kind} is cluster-scoped; do not pass namespace={namespace!r}"
            )

        return resource.get(**request)

    def list(
        self,
        kind: str,
        namespace: str | None = None,
        *,
        api_version: str | None = None,
    ) -> list[Any]:
        """List a kind, across all namespaces when namespace is omitted."""
        resource = self._resource(kind, api_version)
        if not resource.namespaced and namespace is not None:
            raise ValueError(
                f"{kind} is cluster-scoped; do not pass namespace={namespace!r}"
            )

        request = {"namespace": namespace} if namespace is not None else {}
        response = resource.get(**request)
        return response.items

    def _resource(self, kind: str, api_version: str | None) -> Any:
        lookup: dict[str, str] = {"kind": kind}
        if api_version is not None:
            lookup["api_version"] = api_version
        return self._client.resources.get(**lookup)
