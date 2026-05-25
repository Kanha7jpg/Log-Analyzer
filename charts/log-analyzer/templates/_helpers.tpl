{{/* Helper chart template functions */}}
{{- define "log-analyzer.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 -}}
{{- end -}}

{{- define "log-analyzer.fullname" -}}
{{- printf "%s-%s" (include "log-analyzer.name" .) .Release.Name | trunc 63 -}}
{{- end -}}
