"""Database service facade backed by SQLite implementation."""

from __future__ import annotations

import logging
from contextlib import AbstractContextManager, nullcontext
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple, cast

from src.database.database_factory import get_database_service, refresh_database_service
from src.database.database_interface import DatabaseInterface
from src.models.models_sql import Base
from src.utils.constants import (
    COURSE_OFFERINGS_COLLECTION,
    COURSE_OUTCOMES_COLLECTION,
    COURSE_SECTIONS_COLLECTION,
    COURSES_COLLECTION,
    DB_CLIENT_NOT_AVAILABLE_MSG,
    DEFAULT_INSTITUTION_TIMEZONE,
    INSTITUTIONS_COLLECTION,
    TERMS_COLLECTION,
    USERS_COLLECTION,
)
from src.utils.term_utils import TERM_STATUS_ACTIVE, get_term_status

logger = logging.getLogger(__name__)

# Initialize database service singleton
_db_service = get_database_service()

# Database service alias for backwards compatibility
db = _db_service


def refresh_connection() -> DatabaseInterface:
    """Reinitialize the database service (primarily for tests)."""
    global _db_service, db
    _db_service = refresh_database_service()
    db = _db_service
    return _db_service


def reset_database() -> bool:
    """Drop and recreate all tables for a clean database state."""
    sql_backend = getattr(cast(Any, _db_service), "sql", None)
    if sql_backend is not None:
        engine = sql_backend.engine
        Base.metadata.drop_all(engine)
        Base.metadata.create_all(engine)
        return True
    logger.error("[DB Service] reset_database unsupported for current backend")
    return False


def close_connection() -> None:
    """Close the underlying database connection."""
    sql_backend = getattr(cast(Any, _db_service), "sql", None)
    if sql_backend is not None:
        sql_backend.close()


def db_operation_timeout() -> AbstractContextManager[Any]:
    """
    Legacy no-op helper retained for API compatibility.

    Returns a null context manager (does nothing).
    This exists to avoid breaking existing code that calls this function,
    but the timeout functionality is handled internally by database implementations.
    """
    return nullcontext()


def check_db_connection() -> bool:
    """Simple connectivity check for the active database service."""
    try:
        _db_service.get_all_institutions()
        return True
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("[DB Service] Database connection check failed: %s", exc)
        return False


def sanitize_for_logging(value: Any, max_length: int = 100) -> str:
    """Sanitize user input for safe logging to prevent log injection attacks."""
    if value is None:
        return "None"
    text = str(value)[:max_length]
    sanitized = (
        text.replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\x00", "\\x00")
        .replace("\x1b", "\\x1b")
    )
    return "".join(
        char if ord(char) >= 32 or char == "\t" else f"\\x{ord(char):02x}"
        for char in sanitized
    )


