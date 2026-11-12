# TikTo Manifest

This repository defines what Argo CD deploys to EKS. The [Helm chart](charts/tikto) describes the workloads and ALB target bindings. The [Dev](bootstrap/dev.yaml) and [Prod](bootstrap/prod.yaml) Applications select the environment values and pinned GHCR images from `main`. Dev has one Backend deployment. Prod has Blue and Green Backend deployments so a new image can be checked before it receives live traffic.

## Render the chart locally

From the repository root, use Helm 3 to render the Dev chart with the same values as Argo CD. This check renders Kubernetes YAML locally.

```powershell
helm template tikto-dev ./charts/tikto --namespace tikto-dev `
  -f ./charts/tikto/environments/dev/values.yaml `
  -f ./charts/tikto/environments/dev/frontend-image.yaml `
  -f ./charts/tikto/environments/dev/backend-image.yaml `
  -f ./charts/tikto/environments/dev/notification-image.yaml
```

The output includes Deployments for `frontend`, `backend` and `notification`, plus target group bindings for Frontend and Backend. To render Prod, use namespace `tikto-prod` and the files listed under `helm.valueFiles` in [bootstrap/prod.yaml](bootstrap/prod.yaml).

## Deploy with Argo CD

You need an EKS cluster with the TikTo target groups, AWS Load Balancer Controller, Argo CD and kubectl access. For platform and controller setup, follow the [Terraform guide](https://github.com/tikto-calender/infra) or [CloudFormation guide](https://github.com/tikto-calender/infra-by-cloudformation).

Confirm that the environment values and pullable image digests are published to manifest `main`. From the repository root, apply the namespaces and the Application for each enabled environment:

```powershell
kubectl config current-context
kubectl apply -f ./bootstrap/namespaces.yaml
kubectl apply -f ./bootstrap/dev.yaml
# Run this only if the Prod ALB and target groups are enabled.
kubectl apply -f ./bootstrap/prod.yaml
kubectl -n argocd get applications
```

Expect each enabled application to report `Synced` and `Healthy`. Check `/api/health` and `/api/status` on its ALB URL. To enable Telegram, create the `notification-telegram` Secret in the relevant namespace using the [example manifests](examples/secrets).

## Promote to Production

After verifying Dev, open **Actions** in this repository and run the relevant workflow from `main` with a version such as `v2.0.1`. Each workflow promotes the digest already deployed to Dev.

| Workflow in Manifest | Reusable workflow |
| --- | --- |
| [Promote Frontend](.github/workflows/release-frontend.yml) | `cd-prod.yml` |
| [Promote Notification](.github/workflows/release-notification.yml) | `cd-prod.yml` |
| [Promote Backend (blue/green)](.github/workflows/release-backend.yml) | `cd-prod-backend.yml` |
| [Promote All Services](.github/workflows/release.yml) | Both workflows, with one version per service |

Check the Prod application in Argo CD and verify the app through the Prod ALB. Then run **Finalize release** in each corresponding source repository with the same version. [Shared workflow setup](https://github.com/tikto-calender/reusable-workflow)

When publishing this migration, publish `cd-prod-backend.yml` and `scripts/backend_release.py` to `main` in `reusable-workflow` before publishing the Manifest caller.

## Configure Backend blue/green

1. Publish the compatible reusable workflows on `reusable-workflow` `main` first. They support both Helm values and the earlier Kustomize layout.
2. Configure the runner's fixed egress CIDR and the GitHub OIDC provider in your platform stack. For Terraform, use `preview_runner_cidrs` and `github_oidc_provider_arn`. When migrating an existing Terraform deployment, verify the plan moves the Prod API rule in state, preserves Blue's ALB and target group, and adds Green and the preview rules. Apply the infrastructure before switching Argo CD to the chart.
3. Publish the chart and Argo Application specs, then apply the Dev and Prod Applications. Blue keeps the existing backend resource names. Check that both slots have two healthy targets and that normal traffic reaches the active slot recorded in Git. The cluster needs capacity for both slots and one surge replica during an update.
4. Register a trusted Linux runner with label tikto-prod-preview, Python 3.11+, AWS CLI v2, Docker and Buildx. Protect the prod GitHub Environment with a main branch deployment restriction. Restrict the runner to this repository and production workflows.
5. Set the prod Environment variables below. Then deploy a new BE Dev commit containing RELEASE_IMAGE support and check /api/runtime before attempting promotion.

| Variable | Source |
| --- | --- |
| BACKEND_RELEASE_ROLE_ARN | Terraform backend_release_role_arn |
| BACKEND_RELEASE_RULE_ARN | Terraform backend_release_rule_arn |
| BACKEND_RELEASE_BLUE_ARN, BACKEND_RELEASE_GREEN_ARN | The blue and green entries from backend_release_target_arns |
| BACKEND_RELEASE_URL | Prod ALB application URL |
| BACKEND_DEV_URL | Dev ALB application URL |

## Promote Backend

Run **Promote Backend (blue/green)** on manifest main with a new version such as v2.0.1. The workflow checks Dev, retags its digest, and commits it into the inactive slot's values. After the ALB sees two healthy candidate targets, five consecutive preview checks confirm the exact image and a read-only database health query. The preview header is accepted only from the configured runner CIDRs.

The workflow switches the normal API rule, samples the ordinary user path, and checks CloudWatch request and 5xx counts for the candidate target group. Synthetic failure, p95 above one second, more than 1% target 5xx, or insufficient data fail the release and restore the previous rule. The previous slot stays running for the next promotion. A successful release records the active slot and version in Git. Run source **Finalize release** after promotion.

If the runner is forcibly stopped after switching, the next promotion invocation compares the live rule with the last verified Git slot and restores it before proceeding. Verify the live rule promptly after an interrupted run. For recovery while the pipeline is unavailable, point the Prod API rule at the target group in backend-slot after checking that group is healthy. The workflow owns the API rule action and Terraform owns its conditions and the preview rules.

## Argo Rollouts lab on Dev

The lab follows the Dev Backend digest. Its two internal Services are separate from the public Dev Backend and its ALB. Install the controller and CRDs before enabling the lab.

```sh
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm upgrade --install argo-rollouts argo/argo-rollouts --version 2.43.11 --namespace argo-rollouts --create-namespace --wait
kubectl wait --for=condition=Established crd/rollouts.argoproj.io crd/analysistemplates.argoproj.io --timeout=120s
```

1. Reapply bootstrap/dev.yaml so the AppProject allows the lab resources and Argo CD leaves the controller-managed Service selector hashes alone.
2. Deploy a Dev Backend image that reports its digest as image in /api/runtime. Set rolloutLab.enabled to true in charts/tikto/environments/dev/values.yaml on manifest main.
3. After the first revision becomes active, deploy another Backend commit through Dev CD. Watch the new ReplicaSet and the test Jobs.

```sh
kubectl -n tikto-dev get rollouts,analysisruns,jobs -w
kubectl -n tikto-dev logs job/<smoke-job-name>
```

The pre-promotion Job checks the preview Service. The post-promotion Job checks the active Service after switching. Both confirm the expected image and a read-only DynamoDB check. A failed preview check blocks the switch. A failed post-promotion check aborts and restores the previous stable route when a stable revision is available. Use a Dev candidate with a reproducibly broken runtime response to demonstrate a blocked promotion, then deploy a corrected digest.
