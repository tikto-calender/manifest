{{- define "tikto.backendPodSpec" -}}
serviceAccountName: tikto-app
{{- if eq .values.environment "prod" }}
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: kubernetes.io/hostname
          labelSelector:
            matchLabels:
              app: {{ .name }}
{{- end }}
containers:
  - name: tikto
    image: {{ .image | quote }}
    ports:
      - name: http
        containerPort: 3000
    resources:
      requests:
        cpu: 200m
        memory: 256Mi
    env:
      - name: APP_ENV
        value: {{ .values.environment | quote }}
      - name: DYNAMODB_TABLE
        value: {{ .values.backendTable | quote }}
      - name: RELEASE_IMAGE
        value: {{ .image | quote }}
      - name: STORE_BACKEND
        value: dynamodb
      - name: AWS_REGION
        value: ap-southeast-2
      - name: NOTIFICATION_SERVICE_URL
        value: http://notification:8000
    readinessProbe:
      httpGet:
        path: /api/health
        port: http
{{- end -}}
