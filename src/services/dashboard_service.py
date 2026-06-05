"""Dashboard data aggregation service."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from src.database.database_service import (  # noqa: F401  re-export for enrichment mixin + test patches
    get_active_terms,
    get_all_course_offerings,
    get_all_courses,
    get_all_institutions,
    get_all_instructors,
    get_all_sections,
    get_all_terms,
    get_all_users,
    get_course_outcomes,
    get_course_outcomes_by_course_ids,
    get_courses_by_program,
    get_institution_by_id,
    get_programs_by_institution,
)
from src.services.dashboard_service_enrichment import DashboardServiceEnrichmentMixin
from src.services.dashboard_service_support import DashboardServiceSupportMixin
from src.utils.logging_config import get_logger
from src.utils.time_utils import get_current_time


class DashboardServiceError(Exception):
    """Raised when dashboard data cannot be generated."""


class DashboardService(DashboardServiceEnrichmentMixin, DashboardServiceSupportMixin):
    """Aggregate dashboard metrics and datasets based on user scope."""

    def __init__(self) -> None:
        self.logger = get_logger(__name__)

    def get_dashboard_data(self, user: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Return dashboard data tailored to the current user's scope."""
        if not user:
            raise DashboardServiceError("Authenticated user information required")

        role = user.get("role")
        if role == "site_admin":
            payload = self._get_site_admin_data()
            scope = "system_wide"
        elif role == "program_admin":
            payload = self._get_program_admin_data(
                user.get("institution_id"), user.get("program_ids", [])
            )
            scope = "program"
        elif role == "instructor":
            payload = self._get_instructor_data(
                user.get("institution_id"),
                user.get("user_id"),
                user.get("program_ids", []),
            )
            scope = "instructor"
        elif role == "institution_admin":
            # Explicit handling for institution admins
            payload = self._get_institution_admin_data(user.get("institution_id"))
            scope = "institution"
        else:
            # Unknown roles are not allowed - fail securely
            raise ValueError(
                f"Unknown user role: {role}. Valid roles: site_admin, institution_admin, program_admin, instructor"
            )

        current_time = get_current_time()
        metadata = {
            "user_role": role,
            "data_scope": scope,
            "last_updated": current_time.isoformat(),
            "reference_date": current_time.isoformat(),  # For frontend status calculations
        }
        payload.setdefault("metadata", metadata)
        payload["metadata"].update(metadata)
        return payload

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _get_site_admin_data(self) -> Dict[str, Any]:
        institutions = get_all_institutions() or []

        aggregated_institutions: List[Dict[str, Any]] = []
        all_programs: List[Dict[str, Any]] = []
        all_courses: List[Dict[str, Any]] = []
        all_users: List[Dict[str, Any]] = []
        all_instructors: List[Dict[str, Any]] = []
        all_sections: List[Dict[str, Any]] = []
        all_terms: List[Dict[str, Any]] = []
        system_activity: List[Dict[str, Any]] = []

        for institution in institutions:
            inst_id = institution.get("institution_id")
            inst_name = institution.get("name", "Unknown Institution")
            if not inst_id:
                continue

            programs = get_programs_by_institution(inst_id) or []
            courses = get_all_courses(inst_id) or []
            users = get_all_users(inst_id) or []
            instructors = get_all_instructors(inst_id) or []
            sections = get_all_sections(inst_id) or []
            terms = get_active_terms(inst_id) or []

            aggregated_institutions.append(
                {
                    "institution_id": inst_id,
                    "name": inst_name,
                    "user_count": len(users),
                    "program_count": len(programs),
                    "course_count": len(courses),
                }
            )

            # Add course counts to programs
            programs_with_counts = self._add_course_counts_to_programs(
                programs, courses
            )
            all_programs.extend(
                self._with_institution(programs_with_counts, inst_id, inst_name)
            )
            # Enrich courses with CLO data before adding to all_courses
            courses_with_clo = self._enrich_courses_with_clo_data(
                courses, load_clos=False
            )
            all_courses.extend(
                self._with_institution(courses_with_clo, inst_id, inst_name)
            )
            all_users.extend(self._with_institution(users, inst_id, inst_name))
            all_instructors.extend(
                self._with_institution(instructors, inst_id, inst_name)
            )
            all_sections.extend(self._with_institution(sections, inst_id, inst_name))
            all_terms.extend(self._with_institution(terms, inst_id, inst_name))

            system_activity.extend(
                self._build_activity_feed(inst_name, users, courses, sections)
            )

        summary = {
            "institutions": len(aggregated_institutions),
            "programs": len(all_programs),
            "courses": len(all_courses),
            "users": len(all_users),
            "faculty": len(
                {i.get("user_id") for i in all_instructors if i.get("user_id")}
            ),
            "sections": len(all_sections),
        }

        return {
            "summary": summary,
            "institutions": aggregated_institutions,
            "programs": all_programs,
            "courses": all_courses,
            "users": all_users,
            "instructors": all_instructors,
            "sections": all_sections,
            "terms": all_terms,
            "activity": system_activity[:25],
        }

    def _fetch_institution_raw_data(self, institution_id: str) -> Dict[str, Any]:
        """Fetch all raw data for an institution from database."""
        institution = get_institution_by_id(institution_id) or {}
        return {
            "institution": institution,
            "institution_name": institution.get("name"),
            "programs": get_programs_by_institution(institution_id) or [],
            "courses": get_all_courses(institution_id) or [],
            "users": get_all_users(institution_id) or [],
            "instructors": get_all_instructors(institution_id) or [],
            "sections": get_all_sections(institution_id) or [],
            "offerings": get_all_course_offerings(institution_id) or [],
            "terms": get_all_terms(institution_id) or [],
        }

    def _collect_clos_from_courses(
        self,
        courses: List[Dict[str, Any]],
        program_index: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Collect all CLOs from courses, enriching them with course metadata."""
        all_clos: List[Dict[str, Any]] = []
        program_index = program_index or {}

        for course in courses:
            # Resolve program name from course's program_ids
            program_name: Optional[str] = None
            program_ids = self._course_program_ids(course)
            if program_ids:
                # Use first associated program for display context
                pid = program_ids[0]
                program = program_index.get(pid)
                if program:
                    program_name = program.get("name")

            for clo in course.get("clos", []):
                clo_copy = dict(clo)
                clo_copy["course_number"] = course.get("course_number", "")
                clo_copy["course_title"] = course.get("course_title", "")
                if program_name:
                    clo_copy["program_name"] = program_name
                all_clos.append(clo_copy)
        return all_clos

    def _build_offering_to_course_mapping(
        self, offerings: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """Create offering_id -> course_id mapping."""
        offering_to_course: Dict[str, str] = {}
        for offering in offerings:
            offering_id = offering.get("offering_id") or offering.get("id")
            course_id = offering.get("course_id")
            if offering_id and course_id:
                offering_to_course[str(offering_id)] = str(course_id)
        return offering_to_course

    def _build_institution_summary(
        self,
        programs: List[Dict[str, Any]],
        courses: List[Dict[str, Any]],
        users: List[Dict[str, Any]],
        faculty: List[Dict[str, Any]],
        sections: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """Build summary statistics for institution."""
        return {
            "institutions": 1,
            "programs": len(programs),
            "courses": len(courses),
            "users": len(users),
            "faculty": len(faculty),
            "sections": len(sections),
            "students": self._total_enrollment(sections),
        }

    def _get_institution_admin_data(
        self, institution_id: Optional[str]
    ) -> Dict[str, Any]:
        if not institution_id:
            raise DashboardServiceError(
                "Institution context required for admin dashboard"
            )

        # Fetch all raw data
        raw = self._fetch_institution_raw_data(institution_id)
        institution_name = raw["institution_name"]

        # Enrich courses with CLO data
        courses = self._enrich_courses_with_clo_data(raw["courses"], load_clos=True)

        # Build indexes and mappings
        # Create program_index first so it can be used for CLO enrichment and program name resolution
        program_index: Dict[str, Dict[str, Any]] = {
            pid: p
            for p in raw["programs"]
            if (pid := self._get_program_id(p)) is not None
        }

        # Enrich courses with program names
        courses = self._enrich_courses_with_program_names(courses, program_index)

        # Collect CLOs with program context
        all_clos = self._collect_clos_from_courses(courses, program_index)

        course_index = self._index_by_keys(courses, ["course_id", "id"])
        faculty = self._build_faculty_directory(raw["users"], raw["instructors"])
        offering_to_course = self._build_offering_to_course_mapping(raw["offerings"])

        # Enrich sections, terms, and offerings
        sections = self._enrich_sections_with_course_data(
            raw["sections"], course_index, offering_to_course
        )
        sections = self._enrich_sections_with_instructor_data(sections, raw["users"])

        # Enrich courses with section counts (new requirement)
        courses = self._enrich_courses_with_section_counts(courses, sections)

        # Enrich terms with detailed counts (new requirement)
        terms = self._enrich_terms_with_detailed_counts(
            raw["terms"], raw["offerings"], courses, sections
        )

        offerings = self._enrich_offerings_with_section_data(
            raw["offerings"], sections, courses
        )

        # Build metrics and aggregations
        program_metrics = self._build_program_metrics(
            raw["programs"], courses, sections, faculty
        )
        faculty_assignments = self._build_faculty_assignments(
            faculty, program_metrics, course_index, sections
        )
        summary = self._build_institution_summary(
            raw["programs"], courses, raw["users"], faculty, sections
        )

        # Build enriched result
        enriched_programs = [
            self._annotate_program(program_index, m) for m in program_metrics
        ]

        enriched: Dict[str, Any] = {
            "programs": self._with_institution(
                enriched_programs, institution_id, institution_name
            ),
            "courses": self._with_institution(
                courses, institution_id, institution_name
            ),
            "users": self._with_institution(
                raw["users"], institution_id, institution_name
            ),
            "instructors": self._with_institution(
                raw["instructors"], institution_id, institution_name
            ),
            "sections": self._with_institution(
                sections, institution_id, institution_name
            ),
            "offerings": self._with_institution(
                offerings, institution_id, institution_name
            ),
            "terms": self._with_institution(terms, institution_id, institution_name),
            "clos": self._with_institution(all_clos, institution_id, institution_name),
            "faculty": faculty,
            "faculty_assignments": faculty_assignments,
            "program_overview": program_metrics,
        }
        enriched["summary"] = summary
        enriched["institutions"] = [
            {
                "institution_id": institution_id,
                "name": institution_name,
                "user_count": len(raw["users"]),
                "program_count": len(raw["programs"]),
                "course_count": len(courses),
                "faculty_count": len(faculty),
                "section_count": len(sections),
                "student_count": summary["students"],
            }
        ]
        return enriched

    def _get_program_admin_data(
        self, institution_id: Optional[str], program_ids: List[str]
    ) -> Dict[str, Any]:
        if not institution_id:
            raise DashboardServiceError(
                "Institution context required for program admins"
            )

        # Get scoped programs for the admin
        scoped_programs = self._get_scoped_programs(institution_id, program_ids)

        # Process courses across all programs
        courses, courses_by_program = self._process_admin_program_courses(
            scoped_programs, institution_id
        )

        # Get sections and faculty data
        scoped_sections, scoped_faculty = self._get_sections_and_faculty(
            institution_id, courses, program_ids
        )

        # Build metrics and summary data
        program_metrics: List[Dict[str, Any]] = self._build_program_metrics(
            scoped_programs,
            courses,
            scoped_sections,
            scoped_faculty,
        )

        # Build final dashboard response
        return self._build_program_admin_response(
            institution_id,
            scoped_programs,
            courses,
            scoped_sections,
            scoped_faculty,
            program_metrics,
            courses_by_program,
            program_ids,
        )

    def _get_scoped_programs(
        self, institution_id: str, program_ids: List[str]
    ) -> List[Dict[str, Any]]:
        """Get programs scoped to the admin's access."""
        program_ids = program_ids or []
        available_programs = get_programs_by_institution(institution_id) or []
        program_lookup: Dict[str, Dict[str, Any]] = {}
        for program in available_programs:
            pid = self._get_program_id(program)
            if pid:
                program_lookup[pid] = program
        return [program_lookup[pid] for pid in program_ids if pid in program_lookup]

    def _process_admin_program_courses(
        self, scoped_programs: List[Dict[str, Any]], institution_id: str
    ) -> tuple[list[Dict[str, Any]], dict[str, list[Dict[str, Any]]]]:
        """Process courses across all programs, handling deduplication."""
        courses_dict: Dict[str, Dict[str, Any]] = (
            {}
        )  # Use dict to deduplicate by course_id
        courses_by_program: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

        for program in scoped_programs:
            pid = self._get_program_id(program)
            if not pid:
                continue
            program_courses = get_courses_by_program(pid) or []

            for course in program_courses:
                enriched = self._with_program([course], program, institution_id)[0]
                course_id = self._get_course_id(enriched)

                if course_id:
                    # If course already exists, merge program_ids
                    if course_id in courses_dict:
                        self._merge_course_program_ids(
                            courses_dict[course_id], enriched
                        )
                    else:
                        courses_dict[course_id] = enriched

                if pid:
                    courses_by_program[pid].append(enriched)

        courses = list(courses_dict.values())  # Convert back to list

        # Enrich all courses with CLO data
        courses = self._enrich_courses_with_clo_data(courses, load_clos=False)

        # Update courses_by_program with enriched data
        courses_by_program = self._rebuild_courses_by_program(courses, scoped_programs)

        return courses, courses_by_program

    def _merge_course_program_ids(
        self, existing_course: Dict[str, Any], new_course: Dict[str, Any]
    ) -> None:
        """Merge program IDs from new course into existing course."""
        existing_program_ids = set(existing_course.get("program_ids", []))
        new_program_ids = set(new_course.get("program_ids", []))
        existing_course["program_ids"] = list(existing_program_ids | new_program_ids)

    def _rebuild_courses_by_program(
        self, courses: List[Dict[str, Any]], scoped_programs: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Rebuild courses_by_program mapping with enriched course data."""
        courses_by_program: defaultdict[str, List[Dict[str, Any]]] = defaultdict(list)
        for course in courses:
            for program in scoped_programs:
                pid = self._get_program_id(program)
                if pid and pid in self._course_program_ids(course):
                    courses_by_program[pid].append(course)
        return dict(courses_by_program)

    def _get_sections_and_faculty(
        self, institution_id: str, courses: List[Dict[str, Any]], program_ids: List[str]
    ) -> tuple[list[Dict[str, Any]], list[Dict[str, Any]]]:
        """Get sections and faculty data scoped to the programs."""
        # Get scoped sections
        all_sections = get_all_sections(institution_id) or []
        course_index = self._index_by_keys(courses, ["course_id", "id"])
        scoped_sections = [
            section
            for section in all_sections
            if self._matches_course(section, course_index)
        ]

        # Get scoped faculty
        users = get_all_users(institution_id) or []
        instructors = get_all_instructors(institution_id) or []
        faculty = self._build_faculty_directory(users, instructors)
        scoped_faculty = [
            member
            for member in faculty
            if set(member.get("program_ids") or []).intersection(program_ids)
        ]

        return scoped_sections, scoped_faculty

    def _build_program_admin_response(
        self,
        institution_id: str,
        scoped_programs: List[Dict[str, Any]],
        courses: List[Dict[str, Any]],
        scoped_sections: List[Dict[str, Any]],
        scoped_faculty: List[Dict[str, Any]],
        program_metrics: List[Dict[str, Any]],
        courses_by_program: Dict[str, List[Dict[str, Any]]],
        program_ids: List[str],
    ) -> Dict[str, Any]:
        """Build the final program admin dashboard response."""
        users = get_all_users(institution_id) or []

        summary = {
            "institutions": 1,
            "programs": len(scoped_programs),
            "courses": len(courses),
            "users": len(users),
            "faculty": len(scoped_faculty),
            "sections": len(scoped_sections),
            "students": self._total_enrollment(scoped_sections),
        }

        return {
            "summary": summary,
            "institutions": [
                {
                    "institution_id": institution_id,
                    "name": None,
                    "program_count": len(scoped_programs),
                    "course_count": len(courses),
                    "user_count": len(users),
                    "faculty_count": len(scoped_faculty),
                    "section_count": len(scoped_sections),
                    "student_count": summary["students"],
                }
            ],
            "programs": self._with_institution(scoped_programs, institution_id),
            "courses": courses,
            "users": self._with_institution(users, institution_id),
            "instructors": scoped_faculty,
            "sections": self._with_institution(scoped_sections, institution_id),
            "terms": self._with_institution(
                get_active_terms(institution_id) or [], institution_id
            ),
            "program_overview": program_metrics,
            "faculty_assignments": self._build_faculty_assignments(
                scoped_faculty,
                program_metrics,
                self._index_by_keys(courses, ["course_id", "id"]),
                scoped_sections,
            ),
            "courses_by_program": {
                pid: list(courses_by_program.get(pid, [])) for pid in program_ids
            },
        }

    def _get_instructor_data(
        self,
        institution_id: Optional[str],
        user_id: Optional[str],
        program_ids: List[str],
    ) -> Dict[str, Any]:
        if not institution_id or not user_id:
            raise DashboardServiceError(
                "Instructor dashboard requires user and institution context"
            )

        program_ids = program_ids or []
        programs = get_programs_by_institution(institution_id) or []
        program_lookup = {
            self._get_program_id(program): program for program in programs
        }
        sections = [
            section
            for section in get_all_sections(institution_id) or []
            if section.get("instructor_id") == user_id
        ]

        courses_lookup = self._index_by_keys(
            get_all_courses(institution_id) or [], ["course_id", "id"]
        )
        course_ids: set[str] = {
            str(section["course_id"])
            for section in sections
            if section.get("course_id") in courses_lookup
        }

        courses: List[Dict[str, Any]] = []
        for cid in course_ids:
            course = courses_lookup[cid]
            program = self._resolve_program_from_course(
                course, program_lookup, program_ids
            )
            courses.append(self._with_program([course], program, institution_id)[0])

        # Enrich courses with CLO data for progress calculation
        enriched_courses = self._enrich_courses_with_clo_data(courses, load_clos=True)

        program_summaries = self._build_instructor_program_summary(
            program_lookup, enriched_courses
        )

        teaching_assignments = self._build_teaching_assignments(
            enriched_courses, sections, courses_lookup
        )
        assessment_tasks = self._build_assessment_tasks(sections, courses_lookup)

        summary = {
            "institutions": 1,
            "programs": len(program_summaries),
            "courses": len(courses),
            "users": 1,
            "sections": len(sections),
            "students": self._total_enrollment(sections),
        }

        return {
            "summary": summary,
            "institutions": [
                {
                    "institution_id": institution_id,
                    "name": None,
                    "program_count": len(program_summaries),
                    "course_count": len(courses),
                    "user_count": 1,
                    "section_count": len(sections),
                    "student_count": summary["students"],
                }
            ],
            "programs": program_summaries,
            "courses": courses,
            "users": [],
            "instructors": [],
            "sections": self._with_institution(sections, institution_id),
            "terms": self._with_institution(
                get_active_terms(institution_id) or [], institution_id
            ),
            "teaching_assignments": teaching_assignments,
            "assessment_tasks": assessment_tasks,
        }


def build_dashboard_service() -> DashboardService:
    """Factory for dependency injection in tests."""
    return DashboardService()
