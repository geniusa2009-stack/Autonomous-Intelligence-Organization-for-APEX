# APEX Voice Genome

Structured, versioned voice knowledge. No fine-tuning: rules (`config/voice.yaml`) + retrieval of these
patterns + preference learning from human edits (`apex-one voice approve/reject`).

Syntax used in templates:
* `{{slot}}` — a locked fact rendered from its FactLock (Arabic display). `{{slot|en}}` uses the English display.
* `[[term]]` — an English term kept in Latin script and bidi-isolated (e.g. `[[deadline]]`).
* `{name}` — a non-fact variable (institution name, cycle).
Writers may NOT type a locked value directly; the fact guard rejects any unbound number/date/amount.
