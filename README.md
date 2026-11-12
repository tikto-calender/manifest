# TikTo Manifest

Defines how Argo CD deploys TikTo Calendar to EKS. The [Helm chart](charts/tikto) deploys Frontend, Backend and Notification Service with a pinned GHCR image for each environment. Prod has two Backend slots for blue/green releases.

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

After checking Dev, run the relevant **Promote** workflow from `main` in Manifest's **Actions** tab. Enter a version such as `v2.0.1`. After checking Prod, run **Finalize release** in the source repository with the same version. [Shared workflows](https://github.com/tikto-calender/reusable-workflow)

<a name="configure-backend-bluegreen"></a>
<a name="promote-backend"></a>

### Backend blue/green

Enable the preview rules and GitHub OIDC role in IaC. Make a Linux runner labeled `tikto-prod-preview` available to Manifest with Python 3.11+, AWS CLI v2, Docker and Buildx. Set these variables in Manifest's `prod` Environment.

| Variable | Terraform output | CloudFormation output |
| --- | --- | --- |
| `BACKEND_RELEASE_ROLE_ARN` | `backend_release_role_arn` | `BackendReleaseRoleArn` |
| `BACKEND_RELEASE_RULE_ARN` | `backend_release_rule_arn` | `BackendReleaseRuleArn` |
| `BACKEND_RELEASE_BLUE_ARN` | `backend_release_target_arns` → `blue` | `BackendReleaseBlueArn` |
| `BACKEND_RELEASE_GREEN_ARN` | `backend_release_target_arns` → `green` | `BackendReleaseGreenArn` |
| `BACKEND_RELEASE_URL` | `application_url` | `ProdUrl` |
| `BACKEND_DEV_URL` | `dev_application_url` | `DevUrl` |

Check that both slots have two healthy targets and that Dev reports its digest at `/api/runtime`. The shared Backend workflow checks the inactive slot before switching traffic and records the verified slot in [backend-slot](charts/tikto/environments/prod/backend-slot).
