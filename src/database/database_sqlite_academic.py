"""Academic structure mixin for the SQLAlchemy-backed database implementation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_, select, text

from src.models.models_sql import (
    Course,
    CourseOffering,
    CourseOutcome,
    CourseSection,
    CourseSectionOutcome,
    Program,
    Term,
    User,
    course_program_table,
    to_dict,
)
from src.utils.logging_config import get_logger
from src.utils.time_utils import get_current_time

from .database_sqlite_shared import (
    OFFERING_STATUS_FIELDS,
    SECTION_DATETIME_FIELDS,
    TERM_STATUS_FIELDS,
    _ensure_uuid,
    _normalize_section_datetime,
    _remove_fields,
)

logger = get_logger(__name__)


class SQLDatabaseAcademicMixin:
    sql: Any

    def create_course_offering(self, offering_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(offering_data)
        _remove_fields(payload, OFFERING_STATUS_FIELDS)
        offering_id = _ensure_uuid(payload.pop("offering_id", None))
        offering = CourseOffering(
            id=offering_id,
            course_id=payload.get("course_id"),
            term_id=payload.get("term_id"),
            institution_id=payload.get("institution_id"),
            program_id=payload.get("program_id"),
            total_enrollment=payload.get("total_enrollment", 0),
            section_count=payload.get("section_count", 0),
            extras={**payload, "offering_id": offering_id},
        )
        with self.sql.session_scope() as session:
            session.add(offering)
            return offering_id

    def update_course_offering(
        self, offering_id: str, offering_data: Dict[str, Any]
    ) -> bool:
        try:
            with self.sql.session_scope() as session:
                offering = session.get(CourseOffering, offering_id)
                if not offering:
                    return False

                for key, value in offering_data.items():
                    if key in OFFERING_STATUS_FIELDS:
                        continue
                    if hasattr(offering, key) and key != "id":
                        setattr(offering, key, value)

                offering.updated_at = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logger.error(f"Failed to update offering: {e}")
            return False

    def delete_course_offering(self, offering_id: str) -> bool:
        try:
            with self.sql.session_scope() as session:
                offering = session.get(CourseOffering, offering_id)
                if not offering:
                    return False
                session.delete(offering)
                return True
        except Exception as e:
            logger.error(f"Failed to delete offering: {e}")
            return False

    def get_course_offering(self, offering_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            offering = (
                session.execute(
                    select(CourseOffering).where(CourseOffering.id == offering_id)
                )
                .scalars()
                .first()
            )
            return to_dict(offering) if offering else None

    def get_course_offering_by_course_and_term(
        self, course_id: str, term_id: str
    ) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            offering = (
                session.execute(
                    select(CourseOffering).where(
                        and_(
                            CourseOffering.course_id == course_id,
                            CourseOffering.term_id == term_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            return to_dict(offering) if offering else None

    def get_all_course_offerings(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            offerings = (
                session.execute(
                    select(CourseOffering).where(
                        CourseOffering.institution_id == institution_id
                    )
                )
                .scalars()
                .all()
            )

            # Batch-load courses (one query, not one per offering) to avoid N+1.
            course_ids = {o.course_id for o in offerings if o.course_id}
            courses = (
                {
                    c.id: c
                    for c in session.execute(
                        select(Course).where(Course.id.in_(course_ids))
                    ).scalars()
                }
                if course_ids
                else {}
            )

            result: List[Dict[str, Any]] = []
            for offering in offerings:
                offering_dict = to_dict(offering)

                course = courses.get(offering.course_id)
                if course:
                    offering_dict["course_number"] = course.course_number
                    offering_dict["course_title"] = course.course_title

                result.append(offering_dict)

            return result

    def create_term(self, term_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(term_data)
        _remove_fields(payload, TERM_STATUS_FIELDS)
        term_id = _ensure_uuid(payload.pop("term_id", None))
        term_name = payload.get("term_name")
        if not term_name:
            logger.error("[SQLDatabase] term_name is required")
            return None
        term = Term(
            id=term_id,
            term_name=term_name,
            name=payload.get("name", term_name),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            assessment_due_date=payload.get("assessment_due_date"),
            institution_id=payload.get("institution_id"),
            extras={**payload, "term_id": term_id},
        )
        with self.sql.session_scope() as session:
            session.add(term)
            return term_id

    def update_term(self, term_id: str, term_data: Dict[str, Any]) -> bool:
        try:
            with self.sql.session_scope() as session:
                term = session.get(Term, term_id)
                if not term:
                    return False

                for key, value in term_data.items():
                    if key in TERM_STATUS_FIELDS:
                        continue
                    if hasattr(term, key) and key != "id":
                        setattr(term, key, value)

                term.updated_at = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logger.error(f"Failed to update term: {e}")
            return False

    def delete_term(self, term_id: str) -> bool:
        try:
            with self.sql.session_scope() as session:
                term = session.get(Term, term_id)
                if not term:
                    return False
                session.delete(term)
                return True
        except Exception as e:
            logger.error(f"Failed to delete term: {e}")
            return False

    def get_term_by_name(
        self, name: str, institution_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            filters = [Term.term_name == name]
            if institution_id is not None:
                filters.append(Term.institution_id == institution_id)

            term = session.execute(select(Term).where(and_(*filters))).scalars().first()
            return to_dict(term) if term else None

    def get_active_terms(self, institution_id: str) -> List[Dict[str, Any]]:
        current_date_str = get_current_time().strftime("%Y-%m-%d")

        with self.sql.session_scope() as session:
            terms = (
                session.execute(
                    select(Term).where(
                        and_(
                            Term.institution_id == institution_id,
                            func.date(Term.start_date) <= current_date_str,
                            func.date(Term.end_date) >= current_date_str,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(term) for term in terms]

    def get_all_terms(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            terms = (
                session.execute(
                    select(Term)
                    .where(Term.institution_id == institution_id)
                    .order_by(Term.start_date.desc())
                )
                .scalars()
                .all()
            )
            return [to_dict(term) for term in terms]

    def get_term_by_id(self, term_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            term = session.get(Term, term_id)
            return to_dict(term) if term else None

    def get_sections_by_term(self, term_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            sections = (
                session.execute(
                    select(CourseSection)
                    .join(CourseOffering)
                    .where(CourseOffering.term_id == term_id)
                )
                .scalars()
                .all()
            )
            return [to_dict(section) for section in sections]

    def create_course_section(self, section_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(section_data)
        section_id = _ensure_uuid(payload.pop("section_id", None))
        section = CourseSection(
            id=section_id,
            offering_id=payload.get("offering_id"),
            instructor_id=payload.get("instructor_id"),
            section_number=payload.get("section_number", "001"),
            enrollment=payload.get("enrollment"),
            withdrawals=payload.get("withdrawals", 0),
            students_passed=payload.get("students_passed"),
            students_dfic=payload.get("students_dfic"),
            cannot_reconcile=payload.get("cannot_reconcile", False),
            reconciliation_note=payload.get("reconciliation_note"),
            narrative_celebrations=payload.get("narrative_celebrations"),
            narrative_challenges=payload.get("narrative_challenges"),
            narrative_changes=payload.get("narrative_changes"),
            status=payload.get("status", "assigned"),
            due_date=_normalize_section_datetime(payload.get("due_date")),
            assigned_date=_normalize_section_datetime(payload.get("assigned_date")),
            completed_date=_normalize_section_datetime(payload.get("completed_date")),
            extras={**payload, "section_id": section_id},
        )
        with self.sql.session_scope() as session:
            session.add(section)

            if payload.get("offering_id"):
                offering = session.get(CourseOffering, payload.get("offering_id"))
                if offering:
                    filters = [CourseOutcome.course_id == offering.course_id]
                    if offering.program_id:
                        filters.append(
                            or_(
                                CourseOutcome.program_id == offering.program_id,
                                CourseOutcome.program_id.is_(None),
                            )
                        )
                    else:
                        filters.append(CourseOutcome.program_id.is_(None))

                    templates = (
                        session.execute(select(CourseOutcome).where(and_(*filters)))
                        .scalars()
                        .all()
                    )

                    for template in templates:
                        instance = CourseSectionOutcome(
                            section_id=section_id,
                            outcome_id=template.id,
                            status=template.status,
                            approval_status=template.approval_status,
                            submitted_at=template.submitted_at,
                            submitted_by=template.submitted_by_user_id,
                            reviewed_at=template.reviewed_at,
                            reviewed_by=template.reviewed_by_user_id,
                            feedback_comments=template.feedback_comments,
                            students_took=template.students_took,
                            students_passed=template.students_passed,
                            assessment_tool=template.assessment_tool,
                        )
                        session.add(instance)

                    if templates:
                        logger.info(
                            "Auto-populated %s CLO instances for section %s",
                            len(templates),
                            section_id,
                        )

            return section_id

    def update_course_section(
        self, section_id: str, section_data: Dict[str, Any]
    ) -> bool:
        try:
            with self.sql.session_scope() as session:
                section = session.get(CourseSection, section_id)
                if not section:
                    return False

                for key, value in section_data.items():
                    normalized_value = (
                        _normalize_section_datetime(value)
                        if key in SECTION_DATETIME_FIELDS
                        else value
                    )
                    if hasattr(section, key) and key != "id":
                        setattr(section, key, normalized_value)

                section.updated_at = get_current_time()
                return True
        except Exception as e:
            logger.error(f"Failed to update section: {e}")
            return False

    def assign_instructor(self, section_id: str, instructor_id: str) -> bool:
        return self.update_course_section(
            section_id,
            {
                "instructor_id": instructor_id,
                "status": "assigned",
                "assigned_date": get_current_time(),
            },
        )

    def delete_course_section(self, section_id: str) -> bool:
        try:
            with self.sql.session_scope() as session:
                section = session.get(CourseSection, section_id)
                if not section:
                    return False
                session.delete(section)
                return True
        except Exception as e:
            logger.error(f"Failed to delete section: {e}")
            return False

    def get_sections_by_instructor(self, instructor_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            sections = (
                session.execute(
                    select(CourseSection).where(
                        CourseSection.instructor_id == instructor_id
                    )
                )
                .scalars()
                .all()
            )

            enriched_sections: List[Dict[str, Any]] = []

            for section in sections:
                section_dict = to_dict(section)
                offering = session.get(CourseOffering, section.offering_id)

                if offering:
                    section_dict["course_id"] = offering.course_id
                    section_dict["term_id"] = offering.term_id

                    course = session.get(Course, offering.course_id)
                    if course:
                        section_dict["course_number"] = course.course_number
                        section_dict["course_title"] = course.course_title

                    term = session.get(Term, offering.term_id)
                    if term:
                        section_dict["term_name"] = term.term_name

                if section.instructor_id:
                    instructor = session.get(User, section.instructor_id)
                    if instructor:
                        section_dict["instructor_name"] = (
                            f"{instructor.first_name} {instructor.last_name}"
                        )

                enriched_sections.append(section_dict)

            return enriched_sections

    def create_program(self, program_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(program_data)
        program_id = _ensure_uuid(payload.pop("program_id", None))
        program = Program(
            id=program_id,
            name=payload.get("name", ""),
            short_name=payload.get("short_name", "").upper(),
            description=payload.get("description"),
            institution_id=payload.get("institution_id"),
            created_by=payload.get("created_by"),
            is_default=payload.get("is_default", False),
            is_active=payload.get("is_active", True),
            extras={**payload, "program_id": program_id},
        )
        with self.sql.session_scope() as session:
            session.add(program)
            return program_id

    def get_programs_by_institution(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            programs = (
                session.execute(
                    select(Program).where(Program.institution_id == institution_id)
                )
                .scalars()
                .all()
            )
            return [to_dict(program) for program in programs]

    def get_program_by_id(self, program_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            program = session.get(Program, program_id)
            return to_dict(program) if program else None

    def link_course_to_program(self, course_id: str, program_id: str) -> bool:
        try:
            with self.sql.session_scope() as session:
                existing = session.execute(
                    select(course_program_table).where(
                        course_program_table.c.course_id == course_id,
                        course_program_table.c.program_id == program_id,
                    )
                ).first()

                if existing:
                    return True

                session.execute(
                    course_program_table.insert().values(
                        course_id=course_id, program_id=program_id
                    )
                )
                return True
        except Exception as e:
            logger.error(
                "[LINK_COURSE_PROGRAM] Failed to link course %s to program %s: %s",
                course_id,
                program_id,
                e,
            )
            return False

    def get_program_by_name_and_institution(
        self, program_name: str, institution_id: str
    ) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            program = (
                session.execute(
                    select(Program).where(
                        and_(
                            Program.institution_id == institution_id,
                            func.lower(Program.name) == program_name.lower(),
                        )
                    )
                )
                .scalars()
                .first()
            )
            return to_dict(program) if program else None

    def update_program(self, program_id: str, updates: Dict[str, Any]) -> bool:
        with self.sql.session_scope() as session:
            program = session.get(Program, program_id)
            if not program:
                return False
            extras = dict(program.extras or {})
            for key, value in updates.items():
                if hasattr(Program, key):
                    setattr(program, key, value)
                extras[key] = value
            program.extras = extras
            program.updated_at = datetime.now(timezone.utc)
            return True

    def delete_program(self, program_id: str, reassign_to_program_id: str) -> bool:
        with self.sql.session_scope() as session:
            program = session.get(Program, program_id)
            if not program:
                return False
            reassignment = session.get(Program, reassign_to_program_id)
            if not reassignment:
                return False
            for course in list(program.courses):
                if course not in reassignment.courses:
                    reassignment.courses.append(course)
            session.delete(program)
            return True

    def get_courses_by_program(self, program_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            program = session.get(Program, program_id)
            if not program:
                return []
            return [to_dict(course) for course in program.courses]

    def get_programs_for_course(self, course_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            course = session.get(Course, course_id)
            if not course:
                return []
            return [to_dict(program) for program in course.programs]

    def get_program_admins(self, program_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            try:
                users = (
                    session.execute(
                        select(User).where(
                            and_(
                                User.role == "program_admin",
                                text(
                                    "EXISTS (SELECT 1 FROM json_each(users.extras, '$.program_ids') WHERE value = :program_id)"
                                ).bindparams(program_id=program_id),
                            )
                        ),
                        {"program_id": program_id},
                    )
                    .scalars()
                    .all()
                )

                return [to_dict(user) for user in users]
            except Exception as e:
                logger.warning(
                    "Error querying program admins (possibly malformed JSON in extras): %s",
                    e,
                )
                return []

    def get_unassigned_courses(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            courses = (
                session.execute(
                    select(Course)
                    .outerjoin(
                        course_program_table,
                        Course.id == course_program_table.c.course_id,
                    )
                    .where(
                        and_(
                            Course.institution_id == institution_id,
                            course_program_table.c.program_id.is_(None),
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(course) for course in courses]

    def assign_course_to_default_program(
        self, course_id: str, institution_id: str
    ) -> bool:
        with self.sql.session_scope() as session:
            default_program = (
                session.execute(
                    select(Program).where(
                        and_(
                            Program.institution_id == institution_id,
                            Program.is_default.is_(True),
                        )
                    )
                )
                .scalars()
                .first()
            )
            if not default_program:
                return False
            course = session.get(Course, course_id)
            if not course:
                return False
            if course not in default_program.courses:
                default_program.courses.append(course)
            return True

    def add_course_to_program(self, course_id: str, program_id: str) -> bool:
        with self.sql.session_scope() as session:
            course = session.get(Course, course_id)
            program = session.get(Program, program_id)
            if not course or not program:
                return False
            if course not in program.courses:
                program.courses.append(course)
            return True

    def remove_course_from_program(self, course_id: str, program_id: str) -> bool:
        with self.sql.session_scope() as session:
            course = session.get(Course, course_id)
            program = session.get(Program, program_id)
            if not course or not program:
                return False
            if course in program.courses:
                program.courses.remove(course)
            return True

    def bulk_add_courses_to_program(
        self, course_ids: List[str], program_id: str
    ) -> Dict[str, Any]:
        success_count = 0
        failures: List[str] = []
        for course_id in course_ids:
            if self.add_course_to_program(course_id, program_id):
                success_count += 1
            else:
                failures.append(course_id)
        return {"added": success_count, "failed": failures}

    def bulk_remove_courses_from_program(
        self, course_ids: List[str], program_id: str
    ) -> Dict[str, Any]:
        success_count = 0
        failures: List[str] = []
        for course_id in course_ids:
            if self.remove_course_from_program(course_id, program_id):
                success_count += 1
            else:
                failures.append(course_id)
        return {"removed": success_count, "failed": failures}

    def delete_program_simple(self, program_id: str) -> bool:
        with self.sql.session_scope() as session:
            program = session.get(Program, program_id)
            if not program:
                return False
            session.delete(program)
            return True
