"""Abstract database interface for LoopCloser."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class DatabaseInterface(ABC):
    """Database abstraction contract."""

    # Institution operations
    @abstractmethod
    def create_institution(self, institution_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def update_institution(
        self, institution_id: str, institution_data: Dict[str, Any]
    ) -> bool:
        """Update institution details"""
        raise NotImplementedError

    @abstractmethod
    def delete_institution(self, institution_id: str) -> bool:
        """Delete institution (CASCADE deletes all related data)"""
        raise NotImplementedError

    @abstractmethod
    def get_institution_by_id(self, institution_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_institutions(self) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_default_mocku_institution(self) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def create_new_institution(
        self, institution_data: Dict[str, Any], admin_user_data: Dict[str, Any]
    ) -> Optional[Tuple[str, str]]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def get_institution_instructor_count(self, institution_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_institution_by_short_name(
        self, short_name: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    # User operations
    @abstractmethod
    def create_user(self, user_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_user_by_reset_token(self, reset_token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_users(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_user_by_id"""
        raise NotImplementedError

    @abstractmethod
    def update_user(self, user_id: str, user_data: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def update_user_active_status(self, user_id: str, active_user: bool) -> bool:
        raise NotImplementedError

    @abstractmethod
    def calculate_and_update_active_users(self, institution_id: str) -> int:
        raise NotImplementedError

    @abstractmethod
    def update_user_extended(self, user_id: str, update_data: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_user_by_verification_token(self, token: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> bool:
        """Update user profile fields (first_name, last_name, display_name)"""
        raise NotImplementedError

    @abstractmethod
    def update_user_role(
        self, user_id: str, new_role: str, program_ids: Optional[List[str]] = None
    ) -> bool:
        """Update user's role and program associations"""
        raise NotImplementedError

    @abstractmethod
    def deactivate_user(self, user_id: str) -> bool:
        """Soft delete: suspend user account"""
        raise NotImplementedError

    @abstractmethod
    def delete_user(self, user_id: str) -> bool:
        """Hard delete: remove user from database"""
        raise NotImplementedError

    # Course operations
    @abstractmethod
    def create_course(self, course_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def update_course(self, course_id: str, course_data: Dict[str, Any]) -> bool:
        """Update course details"""
        raise NotImplementedError

    @abstractmethod
    def update_course_programs(self, course_id: str, program_ids: List[str]) -> bool:
        """Update course-program associations"""
        raise NotImplementedError

    @abstractmethod
    def delete_course(self, course_id: str) -> bool:
        """Delete course (CASCADE deletes offerings and sections)"""
        raise NotImplementedError

    @abstractmethod
    def get_course_by_number(
        self, course_number: str, institution_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_courses_by_department(
        self, institution_id: str, department: str
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def create_course_outcome(self, outcome_data: Dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def update_course_outcome(
        self, outcome_id: str, outcome_data: Dict[str, Any]
    ) -> bool:
        """Update course outcome details"""
        raise NotImplementedError

    @abstractmethod
    def update_outcome_assessment(
        self,
        outcome_id: str,
        students_took: Optional[int] = None,
        students_passed: Optional[int] = None,
        assessment_tool: Optional[str] = None,
    ) -> bool:
        """Update outcome assessment data (corrected field names from demo feedback)"""
        raise NotImplementedError

    @abstractmethod
    def delete_course_outcome(self, outcome_id: str) -> bool:
        """Delete course outcome"""
        raise NotImplementedError

    @abstractmethod
    def get_course_outcomes(self, course_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_course_outcomes_by_course_ids(
        self, course_ids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Bulk-fetch course outcomes grouped by course_id (avoids N+1)."""
        raise NotImplementedError

    @abstractmethod
    def get_course_outcome(self, outcome_id: str) -> Optional[Dict[str, Any]]:
        """Get single course outcome by ID (includes assessment_data and narrative)"""
        raise NotImplementedError

    @abstractmethod
    def get_outcomes_by_status(
        self,
        institution_id: str,
        status: Optional[str],
        program_id: Optional[str] = None,
        term_id: Optional[str] = None,
        course_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get course outcomes filtered by status (or all if status is None)"""
        raise NotImplementedError

    @abstractmethod
    def get_course_by_id(self, course_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_course(self, course_id: str) -> Optional[Dict[str, Any]]:
        """Alias for get_course_by_id"""
        raise NotImplementedError

    @abstractmethod
    def get_all_courses(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_instructors(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_sections(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_section_by_id(self, section_id: str) -> Optional[Dict[str, Any]]:
        """Get single section by ID"""
        raise NotImplementedError

    @abstractmethod
    def get_sections_by_course(self, course_id: str) -> List[Dict[str, Any]]:
        """Get all sections for a specific course"""
        raise NotImplementedError

    @abstractmethod
    def get_section_outcome_by_course_outcome_and_section(
        self, course_outcome_id: str, section_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get section specific outcome"""
        raise NotImplementedError

    @abstractmethod
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
        """Get section outcomes filtered by various criteria"""
        raise NotImplementedError

    # Section Outcome operations (for section-level CLO workflow)
    @abstractmethod
    def get_section_outcome(self, section_outcome_id: str) -> Optional[Dict[str, Any]]:
        """Get a single section outcome by ID"""
        raise NotImplementedError

    @abstractmethod
    def get_section_outcomes_by_section(self, section_id: str) -> List[Dict[str, Any]]:
        """Get all section outcomes for a specific section"""
        raise NotImplementedError

    @abstractmethod
    def get_section_outcomes_by_outcome(self, outcome_id: str) -> List[Dict[str, Any]]:
        """Get all section outcomes for a course outcome (template)"""
        raise NotImplementedError

    @abstractmethod
    def update_section_outcome(
        self, section_outcome_id: str, outcome_data: Dict[str, Any]
    ) -> bool:
        """Update section outcome details (status, assessment data, etc.)"""
        raise NotImplementedError

    @abstractmethod
    def create_course_offering(self, offering_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def update_course_offering(
        self, offering_id: str, offering_data: Dict[str, Any]
    ) -> bool:
        """Update course offering details"""
        raise NotImplementedError

    @abstractmethod
    def delete_course_offering(self, offering_id: str) -> bool:
        """Delete course offering (CASCADE deletes sections)"""
        raise NotImplementedError

    @abstractmethod
    def get_course_offering(self, offering_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_course_offering_by_course_and_term(
        self, course_id: str, term_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_course_offerings(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # Term operations
    @abstractmethod
    def create_term(self, term_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def update_term(self, term_id: str, term_data: Dict[str, Any]) -> bool:
        """Update term details"""
        raise NotImplementedError

    @abstractmethod
    def delete_term(self, term_id: str) -> bool:
        """Delete term (CASCADE deletes offerings and sections)"""
        raise NotImplementedError

    @abstractmethod
    def get_term_by_name(
        self, name: str, institution_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_active_terms(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_terms(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_term_by_id(self, term_id: str) -> Optional[Dict[str, Any]]:
        """Get single term by ID"""
        raise NotImplementedError

    @abstractmethod
    def get_sections_by_term(self, term_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # Section operations
    @abstractmethod
    def create_course_section(self, section_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def update_course_section(
        self, section_id: str, section_data: Dict[str, Any]
    ) -> bool:
        """Update course section details"""
        raise NotImplementedError

    @abstractmethod
    def assign_instructor(self, section_id: str, instructor_id: str) -> bool:
        """Assign instructor to a section"""
        raise NotImplementedError

    @abstractmethod
    def delete_course_section(self, section_id: str) -> bool:
        """Delete course section"""
        raise NotImplementedError

    @abstractmethod
    def get_sections_by_instructor(self, instructor_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # Program operations
    @abstractmethod
    def create_program(self, program_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def get_programs_by_institution(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_program_by_id(self, program_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_program_by_name_and_institution(
        self, program_name: str, institution_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update_program(self, program_id: str, updates: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_program(self, program_id: str, reassign_to_program_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_courses_by_program(self, program_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_programs_for_course(self, course_id: str) -> List[Dict[str, Any]]:
        """Get all programs that a course is attached to"""
        raise NotImplementedError

    @abstractmethod
    def get_program_admins(self, program_id: str) -> List[Dict[str, Any]]:
        """Get all users with program_admin role for a specific program"""
        raise NotImplementedError

    @abstractmethod
    def get_unassigned_courses(self, institution_id: str) -> List[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def assign_course_to_default_program(
        self, course_id: str, institution_id: str
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def add_course_to_program(self, course_id: str, program_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def remove_course_from_program(self, course_id: str, program_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def bulk_add_courses_to_program(
        self, course_ids: List[str], program_id: str
    ) -> Dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def bulk_remove_courses_from_program(
        self, course_ids: List[str], program_id: str
    ) -> Dict[str, Any]:
        raise NotImplementedError

    # Invitation operations
    @abstractmethod
    def create_invitation(self, invitation_data: Dict[str, Any]) -> Optional[str]:
        raise NotImplementedError

    @abstractmethod
    def get_invitation_by_id(self, invitation_id: str) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_invitation_by_token(
        self, invitation_token: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_invitation_by_email(
        self, email: str, institution_id: str
    ) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def update_invitation(self, invitation_id: str, updates: Dict[str, Any]) -> bool:
        raise NotImplementedError

    @abstractmethod
    def list_invitations(
        self, institution_id: str, status: Optional[str], limit: int, offset: int
    ) -> List[Dict[str, Any]]:
        raise NotImplementedError

    # Audit log operations
    @abstractmethod
    def create_audit_log(self, audit_data: Dict[str, Any]) -> bool:
        """Create audit log entry"""
        raise NotImplementedError

    @abstractmethod
    def get_audit_logs_by_entity(
        self, entity_type: str, entity_id: str, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get audit history for specific entity"""
        raise NotImplementedError

    @abstractmethod
    def get_audit_logs_by_user(
        self,
        user_id: str,
        start_date: Optional[Any] = None,
        end_date: Optional[Any] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get all activity by specific user"""
        raise NotImplementedError

    @abstractmethod
    def get_recent_audit_logs(
        self, institution_id: Optional[str] = None, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get recent system activity"""
        raise NotImplementedError

    @abstractmethod
    def get_audit_logs_filtered(
        self,
        start_date: Any,
        end_date: Any,
        entity_type: Optional[str] = None,
        user_id: Optional[str] = None,
        institution_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get filtered audit logs for export"""
        raise NotImplementedError

    # Instructor Reminder operations
    @abstractmethod
    def create_reminder(
        self,
        section_id: str,
        instructor_id: str,
        sent_by: Optional[str] = None,
        reminder_type: str = "individual",
        message_preview: Optional[str] = None,
    ) -> Optional[str]:
        """Record a reminder email sent to an instructor."""
        raise NotImplementedError

    @abstractmethod
    def get_reminders_by_section(self, section_id: str) -> List[Dict[str, Any]]:
        """Get all reminders sent for a specific section."""
        raise NotImplementedError

    @abstractmethod
    def get_reminders_by_instructor(self, instructor_id: str) -> List[Dict[str, Any]]:
        """Get all reminders sent to a specific instructor."""
        raise NotImplementedError

    # Outcome History operations
    @abstractmethod
    def add_outcome_history(self, section_outcome_id: str, event: str) -> bool:
        """Add a history entry for a section outcome (for manual events like reminders)."""
        raise NotImplementedError

    @abstractmethod
    def get_outcome_history(self, section_outcome_id: str) -> List[Dict[str, Any]]:
        """Get history entries for a section outcome, sorted by date DESC."""
        raise NotImplementedError

    # Program Outcome (PLO) operations
    @abstractmethod
    def create_program_outcome(self, outcome_data: Dict[str, Any]) -> str:
        """Create a new Program Level Outcome template."""
        raise NotImplementedError

    @abstractmethod
    def update_program_outcome(
        self, outcome_id: str, outcome_data: Dict[str, Any]
    ) -> bool:
        """Update a Program Level Outcome template."""
        raise NotImplementedError

    @abstractmethod
    def delete_program_outcome(self, outcome_id: str) -> bool:
        """Soft-delete a PLO by setting is_active=False."""
        raise NotImplementedError

    @abstractmethod
    def get_program_outcomes(
        self, program_id: str, include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """Get all PLOs for a program, ordered by plo_number."""
        raise NotImplementedError

    @abstractmethod
    def get_program_outcome(self, outcome_id: str) -> Optional[Dict[str, Any]]:
        """Get a single PLO by ID."""
        raise NotImplementedError

    # PLO Mapping (versioned draft/publish) operations
    @abstractmethod
    def get_or_create_plo_mapping_draft(
        self, program_id: str, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get the current draft mapping for a program, or create one.

        If a draft already exists, return it. Otherwise create a new draft,
        optionally copying entries from the latest published version.
        """
        raise NotImplementedError

    @abstractmethod
    def get_plo_mapping_draft(self, program_id: str) -> Optional[Dict[str, Any]]:
        """Get the current draft mapping for a program, or None."""
        raise NotImplementedError

    @abstractmethod
    def add_plo_mapping_entry(
        self,
        mapping_id: str,
        program_outcome_id: str,
        course_outcome_id: str,
    ) -> str:
        """Add a PLO↔CLO link to a draft mapping. Returns entry ID."""
        raise NotImplementedError

    @abstractmethod
    def remove_plo_mapping_entry(self, entry_id: str) -> bool:
        """Remove a PLO↔CLO link from a draft mapping."""
        raise NotImplementedError

    @abstractmethod
    def publish_plo_mapping(
        self,
        mapping_id: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish a draft mapping, assigning the next version number.

        Snapshots PLO descriptions into each entry for historical preservation.
        Returns the published mapping dict.
        """
        raise NotImplementedError

    @abstractmethod
    def discard_plo_mapping_draft(self, mapping_id: str) -> bool:
        """Discard (delete) a draft mapping and all its entries."""
        raise NotImplementedError

    @abstractmethod
    def get_plo_mapping(self, mapping_id: str) -> Optional[Dict[str, Any]]:
        """Get a single mapping by ID, including its entries."""
        raise NotImplementedError

    @abstractmethod
    def get_plo_mapping_by_version(
        self, program_id: str, version: int
    ) -> Optional[Dict[str, Any]]:
        """Get a published mapping by program and version number."""
        raise NotImplementedError

    @abstractmethod
    def get_published_plo_mappings(self, program_id: str) -> List[Dict[str, Any]]:
        """Get all published mappings for a program, ordered by version."""
        raise NotImplementedError

    @abstractmethod
    def get_latest_published_plo_mapping(
        self, program_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the most recent published mapping for a program."""
        raise NotImplementedError
