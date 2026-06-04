"""
Import API routes.

Provides endpoints for Excel file import, validation, and progress tracking.
Supports role-based data import with conflict resolution strategies.
"""

import os
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request
from flask.typing import ResponseReturnValue

from src.api.utils import (
    DEFAULT_EXPORT_EXTENSION,
    get_current_institution_id_safe,
    get_current_user_safe,
    handle_api_error,
)
from src.services.auth_service import UserRole, login_required, permission_required
from src.services.import_service import import_excel
from src.utils.constants import ADAPTER_NOT_FOUND_MSG
from src.utils.logging_config import get_logger

# Create blueprint
imports_bp = Blueprint("imports", __name__, url_prefix="/api")

# Initialize logger
logger = get_logger(__name__)

# Simple in-memory progress tracking for imports
_progress_store: Dict[str, Dict[str, Any]] = {}
_progress_lock = threading.Lock()


def create_progress_tracker() -> str:
    """Create a new progress tracker and return its ID"""
    progress_id = str(uuid.uuid4())
    with _progress_lock:
        _progress_store[progress_id] = {
            "status": "starting",
            "percentage": 0,
            "message": "Initializing import...",
            "records_processed": 0,
            "total_records": 0,
            "created_at": time.time(),
        }
    return progress_id


def update_progress(progress_id: str, **kwargs: Any) -> None:
    """Update progress information"""
    with _progress_lock:
        if progress_id in _progress_store:
            _progress_store[progress_id].update(kwargs)


def get_progress(progress_id: str) -> Dict[str, Any]:
    """Get current progress information"""
    with _progress_lock:
        return _progress_store.get(progress_id, {})


def cleanup_progress(progress_id: str) -> None:
    """Remove progress tracker after completion"""
    with _progress_lock:
        _progress_store.pop(progress_id, None)


@imports_bp.route("/import/progress/<progress_id>", methods=["GET"])
def get_import_progress(progress_id: str) -> ResponseReturnValue:
    """Get the current progress of an import operation"""
    progress = get_progress(progress_id)
    if not progress:
        return jsonify({"error": "Progress ID not found"}), 404

    return jsonify(progress)


@imports_bp.route("/import/adapters", methods=["GET"])
@permission_required("import_data")
def list_import_adapters() -> ResponseReturnValue:
    """List import adapters available to the current user's institution.

    Used to populate the import-format dropdown so each institution sees the
    adapters bound to it (e.g. CEI's formats) plus any public adapters.
    """
    try:
        from src.adapters.adapter_registry import get_adapter_registry

        institution_id = get_current_institution_id_safe()
        registry = get_adapter_registry()
        registry.discover_adapters()

        adapters: List[Dict[str, str]] = []
        seen: set[str] = set()
        institution_adapters = (
            registry.get_adapters_for_institution(institution_id)
            if institution_id
            else []
        )
        for adapter in institution_adapters:
            if adapter["id"] not in seen:
                seen.add(adapter["id"])
                adapters.append({"id": adapter["id"], "name": adapter["name"]})
        for adapter in registry.get_all_adapters():
            if adapter.get("public") and adapter["id"] not in seen:
                seen.add(adapter["id"])
                adapters.append({"id": adapter["id"], "name": adapter["name"]})

        return jsonify({"success": True, "adapters": adapters})
    except Exception as e:
        return handle_api_error(e, "List adapters", "Failed to list import adapters")


@imports_bp.route("/import/validate", methods=["POST"])
@permission_required("import_data")
def validate_import_file() -> ResponseReturnValue:
    """
    Validate Excel file format without importing

    Form data:
    - file: Excel file upload
    - adapter_name: Import adapter to use (optional, default "cei_excel_adapter")
    """
    try:
        # Check if file was uploaded
        if "excel_file" not in request.files:
            return jsonify({"success": False, "error": "No Excel file provided"}), 400

        file = request.files["excel_file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400

        # Get parameters
        adapter_name = request.form.get("adapter_name", "cei_excel_adapter")

        # File type validation is handled by the adapter (adapter-driven architecture)
        # Adapters declare their supported formats via get_adapter_info()["supported_formats"]

        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=DEFAULT_EXPORT_EXTENSION
        ) as temp_file:
            file.save(temp_file.name)
            temp_file_path = temp_file.name

        try:
            # Perform dry run validation
            institution_id = get_current_institution_id_safe()
            if not institution_id:
                raise ValueError("Unable to determine current institution ID")

            result = import_excel(
                file_path=temp_file_path,
                institution_id=institution_id,
                conflict_strategy="use_theirs",
                dry_run=True,  # Always dry run for validation
                adapter_id=adapter_name,
            )

            # Create validation response
            validation_result: Dict[str, Any] = {
                "valid": result.success and len(result.errors) == 0,
                "records_found": result.records_processed,
                "potential_conflicts": result.conflicts_detected,
                "errors": result.errors,
                "warnings": result.warnings,
                "file_info": {"filename": file.filename, "adapter": adapter_name},
            }

            return jsonify({"success": True, "validation": validation_result})

        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_file_path)
            except OSError:
                # Ignore cleanup errors - file may already be deleted or locked
                pass

    except Exception as e:
        return handle_api_error(e, "Import validation", "Failed to validate file")


