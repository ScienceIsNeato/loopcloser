"""Unit tests for dashboard_service."""

from typing import Any
from unittest.mock import patch

import pytest

from src.services.dashboard_service import DashboardService, DashboardServiceError


@pytest.fixture(name="service")
def dashboard_service_core_fixture() -> Any:
    return DashboardService()


class TestDashboardServiceSiteAdmin:
    @patch("src.services.dashboard_service.get_all_instructors")
    @patch("src.services.dashboard_service.get_all_users")
    @patch("src.services.dashboard_service.get_all_courses")
    @patch("src.services.dashboard_service.get_programs_by_institution")
    @patch("src.services.dashboard_service.get_active_terms")
    @patch("src.services.dashboard_service.get_all_sections")
    @patch("src.services.dashboard_service.get_all_institutions")
    def test_site_admin_aggregation(
        self,
        mock_institutions: Any,
        mock_sections: Any,
        mock_terms: Any,
        mock_programs: Any,
        mock_courses: Any,
        mock_users: Any,
        mock_instructors: Any,
        service: Any,
    ) -> None:
        mock_institutions.return_value = [
            {"institution_id": "inst-1", "name": "One"},
            {"institution_id": "inst-2", "name": "Two"},
        ]
        mock_programs.side_effect = [[{"id": "prog-1", "name": "Prog 1"}], []]
        mock_courses.side_effect = [[{"course_id": "c1"}], [{"course_id": "c2"}]]
        mock_users.side_effect = [[{"user_id": "u1", "role": "site_admin"}], []]
        mock_instructors.side_effect = [[{"user_id": "u1"}], []]
        mock_sections.side_effect = [[{"section_id": "s1"}], []]
        mock_terms.side_effect = [[{"term_id": "t1"}], []]

        data = service.get_dashboard_data({"role": "site_admin"})

        assert data["summary"]["institutions"] == 2
        assert data["summary"]["programs"] == 1
        assert data["summary"]["courses"] == 2
        assert data["summary"]["users"] == 1
        assert data["summary"]["faculty"] == 1
        assert data["metadata"]["data_scope"] == "system_wide"
        assert len(data["institutions"]) == 2
        assert data["institutions"][0]["name"] == "One"
        assert any(course["institution_id"] == "inst-2" for course in data["courses"])
        assert "activity" in data and len(data["activity"]) > 0
        assert "terms" in data and len(data["terms"]) == 1


