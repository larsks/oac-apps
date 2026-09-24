"""Health checks translated from the NVIDIA GPU Operator Chainsaw suite."""

from typing import Any, Callable

import pytest

from kube import KubernetesClient


NVIDIA_NAMESPACE = "nvidia-gpu-operator"
GPU_PRESENT_LABEL = "nvidia.com/gpu.present"
GPU_PRODUCT_LABEL = "nvidia.com/gpu.product"
DRIVER_DEPLOY_LABEL = "nvidia.com/gpu.deploy.driver"
GPU_OPERATOR_DAEMONSETS = (
    "gpu-feature-discovery",
    "nvidia-container-toolkit-daemonset",
    "nvidia-dcgm",
    "nvidia-dcgm-exporter",
    "nvidia-device-plugin-daemonset",
    "nvidia-device-plugin-mps-control-daemon",
    "nvidia-mig-manager",
    "nvidia-node-status-exporter",
    "nvidia-operator-validator",
)


def _metadata(resource: Any) -> Any:
    return resource.get("metadata", {})


def _labels(resource: Any) -> Any:
    return _metadata(resource).get("labels", {})


def _name(resource: Any) -> str:
    return _metadata(resource).get("name", "<unnamed>")


def _ready_nodes(
    client: KubernetesClient,
    has_condition: Callable[[Any, str, str], bool],
) -> list[Any]:
    return [
        node
        for node in client.list("Node", api_version="v1")
        if has_condition(node, "Ready", "True")
    ]


def test_gpu_nodes_have_product_label(client: KubernetesClient) -> None:
    nodes = client.list("Node", api_version="v1")
    gpu_nodes = [
        node for node in nodes if _labels(node).get(GPU_PRESENT_LABEL) is not None
    ]

    assert gpu_nodes, (
        f"No nodes have the {GPU_PRESENT_LABEL!r} label; "
        "expected at least one GPU node."
    )

    missing_product = sorted(
        _name(node)
        for node in gpu_nodes
        if _labels(node).get(GPU_PRODUCT_LABEL) in (None, "")
    )
    assert not missing_product, (
        f"GPU nodes must have a non-empty {GPU_PRODUCT_LABEL!r} label. "
        f"Missing on: {', '.join(missing_product)}"
    )


def test_gpu_operator_deployment_is_available(
    client: KubernetesClient,
    has_condition: Callable[[Any, str, str], bool],
) -> None:
    deployment = client.get(
        "Deployment",
        "gpu-operator",
        NVIDIA_NAMESPACE,
        api_version="apps/v1",
    )
    available = has_condition(deployment, "Available", "True")
    conditions = deployment.get("status", {}).get("conditions", []) or []

    assert available, (
        f"Deployment {NVIDIA_NAMESPACE}/gpu-operator has no Available=True "
        f"condition. Conditions: {conditions}"
    )


@pytest.mark.parametrize("daemonset_name", GPU_OPERATOR_DAEMONSETS)
def test_gpu_operator_daemonset_available_on_selected_ready_nodes(
    client: KubernetesClient,
    has_condition: Callable[[Any, str, str], bool],
    daemonset_name: str,
) -> None:
    daemonset = client.get(
        "DaemonSet",
        daemonset_name,
        NVIDIA_NAMESPACE,
        api_version="apps/v1",
    )
    pod_spec = daemonset.get("spec", {}).get("template", {}).get("spec", {})
    node_selector = pod_spec.get("nodeSelector", {}) or {}
    selected_ready_nodes = [
        node
        for node in _ready_nodes(client, has_condition)
        if all(
            _labels(node).get(label) == value
            for label, value in node_selector.items()
        )
    ]
    available = daemonset.get("status", {}).get("numberAvailable") or 0

    assert available == len(selected_ready_nodes), (
        f"DaemonSet {NVIDIA_NAMESPACE}/{daemonset_name} has {available} "
        f"available pods for {len(selected_ready_nodes)} selected Ready nodes. "
        "Selected nodes: "
        f"{', '.join(sorted(_name(node) for node in selected_ready_nodes)) or '<none>'}"
    )


def test_gpu_driver_daemonsets_available_on_gpu_ready_nodes(
    client: KubernetesClient,
    has_condition: Callable[[Any, str, str], bool],
) -> None:
    daemonsets = [
        daemonset
        for daemonset in client.list(
            "DaemonSet",
            NVIDIA_NAMESPACE,
            api_version="apps/v1",
        )
        if _labels(daemonset).get("app.kubernetes.io/component") == "nvidia-driver"
    ]
    gpu_ready_nodes = [
        node
        for node in _ready_nodes(client, has_condition)
        if _labels(node).get(DRIVER_DEPLOY_LABEL) == "true"
    ]

    assert daemonsets, (
        "No NVIDIA driver DaemonSet found in namespace "
        f"{NVIDIA_NAMESPACE!r} with label "
        "app.kubernetes.io/component=nvidia-driver."
    )

    mismatches = []
    for daemonset in daemonsets:
        available = daemonset.get("status", {}).get("numberAvailable")
        if available is None or int(available) != len(gpu_ready_nodes):
            mismatches.append(
                f"{_name(daemonset)}: numberAvailable={available!r}, "
                f"expected {len(gpu_ready_nodes)}"
            )

    assert not mismatches, (
        "NVIDIA driver DaemonSets must have one available pod per Ready node "
        f"labelled {DRIVER_DEPLOY_LABEL}='true'.\n  "
        + "\n  ".join(mismatches)
    )


def test_cluster_policies_are_ready(client: KubernetesClient) -> None:
    policies = client.list("ClusterPolicy", api_version="nvidia.com/v1")
    assert policies, "No NVIDIA ClusterPolicy resources were found."

    not_ready = [
        f"{_name(policy)}: {policy.get('status', {}).get('state', '<missing>')}"
        for policy in policies
        if policy.get("status", {}).get("state") != "ready"
    ]
    assert not not_ready, (
        "Every NVIDIA ClusterPolicy must have status.state='ready'. "
        f"Not ready: {', '.join(not_ready)}"
    )


def test_gpu_operator_csv_succeeded(client: KubernetesClient) -> None:
    csvs = [
        csv
        for csv in client.list(
            "ClusterServiceVersion",
            NVIDIA_NAMESPACE,
            api_version="operators.coreos.com/v1alpha1",
        )
        if _labels(csv).get(
            "operators.coreos.com/gpu-operator-certified.nvidia-gpu-operator"
        )
        == ""
    ]

    assert csvs, (
        "No GPU Operator CSV with label "
        "operators.coreos.com/gpu-operator-certified.nvidia-gpu-operator='' "
        f"was found in {NVIDIA_NAMESPACE!r}."
    )

    not_succeeded = [
        f"{_name(csv)}: {csv.get('status', {}).get('phase', '<missing>')}"
        for csv in csvs
        if csv.get("status", {}).get("phase") != "Succeeded"
    ]
    assert not not_succeeded, (
        "GPU Operator CSVs must have status.phase='Succeeded'. "
        f"Not succeeded: {', '.join(not_succeeded)}"
    )