@imports_bp.route("/import/excel", methods=["POST"])
@login_required
def excel_import_api() -> ResponseReturnValue:
    """
    Import data from Excel file

    Supports role-based data import with conflict resolution strategies.

    Form Data:
        excel_file: Excel file (.xlsx, .xls)
        import_adapter: Adapter ID (e.g., cei_excel_format_v1)
        conflict_strategy: How to handle conflicts (use_theirs, use_mine, merge, manual_review)
        dry_run: Test mode without saving (true/false)
        verbose_output: Detailed output (true/false)
        delete_existing_db: Clear database before import (true/false)
        import_data_type: Type of data being imported

    Returns:
        200: Import successful
        400: Invalid request or file
        403: Permission denied
        500: Server error
    """
    try:
        # Validate request and extract parameters
        file, import_params = _validate_excel_import_request()

        # Check user permissions
        current_user, institution_id = _check_excel_import_permissions(
            import_params["import_data_type"]
        )

        # Process the import
        return _process_excel_import(file, current_user, institution_id, import_params)

    except ValueError as e:
        logger.warning(f"Invalid request for import: {e}")
        return jsonify({"success": False, "error": str(e)}), 400

    except PermissionError as e:
        logger.warning(f"Permission denied for import: {e}")
        return jsonify({"success": False, "error": str(e)}), 403

    except Exception as e:
        logger.error(f"Excel import error: {e}")
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Import failed",
                }
            ),
            500,
        )


def _validate_excel_import_request() -> Tuple[Any, Dict[str, Any]]:
    """Validate the Excel import request and extract parameters."""
    # Debug: Log request information
    logger.info("Excel import request received")
    logger.info("Request files: %s", list(request.files.keys()))
    logger.info("Request form: %s", dict(request.form))

    file = _get_excel_file_from_request()

    # Get form parameters (need adapter_id for validation)
    import_params: Dict[str, Any] = {
        "adapter_id": request.form.get("import_adapter", "cei_excel_format_v1"),
        "conflict_strategy": request.form.get("conflict_strategy", "use_theirs"),
        "dry_run": request.form.get("dry_run", "false").lower() == "true",
        "verbose_output": request.form.get("verbose_output", "false").lower() == "true",
        "import_data_type": request.form.get("import_data_type", "courses"),
    }

    # Validate file extension against adapter's supported formats
    from src.adapters.adapter_registry import AdapterRegistry

    registry = AdapterRegistry()
    adapter_id_value = import_params["adapter_id"]
    adapter_id = (
        str(adapter_id_value) if adapter_id_value is not None else "cei_excel_format_v1"
    )
    adapter = registry.get_adapter_by_id(adapter_id)

    if not adapter:
        raise ValueError(ADAPTER_NOT_FOUND_MSG.format(adapter_id=adapter_id))

    # Get supported extensions
    adapter_info = adapter.get_adapter_info()
    if not adapter_info:
        raise ValueError(f"Adapter info not available for: {adapter_id}")

    supported_formats = adapter_info.get("supported_formats", [])
    if not supported_formats:
        raise ValueError(f"No supported formats defined for adapter: {adapter_id}")

    # Validate file extension
    file_ext = Path(file.filename).suffix.lower()
    if not file_ext:
        raise ValueError("File has no extension")

    if file_ext not in supported_formats:
        raise ValueError(
            f"Invalid file format {file_ext} for adapter {adapter_id}. "
            f"Supported formats: {', '.join(supported_formats)}"
        )

    logger.info(f"File extension {file_ext} validated for adapter {adapter_id}")

    return file, import_params


ALLOWED_DEMO_FILE_PREFIXES = ("demos/", "test_data/", "tests/e2e/fixtures/")


def _validate_demo_file_path(demo_file_path: str) -> str:
    """Validate demo file path to prevent traversal and enforce allowed directories."""
    normalized_path = os.path.normpath(demo_file_path)
    if ".." in normalized_path or normalized_path.startswith("/"):
        logger.warning("Path traversal attempt blocked: %s", demo_file_path)
        raise ValueError("Invalid file path: path traversal not allowed")

    if not any(
        normalized_path.startswith(prefix) for prefix in ALLOWED_DEMO_FILE_PREFIXES
    ):
        logger.warning("Demo file path outside allowed directories: %s", demo_file_path)
        raise ValueError(
            f"Invalid file path: must be within {', '.join(ALLOWED_DEMO_FILE_PREFIXES)}"
        )

    if not os.path.isfile(normalized_path):
        raise ValueError(f"Demo file not found: {normalized_path}")

    logger.info("Using validated demo file path: %s", normalized_path)
    return normalized_path


