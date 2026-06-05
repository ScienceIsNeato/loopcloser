"""SQL database implementation using SQLAlchemy.

Supports SQLite, PostgreSQL, and other SQLAlchemy-compatible databases.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, cast

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import joinedload, selectinload

from src.database.database_interface import DatabaseInterface
from src.database.database_sql import SQLService
from src.database.database_sqlite_academic import SQLDatabaseAcademicMixin
from src.database.database_sqlite_shared import (
    _ensure_uuid,
)
from src.database.database_sqlite_workflow import SQLDatabaseWorkflowMixin
from src.models.models_sql import (
    Course,
    CourseOffering,
    CourseOutcome,
    CourseSection,
    CourseSectionOutcome,
    Institution,
    Program,
    Term,
    User,
    course_program_table,
    to_dict,
)
from src.utils.constants import DEFAULT_INSTITUTION_TIMEZONE
from src.utils.logging_config import get_logger

logger = get_logger(__name__)

COURSE_OUTCOME_EXCLUDED_FIELDS = {
    "outcome_id",
    "course_id",
    "clo_number",
    "description",
    "assessment_method",
    "active",
    "status",
    "students_took",
    "students_passed",
    "assessment_tool",
    "created_at",
    "last_modified",
    "updated_at",
    "submitted_at",
    "submitted_by_user_id",
    "reviewed_at",
    "reviewed_by_user_id",
    "approval_status",
    "feedback_comments",
    "feedback_provided_at",
    "assessment_data",
    "narrative",
    "program_id",
}


class SQLDatabase(
    SQLDatabaseWorkflowMixin,
    SQLDatabaseAcademicMixin,
    DatabaseInterface,
):
    """Concrete database implementation using SQLAlchemy.

    Supports any SQLAlchemy-compatible database (SQLite, PostgreSQL, MySQL, etc.).
    The database type is automatically detected from the DATABASE_URL connection string.
    """

    def __init__(self, db_url: Optional[str] = None) -> None:
        self.sql = SQLService(db_url)

    # ------------------------------------------------------------------
    # Institution operations
    # ------------------------------------------------------------------
    def create_institution(self, institution_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(institution_data)
        institution_id = _ensure_uuid(payload.pop("institution_id", None))
        name = payload.get("name") or payload.get("institution_name")
        short_name = payload.get("short_name")
        logo_path = payload.pop("logo_path", None)
        if not name or not short_name:
            logger.error("[SQLDatabase] Institution requires name and short_name")
            return None

        institution = Institution(
            id=institution_id,
            name=name,
            short_name=short_name.upper(),
            website_url=payload.get("website_url"),
            logo_path=logo_path,
            created_by=payload.get("created_by"),
            admin_email=(payload.get("admin_email") or "").lower(),
            allow_self_registration=payload.get("allow_self_registration", False),
            require_email_verification=payload.get("require_email_verification", True),
            is_active=payload.get("is_active", True),
            extras={**payload, "institution_id": institution_id},
        )

        with self.sql.session_scope() as session:
            session.add(institution)
            logger.info("[SQLDatabase] Created institution %s", institution_id)

        # Automatically create default program for the institution
        default_program_data: Dict[str, Any] = {
            "name": f"{short_name} Default Program",
            "institution_id": institution_id,
            "is_default": True,
        }
        default_program_id = self.create_program(default_program_data)
        if default_program_id:
            logger.info(
                "[SQLDatabase] Created default program %s for institution %s",
                default_program_id,
                institution_id,
            )
        else:
            logger.warning(
                "[SQLDatabase] Failed to create default program for institution %s",
                institution_id,
            )

        return institution_id

    def get_institution_by_id(self, institution_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            inst = session.get(Institution, institution_id)
            return to_dict(inst) if inst else None

    def get_all_institutions(self) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            records = (
                session.execute(
                    select(Institution).where(Institution.is_active.is_(True))
                )
                .scalars()
                .all()
            )
            return [to_dict(record) for record in records]

    def create_default_mocku_institution(self) -> Optional[str]:
        existing = self.get_institution_by_short_name("MOCKU")
        if existing:
            return existing["institution_id"]

        mocku_payload: Dict[str, Any] = {
            "name": "Mock University",
            "short_name": "MOCKU",
            "domain": "mocku.edu",
            "timezone": DEFAULT_INSTITUTION_TIMEZONE,
            "is_active": True,
            "billing_settings": {
                "instructor_seat_limit": 100,
                "current_instructor_count": 0,
                "subscription_status": "active",
            },
            "settings": {
                "default_credit_hours": 3,
                "academic_year_start_month": 8,
                "grading_scale": "traditional",
            },
            "created_at": datetime.now(timezone.utc),
        }
        return self.create_institution(mocku_payload)

    def create_new_institution(
        self, institution_data: Dict[str, Any], admin_user_data: Dict[str, Any]
    ) -> Optional[Tuple[str, str]]:
        institution_id = self.create_institution(institution_data)
        if not institution_id:
            return None

        user_payload = dict(admin_user_data)
        user_payload.setdefault("institution_id", institution_id)
        user_id = self.create_user(user_payload)
        if not user_id:
            return None
        return institution_id, user_id

    def create_new_institution_simple(
        self,
        name: str,
        short_name: str,
        active: bool = True,
        *,
        website_url: Optional[str] = None,
        logo_path: Optional[str] = None,
    ) -> Optional[str]:
        """Create a new institution without creating an admin user (site admin workflow)"""
        institution_data: Dict[str, Any] = {
            "name": name,
            "short_name": short_name,
            "active": active,
            "website_url": website_url,
            "logo_path": logo_path,
        }
        return self.create_institution(institution_data)

    def get_institution_instructor_count(self, institution_id: str) -> int:
        with self.sql.session_scope() as session:
            return (
                session.execute(
                    select(func.count(User.id)).where(
                        and_(
                            User.institution_id == institution_id,
                            User.role == "instructor",
                        )
                    )
                ).scalar()
                or 0
            )

    def get_institution_by_short_name(
        self, short_name: str
    ) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            record = (
                session.execute(
                    select(Institution).where(
                        func.lower(Institution.short_name) == short_name.lower()
                    )
                )
                .scalars()
                .first()
            )
            return to_dict(record) if record else None

    def update_institution(
        self, institution_id: str, institution_data: Dict[str, Any]
    ) -> bool:
        """Update institution details."""
        try:
            with self.sql.session_scope() as session:
                inst = session.get(Institution, institution_id)
                if not inst:
                    return False

                for key, value in institution_data.items():
                    if hasattr(inst, key) and key != "id":
                        setattr(inst, key, value)

                inst.updated_at = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logger.error(f"Failed to update institution: {e}")
            return False

    def delete_institution(self, institution_id: str) -> bool:
        """
        Delete institution (CASCADE deletes all related data).
        WARNING: This is DESTRUCTIVE and IRREVERSIBLE.
        """
        try:
            with self.sql.session_scope() as session:
                inst = session.get(Institution, institution_id)
                if not inst:
                    return False
                # SQLAlchemy cascade will handle deletion of related entities
                session.delete(inst)
                return True
        except Exception as e:
            logger.error(f"Failed to delete institution: {e}")
            return False

    # ------------------------------------------------------------------
    # User operations
    # ------------------------------------------------------------------
    def create_user(self, user_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(user_data)
        # Accept both "id" and "user_id" for backward compatibility
        user_id = _ensure_uuid(payload.pop("id", None) or payload.pop("user_id", None))
        email = payload.get("email")
        if not email:
            logger.error("[SQLDatabase] User requires email")
            return None

        # Validate required fields
        first_name = payload.get("first_name", "")
        last_name = payload.get("last_name", "")
        if not first_name or not first_name.strip():
            logger.error("[SQLDatabase] User requires first_name")
            return None
        if not last_name or not last_name.strip():
            logger.error("[SQLDatabase] User requires last_name")
            return None

        user = User(
            id=user_id,
            email=email.lower(),
            password_hash=payload.get("password_hash"),
            first_name=first_name.strip(),
            last_name=last_name.strip(),
            display_name=payload.get("display_name"),
            account_status=payload.get("account_status", "pending"),
            email_verified=payload.get("email_verified", False),
            email_verification_token=payload.get("email_verification_token"),
            email_verification_sent_at=payload.get("email_verification_sent_at"),
            role=payload.get("role", "instructor"),
            institution_id=payload.get("institution_id"),
            login_attempts=payload.get("login_attempts", 0),
            locked_until=payload.get("locked_until"),
            last_login_at=payload.get("last_login_at"),
            invited_by=payload.get("invited_by"),
            invited_at=payload.get("invited_at"),
            registration_completed_at=payload.get("registration_completed_at"),
            oauth_provider=payload.get("oauth_provider"),
            oauth_id=payload.get("oauth_id"),
            password_reset_token=payload.get("password_reset_token"),
            password_reset_expires_at=payload.get("password_reset_expires_at"),
            system_date_override=payload.get("system_date_override"),
            extras={**payload, "user_id": user_id},
        )

        with self.sql.session_scope() as session:
            existing = (
                session.execute(select(User).where(User.email == user.email))
                .scalars()
                .first()
            )
            if existing:
                logger.error(
                    "[SQLDatabase] Duplicate email %s", logger.sanitize(user.email)
                )
                return None
            session.add(user)
            raw_program_ids = payload.get("program_ids")
            program_id_values: List[Any] = (
                cast(List[Any], raw_program_ids)
                if isinstance(raw_program_ids, list)
                else []
            )
            program_ids: List[str] = [
                str(program_id) for program_id in program_id_values if program_id
            ]
            if program_ids:
                programs = (
                    session.execute(select(Program).where(Program.id.in_(program_ids)))
                    .scalars()
                    .all()
                )
                user.programs = programs
            logger.info("[SQLDatabase] Created user %s", user_id)
            return user_id

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            record = (
                session.execute(
                    select(User)
                    .options(joinedload(User.programs))
                    .where(User.email == email.lower())
                )
                .unique()
                .scalars()
                .first()
            )
            return to_dict(record) if record else None

    def get_user_by_reset_token(self, reset_token: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            record = (
                session.execute(
                    select(User)
                    .options(joinedload(User.programs))
                    .where(User.password_reset_token == reset_token)
                )
                .unique()
                .scalars()
                .first()
            )
            return to_dict(record) if record else None

    def get_all_users(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            records = (
                session.execute(
                    select(User)
                    .options(joinedload(User.programs))
                    .where(User.institution_id == institution_id)
                )
                .unique()
                .scalars()
                .all()
            )
            return [to_dict(user) for user in records]

    def get_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            records = (
                session.execute(
                    select(User)
                    .options(joinedload(User.programs))
                    .where(User.role == role)
                )
                .unique()
                .scalars()
                .all()
            )
            return [to_dict(user) for user in records]

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            user = (
                session.execute(
                    select(User)
                    .options(joinedload(User.programs))
                    .where(User.id == user_id)
                )
                .unique()
                .scalars()
                .first()
            )
            return to_dict(user) if user else None

    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_user_by_id"""
        return self.get_user_by_id(user_id)

    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        with self.sql.session_scope() as session:
            user = session.get(User, user_id)
            if not user:
                logger.warning(f"[UPDATE_USER] User {user_id} not found in database")
                return False
            logger.info(
                f"[UPDATE_USER] Updating user {user_id}: {list(user_data.keys())}"
            )
            for key, value in user_data.items():
                if key == "program_ids":
                    programs = (
                        session.execute(
                            select(Program).where(Program.id.in_(value or []))
                        )
                        .scalars()
                        .all()
                    )
                    user.programs = programs
                elif hasattr(User, key):
                    setattr(user, key, value)
                user.extras[key] = value
            user.updated_at = datetime.now(timezone.utc)
            return True

    def update_user_active_status(self, user_id: str, active_user: bool) -> bool:
        status = "active" if active_user else "inactive"
        return self.update_user(user_id, {"account_status": status})

    def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """
        Update user profile fields only (first_name, last_name, display_name, email).
        Used for self-service profile updates by users.
        Institution admins can update email addresses.
        """
        allowed_fields = ["first_name", "last_name", "display_name", "email"]
        filtered_data = {k: v for k, v in profile_data.items() if k in allowed_fields}
        if not filtered_data:
            return False
        return self.update_user(user_id, filtered_data)

    def update_user_role(
        self, user_id: str, new_role: str, program_ids: Optional[List[str]] = None
    ) -> bool:
        """
        Update user's role and program associations.
        Used by admins to change user roles and assignments.
        """
        update_data: Dict[str, Any] = {"role": new_role}
        if program_ids is not None:
            update_data["program_ids"] = program_ids
        return self.update_user(user_id, update_data)

    def deactivate_user(self, user_id: str) -> bool:
        """
        Soft delete: Mark user account as suspended.
        Preserves user data for audit trail while preventing login.
        """
        return self.update_user(user_id, {"account_status": "suspended"})

    def calculate_and_update_active_users(self, institution_id: str) -> int:
        with self.sql.session_scope() as session:
            count = (
                session.execute(
                    select(func.count(User.id)).where(
                        and_(
                            User.institution_id == institution_id,
                            User.account_status == "active",
                        )
                    )
                ).scalar()
                or 0
            )
            institution = session.get(Institution, institution_id)
            if institution:
                extras: Dict[str, Any] = dict(institution.extras or {})
                billing: Dict[str, Any] = dict(extras.get("billing_settings", {}))
                billing["current_instructor_count"] = count
                extras["billing_settings"] = billing
                institution.extras = extras
            return count

    def update_user_extended(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        return self.update_user(user_id, update_data)

    def get_user_by_verification_token(self, token: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            user = (
                session.execute(
                    select(User).where(User.email_verification_token == token)
                )
                .scalars()
                .first()
            )
            return to_dict(user) if user else None

    # ------------------------------------------------------------------
    # Course operations
    # ------------------------------------------------------------------
    def create_course(self, course_data: Dict[str, Any]) -> Optional[str]:
        payload = dict(course_data)
        course_id = _ensure_uuid(payload.pop("course_id", None))
        course = Course(
            id=course_id,
            course_number=payload.get("course_number", "").upper(),
            course_title=payload.get("course_title", ""),
            department=payload.get("department"),
            credit_hours=payload.get("credit_hours", 3),
            institution_id=payload.get("institution_id"),
            active=payload.get("active", True),
            extras={**payload, "course_id": course_id},
        )

        with self.sql.session_scope() as session:
            session.add(course)
            raw_program_ids = payload.get("program_ids")
            program_id_values: List[Any] = (
                cast(List[Any], raw_program_ids)
                if isinstance(raw_program_ids, list)
                else []
            )
            program_ids: List[str] = [
                str(program_id) for program_id in program_id_values if program_id
            ]
            if program_ids:
                programs = (
                    session.execute(select(Program).where(Program.id.in_(program_ids)))
                    .scalars()
                    .all()
                )
                course.programs = programs
            logger.info("[SQLDatabase] Created course %s", course_id)
            return course_id

    def update_course(self, course_id: str, course_data: Dict[str, Any]) -> bool:
        """Update course details."""
        try:
            with self.sql.session_scope() as session:
                course = session.get(Course, course_id)
                if not course:
                    return False

                # Handle program associations separately
                if "program_ids" in course_data:
                    program_ids = course_data.pop("program_ids")
                    if program_ids is not None:
                        programs = (
                            session.execute(
                                select(Program).where(Program.id.in_(program_ids))
                            )
                            .scalars()
                            .all()
                        )
                        course.programs = list(programs)

                # Update regular fields
                for key, value in course_data.items():
                    if hasattr(course, key) and key != "id":
                        setattr(course, key, value)

                course.updated_at = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logger.error(f"Failed to update course: {e}")
            return False

    def update_course_programs(self, course_id: str, program_ids: List[str]) -> bool:
        """Update course-program associations."""
        return self.update_course(course_id, {"program_ids": program_ids})

    def delete_course(self, course_id: str) -> bool:
        """Delete course (CASCADE deletes offerings, sections)."""
        try:
            with self.sql.session_scope() as session:
                course = session.get(Course, course_id)
                if not course:
                    return False
                session.delete(course)
                return True
        except Exception as e:
            logger.error(f"Failed to delete course: {e}")
            return False

    def get_course_by_number(
        self, course_number: str, institution_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            query = select(Course).where(
                func.upper(Course.course_number) == course_number.upper()
            )
            if institution_id:
                query = query.where(Course.institution_id == institution_id)

            record = session.execute(query).scalars().first()
            return to_dict(record) if record else None

    def get_courses_by_department(
        self, institution_id: str, department: str
    ) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            records = (
                session.execute(
                    select(Course).where(
                        and_(
                            Course.institution_id == institution_id,
                            Course.department == department,
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(course) for course in records]

    def _build_course_outcome_extras(
        self, payload: Dict[str, Any], outcome_id: str
    ) -> Dict[str, Any]:
        extras_dict = {
            key: value
            for key, value in payload.items()
            if key not in COURSE_OUTCOME_EXCLUDED_FIELDS
        }
        extras_dict["outcome_id"] = outcome_id
        return extras_dict

    def _sync_course_outcome_to_existing_sections(
        self,
        session: Any,
        course_id: Optional[str],
        outcome_id: str,
        payload: Dict[str, Any],
    ) -> None:
        if not course_id:
            return

        offerings = (
            session.execute(
                select(CourseOffering).where(CourseOffering.course_id == course_id)
            )
            .scalars()
            .all()
        )
        if not offerings:
            return

        offering_ids = [offering.id for offering in offerings]
        sections = (
            session.execute(
                select(CourseSection).where(CourseSection.offering_id.in_(offering_ids))
            )
            .scalars()
            .all()
        )

        for section in sections:
            session.add(
                CourseSectionOutcome(
                    id=str(uuid.uuid4()),
                    section_id=section.id,
                    outcome_id=outcome_id,
                    students_took=payload.get("students_took"),
                    students_passed=payload.get("students_passed"),
                    assessment_tool=payload.get("assessment_tool"),
                    status=payload.get("status", "unassigned"),
                    approval_status="pending",
                )
            )

    def create_course_outcome(self, outcome_data: Dict[str, Any]) -> str:
        payload = dict(outcome_data)
        outcome_id = _ensure_uuid(payload.pop("outcome_id", None))

        outcome = CourseOutcome(
            id=outcome_id,
            course_id=payload.get("course_id"),
            program_id=payload.get("program_id"),
            clo_number=payload.get("clo_number"),
            description=payload.get("description", ""),
            assessment_method=payload.get("assessment_method"),
            active=payload.get("active", True),
            status=payload.get("status", "unassigned"),
            # New CLO assessment fields (corrected from demo feedback)
            students_took=payload.get("students_took"),
            students_passed=payload.get("students_passed"),
            assessment_tool=payload.get("assessment_tool"),
            # Workflow fields
            approval_status=payload.get("approval_status", "pending"),
            submitted_at=payload.get("submitted_at"),
            submitted_by_user_id=payload.get("submitted_by_user_id"),
            reviewed_at=payload.get("reviewed_at"),
            reviewed_by_user_id=payload.get("reviewed_by_user_id"),
            feedback_comments=payload.get("feedback_comments"),
            feedback_provided_at=payload.get("feedback_provided_at"),
            extras=self._build_course_outcome_extras(payload, outcome_id),
        )

        with self.sql.session_scope() as session:
            session.add(outcome)
            session.flush()
            self._sync_course_outcome_to_existing_sections(
                session,
                payload.get("course_id"),
                outcome_id,
                payload,
            )
            return outcome_id

    def update_course_outcome(
        self, outcome_id: str, outcome_data: Dict[str, Any]
    ) -> bool:
        """Update course outcome details."""
        try:
            with self.sql.session_scope() as session:
                outcome = session.get(CourseOutcome, outcome_id)
                if not outcome:
                    return False

                for key, value in outcome_data.items():
                    if hasattr(outcome, key) and key != "id":
                        setattr(outcome, key, value)

                outcome.last_modified = datetime.now(timezone.utc)
                return True
        except Exception as e:
            logger.error(f"Failed to update outcome: {e}")
            return False

    def update_outcome_assessment(
        self,
        outcome_id: str,
        students_took: Optional[int] = None,
        students_passed: Optional[int] = None,
        assessment_tool: Optional[str] = None,
    ) -> bool:
        """Update outcome assessment data (corrected field names from demo feedback)."""
        update_data: Dict[str, Any] = {}
        if students_took is not None:
            update_data["students_took"] = students_took
        if students_passed is not None:
            update_data["students_passed"] = students_passed
        if assessment_tool is not None:
            update_data["assessment_tool"] = assessment_tool
        return self.update_course_outcome(outcome_id, update_data)

    def delete_course_outcome(self, outcome_id: str) -> bool:
        try:
            with self.sql.session_scope() as session:
                outcome = session.get(CourseOutcome, outcome_id)
                if outcome:
                    # Manual cascade for section outcomes
                    session.execute(
                        delete(CourseSectionOutcome).where(
                            CourseSectionOutcome.outcome_id == outcome_id
                        )
                    )
                    session.delete(outcome)
                    return True
                return False
        except Exception as e:
            logger.error(f"Failed to delete outcome: {e}")
            return False

    def get_course_outcomes(self, course_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            outcomes = (
                session.execute(
                    select(CourseOutcome).where(CourseOutcome.course_id == course_id)
                )
                .scalars()
                .all()
            )
            return [to_dict(outcome) for outcome in outcomes]

    def get_course_outcomes_by_course_ids(
        self, course_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Bulk-fetch course outcomes for many courses in one query.

        Returns {course_id: [outcome_dict, ...]}. Avoids the N+1 of calling
        get_course_outcomes once per course (e.g. on the admin dashboard).
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        if not course_ids:
            return grouped
        with self.sql.session_scope() as session:
            outcomes = (
                session.execute(
                    select(CourseOutcome).where(
                        CourseOutcome.course_id.in_(set(course_ids))
                    )
                )
                .scalars()
                .all()
            )
            for outcome in outcomes:
                grouped.setdefault(str(outcome.course_id), []).append(to_dict(outcome))
        return grouped

    def get_course_outcome(self, outcome_id: str) -> Optional[Dict[str, Any]]:
        """Get single course outcome by ID (includes students_took, students_passed, assessment_tool)"""
        with self.sql.session_scope() as session:
            outcome = session.get(CourseOutcome, outcome_id)
            return to_dict(outcome) if outcome else None

    def get_section_outcome_by_course_outcome_and_section(
        self, course_outcome_id: str, section_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the CourseSectionOutcome for a specific section and course outcome."""
        with self.sql.session_scope() as session:
            section_outcome = (
                session.execute(
                    select(CourseSectionOutcome).where(
                        and_(
                            CourseSectionOutcome.outcome_id == course_outcome_id,
                            CourseSectionOutcome.section_id == section_id,
                        )
                    )
                )
                .scalars()
                .first()
            )
            return to_dict(section_outcome) if section_outcome else None

    def get_section_outcome(self, section_outcome_id: str) -> Optional[Dict[str, Any]]:
        """Get a single section outcome by ID."""
        with self.sql.session_scope() as session:
            # Use select instead of get for robustness against session state issues
            result = session.execute(
                select(CourseSectionOutcome).where(
                    CourseSectionOutcome.id == section_outcome_id
                )
            ).scalar_one_or_none()

            return to_dict(result) if result else None

    def get_section_outcomes_by_section(self, section_id: str) -> List[Dict[str, Any]]:
        """Get all section outcomes for a specific section."""
        with self.sql.session_scope() as session:
            section_outcomes = (
                session.execute(
                    select(CourseSectionOutcome).where(
                        CourseSectionOutcome.section_id == section_id
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(so) for so in section_outcomes]

    def get_section_outcomes_by_outcome(self, outcome_id: str) -> List[Dict[str, Any]]:
        """Get all section outcomes for a course outcome (template)."""
        with self.sql.session_scope() as session:
            section_outcomes = (
                session.execute(
                    select(CourseSectionOutcome).where(
                        CourseSectionOutcome.outcome_id == outcome_id
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(so) for so in section_outcomes]

    def update_section_outcome(
        self, section_outcome_id: str, outcome_data: Dict[str, Any]
    ) -> bool:
        """Update section outcome details (status, assessment data, workflow fields).

        If status changes, a history entry is recorded in the same transaction.
        """
        try:
            with self.sql.session_scope() as session:
                section_outcome = session.get(CourseSectionOutcome, section_outcome_id)
                if not section_outcome:
                    return False

                # Capture old status before update
                old_status = section_outcome.status
                new_status = outcome_data.get("status", old_status)

                # Apply updates
                for key, value in outcome_data.items():
                    if hasattr(section_outcome, key) and key != "id":
                        setattr(section_outcome, key, value)

                section_outcome.updated_at = datetime.now(timezone.utc)

                # If status changed, record history entry (same transaction)
                if new_status != old_status:
                    from src.models.models_sql import OutcomeHistory

                    event_label = self._status_to_event_label(new_status)
                    history_entry = OutcomeHistory(
                        section_outcome_id=section_outcome_id,
                        event=event_label,
                        occurred_at=datetime.now(timezone.utc),
                    )
                    session.add(history_entry)
                    logger.info(
                        f"[SQLDatabase] Recorded history: {event_label} for {section_outcome_id}"
                    )

                return True
        except Exception as e:
            logger.error(f"Failed to update section outcome: {e}")
            return False

    def _status_to_event_label(self, status: str) -> str:
        """Map status codes to human-readable event labels."""
        labels = {
            "awaiting_approval": "Submitted",
            "approval_pending": "Rework Requested",
            "approved": "Approved",
            "never_coming_in": "Marked NCI",
            "assigned": "Assigned",
            "in_progress": "In Progress",
        }
        return labels.get(status, status.replace("_", " ").title())

    def get_outcomes_by_status(
        self,
        institution_id: str,
        status: Optional[str],
        program_id: Optional[str] = None,
        term_id: Optional[str] = None,
        course_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get course outcomes filtered by status (or all if status is None)."""
        with self.sql.session_scope() as session:
            # Build query with joins to get institution filtering
            query = (
                select(CourseOutcome)
                .join(Course, CourseOutcome.course_id == Course.id)
                .options(selectinload(CourseOutcome.course))
                .where(Course.institution_id == institution_id)
            )

            # Add status filter only if specified (None = all statuses)
            if status is not None:
                query = query.where(CourseOutcome.status == status)

            # Add program filter if specified (Course has many-to-many relationship with Program)
            if program_id:
                from src.models.models_sql import course_program_table

                query = query.join(
                    course_program_table, Course.id == course_program_table.c.course_id
                ).where(course_program_table.c.program_id == program_id)

            # Add term filter if specified (filter via course_offerings.term_id)
            if term_id:
                from src.models.models_sql import CourseOffering

                query = query.join(
                    CourseOffering, Course.id == CourseOffering.course_id
                ).where(CourseOffering.term_id == term_id)

            # Add course filter if specified
            if course_id:
                query = query.where(Course.id == course_id)

            # Use distinct to prevent duplicates when joining through multiple sections
            # FIX: Do not use SQL-level DISTINCT (query.distinct()) because 'extras' column is JSON
            # and PostgreSQL JSON type does not support equality comparisons.
            # Deduplicate in Python instead.
            outcomes = session.execute(query).scalars().all()
            unique_outcomes = list({o.id: o for o in outcomes}.values())

            return [to_dict(outcome) for outcome in unique_outcomes]

    def get_section_outcomes_by_criteria(
        self,
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
        This is the source of truth for workflow audits (section-level granularity).

        Args:
            term_id: Single term filter (backward compat).
            term_ids: Multiple term filter; when provided, overrides term_id.

        Performance Note: Uses eager loading to fetch all related data in one query
        to avoid N+1 query problems when displaying audit pages.
        """
        with self.sql.session_scope() as session:
            # Start with CourseSectionOutcome and join up to Course/Institution
            # PERFORMANCE: Use joinedload to eagerly fetch related data (avoids N+1 queries)
            query = (
                select(CourseSectionOutcome)
                .join(
                    CourseSection, CourseSectionOutcome.section_id == CourseSection.id
                )
                .join(CourseOffering, CourseSection.offering_id == CourseOffering.id)
                .join(Course, CourseOffering.course_id == Course.id)
                .where(Course.institution_id == institution_id)
                # Eager load all relationships to avoid N+1 queries
                # CRITICAL: Use selectinload (not joinedload) to avoid duplicate paths
                .options(
                    # Load course outcome template with course and programs
                    selectinload(CourseSectionOutcome.outcome)
                    .selectinload(CourseOutcome.course)
                    .selectinload(Course.programs),
                    # Load section with instructor, offering, and term (single path)
                    selectinload(CourseSectionOutcome.section).selectinload(
                        CourseSection.instructor
                    ),
                    selectinload(CourseSectionOutcome.section)
                    .selectinload(CourseSection.offering)
                    .selectinload(CourseOffering.term),
                    # Load outcome history (selectinload for one-to-many)
                    selectinload(CourseSectionOutcome.history),
                )
            )

            if status and status != "all":
                query = query.where(CourseSectionOutcome.status == status)

            if course_id:
                query = query.where(Course.id == course_id)

            if section_id:
                query = query.where(CourseSection.id == section_id)

            if outcome_ids:
                query = query.where(CourseSectionOutcome.outcome_id.in_(outcome_ids))

            if term_ids:
                query = query.where(CourseOffering.term_id.in_(term_ids))
            elif term_id:
                query = query.where(CourseOffering.term_id == term_id)

            if program_id:
                query = query.join(
                    course_program_table, Course.id == course_program_table.c.course_id
                ).where(course_program_table.c.program_id == program_id)

            # Use .unique() to deduplicate results from joined eager loads
            results = session.execute(query).unique().scalars().all()

            # Force load all relationships before session closes (fixes lazy load issues)
            for result in results:
                # Access all eager-loaded relationships to force SQLAlchemy to fetch them
                _ = result.outcome
                if result.outcome:
                    _ = result.outcome.course
                    if result.outcome.course:
                        _ = result.outcome.course.programs
                _ = result.section
                if result.section:
                    _ = result.section.instructor
                    _ = result.section.offering
                    if result.section.offering:
                        _ = result.section.offering.term
                _ = result.history  # Trigger history load

            # Now convert to dicts with all data loaded
            return [to_dict(res) for res in results]

    def get_sections_by_course(self, course_id: str) -> List[Dict[str, Any]]:
        """Get all course sections for a given course."""
        with self.sql.session_scope() as session:
            # Get sections through course offering
            sections = (
                session.execute(
                    select(CourseSection)
                    .join(
                        CourseOffering, CourseSection.offering_id == CourseOffering.id
                    )
                    .where(CourseOffering.course_id == course_id)
                )
                .scalars()
                .all()
            )
            return [to_dict(section) for section in sections]

    def get_course_by_id(self, course_id: str) -> Optional[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            course = session.get(Course, course_id)
            return to_dict(course) if course else None

    def get_course(self, course_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_course_by_id"""
        return self.get_course_by_id(course_id)

    def get_all_courses(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            courses = (
                session.execute(
                    select(Course)
                    .where(Course.institution_id == institution_id)
                    .options(selectinload(Course.programs))
                )
                .scalars()
                .all()
            )
            return [to_dict(course) for course in courses]

    def get_all_instructors(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            instructors = (
                session.execute(
                    select(User).where(
                        and_(
                            User.institution_id == institution_id,
                            User.role == "instructor",
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [to_dict(user) for user in instructors]

    @staticmethod
    def _index_by_id(session: Any, model: Any, ids: Any) -> Dict[str, Any]:
        """Return {id: instance} for the given ids in a single query.

        Empty dict when there are no ids. Used to batch-load related rows and
        avoid N+1 lookups.
        """
        id_set = {value for value in ids if value}
        if not id_set:
            return {}
        rows = session.execute(select(model).where(model.id.in_(id_set))).scalars()
        return {row.id: row for row in rows}

    def get_all_sections(self, institution_id: str) -> List[Dict[str, Any]]:
        with self.sql.session_scope() as session:
            sections = (
                session.execute(
                    select(CourseSection)
                    .join(CourseOffering)
                    .where(CourseOffering.institution_id == institution_id)
                )
                .scalars()
                .all()
            )

            # Batch-load related entities (one query per type, not per section).
            # Previously this did 4 session.get() calls per section — an N+1 that
            # scaled with the data and made the admin dashboard fire ~1k queries.
            offerings = self._index_by_id(
                session, CourseOffering, (s.offering_id for s in sections)
            )
            courses = self._index_by_id(
                session, Course, (o.course_id for o in offerings.values())
            )
            terms = self._index_by_id(
                session, Term, (o.term_id for o in offerings.values())
            )
            instructors = self._index_by_id(
                session, User, (s.instructor_id for s in sections)
            )

            enriched_sections: List[Dict[str, Any]] = []
            for section in sections:
                section_dict = to_dict(section)

                offering = offerings.get(section.offering_id)
                if offering:
                    # Add course_id for easy filtering (e.g., in assessment UI)
                    section_dict["course_id"] = offering.course_id
                    section_dict["term_id"] = offering.term_id

                    course = courses.get(offering.course_id)
                    if course:
                        section_dict["course_number"] = course.course_number
                        section_dict["course_title"] = course.course_title

                    term = terms.get(offering.term_id)
                    if term:
                        section_dict["term_name"] = term.term_name

                if section.instructor_id:
                    instructor = instructors.get(section.instructor_id)
                    if instructor:
                        section_dict["instructor_name"] = (
                            f"{instructor.first_name} {instructor.last_name}"
                        )

                enriched_sections.append(section_dict)

            return enriched_sections

    def get_section_by_id(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Get single section by ID"""
        with self.sql.session_scope() as session:
            section = session.get(CourseSection, section_id)
            return to_dict(section) if section else None
