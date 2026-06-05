"""
CEI Outcomes-Results Import Adapter

Handles CEI's (College of Eastern Idaho) FY25 outcomes-assessment export — the
multi-sheet Access/SQL query dump that reports, per course/instructor/outcome,
how many students were assessed (``took_c``) and how many passed (``passed_c``).

This is a fundamentally different shape from the enrollment-roster formats that
``cei_excel_adapter`` handles, so it lives in its own adapter:

- Granular sheet (``qry_2024FA_cllo_results``): the per-instructor, per-CLLO
  measurements. Columns: course, term, combo (``course:instructor``),
  cllo_text, cllo_id, passed_c, took_c.
- Program sheet (``qry_FY25_sum_by_prg_raw``): the program -> PLLO -> CLLO
  alignment used to build program outcomes and PLO<->CLO mappings.

The adapter is parse-only for now: it normalizes the workbook into the standard
entity lists the import pipeline consumes, plus the extra entity types this data
introduces (programs, program outcomes, PLO<->CLO mapping entries, and
per-section outcome measurements). Persistence of the new entity types is
handled in a later step.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple, cast

import pandas as pd

from src.utils.logging_config import get_logger

from .cei_excel_adapter import parse_cei_term
from .file_base_adapter import FileBaseAdapter, FileCompatibilityError

logger = get_logger("CEIOutcomesResultsAdapter")

# Sheet names in the CEI FY25 workbook
GRANULAR_SHEET = "qry_2024FA_cllo_results"
PROGRAM_SHEET = "qry_FY25_sum_by_prg_raw"

# Columns expected on each sheet
GRANULAR_COLUMNS = {
    "course",
    "term",
    "combo",
    "cllo_text",
    "cllo_id",
    "passed_c",
    "took_c",
}
# Only these terms carry real granular data; everything else is dropped.
VALID_TERMS = {"2024FA", "2025SP"}

# Satisfactory threshold: result is "S" when pass rate >= this, else "U".
PASS_THRESHOLD = 0.75

# Fabricated, unmistakably non-real email domain for demo instructors.
# (.example is reserved by RFC 2606; "cei-demo" marks it as demo data.)
EMAIL_DOMAIN = "cei-demo.example"

# Matches a "COURSE:Instructor Name" combo, e.g. "ACC-201:Jennifer Barzee".
_COMBO_RE = re.compile(r"^[A-Z]{2,}-?\d+[A-Z]?:")
# Extracts a CLLO id like "ASE-103L.1" from free text.
_CLLO_ID_RE = re.compile(r"([A-Z]{2,}-?\d+[A-Z]?\.\d+)")

# Synthesized academic-calendar dates per season (month/day), applied to the
# term's year. Dates land in the past relative to the demo, so the assessment
# workflow shows as completed.
_SEASON_DATES = {
    "Fall": ("08-26", "12-13"),
    "Spring": ("01-13", "05-09"),
    "Summer": ("05-19", "08-08"),
    "Winter": ("01-02", "01-12"),
}


def _read_sheet(file_path: str, sheet_name: str) -> pd.DataFrame:
    """Read one worksheet as a DataFrame (typed wrapper around pd.read_excel)."""
    read_excel = cast(Callable[..., pd.DataFrame], getattr(pd, "read_excel"))
    return read_excel(file_path, sheet_name=sheet_name)


def _sheet_names(file_path: str) -> List[str]:
    """Return the worksheet names in a workbook."""
    excel_file = cast(Any, pd.ExcelFile(file_path))
    return [str(name) for name in excel_file.sheet_names]


def _clean(value: Any) -> Optional[str]:
    """Return a stripped string, or None for NaN/empty values."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip()
    return text or None


def _instructor_from_combo(combo: Optional[str]) -> Optional[str]:
    """Pull the instructor name out of a "COURSE:Name" combo string."""
    if combo and ":" in combo:
        name = combo.split(":", 1)[1].strip()
        return name or None
    return None


def _slug(text: str) -> str:
    """ASCII-lowercase slug of a name part (drops accents, punctuation)."""
    decoded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", decoded.lower())


def fabricate_email(full_name: str) -> str:
    """Build a stable demo email from an instructor's display name.

    Real CEI faculty names are preserved (the demo is shown back to CEI), but
    every email lands on the fabricated demo domain so no real address is used.
    """
    parts = [p for p in (_slug(part) for part in full_name.split()) if p]
    if not parts:
        local = "instructor"
    elif len(parts) == 1:
        local = parts[0]
    else:
        local = f"{parts[0]}.{parts[-1]}"
    return f"{local}@{EMAIL_DOMAIN}"


