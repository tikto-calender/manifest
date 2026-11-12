# TikTo Manifest

Defines how Argo CD deploys TikTo Calendar to EKS. The [Helm chart](charts/tikto) uses one Deployment per service and pins each image by its GHCR digest. The Prod Backend Deployment rolls out new images with two replicas.

## Render the chart locally

Install Helm and run these commands from the repository root. Dev renders three Deployments.

**Linux/macOS**

```sh
helm template tikto-dev ./charts/tikto --namespace tikto-dev \
  -f ./charts/tikto/environments/dev/values.yaml \
  -f ./charts/tikto/environments/dev/frontend-image.yaml \
  -f ./charts/tikto/environments/dev/backend-image.yaml \
  -f ./charts/tikto/environments/dev/notification-image.yaml
```

**Windows PowerShell**

```powershell
helm template tikto-dev ./charts/tikto --namespace tikto-dev `
  -f ./charts/tikto/environments/dev/values.yaml `
  -f ./charts/tikto/environments/dev/frontend-image.yaml `
  -f ./charts/tikto/environments/dev/backend-image.yaml `
  -f ./charts/tikto/environments/dev/notification-image.yaml
```

For Prod, use namespace `tikto-prod` and the value files listed in [bootstrap/prod.yaml](bootstrap/prod.yaml).

## Deploy with Argo CD

Set up EKS, Argo CD and AWS Load Balancer Controller using [Terraform](https://github.com/tikto-calender/infra) or [CloudFormation](https://github.com/tikto-calender/infra-by-cloudformation). Confirm kubectl points to that EKS cluster. Run this on **Linux/macOS or Windows PowerShell**.

```sh
kubectl config current-context
kubectl apply -f ./bootstrap/namespaces.yaml
kubectl apply -f ./bootstrap/dev.yaml
kubectl -n argocd get applications
```

If the Prod ALB and target groups are ready, run `kubectl apply -f ./bootstrap/prod.yaml`. Check for `Synced` and `Healthy` in Argo CD and verify `/api/health` at the ALB URL. To enable Telegram, use the [namespace Secret examples](examples/secrets).

## Promote to Production

<a name="promote-backend"></a>

After checking Dev, run **Promote Frontend**, **Promote Backend**, **Promote Notification**, or **Promote All Services** from `main` in Manifest's **Actions** tab. The shared workflow tags the verified Dev digest and updates the Prod Helm values for Argo CD. Check the rollout and Prod API, then run **Finalize release** in the source repository with the same version. [Shared workflows](https://github.com/tikto-calender/reusable-workflow)

## Migrate an existing Backend deployment

For a running two-slot installation, finish or cancel the old promotion job and confirm `prod/backend-image.yaml` records the digest serving Prod. Reapply `bootstrap/prod.yaml` after publishing the new chart so Argo CD rolls that digest out to `deployment/backend`.

Wait for the Deployment and its existing Backend target group to become healthy. If the listener still points to Green, switch `/api` to the existing Backend target group before applying the IaC changes. Verify the API, apply IaC to remove the old preview rules and target group, then delete the old Kubernetes resources.

```sh
kubectl -n tikto-prod delete deployment/backend-green service/backend-green targetgroupbinding/backend-green --ignore-not-found
```
