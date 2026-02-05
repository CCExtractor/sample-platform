"""Add WebVTT regression test

Revision ID: c1a2b3d4e5f6
Revises: b3ed927671bd
Create Date: 2026-01-04 21:05:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

# revision identifiers, used by Alembic.
revision = 'c1a2b3d4e5f6'
down_revision = 'b3ed927671bd'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # 1. Insert "Output Formats" category if not exists
    existing_cat = conn.execute(
        text("SELECT id FROM category WHERE name = 'Output Formats'")
    ).fetchone()

    if existing_cat is None:
        conn.execute(
            text("INSERT INTO category (name, description) VALUES ('Output Formats', 'Tests for specific output format generation')")
        )
        category_id = conn.execute(text("SELECT id FROM category WHERE name = 'Output Formats'")).fetchone()[0]
    else:
        category_id = existing_cat[0]

    # 2. Check if WebVTT regression test already exists
    existing_test = conn.execute(
        text("SELECT id FROM regression_test WHERE command = '-out=webvtt' AND sample_id = 1")
    ).fetchone()

    if existing_test is None:
        # 3. Insert the WebVTT regression test (sample_id=1 is sample1.ts)
        conn.execute(
            text("""
                INSERT INTO regression_test (sample_id, command, input_type, output_type, expected_rc, active, description)
                VALUES (1, '-out=webvtt', 'file', 'file', 0, 1, 'Validates WebVTT header generation on empty-caption input')
            """)
        )
        test_id = conn.execute(
            text("SELECT id FROM regression_test WHERE command = '-out=webvtt' AND sample_id = 1")
        ).fetchone()[0]

        # 4. Insert RegressionTestOutput with the golden content
        conn.execute(
            text("""
                INSERT INTO regression_test_output (regression_id, correct, correct_extension, expected_filename)
                VALUES (:test_id, 'WEBVTT\r\n\r\n', '.webvtt', 'sample1.webvtt')
            """),
            {"test_id": test_id}
        )

        # 5. Link test to category
        conn.execute(
            text("""
                INSERT INTO regression_test_category (regression_id, category_id)
                VALUES (:test_id, :cat_id)
            """),
            {"test_id": test_id, "cat_id": category_id}
        )


def downgrade():
    conn = op.get_bind()

    # Get the WebVTT test ID
    test_row = conn.execute(
        text("SELECT id FROM regression_test WHERE command = '-out=webvtt' AND sample_id = 1")
    ).fetchone()

    if test_row is not None:
        test_id = test_row[0]

        # Delete in reverse order of dependencies
        conn.execute(
            text("DELETE FROM regression_test_category WHERE regression_id = :test_id"),
            {"test_id": test_id}
        )
        conn.execute(
            text("DELETE FROM regression_test_output WHERE regression_id = :test_id"),
            {"test_id": test_id}
        )
        conn.execute(
            text("DELETE FROM regression_test WHERE id = :test_id"),
            {"test_id": test_id}
        )

    # Check if "Output Formats" category has any remaining tests
    cat_row = conn.execute(
        text("SELECT id FROM category WHERE name = 'Output Formats'")
    ).fetchone()

    if cat_row is not None:
        category_id = cat_row[0]
        remaining = conn.execute(
            text("SELECT COUNT(*) FROM regression_test_category WHERE category_id = :cat_id"),
            {"cat_id": category_id}
        ).fetchone()[0]

        if remaining == 0:
            conn.execute(
                text("DELETE FROM category WHERE id = :cat_id"),
                {"cat_id": category_id}
            )
