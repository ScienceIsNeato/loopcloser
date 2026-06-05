#!/usr/bin/env python3
"""Bootstrap the CEI demo institution (and optionally run the outcomes import).

Creates "College of Eastern Idaho (Demo)" (short_name ``CEI``) plus an admin
login so the CEI outcomes adapter is offered in the import UI and a human can
sign in to drive the upload. With ``--import <file>`` it also runs the import
end to end via the CEI outcomes adapter — handy for a CLI smoke test before the
UI maiden voyage.

Usage:
    python scripts/seed_cei_demo.py
    python scripts/seed_cei_demo.py --import "data/cei/FY25 BTT Division Outcomes Results.xlsx"
    python scripts/seed_cei_demo.py --import <file> --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import database_service as dbs
from src.services.password_service import hash_password

INSTITUTION_NAME = "College of Eastern Idaho (Demo)"
INSTITUTION_SHORT_NAME = "CEI"
ADMIN_EMAIL = "admin.demo@cei-demo.example"
ADMIN_PASSWORD = "Demo2024!"
ADAPTER_ID = "cei_outcomes_results_v1"


def ensure_institution() -> str:
    """Create or fetch the CEI demo institution; return its id."""
    existing = dbs.get_institution_by_short_name(INSTITUTION_SHORT_NAME)
    if existing:
        institution_id = existing["institution_id"]
        print(f"✓ Institution exists: {INSTITUTION_NAME} ({institution_id})")
        return institution_id

    institution_id = dbs.create_institution(
        {
            "name": INSTITUTION_NAME,
            "short_name": INSTITUTION_SHORT_NAME,
            "admin_email": ADMIN_EMAIL,
            "is_active": True,
        }
    )
    if not institution_id:
        raise RuntimeError("Failed to create CEI demo institution")
    print(f"✓ Created institution: {INSTITUTION_NAME} ({institution_id})")
    return institution_id


def ensure_admin(institution_id: str) -> None:
    """Create or fetch the CEI demo admin login."""
    if dbs.get_user_by_email(ADMIN_EMAIL):
        print(f"✓ Admin exists: {ADMIN_EMAIL}")
        return

    user_id = dbs.create_user(
        {
            "email": ADMIN_EMAIL,
            "first_name": "CEI",
            "last_name": "Demo Admin",
            "role": "institution_admin",
            "institution_id": institution_id,
            "account_status": "active",
            "email_verified": True,
            "password_hash": hash_password(ADMIN_PASSWORD),
        }
    )
    if not user_id:
        raise RuntimeError("Failed to create CEI demo admin")
    print(f"✓ Created admin: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")


def run_import(institution_id: str, file_path: str, dry_run: bool) -> int:
    """Run the outcomes import via the CEI adapter and print a summary."""
    from src.services.import_service import ConflictStrategy, ImportService

    if not os.path.exists(file_path):
        print(f"✗ Import file not found: {file_path}")
        return 1

    service = ImportService(institution_id=institution_id, verbose=False)
    result = service.import_excel_file(
        file_path=file_path,
        conflict_strategy=ConflictStrategy.USE_THEIRS,
        dry_run=dry_run,
        adapter_id=ADAPTER_ID,
    )

    stats = service.stats
    print("\n" + "=" * 60)
    print(f"IMPORT {'(DRY RUN) ' if dry_run else ''}SUMMARY")
    print("=" * 60)
    print(f"  success:          {result.success}")
    print(f"  records created:  {stats['records_created']}")
    print(f"  records updated:  {stats['records_updated']}")
    print(f"  records skipped:  {stats['records_skipped']}")
    print(f"  errors:           {len(stats['errors'])}")
    for err in stats["errors"][:10]:
        print(f"    - {err}")
    return 0 if result.success and not stats["errors"] else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the CEI demo environment")
    parser.add_argument(
        "--import",
        dest="import_file",
        default=None,
        help="Path to the CEI outcomes workbook to import after bootstrap",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate the import without writing rows",
    )
    args = parser.parse_args()

    print(f"Database: {os.environ.get('DATABASE_URL', '(default)')}")
    institution_id = ensure_institution()
    ensure_admin(institution_id)

    if args.import_file:
        return run_import(institution_id, args.import_file, args.dry_run)
    print("\nBootstrap complete. Upload the workbook via the import UI, or re-run")
    print("with --import <file> to load it from the CLI.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
