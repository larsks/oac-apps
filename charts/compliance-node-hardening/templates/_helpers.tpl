{{/*
Encode text as a base64 Ignition data: URL. Percent-encoding by hand missed
characters MCO expects escaped, so base64 avoids the mismatch entirely.
*/}}
{{- define "cnh.dataURL" -}}
data:;base64,{{ . | b64enc }}
{{- end -}}

{{/* The sshd AllowUsers drop-in as an Ignition file entry (JSON). */}}
{{- define "cnh.sshdFile" -}}
{{- $s := .Values.sshdAllowUsers -}}
{{- $body := printf "%s\nAllowUsers %s\n" $s.header (join " " $s.users) -}}
{{- dict "path" (printf "/etc/ssh/sshd_config.d/%s" $s.fileName) "mode" 384 "overwrite" true "contents" (dict "source" (include "cnh.dataURL" $body)) | toJson -}}
{{- end -}}

{{/*
Convert a storage file "mode" into the decimal integer Ignition expects.
An int passes through unchanged. A string is either an octal mode such as
"0600"/"600", or a 9-character symbolic mode such as "rw-------".
*/}}
{{- define "cnh.fileMode" -}}
{{- $m := . -}}
{{- if not (kindIs "string" $m) -}}
{{- $m -}}
{{- else if regexMatch "^0?[0-7]{3}$" $m -}}
{{- $digits := trimPrefix "0" $m -}}
{{- $n := 0 -}}
{{- range $i := until (len $digits) -}}
{{- $n = add (mul $n 8) (atoi (substr $i (int (add $i 1)) $digits)) -}}
{{- end -}}
{{- $n -}}
{{- else if regexMatch "^[r-][w-][x-][r-][w-][x-][r-][w-][x-]$" $m -}}
{{- $n := 0 -}}
{{- range $t := list 0 3 6 -}}
{{- $r := substr $t (int (add $t 1)) $m -}}
{{- $w := substr (int (add $t 1)) (int (add $t 2)) $m -}}
{{- $x := substr (int (add $t 2)) (int (add $t 3)) $m -}}
{{- $digit := add (ternary 4 0 (eq $r "r")) (add (ternary 2 0 (eq $w "w")) (ternary 1 0 (eq $x "x"))) -}}
{{- $n = add (mul $n 8) $digit -}}
{{- end -}}
{{- $n -}}
{{- else -}}
{{- fail (printf "cnh.fileMode: invalid mode %q, want octal (\"0600\") or symbolic (\"rw-------\")" $m) -}}
{{- end -}}
{{- end -}}

{{/*
Files under files/ write storage file contents as a literal string, not the
Ignition {source: data:,...} form, so the rule text is readable instead of
percent-encoded. Expand any such strings back into that form in place, and
normalize "mode" into the decimal integer Ignition expects.
*/}}
{{- define "cnh.expandFileContents" -}}
{{- $spec := . -}}
{{- $storage := ($spec.config).storage -}}
{{- if $storage -}}
{{- range $storage.files -}}
{{- if kindIs "string" .contents -}}
{{- $_ := set . "contents" (dict "source" (include "cnh.dataURL" .contents)) -}}
{{- end -}}
{{- if hasKey . "mode" -}}
{{- $_ := set . "mode" (include "cnh.fileMode" .mode | trim | int) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- $spec | toJson -}}
{{- end -}}

{{/*
Every rule to render for a role, as a JSON list of {name, spec}. Honours
excludeRules. The NodePool ConfigMap asks for "worker" only.
*/}}
{{- define "cnh.rules" -}}
{{- $root := index . 0 -}}
{{- $role := index . 1 -}}
{{- $out := list -}}
{{- range $root.Values.profiles -}}
{{- $p := . -}}
{{- if has $role $p.roles -}}
{{- range $path, $_ := $root.Files.Glob (printf "files/%s/*.yaml" $p.dir) -}}
{{- $rule := base $path | trimSuffix ".yaml" -}}
{{- if not (has $rule $root.Values.excludeRules) -}}
{{- $name := ternary (printf "%s-%s-%s" $p.namePrefix $role $rule) (printf "%s-%s" $p.namePrefix $rule) $p.roleInName -}}
{{- $spec := include "cnh.expandFileContents" ($root.Files.Get $path | fromYaml) | fromJson -}}
{{- $out = append $out (dict "name" $name "spec" $spec) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- toJson $out -}}
{{- end -}}
