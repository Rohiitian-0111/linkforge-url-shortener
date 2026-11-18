"""Users, link ownership and replay-safe click events.

Revision ID: 0001
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"))
    op.create_table("urls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("original_url", sa.Text, nullable=False),
        sa.Column("short_code", sa.String(32), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("click_count", sa.BigInteger, nullable=False),
        sa.UniqueConstraint("short_code", name="uq_urls_short_code"))
    op.create_index("ix_urls_user_created", "urls", ["user_id", "created_at"])
    op.create_table("click_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("url_id", sa.String(36), sa.ForeignKey("urls.id"), nullable=False),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("referrer", sa.String(253), nullable=False),
        sa.Column("device", sa.String(16), nullable=False))
    op.create_index("ix_click_events_url_time", "click_events", ["url_id", "clicked_at"])


def downgrade():
    op.drop_index("ix_click_events_url_time", table_name="click_events")
    op.drop_table("click_events")
    op.drop_index("ix_urls_user_created", table_name="urls")
    op.drop_table("urls")
    op.drop_table("users")
