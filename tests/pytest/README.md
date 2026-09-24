# Pytest checks for Kubernetes

This directory contains pytest checks that query a live Kubernetes cluster.
The `client` fixture uses the Kubernetes Python client's dynamic API, so the
same helpers work with built-in resources and installed custom resources.

## Setup and run

Install [uv](https://docs.astral.sh/uv/) if needed, then run these commands from
this directory:

```sh
uv sync
uv run pytest
```

The fixture uses in-cluster service account credentials when
`KUBERNETES_SERVICE_HOST` is set. Otherwise it uses the current context from
`KUBECONFIG` (or the default kubeconfig location). The active identity needs
permission to read the resources checked by the tests. The OperatorGroup
example requires cluster-wide list access to
`operators.coreos.com/operatorgroups`.

## NVIDIA GPU Operator health checks

[`test_nvidia_gpu_operator.py`](test_nvidia_gpu_operator.py) translates the
health checks from
`../../charts/nvidia-gpu-operator/tests/healthcheck/chainsaw-test.yaml`:
GPU node labels, the operator Deployment, its nine DaemonSets, driver DaemonSet
coverage, ClusterPolicy readiness, and the operator CSV phase. Run only these
checks with:

```sh
uv run pytest test_nvidia_gpu_operator.py
```

These checks need read access to Nodes cluster-wide and to Deployments,
DaemonSets, ClusterPolicies, and ClusterServiceVersions used by the checks.

## Resource lookup

`client.get` fetches one resource by kind and name. Namespaced resources require
a namespace, while cluster-scoped resources omit it:

```python
pod = client.get("Pod", "api-123", "payments", api_version="v1")
node = client.get("Node", "worker-1", api_version="v1")
operator_group = client.get(
    "OperatorGroup",
    "global-operators",
    "openshift-operators",
    api_version="operators.coreos.com/v1",
)
```

`client.list` returns the items in a Kubernetes list response. Omit namespace
to list a namespaced resource across the cluster, or pass one to limit the
results:

```python
all_pods = client.list("Pod", api_version="v1")
payments_pods = client.list("Pod", "payments", api_version="v1")
```

The returned resource instances support dictionary access, such as
`pod["metadata"]["name"]`. Pass `api_version` when a kind exists in multiple
API groups or versions.

The `has_condition` fixture checks `status.conditions` by type and status:

```python
def test_node_is_ready(client, has_condition):
    node = client.get("Node", "worker-1", api_version="v1")
    assert has_condition(node, "Ready", "True")
```