class TestDashboardServiceScoped:
    @patch("src.services.dashboard_service.get_institution_by_id")
    @patch("src.services.dashboard_service.get_all_users")
    @patch("src.services.dashboard_service.get_all_courses")
    @patch("src.services.dashboard_service.get_programs_by_institution")
    @patch("src.services.dashboard_service.get_active_terms")
    @patch("src.services.dashboard_service.get_all_instructors")
    @patch("src.services.dashboard_service.get_all_sections")
    def test_institution_admin_scope(
        self,
        mock_sections: Any,
        mock_instructors: Any,
        mock_terms: Any,
        mock_programs: Any,
        mock_courses: Any,
        mock_users: Any,
        mock_institution: Any,
        service: Any,
    ) -> None:
        mock_programs.return_value = [
            {"program_id": "prog-1", "institution_id": "inst-1"}
        ]
        mock_courses.return_value = [
            {"course_id": "course-1", "program_ids": ["prog-1"]}
        ]
        mock_users.return_value = [
            {
                "user_id": "u1",
                "role": "instructor",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "program_ids": ["prog-1"],
            }
        ]
        mock_instructors.return_value = [
            {"user_id": "u1", "first_name": "Grace", "program_ids": ["prog-1"]}
        ]
        mock_sections.return_value = [
            {
                "section_id": "s1",
                "course_id": "course-1",
                "instructor_id": "u1",
                "enrollment": 10,
            }
        ]
        mock_terms.return_value = [
            {"term_id": "t1", "name": "Fall 2024", "status": "ACTIVE"}
        ]
        mock_institution.return_value = {"institution_id": "inst-1", "name": "Inst One"}

        data = service.get_dashboard_data(
            {"role": "institution_admin", "institution_id": "inst-1"}
        )

        assert data["metadata"]["data_scope"] == "institution"
        assert data["summary"]["programs"] == 1
        assert data["programs"][0]["institution_id"] == "inst-1"
        assert data["summary"]["faculty"] == 1
        assert data["institutions"][0]["name"] == "Inst One"
        assert data["program_overview"]
        assert data["faculty"][0]["user_id"] == "u1"

    @patch("src.services.dashboard_service.get_all_instructors")
    @patch("src.services.dashboard_service.get_all_sections")
    @patch("src.services.dashboard_service.get_courses_by_program")
    @patch("src.services.dashboard_service.get_programs_by_institution")
    @patch("src.services.dashboard_service.get_all_users")
    @patch("src.services.dashboard_service.get_active_terms")
    def test_program_admin_scope(
        self,
        mock_terms: Any,
        mock_users: Any,
        mock_programs: Any,
        mock_courses: Any,
        mock_sections: Any,
        mock_instructors: Any,
        service: Any,
    ) -> None:
        mock_programs.return_value = [
            {"program_id": "prog-1", "name": "Program 1", "institution_id": "inst-1"},
            {"program_id": "prog-2", "name": "Program 2", "institution_id": "inst-1"},
        ]
        # Same course appears in both programs - tests deduplication logic
        mock_courses.side_effect = [
            [{"course_id": "c1", "course_number": "CS-101", "program_ids": ["prog-1"]}],
            [{"course_id": "c1", "course_number": "CS-101", "program_ids": ["prog-2"]}],
        ]
        mock_sections.return_value = [
            {
                "section_id": "s1",
                "course_id": "c1",
                "instructor_id": "u1",
                "enrollment": 20,
            }
        ]
        mock_instructors.return_value = [
            {
                "user_id": "u1",
                "full_name": "Prof",
                "program_ids": ["prog-1"],
            }
        ]
        mock_users.return_value = [
            {
                "user_id": "u1",
                "role": "program_admin",
                "program_ids": ["prog-1"],
            }
        ]
        mock_terms.return_value = [{"term_id": "t1"}]

        data = service.get_dashboard_data(
            {
                "role": "program_admin",
                "institution_id": "inst-1",
                "program_ids": ["prog-1", "prog-2"],  # Admin has access to both
            }
        )

        assert data["metadata"]["data_scope"] == "program"
        assert len(data["programs"]) == 2  # Both programs
        # Course appears in both programs but should be deduplicated in courses list
        assert len(data["courses"]) == 1  # Only one course despite being in 2 programs
        assert data["courses"][0]["course_id"] == "c1"
        # The course should have both program IDs merged
        assert set(data["courses"][0]["program_ids"]) == {"prog-1", "prog-2"}
        assert data["sections"][0]["course_id"] == "c1"
        assert data["instructors"][0]["user_id"] == "u1"

    @patch("src.services.dashboard_service.get_programs_by_institution")
    @patch("src.services.dashboard_service.get_all_courses")
    @patch("src.services.dashboard_service.get_active_terms")
    @patch("src.services.dashboard_service.get_all_sections")
    def test_instructor_scope(
        self,
        mock_sections: Any,
        mock_terms: Any,
        mock_courses: Any,
        mock_programs: Any,
        service: Any,
    ) -> None:
        mock_sections.return_value = [
            {
                "section_id": "s1",
                "instructor_id": "u-instructor",
                "course_id": "c1",
                "status": "completed",
                "enrollment": 15,
            },
            {
                "section_id": "s2",
                "instructor_id": "someone-else",
                "course_id": "c2",
            },
        ]
        mock_courses.return_value = [
            {
                "course_id": "c1",
                "course_number": "CS-101",
                "course_title": "Intro",
                "program_ids": ["prog-1"],
            }
        ]
        mock_programs.return_value = [{"id": "prog-1", "name": "Program 1"}]
        mock_terms.return_value = [{"term_id": "t1"}]

        data = service.get_dashboard_data(
            {
                "role": "instructor",
                "institution_id": "inst-1",
                "user_id": "u-instructor",
                "program_ids": ["prog-1"],
            }
        )

        assert data["metadata"]["data_scope"] == "instructor"
        assert len(data["sections"]) == 1
        assert data["sections"][0]["institution_id"] == "inst-1"


class TestDashboardServiceEnrollmentHelpers:
    def test_total_enrollment_handles_invalid_values(self, service: Any) -> None:
        """Covers DashboardService._total_enrollment int() conversion error branches."""

        sections = [
            {"enrollment": "10"},
            {"enrollment": 5},
            {"enrollment": None},
            {"enrollment": "not-a-number"},
            {"enrollment": {"bad": "type"}},
        ]

        assert service._total_enrollment(sections) == 15


class TestDashboardServiceOfferingRollups:
    def test_build_offering_section_rollup_handles_missing_offering_and_invalid_enrollment(
        self, service: Any
    ) -> None:
        sections = [
            {
                "section_id": "s-missing",
                "enrollment": 10,
            },  # missing offering_id (skipped)
            {"section_id": "s1", "offering_id": "o1", "enrollment": "12"},
            {"section_id": "s2", "offering_id": "o1", "enrollment": "bad"},
            {"section_id": "s3", "offering_id": "o2", "enrollment": None},
        ]

        rollup = service._build_offering_section_rollup(sections)
        assert rollup["o1"]["section_count"] == 2
        assert rollup["o1"]["total_enrollment"] == 12  # bad becomes 0
        assert rollup["o2"]["section_count"] == 1
        assert rollup["o2"]["total_enrollment"] == 0

    def test_apply_offering_section_rollup_defaults_to_zero(self, service: Any) -> None:
        offering_data = {"o1": {"section_count": 2, "total_enrollment": 5}}
        enriched = service._apply_offering_section_rollup(
            {"offering_id": "o2"}, offering_data
        )
        assert enriched["section_count"] == 0
        assert enriched["total_enrollment"] == 0


