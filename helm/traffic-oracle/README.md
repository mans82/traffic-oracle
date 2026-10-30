# traffic-oracle Helm chart

Kubernetes deployment of Traffic Oracle: a fetcher that records travel times and
taxi prices on a fixed interval, and a Grafana instance with the dashboard and
Infinity datasource pre-provisioned.

## Install

### 1. Push the fetcher image

The fetcher image is built locally by compose, so push it somewhere the cluster
can pull from first:

```sh
docker build -t ghcr.io/you/traffic-oracle-fetcher:0.2.0 .
docker push ghcr.io/you/traffic-oracle-fetcher:0.2.0
```

### 2. Create the secrets

Never put these in a values file: Helm stores rendered values in the release
secret, so anything there is readable with `helm get values` and tends to end up
committed.

The API credentials are loaded with `envFrom`, so the keys must be named exactly
as the fetcher's environment variables. The project README explains how to
obtain each value.

```sh
kubectl create secret generic traffic-oracle-credentials \
  --from-literal=NESHAN_API_KEY=... \
  --from-literal=SNAPP_API_KEY=... \
  --from-literal=SNAPP_API_REFRESH_TOKEN=... \
  --from-literal=TAPSI_API_KEY=...
```

An existing `.env` has the right shape already, if it holds only those four keys:

```sh
kubectl create secret generic traffic-oracle-credentials --from-env-file=.env
```

The Grafana admin login is a second secret, with keys `admin-user` and
`admin-password`:

```sh
kubectl create secret generic traffic-oracle-grafana \
  --from-literal=admin-user=admin \
  --from-literal=admin-password="$(openssl rand -base64 24)"
```

Both are plain Kubernetes Secrets — base64, not encrypted. Enable encryption at
rest, or source them from SOPS / External Secrets / Vault, if this cluster
warrants it.

### 3. Install

Copy `values-example.yaml`, set the image, the two secret names, your routes and
your hostname, and install:

```sh
helm install traffic-oracle ./helm/traffic-oracle -f my-values.yaml
```

Rendering fails with a named error if `fetcher.image`, `credentials.secretName`,
`grafana.adminSecretName`, or `ingress.host` is unset. Secret names are not
resolved against the cluster, so a typo or a missing secret surfaces as a pod
stuck in `CreateContainerConfigError` — check with
`kubectl describe pod -l component=fetcher`.

## Values

| Key | Default | Description |
| --- | --- | --- |
| `timezone` | `Asia/Tehran` | `TZ` for the fetcher and Grafana. |
| `fetcher.image` | `""` | **Required.** Full image reference, tag included — the chart adds no tag, and an untagged reference resolves to `:latest`. |
| `fetcher.intervalMinutes` | `10` | `FETCH_INTERVAL_MINUTES`. |
| `credentials.secretName` | `""` | **Required.** Secret with `NESHAN_API_KEY`, `SNAPP_API_KEY`, `SNAPP_API_REFRESH_TOKEN`, `TAPSI_API_KEY`. |
| `origins.pairs` | one placeholder pair | Rendered into `origins.yaml`. |
| `persistence.storageClass` | `""` | Applies to both volumes; `""` uses the cluster default. |
| `persistence.dataSize` | `1Gi` | CSV history and Snapp token state. |
| `persistence.grafanaSize` | `2Gi` | Grafana's database. |
| `grafana.adminSecretName` | `""` | **Required.** Secret with `admin-user` and `admin-password`. |
| `ingress.className` | `""` | IngressClass that should claim the Ingress — which controller serves it (`nginx`, `traefik`, …), nothing to do with Grafana. `""` relies on the class marked default; if none is, nothing routes. `kubectl get ingressclass` lists them. |
| `ingress.host` | `""` | **Required.** Hostname, and the basis of Grafana's root URL. |

That is the whole surface. Things a chart often parameterizes are template
literals here, pinned the way `docker-compose.yaml` pins them: image tags for
Grafana and the nginx sidecar, resource requests and limits, both security
contexts, `accessModes: ReadWriteOnce`, the Infinity plugin, the dashboard
landing page, and the service ports. Edit the templates to change them.

Three consequences worth knowing:

- **Grafana's root URL follows the Ingress.** `GF_SERVER_ROOT_URL` is derived as
  `http://<ingress.host>`, so it cannot drift out of sync with the way in.
- **A private registry needs a pull secret.** There is no `imagePullSecrets`
  value; add it to the chart's ServiceAccount in
  `templates/serviceaccount.yaml`, which applies to both pods:

  ```yaml
  imagePullSecrets:
    - name: my-registry-secret
  ```

- **The NetworkPolicy is always applied.** On a CNI that enforces policy it can
  also block `kubectl port-forward` to the `-static` service, since that traffic
  arrives from the node. Port-forward the Grafana service instead, or delete the
  policy while debugging. On a CNI without enforcement the policy is ignored and
  the CSVs are reachable from anywhere in the cluster.

## Grafana config

The chart is the single home for Grafana's configuration, and `docker-compose.yaml`
mounts it from here:

```
files/dashboards/traffic-oracle.json              # the dashboard
files/provisioning/datasources/traffic-data.yaml  # the traffic-data datasource
files/provisioning/dashboards/traffic-oracle.yaml # the dashboard provider
```

Nothing is duplicated or symlinked: the chart reads these with `.Files.Glob`
into three ConfigMaps (all from `templates/grafana-configmaps.yaml`), and
compose bind-mounts the same two directories. Add a
`.json` file to `files/dashboards/`, or a `.yaml` to either provisioning
directory, and both deployments pick it up with no template change.

One string differs between the two deployments — where the CSVs are served
from — so it lives in the environment instead of the file:

| | `TRAFFIC_ORACLE_CSV_BASE_URL` |
| --- | --- |
| compose | `http://static/static` (the nginx service alias) |
| chart | `http://<release>-static/static` (the sidecar's Service) |

Grafana expands `${VAR}` when it parses provisioning files, including inside
`jsonData`, so `traffic-data.yaml` refers to `${TRAFFIC_ORACLE_CSV_BASE_URL}`
and resolves correctly in both. Note that Grafana does not fail when the
variable is unset — it provisions an empty URL — so a hand-rolled `docker run`
that omits it gets a silently broken datasource.

Editing the datasource therefore means reading two places: this file for
everything structural, and compose or `templates/grafana-deployment.yaml` for
the host.