def _with_term_status(term: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Attach computed status metadata to a term record."""
    if not term:
        return None

    enriched = deepcopy(term)
    status = get_term_status(enriched.get("start_date"), enriched.get("end_date"))
    enriched["status"] = status
    enriched["is_active"] = status == TERM_STATUS_ACTIVE
    return enriched


def _with_term_status_list(
    terms: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Vectorized helper for term lists."""
    if not terms:
        return []
    return [t for t in (_with_term_status(term) for term in terms) if t]


# ---------------------------------------------------------------------------
# Institution operations
# ---------------------------------------------------------------------------


def create_institution(institution_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_institution(institution_data)


def get_institution_by_id(institution_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_institution_by_id(institution_id)


def get_all_institutions() -> List[Dict[str, Any]]:
    return _db_service.get_all_institutions()


def create_default_mocku_institution() -> Optional[str]:
    return _db_service.create_default_mocku_institution()


def create_new_institution(
    institution_data: Dict[str, Any], admin_user_data: Dict[str, Any]
) -> Optional[Tuple[str, str]]:
    return _db_service.create_new_institution(institution_data, admin_user_data)


def create_new_institution_simple(
    name: str, short_name: str, active: bool = True
) -> Optional[str]:
    """Create a new institution without creating an admin user (site admin workflow)"""
    return _db_service.create_new_institution_simple(name, short_name, active)


def get_institution_instructor_count(institution_id: str) -> int:
    return _db_service.get_institution_instructor_count(institution_id)


def get_institution_by_short_name(short_name: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_institution_by_short_name(short_name)


def update_institution(institution_id: str, institution_data: Dict[str, Any]) -> bool:
    return _db_service.update_institution(institution_id, institution_data)


def delete_institution(institution_id: str) -> bool:
    return _db_service.delete_institution(institution_id)


# ---------------------------------------------------------------------------
# User operations
# ---------------------------------------------------------------------------


def create_user(  # noqa: ambiguity-mine - service facade intentionally mirrors storage verb
    user_data: Dict[str, Any],
) -> Optional[str]:
    return _db_service.create_user(user_data)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_user_by_email(email)


def get_user_by_reset_token(reset_token: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_user_by_reset_token(reset_token)


def get_all_users(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_all_users(institution_id)


def get_users_by_role(role: str) -> List[Dict[str, Any]]:
    return _db_service.get_users_by_role(role)


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_user_by_id(user_id)


def update_user(user_id: str, user_data: Dict[str, Any]) -> bool:
    return _db_service.update_user(user_id, user_data)


def update_user_active_status(user_id: str, active_user: bool) -> bool:
    return _db_service.update_user_active_status(user_id, active_user)


def calculate_and_update_active_users(institution_id: str) -> int:
    return _db_service.calculate_and_update_active_users(institution_id)


def update_user_extended(user_id: str, update_data: Dict[str, Any]) -> bool:
    return _db_service.update_user_extended(user_id, update_data)


def get_user_by_verification_token(token: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_user_by_verification_token(token)


def update_user_profile(user_id: str, profile_data: Dict[str, Any]) -> bool:
    return _db_service.update_user_profile(user_id, profile_data)


def update_user_role(
    user_id: str, new_role: str, program_ids: Optional[List[str]] = None
) -> bool:
    return _db_service.update_user_role(user_id, new_role, program_ids)


def deactivate_user(user_id: str) -> bool:
    return _db_service.deactivate_user(user_id)


def delete_user(user_id: str) -> bool:
    return _db_service.delete_user(user_id)


# ---------------------------------------------------------------------------
# Audit log operations
# ---------------------------------------------------------------------------


def create_audit_log(audit_data: Dict[str, Any]) -> bool:
    return _db_service.create_audit_log(audit_data)


def get_audit_logs_by_entity(
    entity_type: str, entity_id: str, limit: int = 50
) -> List[Dict[str, Any]]:
    return _db_service.get_audit_logs_by_entity(entity_type, entity_id, limit)


def get_audit_logs_by_user(
    user_id: str,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    return _db_service.get_audit_logs_by_user(user_id, start_date, end_date, limit)


def get_recent_audit_logs(
    institution_id: Optional[str] = None, limit: int = 50
) -> List[Dict[str, Any]]:
    return _db_service.get_recent_audit_logs(institution_id, limit)


def get_audit_logs_filtered(
    start_date: Any,
    end_date: Any,
    entity_type: Optional[str] = None,
    user_id: Optional[str] = None,
    institution_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    return _db_service.get_audit_logs_filtered(
        start_date, end_date, entity_type, user_id, institution_id
    )


# ---------------------------------------------------------------------------
# Course operations
# ---------------------------------------------------------------------------


def create_course(course_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_course(course_data)


def update_course(course_id: str, course_data: Dict[str, Any]) -> bool:
    return _db_service.update_course(course_id, course_data)


def update_course_programs(course_id: str, program_ids: List[str]) -> bool:
    return _db_service.update_course_programs(course_id, program_ids)


def delete_course(course_id: str) -> bool:
    return _db_service.delete_course(course_id)


def get_course_by_number(
    course_number: str, institution_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    return _db_service.get_course_by_number(course_number, institution_id)


def get_courses_by_department(
    institution_id: str, department: str
) -> List[Dict[str, Any]]:
    return _db_service.get_courses_by_department(institution_id, department)


def create_course_outcome(outcome_data: Dict[str, Any]) -> str:
    return _db_service.create_course_outcome(outcome_data)


def update_course_outcome(outcome_id: str, outcome_data: Dict[str, Any]) -> bool:
    return _db_service.update_course_outcome(outcome_id, outcome_data)


def update_outcome_assessment(
    outcome_id: str,
    students_took: Optional[int] = None,
    students_passed: Optional[int] = None,
    assessment_tool: Optional[str] = None,
) -> bool:
    """Update outcome assessment data (corrected field names from demo feedback)."""
    return _db_service.update_outcome_assessment(
        outcome_id, students_took, students_passed, assessment_tool
    )


def delete_course_outcome(outcome_id: str) -> bool:
    return _db_service.delete_course_outcome(outcome_id)


def get_course_outcomes(course_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_course_outcomes(course_id)


def get_course_outcomes_by_course_ids(
    course_ids: List[str],
) -> Dict[str, List[Dict[str, Any]]]:
    return _db_service.get_course_outcomes_by_course_ids(course_ids)


def get_course_outcome(outcome_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_course_outcome(outcome_id)


def get_section_outcome(section_outcome_id: str) -> Optional[Dict[str, Any]]:
    """Get a section outcome by ID."""
    return _db_service.get_section_outcome(section_outcome_id)


def get_section_outcomes_by_section(section_id: str) -> List[Dict[str, Any]]:
    """Get all section outcomes for a section."""
    return _db_service.get_section_outcomes_by_section(section_id)


def get_section_outcomes_by_outcome(outcome_id: str) -> List[Dict[str, Any]]:
    """Get all section outcomes for a course outcome (template)."""
    return _db_service.get_section_outcomes_by_outcome(outcome_id)


def update_section_outcome(section_outcome_id: str, updates: Dict[str, Any]) -> bool:
    """Update a section outcome."""
    return _db_service.update_section_outcome(section_outcome_id, updates)


def get_course_by_id(course_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_course_by_id(course_id)


def _generate_unique_course_number(base_number: str, institution_id: str) -> str:
    """
    Generate a duplicate-friendly course number (e.g., BIOL-201-V2, -V3, etc.)
    that does not collide with existing records for the institution.
    """
    normalized = (base_number or "COURSE").strip().upper()
    suffix_index = 2
    candidate = f"{normalized}-V{suffix_index}"

    while get_course_by_number(candidate, institution_id):
        suffix_index += 1
        candidate = f"{normalized}-V{suffix_index}"

    return candidate


def duplicate_course_record(
    source_course: Dict[str, Any],
    overrides: Optional[Dict[str, Any]] = None,
    duplicate_programs: bool = True,
) -> Optional[str]:
    """
    Clone an existing course (and optionally program assignments) for demo workflows.
    """
    if not source_course:
        return None

    institution_id = _get_institution_id_or_log(source_course)
    if not institution_id:
        return None

    overrides = overrides or {}
    sanitized_overrides, program_ids_override = _sanitize_course_duplication_overrides(
        overrides
    )

    base_number = sanitized_overrides.get("course_number") or source_course.get(
        "course_number"
    )
    if not base_number:
        logger.error(
            "[DB Service] Source course missing course_number; cannot duplicate"
        )
        return None

    sanitized_overrides.setdefault(
        "course_number", _generate_unique_course_number(base_number, institution_id)
    )

    new_course_data = _build_course_duplication_payload(
        source_course, institution_id, sanitized_overrides
    )
    new_course_data["program_ids"] = _resolve_course_duplication_program_ids(
        source_course, program_ids_override, duplicate_programs
    )

    return create_course(new_course_data)


def _get_institution_id_or_log(source_course: Dict[str, Any]) -> Optional[str]:
    institution_id = source_course.get("institution_id")
    if not institution_id:
        logger.error("[DB Service] Cannot duplicate course without institution context")
    return institution_id


def _sanitize_course_duplication_overrides(
    overrides: Dict[str, Any],
) -> tuple[Dict[str, Any], Optional[Any]]:
    allowed_override_fields = {
        "course_number",
        "course_title",
        "department",
        "credit_hours",
        "active",
    }
    sanitized_overrides = {
        key: value
        for key, value in overrides.items()
        if key in allowed_override_fields and value is not None
    }
    program_ids_override = (
        overrides.get("program_ids") if "program_ids" in overrides else None
    )
    return sanitized_overrides, program_ids_override


def _build_course_duplication_payload(
    source_course: Dict[str, Any],
    institution_id: str,
    sanitized_overrides: Dict[str, Any],
) -> Dict[str, Any]:
    new_course_data: Dict[str, Any] = {
        "course_number": source_course.get("course_number"),
        "course_title": source_course.get("course_title"),
        "department": source_course.get("department"),
        "credit_hours": source_course.get("credit_hours", 3),
        "institution_id": institution_id,
        "active": source_course.get("active", True),
        "extras": deepcopy(source_course.get("extras") or {}),
    }

    new_course_data.update(sanitized_overrides)

    extras = cast(Dict[str, Any], new_course_data.get("extras") or {})
    extras["duplicated_from_course_id"] = source_course.get(
        "course_id"
    ) or source_course.get("id")
    extras["duplicated_from_course_number"] = source_course.get("course_number")
    new_course_data["extras"] = extras
    return new_course_data


def _resolve_course_duplication_program_ids(
    source_course: Dict[str, Any],
    program_ids_override: Optional[Any],
    duplicate_programs: bool,
) -> Any:
    if program_ids_override is not None:
        return program_ids_override
    if duplicate_programs:
        return source_course.get("program_ids") or []
    return []


def get_all_courses(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_all_courses(institution_id)


def get_all_instructors(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_all_instructors(institution_id)


def get_all_sections(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_all_sections(institution_id)


def get_section_by_id(section_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_section_by_id(section_id)


def create_course_offering(offering_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_course_offering(offering_data)


def update_course_offering(offering_id: str, offering_data: Dict[str, Any]) -> bool:
    return _db_service.update_course_offering(offering_id, offering_data)


def delete_course_offering(offering_id: str) -> bool:
    return _db_service.delete_course_offering(offering_id)


def get_course_offering(offering_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_course_offering(offering_id)


def get_course_offering_by_course_and_term(
    course_id: str, term_id: str
) -> Optional[Dict[str, Any]]:
    return _db_service.get_course_offering_by_course_and_term(course_id, term_id)


def get_all_course_offerings(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_all_course_offerings(institution_id)


# ---------------------------------------------------------------------------
# Term operations
# ---------------------------------------------------------------------------


def create_term(term_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_term(term_data)


def update_term(term_id: str, term_data: Dict[str, Any]) -> bool:
    return _db_service.update_term(term_id, term_data)


def delete_term(term_id: str) -> bool:
    return _db_service.delete_term(term_id)


def get_term_by_name(
    name: str, institution_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    return _with_term_status(_db_service.get_term_by_name(name, institution_id))


def get_active_terms(institution_id: str) -> List[Dict[str, Any]]:
    return _with_term_status_list(_db_service.get_active_terms(institution_id))


def get_all_terms(institution_id: str) -> List[Dict[str, Any]]:
    return _with_term_status_list(_db_service.get_all_terms(institution_id))


def get_term_by_id(term_id: str) -> Optional[Dict[str, Any]]:
    return _with_term_status(_db_service.get_term_by_id(term_id))


def get_sections_by_term(term_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_sections_by_term(term_id)


# ---------------------------------------------------------------------------
# Section operations
# ---------------------------------------------------------------------------


def create_course_section(section_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_course_section(section_data)


def update_course_section(section_id: str, section_data: Dict[str, Any]) -> bool:
    return _db_service.update_course_section(section_id, section_data)


def assign_instructor(section_id: str, instructor_id: str) -> bool:
    return _db_service.assign_instructor(section_id, instructor_id)


def delete_course_section(section_id: str) -> bool:
    return _db_service.delete_course_section(section_id)


def get_sections_by_instructor(instructor_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_sections_by_instructor(instructor_id)


# ---------------------------------------------------------------------------
# Program operations
# ---------------------------------------------------------------------------


def create_program(program_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_program(program_data)


def get_programs_by_institution(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_programs_by_institution(institution_id)


def get_program_by_id(program_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_program_by_id(program_id)


def get_program_by_name_and_institution(
    program_name: str, institution_id: str
) -> Optional[Dict[str, Any]]:
    return _db_service.get_program_by_name_and_institution(program_name, institution_id)


def update_program(  # noqa: ambiguity-mine - service facade intentionally mirrors domain verb
    program_id: str, updates: Dict[str, Any]
) -> bool:
    return _db_service.update_program(program_id, updates)


def delete_program(program_id: str, reassign_to_program_id: str) -> bool:
    return _db_service.delete_program(program_id, reassign_to_program_id)


def get_courses_by_program(program_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_courses_by_program(program_id)


def get_programs_for_course(course_id: str) -> List[Dict[str, Any]]:
    """Get all programs that a course is attached to."""
    return _db_service.get_programs_for_course(course_id)


def get_unassigned_courses(institution_id: str) -> List[Dict[str, Any]]:
    return _db_service.get_unassigned_courses(institution_id)


def assign_course_to_default_program(course_id: str, institution_id: str) -> bool:
    return _db_service.assign_course_to_default_program(course_id, institution_id)


def add_course_to_program(course_id: str, program_id: str) -> bool:
    return _db_service.add_course_to_program(course_id, program_id)


def remove_course_from_program(course_id: str, program_id: str) -> bool:
    return _db_service.remove_course_from_program(course_id, program_id)


def bulk_add_courses_to_program(
    course_ids: List[str], program_id: str
) -> Dict[str, Any]:
    return _db_service.bulk_add_courses_to_program(course_ids, program_id)


def bulk_remove_courses_from_program(
    course_ids: List[str], program_id: str
) -> Dict[str, Any]:
    return _db_service.bulk_remove_courses_from_program(course_ids, program_id)


# ---------------------------------------------------------------------------
# Invitation operations
# ---------------------------------------------------------------------------


def create_invitation(invitation_data: Dict[str, Any]) -> Optional[str]:
    return _db_service.create_invitation(invitation_data)


def get_invitation_by_id(invitation_id: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_invitation_by_id(invitation_id)


def get_invitation_by_token(invitation_token: str) -> Optional[Dict[str, Any]]:
    return _db_service.get_invitation_by_token(invitation_token)


def get_invitation_by_email(
    email: str, institution_id: str
) -> Optional[Dict[str, Any]]:
    return _db_service.get_invitation_by_email(email, institution_id)


def update_invitation(invitation_id: str, updates: Dict[str, Any]) -> bool:
    return _db_service.update_invitation(invitation_id, updates)


def list_invitations(
    institution_id: str, status: Optional[str] = None, limit: int = 50, offset: int = 0
) -> List[Dict[str, Any]]:
    return _db_service.list_invitations(institution_id, status, limit, offset)


def get_outcomes_by_status(
    institution_id: str,
    status: Optional[str],
    program_id: Optional[str] = None,
    term_id: Optional[str] = None,
    course_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get course outcomes filtered by status.

    Args:
        institution_id: Institution ID to filter by
        status: CLO status to filter by (None for all statuses)
        program_id: Optional program ID to further filter results
        term_id: Optional term ID to further filter results
        course_id: Optional course ID to further filter results

    Returns:
        List of course outcome dictionaries
    """
    return _db_service.get_outcomes_by_status(
        institution_id, status, program_id, term_id, course_id
    )


def get_sections_by_course(course_id: str) -> List[Dict[str, Any]]:
    """
    Get all course sections for a given course.

    Args:
        course_id: The course ID to get sections for

    Returns:
        List of course section dictionaries
    """
    return _db_service.get_sections_by_course(course_id)


def get_section_outcomes_by_criteria(
    institution_id: str,
    status: Optional[str] = None,
    program_id: Optional[str] = None,
    term_id: Optional[str] = None,
    course_id: Optional[str] = None,
    section_id: Optional[str] = None,
    outcome_ids: Optional[List[str]] = None,
    term_ids: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Get section outcomes filtered by various criteria.

    Args:
        institution_id: The institution ID
        status: The status to filter by
        program_id: The program ID to filter by
        term_id: The term ID to filter by (single term)
        course_id: The course ID to filter by
        section_id: The section ID to filter by
        outcome_ids: Restrict to section outcomes referencing these
            CourseOutcome template IDs (used by the PLO dashboard to fetch
            only sections using CLOs that are mapped to a given PLO set).
        term_ids: Multiple term filter; when provided, overrides term_id.

    Returns:
        List of section outcome dictionaries
    """
    return _db_service.get_section_outcomes_by_criteria(
        institution_id,
        status,
        program_id,
        term_id,
        course_id,
        section_id,
        outcome_ids,
        term_ids,
    )


def get_section_outcome_by_course_outcome_and_section(
    course_outcome_id: str, section_id: str
) -> Optional[Dict[str, Any]]:
    """
    Get a specific section outcome by template ID and section ID.

    Args:
        course_outcome_id: The template outcome ID
        section_id: The section ID

    Returns:
        The section outcome dictionary or None if not found
    """
    return _db_service.get_section_outcome_by_course_outcome_and_section(
        course_outcome_id, section_id
    )


# ---------------------------------------------------------------------------
# Instructor Reminder operations
# ---------------------------------------------------------------------------


def create_reminder(
    section_id: str,
    instructor_id: str,
    sent_by: Optional[str] = None,
    reminder_type: str = "individual",
    message_preview: Optional[str] = None,
) -> Optional[str]:
    """Record a reminder email sent to an instructor."""
    return _db_service.create_reminder(
        section_id, instructor_id, sent_by, reminder_type, message_preview
    )


def get_reminders_by_section(section_id: str) -> List[Dict[str, Any]]:
    """Get all reminders sent for a specific section."""
    return _db_service.get_reminders_by_section(section_id)


def get_reminders_by_instructor(instructor_id: str) -> List[Dict[str, Any]]:
    """Get all reminders sent to a specific instructor."""
    return _db_service.get_reminders_by_instructor(instructor_id)


# ---------------------------------------------------------------------------
# Outcome History operations
# ---------------------------------------------------------------------------


def add_outcome_history(section_outcome_id: str, event: str) -> bool:
    """Add a history entry for a section outcome (for manual events like reminders)."""
    return _db_service.add_outcome_history(section_outcome_id, event)


def get_outcome_history(section_outcome_id: str) -> List[Dict[str, Any]]:
    """Get history entries for a section outcome, sorted by date DESC."""
    return _db_service.get_outcome_history(section_outcome_id)


# Program Outcome (PLO) operations


def create_program_outcome(  # noqa: ambiguity-mine - service facade intentionally mirrors domain verb
    outcome_data: Dict[str, Any],
) -> str:
    """Create a new Program Level Outcome template."""
    return _db_service.create_program_outcome(outcome_data)


def update_program_outcome(  # noqa: ambiguity-mine - service facade intentionally mirrors domain verb
    outcome_id: str, outcome_data: Dict[str, Any]
) -> bool:
    """Update a Program Level Outcome template."""
    return _db_service.update_program_outcome(outcome_id, outcome_data)


def delete_program_outcome(  # noqa: ambiguity-mine - service facade intentionally mirrors domain verb
    outcome_id: str,
) -> bool:
    """Soft-delete a PLO by setting is_active=False."""
    return _db_service.delete_program_outcome(outcome_id)


def get_program_outcomes(
    program_id: str, include_inactive: bool = False
) -> List[Dict[str, Any]]:
    """Get all PLOs for a program, ordered by plo_number."""
    return _db_service.get_program_outcomes(program_id, include_inactive)


def get_program_outcome(  # noqa: ambiguity-mine - service facade intentionally mirrors domain verb
    outcome_id: str,
) -> Optional[Dict[str, Any]]:
    """Get a single PLO by ID."""
    return _db_service.get_program_outcome(outcome_id)


# PLO Mapping (versioned draft/publish) operations


def get_or_create_plo_mapping_draft(
    program_id: str, user_id: Optional[str] = None
) -> Dict[str, Any]:
    """Get or create the draft mapping for a program."""
    return _db_service.get_or_create_plo_mapping_draft(program_id, user_id)


def get_plo_mapping_draft(program_id: str) -> Optional[Dict[str, Any]]:
    """Get the current draft mapping for a program, or None."""
    return _db_service.get_plo_mapping_draft(program_id)


def add_plo_mapping_entry(
    mapping_id: str,
    program_outcome_id: str,
    course_outcome_id: str,
) -> str:
    """Add a PLO↔CLO link to a draft mapping. Returns entry ID."""
    return _db_service.add_plo_mapping_entry(
        mapping_id, program_outcome_id, course_outcome_id
    )


def remove_plo_mapping_entry(entry_id: str) -> bool:
    """Remove a PLO↔CLO link from a draft mapping."""
    return _db_service.remove_plo_mapping_entry(entry_id)


def publish_plo_mapping(
    mapping_id: str,
    description: Optional[str] = None,
) -> Dict[str, Any]:
    """Publish a draft mapping, assigning the next version number."""
    return _db_service.publish_plo_mapping(mapping_id, description)


def discard_plo_mapping_draft(mapping_id: str) -> bool:
    """Discard (delete) a draft mapping and all its entries."""
    return _db_service.discard_plo_mapping_draft(mapping_id)


def get_plo_mapping(mapping_id: str) -> Optional[Dict[str, Any]]:
    """Get a single mapping by ID, including its entries."""
    return _db_service.get_plo_mapping(mapping_id)


def get_plo_mapping_by_version(
    program_id: str, version: int
) -> Optional[Dict[str, Any]]:
    """Get a published mapping by program and version number."""
    return _db_service.get_plo_mapping_by_version(program_id, version)


def get_published_plo_mappings(program_id: str) -> List[Dict[str, Any]]:
    """Get all published mappings for a program, ordered by version."""
    return _db_service.get_published_plo_mappings(program_id)


def get_latest_published_plo_mapping(
    program_id: str,
) -> Optional[Dict[str, Any]]:
    """Get the most recent published mapping for a program."""
    return _db_service.get_latest_published_plo_mapping(program_id)


__all__ = [
    "COURSE_OFFERINGS_COLLECTION",
    "COURSE_OUTCOMES_COLLECTION",
    "COURSE_SECTIONS_COLLECTION",
    "COURSES_COLLECTION",
    "DB_CLIENT_NOT_AVAILABLE_MSG",
    "DEFAULT_INSTITUTION_TIMEZONE",
    "INSTITUTIONS_COLLECTION",
    "TERMS_COLLECTION",
    "USERS_COLLECTION",
    "db",
    "reset_database",
    "refresh_connection",
    "db_operation_timeout",
    "check_db_connection",
    "sanitize_for_logging",
    "create_institution",
    "get_institution_by_id",
    "get_all_institutions",
    "create_default_mocku_institution",
    "create_new_institution",
    "get_institution_instructor_count",
    "get_institution_by_short_name",
    "create_user",
    "get_user_by_email",
    "get_user_by_reset_token",
    "get_all_users",
    "get_users_by_role",
    "get_user_by_id",
    "update_user",
    "update_user_active_status",
    "calculate_and_update_active_users",
    "update_user_extended",
    "get_user_by_verification_token",
    "create_course",
    "get_course_by_number",
    "get_courses_by_department",
    "create_course_outcome",
    "get_course_outcomes",
    "get_course_by_id",
    "get_all_courses",
    "get_all_instructors",
    "get_all_sections",
    "create_course_offering",
    "get_course_offering",
    "get_course_offering_by_course_and_term",
    "get_all_course_offerings",
    "create_term",
    "get_term_by_name",
    "get_active_terms",
    "get_sections_by_term",
    "create_course_section",
    "get_sections_by_instructor",
    "create_program",
    "get_programs_by_institution",
    "get_program_by_id",
    "get_program_by_name_and_institution",
    "update_program",
    "delete_program",
    "get_courses_by_program",
    "get_unassigned_courses",
    "assign_course_to_default_program",
    "add_course_to_program",
    "remove_course_from_program",
    "bulk_add_courses_to_program",
    "bulk_remove_courses_from_program",
    "create_invitation",
    "get_invitation_by_id",
    "get_invitation_by_token",
    "get_invitation_by_email",
    "update_invitation",
    "list_invitations",
    "get_outcomes_by_status",
    "get_sections_by_course",
    "get_section_outcome",
    "get_section_outcomes_by_section",
    "update_section_outcome",
    "get_section_outcome_by_course_outcome_and_section",
    "get_section_outcomes_by_criteria",
    # Reminder operations
    "create_reminder",
    "get_reminders_by_section",
    "get_reminders_by_instructor",
    # Outcome history operations
    "add_outcome_history",
    "get_outcome_history",
    # Program Outcome (PLO) operations
    "create_program_outcome",
    "update_program_outcome",
    "delete_program_outcome",
    "get_program_outcomes",
    "get_program_outcome",
    # PLO Mapping (versioned draft/publish) operations
    "get_or_create_plo_mapping_draft",
    "get_plo_mapping_draft",
    "add_plo_mapping_entry",
    "remove_plo_mapping_entry",
    "publish_plo_mapping",
    "discard_plo_mapping_draft",
    "get_plo_mapping",
    "get_plo_mapping_by_version",
    "get_published_plo_mappings",
    "get_latest_published_plo_mapping",
]
