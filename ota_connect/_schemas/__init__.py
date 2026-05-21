"""JSON Schemas for ota_connect contracts and manifests.

Schemas under this package are generated from the Pydantic models in
`ota_core.contracts.*` (and `ota_core.integration_source.manifest`) so that
external adapter authors can validate adapter manifests / bindings without
importing the framework.

Regenerate via:

    python -m ota_connect._schemas.gen
"""
