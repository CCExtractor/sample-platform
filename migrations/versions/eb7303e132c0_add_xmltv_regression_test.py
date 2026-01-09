"""add_xmltv_regression_test

Revision ID: eb7303e132c0
Revises: c8f3a2b1d4e5
Create Date: 2026-01-06 21:43:46.009899

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eb7303e132c0'
down_revision = 'c8f3a2b1d4e5'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Check if the XMLTV regression test already exists
    existing_test = conn.execute(
        sa.text(
            "SELECT id FROM regression_test "
            "WHERE sample_id = 187 AND command = '--xmltv=1 --out=null'"
        )
    ).fetchone()

    if existing_test is not None:
        # Already present, nothing to do
        return

    # 2. Insert regression test
    conn.execute(
        sa.text(
            """
            INSERT INTO regression_test
                (sample_id, command, input_type, output_type, expected_rc, active, description)
            VALUES
                (187, '--xmltv=1 --out=null', 'file', 'null', 10, 1,
                 'Validates ATSC XMLTV generation from broadcast EPG data (VCT/ETT/EIT)')
            """
        )
    )

    # 3. Fetch newly created test id
    test_id = conn.execute(
        sa.text(
            "SELECT id FROM regression_test "
            "WHERE sample_id = 187 AND command = '--xmltv=1 --out=null'"
        )
    ).fetchone()[0]

    # 4. Get existing "General" category
    cat_row = conn.execute(
        sa.text("SELECT id FROM category WHERE name = 'General'")
    ).fetchone()

    # Should exist on production
    if cat_row is None:
        raise RuntimeError("Required 'General' category not found")

    category_id = cat_row[0]

    # 5. Link regression test to category
    conn.execute(
        sa.text(
            "INSERT INTO regression_test_category (regression_id, category_id) "
            "VALUES (:test_id, :category_id)"
        ),
        {"test_id": test_id, "category_id": category_id},
    )

    # 6. Insert expected XMLTV output (exit-code based validation)
    conn.execute(
        sa.text(
            """
            INSERT INTO regression_test_output
                (regression_id, correct, correct_extension, expected_filename, ignore)
            VALUES
                (:test_id, '', '.xml', '', 0)
            """
        ),
        {"test_id": test_id},
    )



def downgrade():
    conn = op.get_bind()

    test_row = conn.execute(

        sa.text(
            "SELECT id FROM regression_test "
            "WHERE sample_id = 187 AND command = '--xmltv=1 --out=null'"
        )
    ).fetchone()

    if test_row is None:
        return

    test_id = test_row[0]

    # Remove output first (FK dependency)
    conn.execute(
        sa.text(
            "DELETE FROM regression_test_output WHERE regression_id = :test_id"
        ),
        {"test_id": test_id},
    )

    # Remove category linkage
    conn.execute(
        sa.text(
            "DELETE FROM regression_test_category WHERE regression_id = :test_id"
        ),
        {"test_id": test_id},
    )

    # Remove regression test
    conn.execute(
        sa.text(
            "DELETE FROM regression_test WHERE id = :test_id"
        ),
        {"test_id": test_id},
    )

