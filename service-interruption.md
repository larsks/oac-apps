# Service interruption: oac-dev-workload0 namespace deletions (2026-10-27)

Status: **investigation paused** — root cause of the master node reboot (the
ultimate trigger) is not yet confirmed. Session paused before the audit-log
search finished; see "Resuming this investigation" below.

## Symptom

Several namespaces on the `oac-dev-workload0` hosted cluster were observed
stuck `Terminating`:

```
container-object-storage-system
metallb-system
nvidia-gpu-operator
openshift-cnv
openshift-jobset-operator
openshift-kueue-operator
openshift-nfd
openshift-serverless
rossoctl-system
```

All had `deletionTimestamp` values within a few minutes of each other,
**2026-10-27 17:31:54Z – 17:38Z** (`nvidia-gpu-operator` deleted later, at
18:17:51Z, see open question below).

## Root cause chain (confirmed)

1. **17:16:53–17:16:57Z** — The hub cluster (`api-infra-oac-int-massopen-cloud`,
   which also runs ArgoCD/`openshift-gitops` and the ACM hub) had master node
   `moc-r4pac22u15-s1` go `NotReady`. Multiple pods on that node (including
   `machine-config-daemon`, `machine-config-server`, and
   `kube-rbac-proxy-crio`) logged `NodeNotReady` at this time.
2. ACM runs the klusterlet for HyperShift-hosted clusters in **"Hosted
   mode"**: the `registration-agent` and `work-agent` pods that report a
   managed cluster's health run **on the hub cluster itself**, not inside the
   guest/hosted cluster. The agent pods for both `oac-dev-workload0` and
   `oac-dev-workload1` (namespaces `klusterlet-oac-dev-workload0` and
   `klusterlet-oac-dev-workload1`) happened to be scheduled on
   `moc-r4pac22u15-s1`.
3. Kubernetes does not instantly evict pods when a node goes `NotReady` — it
   waits out the default `node.kubernetes.io/not-ready:NoExecute` toleration
   (300 seconds). Confirmed: `TaintManagerEviction` fired at **17:21:53Z**,
   evicting the old agent pods; replacements were scheduled onto a healthy
   node (`moc-r4pac08u05-s3`), became ready, and won leader election by
   **17:22:20–17:22:23Z**.
4. For that ~5.5 minute gap, `oac-dev-workload0`'s registration-agent could
   not renew its heartbeat `Lease` to the hub's registration controller, so
   ACM flipped `ManagedClusterConditionAvailable` to `Unknown` (confirmed via
   the `AvailableUnknown` → `Available` event pair on
   `managedcluster/oac-dev-workload0`, with the condition's
   `lastTransitionTime` recorded as **17:22:20Z** once it recovered).
5. Every ACM `Placement` used by this repo's ArgoCD `ApplicationSet`s selects
   clusters with a plain `matchLabels` selector and **no `tolerations`**
   (`charts/acm-placements/templates/placement.yaml`). The instant
   `oac-dev-workload0` reported unavailable, it was evicted from every
   `PlacementDecision` that depends on it.
6. Each `clusterDecisionResource`-driven `ApplicationSet`
   (`metallb-clusters`, `gpu-clusters`, `virtualization-clusters`,
   `rossoctl-clusters`, `portworx-clusters`, `pure-cosi`, `hosted-ingress`,
   `hypervisor-clusters`, `github-oauth-clusters`) immediately deleted its
   generated `oac-dev-workload0-*` `Application` object. Confirmed: all 9
   `Application` objects got `deletionTimestamp` within a 37-second window,
   **17:21:22Z – 17:21:59Z**.
7. Those `Application` objects carry
   `finalizers: [resources-finalizer.argocd.argoproj.io]` (ArgoCD's
   cascade-delete finalizer), so ArgoCD's application-controller proceeded to
   prune every resource they managed — the namespaces and everything in them
   — which is why the namespace `deletionTimestamp`s landed a few minutes
   later (17:31–17:38Z). The cluster reconnecting a minute after going
   unavailable did not stop this: once cascade deletion starts via the
   finalizer, it runs to completion.
8. By the time of investigation, the `ApplicationSet`s had regenerated the
   `Application` objects (the cluster is back in the `PlacementDecision`),
   and they showed `OutOfSync`/`Progressing` — ArgoCD recreating what it had
   just deleted.

