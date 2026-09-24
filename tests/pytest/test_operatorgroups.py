"""Checks for OperatorGroup resources across the cluster."""

from collections import defaultdict

from kube import KubernetesClient


def test_at_most_one_operatorgroup_per_namespace(client: KubernetesClient) -> None:
    operator_groups = client.list(
        "OperatorGroup",
        api_version="operators.coreos.com/v1",
    )
    by_namespace: dict[str, list[str]] = defaultdict(list)

    for operator_group in operator_groups:
        metadata = operator_group.get("metadata", {})
        namespace = metadata.get("namespace", "<unknown namespace>")
        name = metadata.get("name", "<unnamed OperatorGroup>")
        by_namespace[namespace].append(name)

    duplicates = {
        namespace: sorted(names)
        for namespace, names in by_namespace.items()
        if len(names) > 1
    }
    details = "\n".join(
        f"  {namespace}: {', '.join(names)} ({len(names)} total)"
        for namespace, names in sorted(duplicates.items())
    )

    assert not duplicates, (
        "Every namespace may have at most one OperatorGroup. "
        "Found multiple OperatorGroups in:\n"
        f"{details}"
    )
