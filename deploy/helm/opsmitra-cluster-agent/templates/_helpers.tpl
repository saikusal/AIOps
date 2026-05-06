{{- define "opsmitra-cluster-agent.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "opsmitra-cluster-agent.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "opsmitra-cluster-agent.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
