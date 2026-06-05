"""Persistence path for the CEI outcomes-results adapter.

The generic import pipeline handles enrollment-roster data (users, courses,
terms, offerings, sections, CLOs). CEI's outcomes-results export introduces
additional entity types — programs, program outcomes, published PLO<->CLO
mappings, and per-section outcome measurements — that the generic path does not
persist. This mixin adds a dedicated, dependency-ordered persistence routine for
that richer shape.

Key behaviors:
- Course outcomes are stored with ``program_id = None``; a single CLO can map to
  several programs, and program rollups resolve through the published PLO<->CLO
  mapping (by outcome id), not through the outcome's program_id.
- Creating a section auto-instantiates a CourseSectionOutcome for every CLO of
  the course (see database_sqlite_academic.create_course_section). We therefore
  *update* those instances with the file's per-instructor pass/took rather than
  inserting new ones.
- Program outcome ``plo_number`` is a sequential ordinal; the source label
  (e.g. "AT1", "G1.1") is preserved in ``extras.label``.
- The routine is idempotent: re-running against the same institution reuses
  existing entities instead of duplicating them.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.database import database_service as dbs

# Strip the trailing ".N" from a CLLO id to get its course number
# (e.g. "ASE-103L.1" -> "ASE-103L").
_COURSE_FROM_CLLO = re.compile(r"^(.*)\.\d+$")


class ImportServiceCEIOutcomesMixin:
    """Persist the CEI outcomes-results adapter's parsed entities."""

    stats: Any
    institution_id: str
    _log: Callable[..., None]
    logger: Any

    def _process_cei_outcomes(
        self, parsed_data: Dict[str, List[Dict[str, Any]]], dry_run: bool = False
    ) -> None:
        """Persist parsed CEI outcomes data in dependency order."""
        if dry_run:
            for data_type, records in parsed_data.items():
                self._log(f"DRY RUN: would persist {len(records)} {data_type}")
            return

        program_ids = self._persist_programs(parsed_data.get("programs", []))
        course_ids = self._persist_courses(parsed_data.get("courses", []))
        outcome_ids = self._persist_course_outcomes(
            parsed_data.get("clos", []), course_ids
        )
        plo_ids = self._persist_program_outcomes(
            parsed_data.get("program_outcomes", []), program_ids
        )
        self._persist_users(parsed_data.get("users", []))
        self._persist_terms(parsed_data.get("terms", []))
        offering_ids = self._persist_offerings(
            parsed_data.get("offerings", []), course_ids
        )
        section_ids = self._persist_sections(
            parsed_data.get("sections", []), offering_ids
        )
        self._persist_section_outcomes(
            parsed_data.get("section_outcomes", []), section_ids, outcome_ids
        )
        self._persist_plo_mappings(
            parsed_data.get("plo_mapping_entries", []),
            program_ids,
            plo_ids,
            outcome_ids,
            course_ids,
        )

    # ------------------------------------------------------------------ #
    # Individual entity persistence (each returns a lookup for later steps)
    # ------------------------------------------------------------------ #
    def _persist_programs(self, programs: List[Dict[str, Any]]) -> Dict[str, str]:
        """Create programs; return {short_name: program_id}."""
        lookup = {
            p["short_name"]: p["program_id"]
            for p in dbs.get_programs_by_institution(self.institution_id)
        }
        for program in programs:
            short = program["short_name"]
            if short in lookup:
                self.stats["records_skipped"] += 1
                continue
            program_id = dbs.create_program(
                {
                    "name": program["name"],
                    "short_name": short,
                    "institution_id": self.institution_id,
                }
            )
            if program_id:
                lookup[short] = program_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_courses(self, courses: List[Dict[str, Any]]) -> Dict[str, str]:
        """Create courses; return {course_number: course_id}."""
        lookup: Dict[str, str] = {}
        for course in courses:
            number = course["course_number"]
            existing = dbs.get_course_by_number(number, self.institution_id)
            if existing:
                lookup[number] = existing["course_id"]
                self.stats["records_skipped"] += 1
                continue
            course_id = dbs.create_course(
                {
                    "course_number": number,
                    "course_title": course.get("course_title", number),
                    "institution_id": self.institution_id,
                }
            )
            if course_id:
                lookup[number] = course_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_course_outcomes(
        self, clos: List[Dict[str, Any]], course_ids: Dict[str, str]
    ) -> Dict[str, str]:
        """Create CLOs (program_id=None); return {clo_number: outcome_id}."""
        lookup: Dict[str, str] = {}
        existing_by_course: Dict[str, Dict[str, str]] = {}
        for clo in clos:
            course_id = course_ids.get(clo["course_number"])
            if not course_id:
                continue
            if course_id not in existing_by_course:
                course_outcomes: Dict[str, str] = {}
                for existing in dbs.get_course_outcomes(course_id):
                    existing_id = existing.get("outcome_id") or existing.get("id")
                    if existing_id:
                        course_outcomes[existing["clo_number"]] = str(existing_id)
                existing_by_course[course_id] = course_outcomes
            clo_number = clo["clo_number"]
            if clo_number in existing_by_course[course_id]:
                lookup[clo_number] = existing_by_course[course_id][clo_number]
                self.stats["records_skipped"] += 1
                continue
            outcome_id = dbs.create_course_outcome(
                {
                    "course_id": course_id,
                    "clo_number": clo_number,
                    "description": clo["description"],
                    "program_id": None,
                    "active": True,
                }
            )
            if outcome_id:
                lookup[clo_number] = outcome_id
                existing_by_course[course_id][clo_number] = outcome_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_program_outcomes(
        self, program_outcomes: List[Dict[str, Any]], program_ids: Dict[str, str]
    ) -> Dict[str, str]:
        """Create PLOs; return {f'{short}|{label}': program_outcome_id}."""
        lookup: Dict[str, str] = {}
        existing_by_program: Dict[str, Dict[int, str]] = {}
        for plo in program_outcomes:
            short = plo["program_short_name"]
            program_id = program_ids.get(short)
            if not program_id:
                continue
            if program_id not in existing_by_program:
                existing_by_program[program_id] = {
                    e["plo_number"]: e["id"]
                    for e in dbs.get_program_outcomes(program_id)
                }
            key = f"{short}|{plo['plo_label']}"
            if plo["plo_number"] in existing_by_program[program_id]:
                lookup[key] = existing_by_program[program_id][plo["plo_number"]]
                self.stats["records_skipped"] += 1
                continue
            plo_id = dbs.create_program_outcome(
                {
                    "program_id": program_id,
                    "institution_id": self.institution_id,
                    "plo_number": plo["plo_number"],
                    "description": plo["description"],
                    "label": plo["plo_label"],
                }
            )
            if plo_id:
                lookup[key] = plo_id
                existing_by_program[program_id][plo["plo_number"]] = plo_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_users(self, users: List[Dict[str, Any]]) -> None:
        """Create instructor accounts (demo emails, no login expected)."""
        for user in users:
            if dbs.get_user_by_email(user["email"]):
                self.stats["records_skipped"] += 1
                continue
            user_id = dbs.create_user(
                {
                    "email": user["email"],
                    "first_name": user.get("first_name") or "Instructor",
                    "last_name": user.get("last_name") or user["email"].split("@")[0],
                    "role": "instructor",
                    "institution_id": self.institution_id,
                    "account_status": "active",
                    "email_verified": True,
                }
            )
            if user_id:
                self.stats["records_created"] += 1

    def _persist_terms(self, terms: List[Dict[str, Any]]) -> None:
        for term in terms:
            if dbs.get_term_by_name(term["term_name"], self.institution_id):
                self.stats["records_skipped"] += 1
                continue
            term_id = dbs.create_term(
                {
                    "term_name": term["term_name"],
                    "name": term["name"],
                    "start_date": term.get("start_date"),
                    "end_date": term.get("end_date"),
                    "institution_id": self.institution_id,
                }
            )
            if term_id:
                self.stats["records_created"] += 1

    def _persist_offerings(
        self, offerings: List[Dict[str, Any]], course_ids: Dict[str, str]
    ) -> Dict[Tuple[str, ...], str]:
        """Create offerings (program_id=None); return {(course,term): offering_id}."""
        lookup: Dict[Tuple[str, ...], str] = {}
        for offering in offerings:
            course_id = course_ids.get(offering["course_number"])
            term = dbs.get_term_by_name(offering["term_name"], self.institution_id)
            if not course_id or not term:
                continue
            term_id = term["term_id"]
            key = (offering["course_number"], offering["term_name"])
            existing = dbs.get_course_offering_by_course_and_term(course_id, term_id)
            if existing:
                lookup[key] = existing["offering_id"]
                self.stats["records_skipped"] += 1
                continue
            offering_id = dbs.create_course_offering(
                {
                    "course_id": course_id,
                    "term_id": term_id,
                    "institution_id": self.institution_id,
                }
            )
            if offering_id:
                lookup[key] = offering_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_sections(
        self, sections: List[Dict[str, Any]], offering_ids: Dict[Tuple[str, ...], str]
    ) -> Dict[Tuple[str, ...], str]:
        """Create sections; return {(course,term,instructor_email): section_id}.

        Creating a section auto-instantiates a CourseSectionOutcome per CLO of
        the course (handled in the academic DB layer).
        """
        lookup: Dict[Tuple[str, ...], str] = {}
        for section in sections:
            offering_id = offering_ids.get(
                (section["course_number"], section["term_name"])
            )
            if not offering_id:
                continue
            instructor = dbs.get_user_by_email(section["instructor_email"])
            instructor_id = instructor["user_id"] if instructor else None
            section_id = dbs.create_course_section(
                {
                    "offering_id": offering_id,
                    "section_number": section.get("section_number", "001"),
                    "instructor_id": instructor_id,
                    "status": "approved",
                }
            )
            if section_id:
                lookup[
                    (
                        section["course_number"],
                        section["term_name"],
                        section["instructor_email"],
                    )
                ] = section_id
                self.stats["records_created"] += 1
        return lookup

    def _persist_section_outcomes(
        self,
        section_outcomes: List[Dict[str, Any]],
        section_ids: Dict[Tuple[str, ...], str],
        outcome_ids: Dict[str, str],
    ) -> None:
        """Update auto-created section outcomes with per-instructor pass/took."""
        for measurement in section_outcomes:
            section_id = section_ids.get(
                (
                    measurement["course_number"],
                    measurement["term_name"],
                    measurement["instructor_email"],
                )
            )
            outcome_id = outcome_ids.get(measurement["clo_number"])
            if not section_id or not outcome_id:
                continue
            instance = dbs.get_section_outcome_by_course_outcome_and_section(
                outcome_id, section_id
            )
            if not instance:
                continue
            updated = dbs.update_section_outcome(
                instance["id"],
                {
                    "students_took": measurement["students_took"],
                    "students_passed": measurement["students_passed"],
                    "status": "approved",
                    "approval_status": "approved",
                },
            )
            if updated:
                self.stats["records_updated"] += 1

    def _persist_plo_mappings(
        self,
        entries: List[Dict[str, Any]],
        program_ids: Dict[str, str],
        plo_ids: Dict[str, str],
        outcome_ids: Dict[str, str],
        course_ids: Dict[str, str],
    ) -> None:
        """Build + publish one PLO<->CLO mapping per program, then link courses.

        Program rollups read through the published mapping, so this is what makes
        the program scorecards populate. Course<->program links are derived from
        the same entries (a course belongs to a program if one of its CLOs maps
        to that program's PLOs).
        """
        by_program: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for entry in entries:
            by_program[entry["program_short_name"]].append(entry)

        for short, program_entries in by_program.items():
            program_id = program_ids.get(short)
            if not program_id:
                continue
            draft = dbs.get_or_create_plo_mapping_draft(program_id, None)
            mapping_id = draft["id"]
            linked_courses: set[str] = set()

            for entry in program_entries:
                plo_id = plo_ids.get(f"{short}|{entry['plo_label']}")
                outcome_id = outcome_ids.get(entry["clo_number"])
                if plo_id and outcome_id:
                    try:
                        dbs.add_plo_mapping_entry(mapping_id, plo_id, outcome_id)
                    except Exception:  # noqa: BLE001 - duplicate entry is fine
                        pass

                course_number = self._course_from_clo(entry["clo_number"])
                course_id = course_ids.get(course_number) if course_number else None
                if course_id and course_id not in linked_courses:
                    dbs.add_course_to_program(course_id, program_id)
                    linked_courses.add(course_id)

            try:
                dbs.publish_plo_mapping(
                    mapping_id, "Imported from CEI FY25 outcomes export"
                )
                self.stats["records_created"] += 1
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    "Failed to publish PLO mapping for program %s: %s", short, exc
                )

    @staticmethod
    def _course_from_clo(clo_number: str) -> Optional[str]:
        match = _COURSE_FROM_CLLO.match(clo_number)
        return match.group(1) if match else None
