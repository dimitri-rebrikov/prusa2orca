"""Data models for PrusaSlicer and OrcaSlicer profiles."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SectionType(Enum):
    """Types of sections in a PrusaSlicer .ini file."""
    VENDOR = "vendor"
    PRINTER_MODEL = "printer_model"
    PRINTER = "printer"
    PRINT = "print"
    FILAMENT = "filament"


@dataclass
class PrusaSection:
    """A parsed section from a PrusaSlicer .ini file."""
    raw_name: str                # e.g. "printer:*CR5PROH*" or "print:0.16 mm OPTIMAL @CREALITY"
    section_type: SectionType
    profile_name: str            # e.g. "*CR5PROH*" or "0.16 mm OPTIMAL @CREALITY"
    params: Dict[str, str]       # key=value pairs
    inherits: List[str] = field(default_factory=list)  # templates to inherit from, in order

    def is_template(self) -> bool:
        """Template sections have *wildcard* names (internal, not user-selectable)."""
        return "*" in self.profile_name


@dataclass
class ResolvedProfile:
    """A fully resolved profile with all inherited parameters merged."""
    source_section: PrusaSection
    resolved_params: Dict[str, str]  # all params after inheritance resolution


@dataclass
class OrcaProfile:
    """An OrcaSlicer JSON profile ready for serialization."""
    type: str            # "machine_model", "machine", "process", "filament"
    name: str
    inherits: Optional[str] = None
    from_field: str = "system"
    setting_id: Optional[str] = None
    instantiation: str = "true"
    data: Dict = field(default_factory=dict)
