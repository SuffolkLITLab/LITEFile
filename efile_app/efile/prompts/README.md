# LLM prompts

This package directory is the source of truth for prompts used by LITEFile.
Prompt files include the model preferences and inference settings that should be
evaluated with the prompt text. Setuptools includes these YAML files in installed
packages, and the repository Docker build copies them under `/app/efile_app`.

`document_extraction.yaml` contains the current production prompt and its
experimental successor. `document_evidence_extraction.yaml` and
`efile_taxonomy_classification.yaml` define the proposed staged flow: preserve
direct facts first, then select court-specific codes from live candidate lists.
The `production_version` key controls which version the application uses.
Benchmark configurations may evaluate every listed version without changing
production behavior.

Prompt templates use Python `string.Template` placeholders such as
`${field_definitions}`. Keep prompts provider-neutral so the same version can be
tested through supported providers.
