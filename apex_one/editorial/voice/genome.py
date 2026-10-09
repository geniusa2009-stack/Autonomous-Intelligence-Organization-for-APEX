"""APEX Voice Genome: rules + retrievable patterns, versioned."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from apex_one.core.schemas.common import stable_hash
from apex_one.settings import get_settings


@dataclass
class VoiceGenome:
    version: str
    rules: dict[str, Any]
    sections: dict[str, list[dict[str, Any]]]
    warnings: dict[str, dict[str, str]]
    transitions: list[str]
    jokes: list[dict[str, str]]
    ctas: list[str]
    terms: list[str]
    jake: list[str]
    rejected: list[str]
    content_hash: str = ""
    learned_rejections: list[str] = field(default_factory=list)

    def variant(self, section: str, seed: int, avoid: set[int] | None = None) -> tuple[int, dict[str, Any]]:
        options = self.sections.get(section, [])
        if not options:
            return -1, {}
        avoid = avoid or set()
        order = [(seed + i) % len(options) for i in range(len(options))]
        for idx in order:
            if idx not in avoid:
                return idx, options[idx]
        return order[0], options[order[0]]


def _y(path: Path) -> Any:
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def load_voice(voice_dir: Path | None = None, config_dir: Path | None = None) -> VoiceGenome:
    vd = Path(voice_dir or get_settings().voice_dir)
    cd = Path(config_dir or get_settings().config_dir)
    rules = _y(cd / "voice.yaml")
    sections = _y(vd / "approved" / "sections.yaml")
    sections.pop("schema_version", None)
    warnings = _y(vd / "warnings" / "warnings.yaml")
    warnings.pop("schema_version", None)
    blob = {"rules": rules, "sections": sections, "warnings": warnings}
    g = VoiceGenome(
        version=rules.get("voice_version", "unversioned"), rules=rules, sections=sections, warnings=warnings,
        transitions=_y(vd / "transitions" / "transitions.yaml").get("transitions", []),
        jokes=_y(vd / "jokes" / "jokes.yaml").get("jokes", []),
        ctas=_y(vd / "calls_to_action" / "cta.yaml").get("ctas", []),
        terms=_y(vd / "bilingual_patterns" / "patterns.yaml").get("terms", []),
        jake=_y(vd / "jake_patterns" / "jake.yaml").get("patterns", []),
        rejected=_y(vd / "rejected" / "rejected.yaml").get("phrases", []),
    )
    g.content_hash = stable_hash(blob)[:16]
    return g