class TestDashboardServiceCLOEnrichment:
    """Test CLO data enrichment functionality."""

    @patch("src.services.dashboard_service.get_course_outcomes_by_course_ids")
    def test_enrich_courses_with_clo_data_success(
        self, mock_get_clos: Any, service: Any
    ) -> None:
        """Test successful CLO data enrichment (bulk-fetched in one query)."""
        # Mock CLO data
        mock_clos = [
            {"clo_number": "CLO1", "description": "First learning outcome"},
            {"clo_number": "CLO2", "description": "Second learning outcome"},
        ]
        mock_get_clos.return_value = {
            "course-1": mock_clos,
            "course-2": mock_clos,
        }

        courses = [
            {"course_id": "course-1", "course_number": "CS-101"},
            {"id": "course-2", "course_number": "CS-201"},  # Test fallback to "id"
        ]

        result = service._enrich_courses_with_clo_data(courses)

        assert len(result) == 2
        assert result[0]["clo_count"] == 2
        assert result[0]["clos"] == mock_clos
        assert result[1]["clo_count"] == 2
        assert result[1]["clos"] == mock_clos

        # Verify CLOs were fetched in a single bulk call for all courses
        assert mock_get_clos.call_count == 1
        mock_get_clos.assert_called_once_with(["course-1", "course-2"])

    @patch("src.services.dashboard_service.get_course_outcomes_by_course_ids")
    def test_enrich_courses_with_clo_data_no_clos(
        self, mock_get_clos: Any, service: Any
    ) -> None:
        """Test CLO enrichment when no CLOs exist."""
        mock_get_clos.return_value = {}

        courses = [{"course_id": "course-1", "course_number": "CS-101"}]
        result = service._enrich_courses_with_clo_data(courses)

        assert result[0]["clo_count"] == 0
        assert result[0]["clos"] == []

    @patch("src.services.dashboard_service.get_course_outcomes_by_course_ids")
    def test_enrich_courses_with_clo_data_error_handling(
        self, mock_get_clos: Any, service: Any
    ) -> None:
        """Test CLO enrichment handles errors gracefully."""
        mock_get_clos.side_effect = Exception("Database error")

        courses = [{"course_id": "course-1", "course_number": "CS-101"}]
        result = service._enrich_courses_with_clo_data(courses)

        assert result[0]["clo_count"] == 0
        assert result[0]["clos"] == []

    def test_enrich_courses_with_clo_data_no_course_id(self, service: Any) -> None:
        """Test CLO enrichment when course has no ID."""
        courses = [{"course_number": "CS-101"}]  # No course_id or id field
        result = service._enrich_courses_with_clo_data(courses)

        assert result[0]["clo_count"] == 0
        assert result[0]["clos"] == []


class TestDashboardServiceFailures:
    def test_missing_user(self, service: Any) -> None:
        with pytest.raises(DashboardServiceError):
            service.get_dashboard_data(None)

    def test_missing_institution_for_admin(self, service: Any) -> None:
        with pytest.raises(DashboardServiceError):
            service.get_dashboard_data({"role": "institution_admin"})


class TestDashboardServiceHelpers:
    """Test helper methods in DashboardService"""

    def test_get_course_id_with_course_id_field(self, service: Any) -> None:
        """Test _get_course_id with course_id field"""
        course = {"course_id": "course-123", "name": "Test Course"}
        result = service._get_course_id(course)
        assert result == "course-123"

    def test_get_course_id_with_id_field(self, service: Any) -> None:
        """Test _get_course_id with id field"""
        course = {"id": "course-456", "name": "Test Course"}
        result = service._get_course_id(course)
        assert result == "course-456"

    def test_get_course_id_prefers_id_over_course_id(self, service: Any) -> None:
        """Test _get_course_id prefers id field when both exist"""
        course = {"id": "course-789", "course_id": "course-123", "name": "Test Course"}
        result = service._get_course_id(course)
        assert result == "course-789"

    def test_get_course_id_with_none_course(self, service: Any) -> None:
        """Test _get_course_id with None course"""
        result = service._get_course_id(None)
        assert result is None

    def test_get_course_id_with_empty_course(self, service: Any) -> None:
        """Test _get_course_id with course missing both id fields"""
        course = {"name": "Test Course"}
        result = service._get_course_id(course)
        assert result is None