def _get_excel_file_from_request() -> Any:
    """
    Extract the Excel file from the request.

    Priority:
    1) demo_file_path (validated filesystem path)
    2) uploaded excel_file (multipart upload)
    """
    demo_file_path = request.form.get("demo_file_path")
    if demo_file_path:
        normalized_path = _validate_demo_file_path(demo_file_path)
        # Create a minimal mock file object for downstream compatibility.
        return type(
            "DemoFile",
            (object,),
            {"filename": normalized_path, "demo_path": normalized_path},
        )()

    if "excel_file" not in request.files:
        logger.warning("No excel_file in request.files")
        raise ValueError("No Excel file provided")

    file = request.files["excel_file"]
    if not file.filename:
        logger.warning("Empty filename in uploaded file")
        raise ValueError("No file selected")

    logger.info(
        "File received: %s, size: %s",
        file.filename,
        file.content_length if hasattr(file, "content_length") else "unknown",
    )
    return file


def _check_excel_import_permissions(
    import_data_type: str,
) -> Tuple[Dict[str, Any], str]:
    """Check user permissions for Excel import."""
    # Get current user and check authentication
    current_user = get_current_user_safe()
    if not current_user:
        raise PermissionError("Authentication required")

    user_role_value = current_user.get("role")
    if not isinstance(user_role_value, str):
        raise PermissionError("Invalid user role")
    user_institution_id_value = current_user.get("institution_id")
    user_institution_id = (
        str(user_institution_id_value) if user_institution_id_value else None
    )

    # Determine institution_id based on user role and adapter
    institution_id = _determine_target_institution(user_institution_id)

    # Check role-based permissions
    _validate_import_permissions(user_role_value, import_data_type)

    return current_user, institution_id


def _determine_target_institution(user_institution_id: Optional[str]) -> str:
    """Determine the target institution for the import."""
    # SECURITY & DESIGN: All users (including site admins) import into their own institution
    # This enforces multi-tenant isolation and prevents cross-institution data injection
    # The institution context comes from authentication, NOT from adapters or CSV data
    if not user_institution_id:
        raise PermissionError("User has no associated institution")
    return user_institution_id


def _validate_import_permissions(user_role: str, import_data_type: str) -> None:
    """Validate that the user role can import the specified data type."""
    allowed_data_types: Dict[str, List[str]] = {
        UserRole.SITE_ADMIN.value: ["institutions", "programs", "courses", "users"],
        UserRole.INSTITUTION_ADMIN.value: [
            "programs",
            "courses",
            "faculty",
            "students",
        ],
        UserRole.PROGRAM_ADMIN.value: [],  # Program admins cannot import per requirements
        UserRole.INSTRUCTOR.value: [],  # Instructors cannot import
    }

    if user_role not in allowed_data_types:
        raise PermissionError("Invalid user role")

    if import_data_type not in allowed_data_types[user_role]:
        raise PermissionError(
            f"Permission denied: {user_role} cannot import {import_data_type}"
        )


def _process_excel_import(
    file: Any,
    current_user: Dict[str, Any],
    institution_id: str,
    import_params: Dict[str, Any],
) -> Tuple[Any, int]:
    """Process the Excel import with the validated parameters."""
    # Check if this is a demo file path (not an uploaded file)
    if hasattr(file, "demo_path"):
        # Use the demo file path directly
        temp_filepath = file.demo_path
        cleanup_temp = False
        logger.info(f"Using demo file: {temp_filepath}")
    else:
        # Sanitize filename for logging/display purposes only
        safe_filename = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename)
        if not safe_filename or safe_filename.startswith("."):
            safe_filename = f"upload_{hash(file.filename) % 10000}"

        # Use secure temporary file creation
        temp_file_prefix = (
            f"import_{current_user.get('user_id')}_{import_params['import_data_type']}_"
        )

        # Create secure temporary file
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=temp_file_prefix,
            suffix=f"_{safe_filename}",
            delete=False,
        ) as temp_file:
            file.save(temp_file)
            temp_filepath = temp_file.name
        cleanup_temp = True

    try:
        # Import the Excel processing function
        from src.services.import_service import import_excel

        # Execute the import
        result = import_excel(
            file_path=temp_filepath,
            institution_id=institution_id,
            conflict_strategy=import_params["conflict_strategy"],
            dry_run=import_params["dry_run"],
            adapter_id=import_params["adapter_id"],
            verbose=import_params["verbose_output"],
        )

        return (
            jsonify(
                {
                    "success": True,
                    "message": (
                        "Import completed successfully"
                        if not import_params["dry_run"]
                        else "Validation completed successfully"
                    ),
                    "records_processed": result.records_processed,
                    "records_created": result.records_created,
                    "records_updated": result.records_updated,
                    "records_skipped": result.records_skipped,
                    "conflicts_detected": result.conflicts_detected,
                    "execution_time": result.execution_time,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "dry_run": import_params["dry_run"],
                }
            ),
            200,
        )

    finally:
        # Clean up temporary file (but not demo files)
        if cleanup_temp and os.path.exists(temp_filepath):
            os.remove(temp_filepath)
