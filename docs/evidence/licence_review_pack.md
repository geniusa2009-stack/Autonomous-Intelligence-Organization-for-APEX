# Licence review pack

Prepared offline from the artifacts' own declarations (`config/license_verifications.yaml`). Claude does NOT decide licences: a person entitled to make the call reads the licence text and records the decision with `apex-one license verify`. Until then each model below is evaluation-only.

## `lic-gemma` — artifacts: gemma3-4b-q4km

* declared: **gemma (declared; not verified)** (state DECLARED_BUT_UNVERIFIED)
* artifact source: `registry-1.docker.io/ai/gemma3:4b-q4_K_M`
* evidence: oci_descriptor=gemma
* why not allowed automatically: custom / non-permissive licence declared (['gemma']); its text is not available locally; only 1 independent declaration source(s); 2 required
* what to read: the licence/terms text named above at its official source (not reachable from this container)
* record the decision: `apex-one license verify lic-gemma --license "<name>" --state PRODUCTION_ALLOWED|BLOCKED --source <URL you read> --by "<your name>"`

## `lic-gemma3-12b` — artifacts: gemma3-12b-q4km

* declared: **gemma (declared; not verified)** (state DECLARED_BUT_UNVERIFIED)
* artifact source: `registry-1.docker.io/ai/gemma3:12b-q4_K_M`
* evidence: oci_descriptor=gemma
* why not allowed automatically: custom / non-permissive licence declared (['gemma']); its text is not available locally; only 1 independent declaration source(s); 2 required
* what to read: the licence/terms text named above at its official source (not reachable from this container)
* record the decision: `apex-one license verify lic-gemma3-12b --license "<name>" --state PRODUCTION_ALLOWED|BLOCKED --source <URL you read> --by "<your name>"`

## `lic-nvidia-nemotron-nano` — artifacts: nemotron-3-nano-4b-q4km

* declared: **nvidia-nemotron-open-model-license (declared; text not verified)** (state DECLARED_BUT_UNVERIFIED)
* artifact source: `registry-1.docker.io/ai/nemotron-3-nano:4b`
* evidence: gguf_metadata=other
* why not allowed automatically: custom / non-permissive licence declared (['other:nvidia-nemotron-open-model-license']); its text is not available locally; only 1 independent declaration source(s); 2 required
* what to read: the licence/terms text named above at its official source (not reachable from this container)
* record the decision: `apex-one license verify lic-nvidia-nemotron-nano --license "<name>" --state PRODUCTION_ALLOWED|BLOCKED --source <URL you read> --by "<your name>"`

## `lic-gpt-oss` — artifacts: gpt-oss-20b-mxfp4

* declared: **Apache-2.0 (declared; not production-verified)** (state UNKNOWN)
* artifact source: `registry-1.docker.io/ai/gpt-oss:latest`
* evidence: oci_descriptor=Apache-2.0; gguf_metadata=apache-2.0
* why not allowed automatically: licence registry reports additional terms ('Apache-2.0 + gpt-oss usage policy (reported)') not available locally
* what to read: the licence/terms text named above at its official source (not reachable from this container)
* record the decision: `apex-one license verify lic-gpt-oss --license "<name>" --state PRODUCTION_ALLOWED|BLOCKED --source <URL you read> --by "<your name>"`

