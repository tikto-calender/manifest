# TikTo Manifest

Repo này chứa cấu hình để Argo CD triển khai **Frontend, Backend và Notification Service** lên EKS. [Helm chart](charts/tikto) định nghĩa pod và Service. Các file values chọn image GHCR theo digest cho từng môi trường. Dev có một Backend, còn Prod có hai nhóm Backend Blue và Green để kiểm tra bản mới trước khi chuyển lưu lượng.

| Bạn muốn làm gì? | Bắt đầu ở đâu? |
| --- | --- |
| Xem YAML mà Argo CD sẽ tạo | [Render Helm trên máy](#render-helm) |
| Đưa TikTo lên một cụm EKS đã có hạ tầng | [Triển khai bằng Argo CD](#deploy-with-argo-cd) |
| Đưa image đã kiểm tra ở Dev lên Prod | [Promote lên Prod](#promote-to-production) |

<a name="render-helm"></a>

## 1. Render Helm trên máy

Cài Helm và mở terminal ở thư mục gốc repo. Nếu chưa clone, lệnh sau dùng được trên **Linux/macOS và Windows PowerShell**.

```sh
git clone https://github.com/tikto-calender/manifest.git
cd manifest
```

### Linux/macOS

```sh
helm template tikto-dev ./charts/tikto --namespace tikto-dev \
  -f ./charts/tikto/environments/dev/values.yaml \
  -f ./charts/tikto/environments/dev/frontend-image.yaml \
  -f ./charts/tikto/environments/dev/backend-image.yaml \
  -f ./charts/tikto/environments/dev/notification-image.yaml

helm template tikto-prod ./charts/tikto --namespace tikto-prod \
  -f ./charts/tikto/environments/prod/values.yaml \
  -f ./charts/tikto/environments/prod/frontend-image.yaml \
  -f ./charts/tikto/environments/prod/notification-image.yaml \
  -f ./charts/tikto/environments/prod/blue-image.yaml \
  -f ./charts/tikto/environments/prod/green-image.yaml
```

### Windows PowerShell

```powershell
helm template tikto-dev ./charts/tikto --namespace tikto-dev `
  -f ./charts/tikto/environments/dev/values.yaml `
  -f ./charts/tikto/environments/dev/frontend-image.yaml `
  -f ./charts/tikto/environments/dev/backend-image.yaml `
  -f ./charts/tikto/environments/dev/notification-image.yaml

helm template tikto-prod ./charts/tikto --namespace tikto-prod `
  -f ./charts/tikto/environments/prod/values.yaml `
  -f ./charts/tikto/environments/prod/frontend-image.yaml `
  -f ./charts/tikto/environments/prod/notification-image.yaml `
  -f ./charts/tikto/environments/prod/blue-image.yaml `
  -f ./charts/tikto/environments/prod/green-image.yaml
```

Dev render ba Deployment, Prod render bốn Deployment. `helm template` chỉ in YAML. Cấu hình triển khai cần EKS, ALB target group và DynamoDB của TikTo.

<a name="deploy-with-argo-cd"></a>

## 2. Triển khai bằng Argo CD

Cần kubectl trỏ vào cụm EKS, AWS Load Balancer Controller, Argo CD và các target group đã được tạo. Làm theo [Terraform](https://github.com/tikto-calender/infra) hoặc [CloudFormation](https://github.com/tikto-calender/infra-by-cloudformation) để dựng các phần này. Argo CD đọc chart và các digest từ `main`, vì vậy hãy kiểm tra các image trên nhánh đó kéo được từ GHCR.

Từ thư mục repo Manifest, kiểm tra kube context rồi tạo Application Dev. Lệnh dùng chung cho **Linux/macOS và Windows PowerShell**.

```sh
kubectl config current-context
kubectl apply -f ./bootstrap/namespaces.yaml
kubectl apply -f ./bootstrap/dev.yaml
kubectl -n argocd get applications
kubectl -n tikto-dev get pods
```

Nếu đã bật ALB và target group Prod, chạy thêm:

```sh
kubectl apply -f ./bootstrap/prod.yaml
kubectl -n argocd get applications
kubectl -n tikto-prod get pods
```

Application cần báo `Synced` và `Healthy`. Mở URL ALB của môi trường, sau đó kiểm tra `/api/health` và `/api/status`. URL nằm trong output Terraform (`dev_application_url`, `application_url`) hoặc CloudFormation (`DevUrl`, `ProdUrl`). Có thể mở giao diện Argo CD qua `kubectl -n argocd port-forward svc/argocd-server 8080:443`.

Để bật Telegram, sao chép file mẫu cho đúng môi trường trong [examples/secrets](examples/secrets), điền token và chat ID, rồi áp dụng file chứa Secret `notification-telegram` vào namespace tương ứng. Các file YAML tạo trong thư mục đó được Git ignore.

<a name="promote-to-production"></a>

## 3. Promote lên Prod

Sau khi xác minh bản Dev, mở **Actions** trong repo Manifest, chọn nhánh `main` và nhập version mới, ví dụ `v2.0.1`. Mỗi workflow dùng đúng digest đã triển khai ở Dev.

| Chọn trong Actions | Workflow dùng chung |
| --- | --- |
| [Promote Frontend](.github/workflows/release-frontend.yml) | `cd-prod.yml` |
| [Promote Notification](.github/workflows/release-notification.yml) | `cd-prod.yml` |
| [Promote Backend (blue/green)](.github/workflows/release-backend.yml) | `cd-prod-backend.yml` |
| [Promote All Services](.github/workflows/release.yml) | Cả hai workflow, mỗi dịch vụ nhận một version |

Kiểm tra Argo CD và URL Prod sau khi chạy. Sau đó chạy **Finalize release** trên `main` của repo ứng dụng tương ứng với cùng version. Khi thay đổi một workflow dùng chung, publish thay đổi đó lên `main` của [reusable-workflow](https://github.com/tikto-calender/reusable-workflow) trước khi publish caller.

<a name="configure-backend-bluegreen"></a>

## Cấu hình Backend blue/green

1. Bật preview listener rules và IAM role dùng GitHub OIDC trong IaC. Terraform dùng `preview_runner_cidrs` và `github_oidc_provider_arn`. CloudFormation dùng `PreviewRunnerCidr` và `GitHubOidcProviderArn`. Khi nâng cấp Terraform, xem plan để xác nhận ALB và target group Blue được giữ lại.
2. Dùng runner Linux có nhãn `tikto-prod-preview`, IP egress cố định, Python 3.11+, AWS CLI v2, Docker và Buildx. Đặt GitHub Environment `prod` của Manifest cho nhánh `main`. Cấp Manifest quyền **Write** trên package Backend ở GHCR.
3. Cấu hình các biến trong Environment `prod` theo bảng dưới. Xác nhận cả hai slot có hai target khỏe, cluster đủ chỗ cho một pod tăng thêm khi cập nhật và Backend Dev hiển thị digest tại `/api/runtime`.

| Biến GitHub Actions | Terraform output | CloudFormation output |
| --- | --- | --- |
| `BACKEND_RELEASE_ROLE_ARN` | `backend_release_role_arn` | `BackendReleaseRoleArn` |
| `BACKEND_RELEASE_RULE_ARN` | `backend_release_rule_arn` | `BackendReleaseRuleArn` |
| `BACKEND_RELEASE_BLUE_ARN` | `backend_release_target_arns` → `blue` | `BackendReleaseBlueArn` |
| `BACKEND_RELEASE_GREEN_ARN` | `backend_release_target_arns` → `green` | `BackendReleaseGreenArn` |
| `BACKEND_RELEASE_URL` | `application_url` | `ProdUrl` |
| `BACKEND_DEV_URL` | `dev_application_url` | `DevUrl` |

<a name="promote-backend"></a>

### Cách workflow Backend chuyển lưu lượng

**Promote Backend (blue/green)** ghi image mới vào slot đang chờ. Workflow xác nhận hai target khỏe và yêu cầu năm lần kiểm tra preview liên tiếp, gồm kiểm tra đúng digest và đọc DynamoDB. Sau khi chuyển ALB, workflow kiểm tra đường dẫn người dùng và số liệu CloudWatch. Lỗi kiểm tra, p95 trên một giây, tỷ lệ target 5xx trên 1% hoặc thiếu dữ liệu sẽ đưa lưu lượng về slot trước.

Sau khi thành công, workflow ghi slot đang chạy vào [backend-slot](charts/tikto/environments/prod/backend-slot). Nếu job bị ngắt sau lúc chuyển lưu lượng, kiểm tra ngay listener ALB và slot đã xác minh trong Git. Lần promote tiếp theo sẽ thử khôi phục slot đã ghi nếu nó còn khỏe. Khi cần khôi phục thủ công, đối chiếu sức khỏe target group trước khi chuyển listener.

## Lab Argo Rollouts trên Dev

Lab theo digest Backend Dev và dùng hai Service nội bộ. Cài controller trước khi bật lab. Các lệnh dùng chung cho **Linux/macOS và Windows PowerShell**.

```sh
helm repo add argo https://argoproj.github.io/argo-helm
helm repo update
helm upgrade --install argo-rollouts argo/argo-rollouts --version 2.43.11 --namespace argo-rollouts --create-namespace --wait
kubectl wait --for=condition=Established crd/rollouts.argoproj.io crd/analysistemplates.argoproj.io --timeout=120s
```

Áp lại [Application Dev](bootstrap/dev.yaml), kiểm tra Backend Dev có digest tại `/api/runtime`, rồi đặt `rolloutLab.enabled: true` trong [values Dev](charts/tikto/environments/dev/values.yaml) trên `main`. Khi bản đầu đã active, deploy thêm một Backend commit vào Dev để xem các job kiểm tra preview và active.

```sh
kubectl -n tikto-dev get rollouts,analysisruns,jobs -w
```

Nếu kiểm tra preview thất bại, workflow rollout giữ route đang chạy. Nếu kiểm tra sau khi chuyển thất bại, controller có thể trở về bản ổn định trước đó.
