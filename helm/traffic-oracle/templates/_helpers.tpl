{{- define "traffic-oracle.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "traffic-oracle.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
name: {{ .Chart.Name }}
instance: {{ .Release.Name }}
version: {{ .Chart.AppVersion | quote }}
managed-by: {{ .Release.Service }}
{{- end -}}

{{- define "traffic-oracle.selectorLabels" -}}
name: {{ .ctx.Chart.Name }}
instance: {{ .ctx.Release.Name }}
component: {{ .component }}
{{- end -}}

{{- define "traffic-oracle.staticName" -}}
{{- printf "%s-static" (include "traffic-oracle.fullname" .) -}}
{{- end -}}

{{- define "traffic-oracle.grafanaName" -}}
{{- printf "%s-grafana" (include "traffic-oracle.fullname" .) -}}
{{- end -}}

{{- define "traffic-oracle.dataClaimName" -}}
{{- printf "%s-data" (include "traffic-oracle.fullname" .) -}}
{{- end -}}

{{- define "traffic-oracle.grafanaSecretName" -}}
{{- required "grafana.adminSecretName is required" .Values.grafana.adminSecretName -}}
{{- end -}}

{{- define "traffic-oracle.ingressHost" -}}
{{- required "ingress.host is required" .Values.ingress.host -}}
{{- end -}}

{{- define "traffic-oracle.grafanaRootUrl" -}}
{{- printf "http://%s" (include "traffic-oracle.ingressHost" .) -}}
{{- end -}}