This is **not** a case of a user or service account explicitly deleting
namespaces. The deletions were an automated, if unintended, side effect of
ArgoCD/ApplicationSet logic reacting to a brief ACM availability flap.

## Why "the cluster became unavailable" is misleading

The HyperShift-hosted control plane for `oac-dev-workload0` (kube-apiserver,
etc.) runs as pods in namespace `clusters-oac-dev-workload0` on the **same**
infra/hub cluster as ArgoCD and ACM — it never went down. The thing ACM
actually uses to decide "is this managed cluster available" is the
**hosted-mode klusterlet agent pods**, which also run on the hub cluster (not
inside the guest cluster's own worker nodes). So the real exposure was a hub
master node outage, not anything on `oac-dev-workload0`'s own
infrastructure — the "ManagedClusterConditionAvailable" name is misleading in
this hosted-mode topology.

## Why did master node moc-r4pac22u15-s1 reboot? (open question)

Confirmed facts so far:

- `oc get clusterversion` shows the cluster has been sitting completed at
  `4.22.14` since 2026-09-22 (`Progressing=False`) — **this was not an OCP
  version upgrade**.
- The master `MachineConfigPool`'s current rendered config is
  `rendered-master-90187bda9ccee540b216bafe851b311c`, composed of:
  ```
  00-master
  01-master-container-runtime
  01-master-kubelet
  50-masters-chrony-configuration
  95-oc-initiated-reboot-master
  97-master-generated-kubelet
  98-master-generated-kubelet
  99-assisted-installer-master-ssh
  99-master-generated-registries
  99-master-ssh
  ```
- `95-oc-initiated-reboot-master` looked suspicious (not a stock OpenShift
  name; matches a known manual technique for forcing a one-off pool reboot
  via a trivial file write). Pulled via `--as system:admin` impersonation
  (the `larsks` identity lacks RBAC on `machineconfigs` cluster-wide): it was
  created **2026-08-13T15:07:12Z**, `generation: 1` (never edited since). It
  predates this incident by over two months and is simply a static ingredient
  of the rendered config — **it did not trigger this reboot**.
- The `ControllerConfig` (`machine-config-controller`) last completed a
  template sync at **2026-10-13T01:01:59Z** (generation 22) — two weeks
  before the incident, ruling out a same-day CA bundle/controller-config
  change as the direct trigger.
- All three master nodes currently report the same
  `currentConfig=rendered-master-90187bda9ccee540b216bafe851b311c` and
  state `Done` — consistent with either a completed rolling update or no
  rollout having happened at all; not enough by itself to distinguish the
  two after the fact.
- No `ImageDigestMirrorSet`, `ImageContentSourcePolicy`, `ImageTagMirrorSet`,
  or `KubeletConfig` manifests exist in this repo that could explain a
  GitOps-driven regeneration of `99-master-generated-registries` or
  `97/98-master-generated-kubelet`.
- Node `moc-r4pac22u15-s1` did report a **new boot ID**
  (`1985aa9a-f8cc-49b7-a30c-67bec93fb6a0`) at **17:29:15Z**, confirming an
  actual host-level reboot occurred, not just a kubelet hiccup. An earlier
  (now expired from the 1h event TTL) `NodeNotSchedulable` event appeared to
  precede the `NodeNotReady` event, suggesting a deliberate
  cordon-before-reboot sequence (MCO's standard single-node update
  procedure) rather than an unplanned crash — but this ordering could not be
  re-verified with precise timestamps before the events aged out.

**Not yet determined:** which specific change (if any) caused MCO to
re-render and roll the master pool, or whether this was instead an
unplanned/infrastructure-level reboot (hypervisor action, hardware event,
manual `reboot` via SSH/BMC) that merely happened to go through the normal
cordon/drain/uncordon dance once the node came back.

**Paused, not yet complete:** a search of this master node's own
kube-apiserver audit log for `update`/`patch` operations on the
`nodes/moc-r4pac22u15-s1` object around 17:12–17:17Z, to identify the user or
service account that cordoned the node (accessed via `--as system:admin`
impersonation, since `larsks` lacks direct RBAC on this cluster for
`node-logs`/exec). See "Resuming this investigation" below for exact
commands and status.

## Fixes applied (not yet committed)

1. **`charts/acm-placements/templates/placement.yaml`** — added
   `tolerations` for the `cluster.open-cluster-management.io/{unreachable,unavailable}`
   taints with no `tolerationSeconds` (i.e. indefinite), so a cluster is never
   evicted from its `PlacementDecision` due to an availability flap — only by
   actually being removed/unlabeled. Health monitoring/alerting on
   `ManagedCluster` conditions is a separate concern from GitOps placement and
   isn't affected by this. This alone would have prevented today's incident:
   the `Application` deletions (step 6) and cascade-prune (step 7) only
   happen because the untoleranced placement evicted the cluster from its
   `PlacementDecision` (step 5) in the first place.
2. Added `helm-unittest` coverage for the above
   (`charts/acm-placements/tests/unit/placement_test.yaml`), plus two
   previously-untested `applicationsets` templates picked up along the way:
   `hypervisor-clusters` and the managed `pure-cosi` ApplicationSet
   (`applicationsets/tests/unit/hypervisor-clusters_test.yaml`,
   `applicationsets/tests/unit/pure-cosi_test.yaml`).

A `preserveResourcesOnDeletion: true` change to the 8 affected
`ApplicationSet`s (matching the existing `all-managed-clusters` pattern) was
also drafted as defense-in-depth, but was dropped for now: it would silently
stop ArgoCD from cleaning up resources on any *legitimate* cluster/feature
removal too (see discussion — orphaned namespaces/operators/RBAC left behind
with no automatic cleanup), and isn't needed to prevent today's specific
incident since the toleration fix above addresses the root cause directly.
Worth revisiting separately if we want that extra safety net.

All 61 tests across both charts pass (`helm unittest -f 'tests/unit/*_test.yaml' <chart>`).
Both charts lint cleanly (`helm lint`). The only CI test failures in the
full repo-wide run (`./scripts/helm-unittest-all.sh`) are 6 pre-existing,
unrelated charts (`grafana-operator`, `jobset-operator`, `kueue-operator`,
`openshift-virtualization`, `rhacs`, `rossoctl-operator`) failing due to a
missing `operator-library` subchart dependency that needs
`helm dependency update` against a chart repo (no network access in this
environment) — not caused by these changes.

## Resuming this investigation

The audit-log search was stopped cleanly (no orphaned background processes)
before the laptop was unplugged. To pick it back up:

```
oc --context default/api-infra-oac-int-massopen-cloud:6443/larsks \
  --as system:admin adm node-logs moc-r4pac22u15-s1 \
  --path=kube-apiserver/audit-2026-10-27T16-52-21.074.log \
  | grep -F '"moc-r4pac22u15-s1"' > /tmp/audit-node-matches.log
```

Notable finding along the way, worth a quick look on its own: `oc adm
node-logs` streamed this file at only **~170KB/s**, and the single rotation
window covering the incident (16:52:21Z–17:59:41Z) is 90MB+ and growing —
a full download would take 10–20+ minutes. That's slow for what should be a
same-datacenter transfer through the kubelet log-retrieval proxy; worth
checking whether that's normal for this cluster/connection or a separate
problem (CPU-throttled kubelet, networking path, apiserver load) before
assuming it's just "large file, normal speed." Piping through `grep` (as
above) avoids buffering the whole thing to disk/memory but doesn't speed up
the transfer itself — the bottleneck is upstream of the local shell.

Once matches come back, cross-reference the `user.username` field for any
`update`/`patch` on `nodes/moc-r4pac22u15-s1` around 17:12–17:17Z against
known identities (human users vs. `system:serviceaccount:...`) to determine
whether this was a deliberate human-initiated cordon/reboot or something
else.

## Open items

- [ ] Finish the audit-log search to confirm who/what cordoned/rebooted
      `moc-r4pac22u15-s1` and why.
- [x] Decided the toleration should have no expiry at all, rather than a
      fixed grace period — see fix #1 above.
- [ ] Commit the toleration fix once the user confirms.
- [ ] Consider whether `nvidia-gpu-operator` deleting later (18:17:51Z,
      versus the rest at 17:31–17:38Z) is related or a separate event —
      not yet investigated.
