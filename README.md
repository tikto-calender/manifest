# TikTo Helm deployments

Argo CD renders [the chart](charts/tikto) with the values listed in [Dev](bootstrap/dev.yaml) and [Prod](bootstrap/prod.yaml). Dev uses one Backend slot and a GHCR image pinned by commit digest. Frontend and Notification continue to use one deployment per environment. Prod uses SemVer tags pinned to the same digest tested in Dev. The Helm chart version tracks the chart itself.

## Bootstrap the migration

1. Publish the compatible reusable workflows on reusable-workflow main first. They can update both the old Kustomize layout and the new Helm values.
2. Set Terraform preview_runner_cidrs to the trusted release runner's fixed egress CIDR and github_oidc_provider_arn to the existing GitHub OIDC provider. Review the Terraform plan. It should move the existing Prod API rule in state, preserve Blue's ALB and target group, and add Green and the preview rules. Apply this infrastructure before switching Argo CD to the chart.
3. Publish the chart and Argo Application specs. Reapply bootstrap/dev.yaml and bootstrap/prod.yaml. Blue intentionally keeps the existing backend resource names. Check that both slots have two healthy targets and that normal traffic still reaches Blue. The cluster needs capacity for both slots and one surge replica during an update.
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
