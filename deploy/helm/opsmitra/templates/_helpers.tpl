{{- define "opsmitra.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "opsmitra.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "opsmitra.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "opsmitra.labels" -}}
app.kubernetes.io/name: {{ include "opsmitra.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "opsmitra.webServiceName" -}}
{{- printf "%s-web" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.frontendServiceName" -}}
{{- printf "%s-frontend" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.postgresServiceName" -}}
{{- printf "%s-postgres" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.redisServiceName" -}}
{{- printf "%s-redis" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.otelServiceName" -}}
{{- printf "%s-otel-collector" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.jaegerServiceName" -}}
{{- printf "%s-jaeger" (include "opsmitra.fullname" .) -}}
{{- end -}}

{{- define "opsmitra.metricsServiceName" -}}
{{- printf "%s-metrics" (include "opsmitra.fullname" .) -}}
{{- end -}}
