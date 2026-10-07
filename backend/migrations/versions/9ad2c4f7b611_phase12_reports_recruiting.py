"""phase12 reports, recruiter access and worker health"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "9ad2c4f7b611"
down_revision = "6180c9689cfe"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_job_description_owner", "job_descriptions", ["id", "candidate_id"])
    op.create_unique_constraint("uq_interview_owner", "interviews", ["id", "candidate_id"])

    op.create_table(
        "reports",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("latest_version >= 0", name="ck_report_version"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["interview_id", "candidate_id"], ["interviews.id", "interviews.candidate_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "interview_id", name="uq_report_candidate_interview"),
        sa.UniqueConstraint("id", "candidate_id", name="uq_report_owner"),
    )
    op.create_table(
        "report_versions",
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("version > 0 AND schema_version > 0", name="ck_report_version_positive"),
        sa.ForeignKeyConstraint(["report_id", "candidate_id"], ["reports.id", "reports.candidate_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("report_id", "version", name="uq_report_version"),
        sa.UniqueConstraint("report_id", "source_fingerprint", name="uq_report_fingerprint"),
    )
    op.create_index("ix_report_versions_candidate", "report_versions", ["candidate_id", "generated_at"])

    op.create_table(
        "recruiter_jobs",
        sa.Column("recruiter_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("company", sa.String(length=160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="active"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('active','paused','closed')", name="ck_recruiter_job_status"),
        sa.CheckConstraint("version > 0", name="ck_recruiter_job_version"),
        sa.ForeignKeyConstraint(["recruiter_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "recruiter_user_id", name="uq_recruiter_job_owner"),
    )
    op.create_index("ix_recruiter_jobs_status_created", "recruiter_jobs", ["status", "created_at"])

    op.create_table(
        "recruiter_applications",
        sa.Column("recruiter_user_id", sa.Uuid(), nullable=False),
        sa.Column("recruiter_job_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_job_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="applied"),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("status IN ('applied','withdrawn','closed')", name="ck_application_status"),
        sa.CheckConstraint("consent_version > 0", name="ck_application_consent_version"),
        sa.ForeignKeyConstraint(["recruiter_job_id", "recruiter_user_id"], ["recruiter_jobs.id", "recruiter_jobs.recruiter_user_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_job_id", "candidate_id"], ["job_descriptions.id", "job_descriptions.candidate_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "recruiter_job_id", name="uq_application_candidate_job"),
        sa.UniqueConstraint("id", "candidate_id", "recruiter_user_id", name="uq_application_owner"),
    )
    op.create_index("ix_recruiter_applications_owner", "recruiter_applications", ["recruiter_user_id", "recruiter_job_id", "status"])
    op.create_index("ix_recruiter_applications_candidate", "recruiter_applications", ["candidate_id", "created_at"])

    op.create_table(
        "admin_audit",
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("id", sa.Uuid(), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_admin_audit_created", "admin_audit", ["created_at"])

    op.create_table(
        "worker_heartbeats",
        sa.Column("service", sa.String(length=40), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.CheckConstraint("status IN ('running','degraded')", name="ck_worker_status"),
        sa.PrimaryKeyConstraint("service"),
    )
    op.execute("""CREATE FUNCTION preserve_report_version() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Report versions are immutable'; END $$""")
    op.execute("CREATE TRIGGER report_version_immutable BEFORE UPDATE OR DELETE ON report_versions FOR EACH ROW EXECUTE FUNCTION preserve_report_version()")
    op.execute("""CREATE FUNCTION preserve_admin_audit() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Administrative audit is append-only'; END $$""")
    op.execute("CREATE TRIGGER admin_audit_immutable BEFORE UPDATE OR DELETE ON admin_audit FOR EACH ROW EXECUTE FUNCTION preserve_admin_audit()")


def downgrade():
    op.execute("DROP TRIGGER admin_audit_immutable ON admin_audit")
    op.execute("DROP FUNCTION preserve_admin_audit()")
    op.execute("DROP TRIGGER report_version_immutable ON report_versions")
    op.execute("DROP FUNCTION preserve_report_version()")
    op.drop_table("worker_heartbeats")
    op.drop_index("ix_admin_audit_created", table_name="admin_audit")
    op.drop_table("admin_audit")
    op.drop_index("ix_recruiter_applications_candidate", table_name="recruiter_applications")
    op.drop_index("ix_recruiter_applications_owner", table_name="recruiter_applications")
    op.drop_table("recruiter_applications")
    op.drop_index("ix_recruiter_jobs_status_created", table_name="recruiter_jobs")
    op.drop_table("recruiter_jobs")
    op.drop_index("ix_report_versions_candidate", table_name="report_versions")
    op.drop_table("report_versions")
    op.drop_table("reports")
    op.drop_constraint("uq_interview_owner", "interviews", type_="unique")
    op.drop_constraint("uq_job_description_owner", "job_descriptions", type_="unique")
