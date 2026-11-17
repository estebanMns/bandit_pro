"""cámaras móviles

Bandit Mobile Camera: teléfonos vinculados por QR, códigos de vinculación de un solo uso y
sesiones de transmisión bajo demanda. Solo se guardan huellas (sha256) de códigos y tokens,
nunca audio ni video. Las tablas nacen con RLS para que la API pública de Supabase no las
exponga: todo pasa por el backend.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op

import bandit.shared.db

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TABLES = ("mobile_camera_devices", "mobile_camera_pairings", "mobile_camera_sessions")


def upgrade() -> None:
    op.create_table(
        "mobile_camera_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("establishment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_name", sa.String(length=120), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("device_token_hash", sa.String(length=64), nullable=False),
        sa.Column("is_available", sa.Boolean(), nullable=False),
        sa.Column("analysis_enabled", sa.Boolean(), nullable=False),
        sa.Column("camera_id", sa.Uuid(), nullable=True),
        sa.Column("last_seen", bandit.shared.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("created_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("updated_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["establishment_id"], ["establishments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("device_token_hash"),
    )
    with op.batch_alter_table("mobile_camera_devices", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_devices_establishment_id"),
            ["establishment_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_devices_user_id"), ["user_id"], unique=False
        )

    op.create_table(
        "mobile_camera_pairings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("establishment_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("pairing_code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("used_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("created_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["establishment_id"], ["establishments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pairing_code_hash"),
    )
    with op.batch_alter_table("mobile_camera_pairings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_pairings_establishment_id"),
            ["establishment_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_pairings_expires_at"), ["expires_at"], unique=False
        )

    op.create_table(
        "mobile_camera_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("establishment_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("requested_by_label", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("audio_enabled", sa.Boolean(), nullable=False),
        sa.Column("video_enabled", sa.Boolean(), nullable=False),
        sa.Column("media_path", sa.String(length=80), nullable=False),
        sa.Column("created_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("answer_by", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("expires_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=False),
        sa.Column("started_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("ended_at", bandit.shared.db.UtcDateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(["device_id"], ["mobile_camera_devices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["establishment_id"], ["establishments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("mobile_camera_sessions", schema=None) as batch_op:
        batch_op.create_index(
            "ix_mobile_camera_sessions_device_status", ["device_id", "status"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_sessions_establishment_id"),
            ["establishment_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_mobile_camera_sessions_expires_at"), ["expires_at"], unique=False
        )

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("mobile_camera_sessions")
    op.drop_table("mobile_camera_pairings")
    op.drop_table("mobile_camera_devices")
