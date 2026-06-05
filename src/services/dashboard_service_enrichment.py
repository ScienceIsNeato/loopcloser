"""Enrichment mixin for dashboard datasets."""

from __future__ import annotations

import sys
from typing import Any, Callable, Dict, List, Optional, cast

from src.database.database_service import (
    get_course_outcomes,
    get_course_outcomes_by_course_ids,
)
from src.utils.logging_config import get_logger
from src.utils.term_utils import TERM_STATUS_ACTIVE, get_all_term_statuses

logger = get_logger(__name__)


class DashboardServiceEnrichmentMixin:
    logger: Any
    _course_program_ids: Callable[[Dict[str, Any]], List[str]]
    _full_name: Callable[[Dict[str, Any]], str]

    @staticmethod
    def _service_get_course_outcomes() -> Any:
        service_module = sys.modules.get("src.services.dashboard_service")
        return getattr(service_module, "get_course_outcomes", get_course_outcomes)

    @staticmethod
    def _service_get_course_outcomes_by_course_ids() -> Any:
        service_module = sys.modules.get("src.services.dashboard_service")
        return getattr(
            service_module,
            "get_course_outcomes_by_course_ids",
            get_course_outcomes_by_course_ids,
        )

    def _add_course_counts_to_programs(
        self, programs: List[Dict[str, Any]], courses: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        programs_with_counts: List[Dict[str, Any]] = []
        for program in programs:
            program_copy = program.copy()
            program_id = program.get("id", program.get("program_id"))
            course_count = 0
            if program_id:
                for course in courses:
                    if program_id in self._course_program_ids(course):
                        course_count += 1
            program_copy["course_count"] = course_count
            programs_with_counts.append(program_copy)
        return programs_with_counts

    def _enrich_courses_with_clo_data(
        self, courses: List[Dict[str, Any]], load_clos: bool = True
    ) -> List[Dict[str, Any]]:
        enriched_courses: List[Dict[str, Any]] = []

        # Bulk-fetch all CLOs in one query, then assign per course (avoids the
        # N+1 of calling get_course_outcomes once per course on the dashboard).
        clo_map: Dict[str, List[Dict[str, Any]]] = {}
        if load_clos:
            course_ids = [
                str(cid)
                for course in courses
                if (cid := course.get("course_id", course.get("id"))) is not None
            ]
            try:
                clo_map = self._service_get_course_outcomes_by_course_ids()(course_ids)
            except Exception as e:
                self.logger.warning(f"Failed to bulk-fetch CLOs: {e}")
                clo_map = {}

        for course in courses:
            course_copy = course.copy()
            course_id = course.get("course_id", course.get("id"))

            if course_id and load_clos:
                clos = clo_map.get(str(course_id), [])
                course_copy["clo_count"] = len(clos)
                course_copy["clos"] = clos
            else:
                course_copy["clo_count"] = 0
                course_copy["clos"] = []

            enriched_courses.append(course_copy)

        return enriched_courses

    def _enrich_sections_with_course_data(
        self,
        sections: List[Dict[str, Any]],
        course_index: Dict[str, Dict[str, Any]],
        offering_to_course: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        return [
            self._enrich_single_section(
                index, section, course_index, offering_to_course
            )
            for index, section in enumerate(sections)
        ]

    def _enrich_sections_with_instructor_data(
        self,
        sections: List[Dict[str, Any]],
        users: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        instructor_lookup: Dict[str, Dict[str, str]] = {}
        for user in users:
            user_id = user.get("user_id") or user.get("id")
            if user_id:
                instructor_lookup[str(user_id)] = {
                    "name": self._full_name(user) or user.get("email", ""),
                    "email": user.get("email", ""),
                }

        enriched_sections: List[Dict[str, Any]] = []
        for section in sections:
            section_copy = section.copy()
            instructor_id = section.get("instructor_id")
            if instructor_id and str(instructor_id) in instructor_lookup:
                instructor = instructor_lookup[str(instructor_id)]
                section_copy["instructor_name"] = instructor["name"]
                section_copy["instructor_email"] = instructor["email"]
            enriched_sections.append(section_copy)

        return enriched_sections

    def _enrich_terms_with_offering_counts(
        self,
        terms: List[Dict[str, Any]],
        offerings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        offering_counts: Dict[str, int] = {}
        for offering in offerings:
            term_id = offering.get("term_id")
            if term_id:
                term_key = str(term_id)
                offering_counts[term_key] = offering_counts.get(term_key, 0) + 1

        enriched_terms: List[Dict[str, Any]] = []
        for term in terms:
            raw_term_id = term.get("term_id") or term.get("id")
            enriched_term = dict(term)
            term_key = str(raw_term_id) if raw_term_id else ""
            enriched_term["offering_count"] = offering_counts.get(term_key, 0)
            enriched_terms.append(enriched_term)

        return enriched_terms

    def _build_term_section_counts(
        self, offerings: List[Dict[str, Any]], sections: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        offering_term_map: Dict[str, Optional[Any]] = {}
        for offering in offerings:
            offering_id = offering.get("offering_id")
            term_id = offering.get("term_id")
            if offering_id and term_id:
                offering_term_map[str(offering_id)] = term_id

        term_section_counts: Dict[str, int] = {}
        for section in sections:
            offering_id = section.get("offering_id")
            term_id = offering_term_map.get(str(offering_id)) if offering_id else None
            if term_id:
                term_key = str(term_id)
                term_section_counts[term_key] = term_section_counts.get(term_key, 0) + 1

        return term_section_counts

    def _extract_program_ids_from_offering(
        self,
        offering: Dict[str, Any],
        course_lookup: Dict[str, Dict[str, Any]],
    ) -> set[str]:
        program_ids: set[str] = set()
        offering_program_id = offering.get("program_id")
        if offering_program_id:
            program_ids.add(str(offering_program_id))

        course_id = offering.get("course_id")
        course_key = str(course_id) if course_id else None
        if course_key and course_key in course_lookup:
            course = course_lookup[course_key]
            raw_program_ids = course.get("program_ids")
            if isinstance(raw_program_ids, list):
                program_id_values: List[Any] = cast(List[Any], raw_program_ids)
                program_ids.update(
                    str(program_id) for program_id in program_id_values if program_id
                )
            elif isinstance(raw_program_ids, str):
                program_ids.add(raw_program_ids)

            course_program_id = course.get("program_id")
            if course_program_id:
                program_ids.add(str(course_program_id))

        return program_ids

    def _enrich_terms_with_detailed_counts(
        self,
        terms: List[Dict[str, Any]],
        offerings: List[Dict[str, Any]],
        courses: List[Dict[str, Any]],
        sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        course_lookup: Dict[str, Dict[str, Any]] = {}
        for course in courses:
            course_key = course.get("course_id") or course.get("id")
            if course_key:
                course_lookup[str(course_key)] = course

        term_offerings: Dict[str, List[Dict[str, Any]]] = {}
        for offering in offerings:
            term_id = offering.get("term_id") or offering.get("termId")
            if term_id:
                term_key = str(term_id)
                term_offerings.setdefault(term_key, []).append(offering)

        term_section_counts = self._build_term_section_counts(offerings, sections)
        term_statuses = get_all_term_statuses(terms)

        enriched_terms: List[Dict[str, Any]] = []
        for term in terms:
            raw_term_id = term.get("term_id") or term.get("id")
            term_copy = dict(term)
            term_key = str(raw_term_id) if raw_term_id else ""
            term_specific_offerings = term_offerings.get(term_key, [])

            unique_program_ids: set[str] = set()
            unique_course_ids: set[str] = set()
            for offering in term_specific_offerings:
                unique_program_ids.update(
                    self._extract_program_ids_from_offering(offering, course_lookup)
                )
                if offering.get("course_id"):
                    unique_course_ids.add(str(offering["course_id"]))

            term_copy["program_count"] = len(unique_program_ids)
            term_copy["course_count"] = len(unique_course_ids)
            term_copy["offering_count"] = len(term_specific_offerings)
            term_copy["section_count"] = term_section_counts.get(term_key, 0)

            context_status = term_statuses.get(term_key)
            if context_status:
                term_copy["status"] = context_status
                term_copy["is_active"] = context_status == TERM_STATUS_ACTIVE

            enriched_terms.append(term_copy)

        return enriched_terms

    def _enrich_courses_with_section_counts(
        self,
        courses: List[Dict[str, Any]],
        sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        course_section_counts: Dict[str, int] = {}
        for section in sections:
            course_id = section.get("course_id")
            if course_id:
                course_key = str(course_id)
                course_section_counts[course_key] = (
                    course_section_counts.get(course_key, 0) + 1
                )

        enriched_courses: List[Dict[str, Any]] = []
        for course in courses:
            course_copy = course.copy()
            course_id = course.get("course_id") or course.get("id")
            course_id_str = str(course_id) if course_id else ""
            course_copy["section_count"] = course_section_counts.get(course_id_str, 0)
            enriched_courses.append(course_copy)
        return enriched_courses

    def _enrich_offerings_with_section_data(
        self,
        offerings: List[Dict[str, Any]],
        sections: List[Dict[str, Any]],
        courses: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        offering_data = self._build_offering_section_rollup(sections)
        course_lookup: Dict[str, Dict[str, Any]] = {}
        if courses:
            for course in courses:
                course_id = course.get("course_id") or course.get("id")
                if course_id:
                    course_lookup[str(course_id)] = course

        enriched: List[Dict[str, Any]] = []
        for offering in offerings:
            enriched_offering = self._apply_offering_section_rollup(
                offering, offering_data
            )
            course_id = offering.get("course_id")
            course_key = str(course_id) if course_id else None
            if course_key and course_key in course_lookup:
                enriched_offering["program_names"] = course_lookup[course_key].get(
                    "program_names", []
                )
            else:
                enriched_offering["program_names"] = []
            enriched.append(enriched_offering)
        return enriched

    def _build_offering_section_rollup(
        self, sections: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, int]]:
        offering_data: Dict[str, Dict[str, int]] = {}
        for section in sections:
            offering_id = section.get("offering_id")
            if not offering_id:
                continue
            offering_key = str(offering_id)
            entry = offering_data.setdefault(
                offering_key, {"section_count": 0, "total_enrollment": 0}
            )
            entry["section_count"] += 1
            entry["total_enrollment"] += self._safe_int(
                section.get("enrollment"), section.get("section_id")
            )
        return offering_data

    def _apply_offering_section_rollup(
        self,
        offering: Dict[str, Any],
        offering_data: Dict[str, Dict[str, int]],
    ) -> Dict[str, Any]:
        offering_id = offering.get("offering_id") or offering.get("id")
        enriched_offering = dict(offering)
        rollup = offering_data.get(str(offering_id)) if offering_id else None
        enriched_offering["section_count"] = rollup["section_count"] if rollup else 0
        enriched_offering["total_enrollment"] = (
            rollup["total_enrollment"] if rollup else 0
        )
        return enriched_offering

    def _safe_int(self, value: Any, context_id: Any = None) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (ValueError, TypeError):
            self.logger.warning(
                f"Invalid enrollment value for section {context_id}: {value}"
            )
            return 0

    def _enrich_single_section(
        self,
        index: int,
        section: Dict[str, Any],
        course_index: Dict[str, Dict[str, Any]],
        offering_to_course: Dict[str, str],
    ) -> Dict[str, Any]:
        section_copy = section.copy()
        offering_id = section.get("offering_id")
        course_id = offering_to_course.get(str(offering_id)) if offering_id else None

        if course_id and course_id in course_index:
            course = course_index[course_id]
            section_copy["course_number"] = course.get("course_number", "")
            section_copy["course_title"] = course.get("course_title", "")
            section_copy["course_id"] = course_id
            return section_copy

        self._log_enrichment_failure(
            index, offering_id, course_id, offering_to_course, course_index
        )
        section_copy.setdefault("course_number", "")
        section_copy.setdefault("course_title", "")
        return section_copy

    def _log_enrichment_failure(
        self,
        index: int,
        offering_id: Optional[str],
        course_id: Optional[str],
        offering_to_course: Dict[str, str],
        course_index: Dict[str, Dict[str, Any]],
    ) -> None:
        if index >= 3:
            return

        in_offering_map = (
            str(offering_id) in offering_to_course if offering_id else False
        )
        in_course_index = course_id in course_index if course_id else False
        self.logger.warning(
            f"[SECTION ENRICHMENT] Failed to enrich section {index}: "
            f"offering_id={offering_id}, course_id={course_id}, "
            f"in_offering_map={in_offering_map}, in_course_index={in_course_index}"
        )

    def _enrich_courses_with_program_names(
        self,
        courses: List[Dict[str, Any]],
        program_index: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        enriched_courses: List[Dict[str, Any]] = []
        for course in courses:
            course_copy = course.copy()
            program_names: List[str] = []
            for program_id in self._course_program_ids(course):
                if program_id in program_index:
                    program_names.append(
                        program_index[program_id].get("name") or "Unknown Program"
                    )
            course_copy["program_names"] = program_names
            enriched_courses.append(course_copy)
        return enriched_courses
