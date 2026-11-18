# Cluster observability

The `monitoring` Helm release runs [kube-prometheus-stack 93.4.0](https://github.com/prometheus-community/helm-charts/tree/kube-prometheus-stack-93.4.0/charts/kube-prometheus-stack) in namespace `observability`. [values.yaml](values.yaml) is the configuration for installs and upgrades. It includes Prometheus, Grafana, Alertmanager, kube-state-metrics and one node-exporter per eligible node. The existing CloudWatch add-on can continue running alongside it.

## Install or update from WSL / Bash

Run from the Manifest repository root. Check the context points to the intended cluster before installing.

```bash
kubectl config current-context
kubectl get nodes

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update prometheus-community

helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  --version 93.4.0 \
  --namespace observability \
  --create-namespace \
  --values ./observability/values.yaml \
  --wait --timeout 10m

helm status monitoring --namespace observability
kubectl -n observability get pods,serviceaccounts
```

Edit `values.yaml` and run the same command to update the release. No `--reuse-values` is needed: the file supplies the configuration. The Grafana chart generates an admin password on the first install and reuses the existing `monitoring-grafana` Secret on upgrades; no password is committed here.

This release is managed with Helm. The `tikto-dev` and `tikto-prod` Argo CD Applications manage the application chart only, so observability resources do not appear in their resource trees.

If an earlier attempt installed `monitoring` in `default`, its cluster-scoped resources can conflict with this release. Inspect it first:

```bash
helm list -A --filter '^monitoring$'
helm status monitoring -n default
```

If it is the disposable trial installation, remove it before installing into `observability`. This removes the old monitoring stack and its temporary data:

```bash
helm uninstall monitoring -n default --wait --timeout 5m
```

## ServiceAccounts and permissions

These names are explicitly declared in `values.yaml`. Helm creates the ServiceAccounts and matching Roles/ClusterRoles and bindings supplied by the upstream chart.

| Component | ServiceAccount in `observability` |
| --- | --- |
| Prometheus Operator | `monitoring-kube-prometheus-operator` |
| Prometheus | `monitoring-kube-prometheus-prometheus` |
| Grafana | `monitoring-grafana` |
| Alertmanager | `monitoring-kube-prometheus-alertmanager` |
| kube-state-metrics | `monitoring-kube-state-metrics` |
| node-exporter | `monitoring-prometheus-node-exporter` |

The chart also manages temporary ServiceAccounts used by webhook installation hooks. Monitoring uses Kubernetes RBAC to discover workloads and scrape cluster metrics; this configuration does not require an AWS IAM role for these ServiceAccounts.

## Open Grafana and Prometheus

Grafana username: `admin`. Read the password from its Secret:

```bash
kubectl -n observability get secret monitoring-grafana \
  -o jsonpath='{.data.admin-password}' | base64 --decode; echo

kubectl -n observability port-forward svc/monitoring-grafana 3000:80
```

Open [Grafana](http://localhost:3000). The chart provisions a Prometheus datasource and Kubernetes dashboards. Start with **Kubernetes / Compute Resources / Cluster**, then select a namespace or workload dashboard for `tikto-prod`.

In a second terminal:

```bash
kubectl -n observability port-forward \
  svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Open [Prometheus targets](http://localhost:9090/targets) and check targets are `UP`. Query `up` or `kube_pod_info` to confirm ingestion.

## Collection and storage

Node, container and Kubernetes object metrics are discovered automatically by the bundled monitors. Application HTTP request counts, latency and error rates need an application `/metrics` endpoint plus a `ServiceMonitor` or `PodMonitor`. Custom monitors must have `metadata.labels.release: monitoring`; the selectors in `values.yaml` allow discovery across namespaces. Backend and Notification currently have no metrics endpoint configured in this repository.

This is a trial storage configuration. Prometheus uses `emptyDir` at `/prometheus`, retaining metrics for up to 2 days or the 2GB retention threshold, whichever removes old blocks first. WAL and current data can consume additional space. Data is lost when the Pod is replaced. Grafana persistence is also disabled, so dashboard edits made only in its UI can be lost when its Pod is replaced; provisioned dashboards and datasources are restored by the chart. Alertmanager also uses temporary storage, and external notification receivers have not been configured.

For durable storage, configure a PVC through `prometheus.prometheusSpec.storageSpec.volumeClaimTemplate` and enable `grafana.persistence` after checking that the cluster has a working StorageClass and EBS CSI driver. Changing to PVC storage does not automatically migrate the current temporary data.