class TestDashboardServiceHelperMethods:
    """Test helper methods for data organization and processing."""

    def test_group_courses_by_program(self, service: Any) -> None:
        """Test _group_courses_by_program helper method."""
        courses = [
            {"course_id": "MATH101", "program_ids": ["MATH", "STEM"]},
            {"course_id": "ENG101", "program_ids": ["ENG"]},
            {"course_id": "MATH201", "program_ids": ["MATH"]},
        ]

        with patch.object(service, "_course_program_ids") as mock_program_ids:
            mock_program_ids.side_effect = [
                ["MATH", "STEM"],  # MATH101
                ["ENG"],  # ENG101
                ["MATH"],  # MATH201
            ]

            result = service._group_courses_by_program(courses)

            assert len(result) == 3
            assert len(result["MATH"]) == 2
            assert len(result["STEM"]) == 1
            assert len(result["ENG"]) == 1
            assert result["MATH"][0]["course_id"] == "MATH101"
            assert result["MATH"][1]["course_id"] == "MATH201"

    def test_group_sections_by_course(self, service: Any) -> None:
        """Test _group_sections_by_course helper method."""
        sections = [
            {"section_id": "001", "course_id": "MATH101"},
            {"section_id": "002", "course_id": "MATH101"},
            {"section_id": "001", "courseId": "ENG101"},  # Different key
            {"section_id": "003"},  # No course_id
        ]

        result = service._group_sections_by_course(sections)

        assert len(result) == 2
        assert len(result["MATH101"]) == 2
        assert len(result["ENG101"]) == 1
        assert result["MATH101"][0]["section_id"] == "001"
        assert result["MATH101"][1]["section_id"] == "002"
        assert result["ENG101"][0]["section_id"] == "001"

    def test_process_program_courses(self, service: Any) -> None:
        """Test _process_program_courses helper method."""
        program_courses = [
            {
                "course_id": "MATH101",
                "course_number": "MATH 101",
                "course_title": "Algebra",
            },
            {"id": "MATH102", "number": "MATH 102", "title": "Calculus"},
            {"course_id": "MATH101"},  # Duplicate - should be skipped
        ]

        sections_by_course = {
            "MATH101": [{"enrollment": 25}, {"enrollment": 30}],
            "MATH102": [{"enrollment": 20}],
        }

        with patch.object(service, "_total_enrollment") as mock_enrollment:
            mock_enrollment.side_effect = [55, 20]  # Total for each course

            course_summaries, program_sections = service._process_program_courses(
                program_courses, sections_by_course
            )

            assert len(course_summaries) == 2
            assert len(program_sections) == 3  # 2 + 1 sections

            # Check first course summary
            assert course_summaries[0]["course_id"] == "MATH101"
            assert course_summaries[0]["course_number"] == "MATH 101"
            assert course_summaries[0]["course_title"] == "Algebra"
            assert course_summaries[0]["section_count"] == 2
            assert course_summaries[0]["enrollment"] == 55

            # Check second course summary
            assert course_summaries[1]["course_id"] == "MATH102"
            assert course_summaries[1]["course_number"] == "MATH 102"
            assert course_summaries[1]["course_title"] == "Calculus"
            assert course_summaries[1]["section_count"] == 1
            assert course_summaries[1]["enrollment"] == 20


class TestDashboardServiceErrorHandling:
    """Test error handling and edge cases in DashboardService."""

    def test_get_dashboard_data_unknown_role(self) -> None:
        """Test get_dashboard_data with unknown user role."""
        import pytest

        service = DashboardService()
        user = {"user_id": "user1", "role": "unknown_role", "institution_id": "inst1"}

        with pytest.raises(
            ValueError,
            match="Unknown user role: unknown_role",
        ):
            service.get_dashboard_data(user)

    def test_build_single_faculty_assignment_no_user_id(self) -> None:
        """Test _build_single_faculty_assignment returns None when member has no user_id."""
        service = DashboardService()

        member = {"name": "John Doe"}  # No user_id
        result = service._build_single_faculty_assignment(member, {}, {}, {})

        assert result is None

    def test_build_single_faculty_assignment_no_course_ids(self) -> None:
        """Test _build_single_faculty_assignment returns None when no courses found."""
        service = DashboardService()

        member = {"user_id": "user1", "name": "John Doe"}
        sections_by_instructor: dict[str, list[Any]] = {"user1": []}  # No sections

        result = service._build_single_faculty_assignment(
            member, sections_by_instructor, {}, {}
        )

        assert result is None

    def test_build_program_metrics_no_program_id(self) -> None:
        """Test _build_program_metrics skips programs with no ID."""
        service = DashboardService()

        programs = [{"name": "Program 1"}]  # No ID field

        with patch.object(service, "_get_program_id", return_value=None):
            metrics = service._build_program_metrics(programs, [], [], [])

            assert metrics == []