def split_name(full_name: str) -> Tuple[str, str]:
    """Split a display name into (first, last). Single-token names get a blank last."""
    parts = full_name.split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


def term_dates(year: str, season: str) -> Tuple[str, str]:
    """Return synthesized (start_date, end_date) ISO strings for a term."""
    start_md, end_md = _SEASON_DATES.get(season, ("01-01", "05-01"))
    return f"{year}-{start_md}", f"{year}-{end_md}"


def is_satisfactory(passed: int, took: int) -> bool:
    """Apply CEI's S/U rule: satisfactory when pass rate meets the threshold."""
    if took <= 0:
        return False
    return (passed / took) >= PASS_THRESHOLD


class CEIOutcomesResultsAdapter(FileBaseAdapter):
    """Parse CEI's FY25 outcomes-results workbook into import-ready entities."""

    def __init__(self) -> None:
        # Diagnostics from the most recent parse_file run (for dry-run reporting).
        self.last_parse_stats: Dict[str, Any] = {}

    # ------------------------------------------------------------------ #
    # Compatibility / detection
    # ------------------------------------------------------------------ #
    def validate_file_compatibility(self, file_path: str) -> Tuple[bool, str]:
        ext_ok, ext_msg = self.validate_file_extension(file_path)
        if not ext_ok:
            return False, ext_msg

        try:
            sheets = _sheet_names(file_path)
        except Exception as exc:  # noqa: BLE001 - surface any read failure to caller
            return False, f"Cannot read Excel file: {exc}"

        if GRANULAR_SHEET not in sheets:
            return (
                False,
                f"Missing required sheet '{GRANULAR_SHEET}'. "
                "This adapter expects CEI's outcomes-results workbook.",
            )

        granular = _read_sheet(file_path, GRANULAR_SHEET)
        missing = GRANULAR_COLUMNS - set(granular.columns)
        if missing:
            return False, f"Sheet '{GRANULAR_SHEET}' missing columns: {sorted(missing)}"

        course_count = granular["course"].dropna().nunique()
        outcome_count = granular["cllo_id"].dropna().nunique()
        has_programs = PROGRAM_SHEET in sheets
        program_note = (
            f", program mappings from '{PROGRAM_SHEET}'"
            if has_programs
            else " (no program sheet — outcomes will not roll up to programs)"
        )
        return (
            True,
            f"Compatible. Detected ~{course_count} courses and "
            f"~{outcome_count} course outcomes{program_note}.",
        )

    def detect_data_types(self, file_path: str) -> List[str]:
        try:
            sheets = _sheet_names(file_path)
        except Exception:  # noqa: BLE001 - detection is best-effort
            return []
        types = [
            "courses",
            "course_outcomes",
            "faculty",
            "terms",
            "sections",
            "assessments",
        ]
        if PROGRAM_SHEET in sheets:
            types.extend(["programs", "program_outcomes"])
        return types

    def get_adapter_info(self) -> Dict[str, Any]:
        return {
            "id": "cei_outcomes_results_v1",
            "name": "CEI Outcomes Results",
            "description": (
                "Imports CEI's FY25 outcomes-assessment export: program and "
                "course outcomes, per-instructor pass/took measurements, and the "
                "program-to-outcome alignment used for PLO dashboards."
            ),
            "supported_formats": [".xlsx", ".xls"],
            "institution_short_name": "CEI",
            "public": False,
            "data_types": [
                "programs",
                "program_outcomes",
                "courses",
                "course_outcomes",
                "faculty",
                "terms",
                "sections",
                "assessments",
            ],
            "version": "1.0.0",
            "created_by": "System Developer",
            "last_updated": "2026-06-04",
        }

    # ------------------------------------------------------------------ #
    # Parsing
    # ------------------------------------------------------------------ #
    def parse_file(
        self, file_path: str, options: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        is_ok, message = self.validate_file_compatibility(file_path)
        if not is_ok:
            raise FileCompatibilityError(f"File incompatible: {message}")

        institution_id = options.get("institution_id")
        if not institution_id:
            raise ValueError("institution_id is required in options")

        measurements, stats = self._read_measurements(file_path)
        result = self._build_entities(measurements, institution_id)

        programs, program_outcomes, mapping_entries, prog_stats = (
            self._read_program_structure(file_path, institution_id)
        )
        result["programs"] = programs
        result["program_outcomes"] = program_outcomes
        result["plo_mapping_entries"] = mapping_entries

        stats.update(prog_stats)
        stats["entity_counts"] = {key: len(rows) for key, rows in result.items()}
        self.last_parse_stats = stats
        return result

    def _read_measurements(
        self, file_path: str
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Read + clean the granular sheet into normalized measurement records.

        Each record: course, term, instructor, cllo_id, cllo_text, passed, took.
        Handles the interleaved "Total" rollup rows and the column-shifted rows.
        """
        df = _read_sheet(file_path, GRANULAR_SHEET)
        total_rows = len(df)
        data_rows = df[df["course"].notna()].copy()
        rollup_dropped = total_rows - len(data_rows)

        records: List[Dict[str, Any]] = []
        shifted_repaired = 0
        # Build a course -> most common term map from clean rows, to recover the
        # term for shifted rows (whose term column was consumed by the shift).
        term_hint: Dict[str, str] = {}
        for _, row in data_rows.iterrows():
            term = _clean(row["term"])
            course = _clean(row["course"])
            if course and term in VALID_TERMS:
                term_hint.setdefault(course, term)

        unknown_term = 0
        for _, row in data_rows.iterrows():
            course = _clean(row["course"])
            term = _clean(row["term"])
            if not course:
                continue

            if term is not None and _COMBO_RE.match(term):
                # Column-shifted row: values slipped one column right starting at
                # `term`. Recover by reading one column to the left of each field.
                shifted_repaired += 1
                combo = term
                cllo_text = _clean(row["combo"])
                cllo_id = _clean(row["cllo_text"])
                passed = row["cllo_id"]
                took = row["passed_c"]
                term = term_hint.get(course)
            else:
                combo = _clean(row["combo"])
                cllo_text = _clean(row["cllo_text"])
                cllo_id = _clean(row["cllo_id"])
                passed = row["passed_c"]
                took = row["took_c"]

            if term not in VALID_TERMS:
                unknown_term += 1
                continue

            instructor = _instructor_from_combo(combo)
            passed_i = self._to_int(passed)
            took_i = self._to_int(took)
            if not (course and instructor and cllo_id) or took_i is None:
                continue

            records.append(
                {
                    "course": course,
                    "term": term,
                    "instructor": instructor,
                    "cllo_id": cllo_id,
                    "cllo_text": cllo_text or cllo_id,
                    "passed": passed_i or 0,
                    "took": took_i,
                }
            )

        stats: Dict[str, Any] = {
            "granular_total_rows": total_rows,
            "rollup_rows_dropped": rollup_dropped,
            "shifted_rows_repaired": shifted_repaired,
            "rows_dropped_unknown_term": unknown_term,
            "measurements": len(records),
        }
        return records, stats

    @staticmethod
    def _to_int(value: Any) -> Optional[int]:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return None
        try:
            return int(round(float(value)))
        except (ValueError, TypeError):
            return None

    def _build_entities(
        self, measurements: List[Dict[str, Any]], institution_id: str
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Turn normalized measurements into deduplicated entity lists."""
        courses: Dict[str, Dict[str, Any]] = {}
        outcomes: Dict[str, Dict[str, Any]] = {}
        faculty: Dict[str, Dict[str, Any]] = {}
        terms: Dict[str, Dict[str, Any]] = {}
        offerings: Dict[Tuple[str, str], Dict[str, Any]] = {}
        sections: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        section_outcomes: List[Dict[str, Any]] = []

        for rec in measurements:
            course = rec["course"]
            term = rec["term"]
            instructor = rec["instructor"]
            email = fabricate_email(instructor)

            courses.setdefault(
                course,
                {
                    "course_number": course,
                    "course_title": course,  # no titles in source — use the code
                    "institution_id": institution_id,
                },
            )
            outcomes.setdefault(
                rec["cllo_id"],
                {
                    "course_number": course,
                    "clo_number": rec["cllo_id"],
                    "description": rec["cllo_text"],
                    "institution_id": institution_id,
                },
            )
            if email not in faculty:
                first, last = split_name(instructor)
                faculty[email] = {
                    "email": email,
                    "first_name": first,
                    "last_name": last,
                    "role": "instructor",
                    "institution_id": institution_id,
                }
            if term not in terms:
                year, season = parse_cei_term(term)
                start, end = term_dates(year, season)
                terms[term] = {
                    "term_name": term,
                    "name": f"{season} {year}",
                    "year": year,
                    "season": season,
                    "start_date": start,
                    "end_date": end,
                    "institution_id": institution_id,
                }
            offerings.setdefault(
                (course, term),
                {
                    "course_number": course,
                    "term_name": term,
                    "institution_id": institution_id,
                },
            )
            sec_key = (course, term, instructor)
            if sec_key not in sections:
                sections[sec_key] = {
                    "course_number": course,
                    "term_name": term,
                    "instructor_email": email,
                    "section_number": f"{len([s for s in sections if s[0] == course and s[1] == term]) + 1:03d}",
                    "institution_id": institution_id,
                }
            section_outcomes.append(
                {
                    "course_number": course,
                    "term_name": term,
                    "instructor_email": email,
                    "clo_number": rec["cllo_id"],
                    "students_took": rec["took"],
                    "students_passed": rec["passed"],
                    "result": (
                        "S" if is_satisfactory(rec["passed"], rec["took"]) else "U"
                    ),
                    "institution_id": institution_id,
                }
            )

        return {
            "courses": list(courses.values()),
            "users": list(faculty.values()),
            "terms": list(terms.values()),
            "offerings": list(offerings.values()),
            "sections": list(sections.values()),
            "clos": list(outcomes.values()),
            "section_outcomes": section_outcomes,
        }

    def _read_program_structure(self, file_path: str, institution_id: str) -> Tuple[
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        List[Dict[str, Any]],
        Dict[str, Any],
    ]:
        """Read programs, program outcomes, and PLO<->CLO mapping entries.

        PLO numbers in the source are alphanumeric labels (e.g. "AT1", "G1.1"),
        so each program's PLOs get a sequential ordinal ``plo_number`` while the
        original label is preserved in ``extras.label``.
        """
        sheets = _sheet_names(file_path)
        if PROGRAM_SHEET not in sheets:
            return [], [], [], {"program_sheet_present": False}

        df = _read_sheet(file_path, PROGRAM_SHEET)
        programs: Dict[str, Dict[str, Any]] = {}
        # (program_code, plo_label) -> ordinal program-outcome record
        plos: Dict[Tuple[str, str], Dict[str, Any]] = {}
        plo_order: Dict[str, int] = {}
        mapping_entries: List[Dict[str, Any]] = []
        seen_entries: set[Tuple[str, str, str]] = set()

        for _, row in df.iterrows():
            code = _clean(row["code"])
            program_name = _clean(row["program"])
            plo_label = _clean(row["pllo_num"])
            plo_text = _clean(row["pllo_text"])
            cllo_match = _CLLO_ID_RE.search(str(row["cllo_text"]))
            if not (code and plo_label and cllo_match):
                continue
            clo_number = cllo_match.group(1)

            programs.setdefault(
                code,
                {
                    "short_name": code,
                    "name": program_name or code,
                    "institution_id": institution_id,
                },
            )
            plo_key = (code, plo_label)
            if plo_key not in plos:
                plo_order[code] = plo_order.get(code, 0) + 1
                plos[plo_key] = {
                    "program_short_name": code,
                    "plo_number": plo_order[code],
                    "plo_label": plo_label,
                    "description": plo_text or plo_label,
                    "institution_id": institution_id,
                }

            entry_key = (code, plo_label, clo_number)
            if entry_key not in seen_entries:
                seen_entries.add(entry_key)
                mapping_entries.append(
                    {
                        "program_short_name": code,
                        "plo_label": plo_label,
                        "clo_number": clo_number,
                    }
                )

        stats: Dict[str, Any] = {
            "program_sheet_present": True,
            "program_rows": len(df),
            "mapping_entries": len(mapping_entries),
        }
        return (
            list(programs.values()),
            list(plos.values()),
            mapping_entries,
            stats,
        )

    # ------------------------------------------------------------------ #
    # Export (not supported for this read-only assessment format)
    # ------------------------------------------------------------------ #
    def supports_export(self) -> bool:
        return False

    def export_data(
        self,
        data: Dict[str, List[Dict[str, Any]]],
        output_path: str,
        options: Dict[str, Any],
    ) -> Tuple[bool, str, int]:
        return (
            False,
            "Export is not supported by the CEI outcomes-results adapter.",
            0,
        )
