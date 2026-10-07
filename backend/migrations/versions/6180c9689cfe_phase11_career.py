"""phase11_career"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "6180c9689cfe"
down_revision = "3ebc31f2890a"
branch_labels = None
depends_on = None


ROLE_SEED = [
    {
        "slug": "software-engineer",
        "name": "Software Engineer",
        "description": "Design, implement, test, and maintain software.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Data Structures",
                "aliases": ["data structures", "arrays", "hash tables", "binary search"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Software Testing",
                "aliases": ["Software Testing"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "System Design",
                "aliases": ["System Design"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Git",
                "aliases": ["Git"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Design, implement, test, and maintain software."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "backend-engineer",
        "name": "Backend Engineer",
        "description": "Build services, database interactions, and reliable APIs.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "SQL",
                "aliases": ["sql", "dbms", "databases"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": ["normalization", "transactions", "indexing", "deadlocks"],
            },
            {
                "skill": "APIs",
                "aliases": ["rest api", "rest apis", "api design", "apis"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Docker",
                "aliases": ["Docker"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "System Design",
                "aliases": ["System Design"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Build services, database interactions, and reliable APIs."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "frontend-engineer",
        "name": "Frontend Engineer",
        "description": "Build accessible browser experiences and maintain client applications.",
        "requirements": [
            {
                "skill": "JavaScript",
                "aliases": ["javascript", "js"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "HTML/CSS",
                "aliases": ["html", "css"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "React",
                "aliases": ["React"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "TypeScript",
                "aliases": ["TypeScript"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Accessibility",
                "aliases": ["Accessibility"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": [
            "Build accessible browser experiences and maintain client applications."
        ],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "full-stack-engineer",
        "name": "Full Stack Engineer",
        "description": "Connect browser experiences to application services and data.",
        "requirements": [
            {
                "skill": "JavaScript",
                "aliases": ["javascript", "js"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "SQL",
                "aliases": ["sql", "dbms", "databases"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": ["normalization", "transactions", "indexing", "deadlocks"],
            },
            {
                "skill": "APIs",
                "aliases": ["rest api", "rest apis", "api design", "apis"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "React",
                "aliases": ["React"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Docker",
                "aliases": ["Docker"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Connect browser experiences to application services and data."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "ai-ml-engineer",
        "name": "AI/ML Engineer",
        "description": "Develop, evaluate, and integrate machine-learning systems.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Machine Learning",
                "aliases": ["machine learning", "ml"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Model Evaluation",
                "aliases": ["model evaluation"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Deep Learning",
                "aliases": ["Deep Learning"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "MLOps",
                "aliases": ["MLOps"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Cloud",
                "aliases": ["Cloud"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Develop, evaluate, and integrate machine-learning systems."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "data-scientist",
        "name": "Data Scientist",
        "description": "Analyze data, test hypotheses, and evaluate predictive models.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Statistics",
                "aliases": ["Statistics"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Machine Learning",
                "aliases": ["machine learning", "ml"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "SQL",
                "aliases": ["sql", "dbms", "databases"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": ["normalization", "transactions", "indexing", "deadlocks"],
            },
            {
                "skill": "Data Visualization",
                "aliases": ["Data Visualization"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Analyze data, test hypotheses, and evaluate predictive models."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "data-engineer",
        "name": "Data Engineer",
        "description": "Build reliable data ingestion, transformation, and delivery pipelines.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "SQL",
                "aliases": ["sql", "dbms", "databases"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": ["normalization", "transactions", "indexing", "deadlocks"],
            },
            {
                "skill": "Data Pipelines",
                "aliases": ["Data Pipelines"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Cloud",
                "aliases": ["Cloud"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Distributed Systems",
                "aliases": ["Distributed Systems"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": [
            "Build reliable data ingestion, transformation, and delivery pipelines."
        ],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "devops-engineer",
        "name": "DevOps Engineer",
        "description": "Automate delivery and operate reliable software environments.",
        "requirements": [
            {
                "skill": "Linux",
                "aliases": ["Linux"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "CI/CD",
                "aliases": ["CI/CD"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Docker",
                "aliases": ["Docker"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Cloud",
                "aliases": ["Cloud"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Monitoring",
                "aliases": ["Monitoring"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Automate delivery and operate reliable software environments."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "cloud-engineer",
        "name": "Cloud Engineer",
        "description": "Design and operate cloud infrastructure and connectivity.",
        "requirements": [
            {
                "skill": "Cloud",
                "aliases": ["Cloud"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Networking",
                "aliases": ["Networking"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Linux",
                "aliases": ["Linux"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Infrastructure as Code",
                "aliases": ["Infrastructure as Code"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Security",
                "aliases": ["Security"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Design and operate cloud infrastructure and connectivity."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "nlp-engineer",
        "name": "NLP Engineer",
        "description": "Build and evaluate systems processing language.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "NLP",
                "aliases": ["NLP"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Model Evaluation",
                "aliases": ["model evaluation"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Deep Learning",
                "aliases": ["Deep Learning"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "RAG",
                "aliases": ["RAG"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Build and evaluate systems processing language."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "computer-vision-engineer",
        "name": "Computer Vision Engineer",
        "description": "Develop and evaluate image-processing systems.",
        "requirements": [
            {
                "skill": "Python",
                "aliases": ["python"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Computer Vision",
                "aliases": ["Computer Vision"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Model Evaluation",
                "aliases": ["model evaluation"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Deep Learning",
                "aliases": ["Deep Learning"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Deployment",
                "aliases": ["Deployment"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": ["Develop and evaluate image-processing systems."],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
    {
        "slug": "technical-product",
        "name": "Technical Product",
        "description": "Clarify product problems and coordinate evidence-informed "
        "technical delivery.",
        "requirements": [
            {
                "skill": "Product Discovery",
                "aliases": ["Product Discovery"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Communication",
                "aliases": ["Communication"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Data Analysis",
                "aliases": ["Data Analysis"],
                "requirement": "required",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "APIs",
                "aliases": ["rest api", "rest apis", "api design", "apis"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
            {
                "skill": "Software Testing",
                "aliases": ["Software Testing"],
                "requirement": "preferred",
                "certainty": "illustrative",
                "related_concepts": [],
            },
        ],
        "responsibilities": [
            "Clarify product problems and coordinate evidence-informed technical delivery."
        ],
        "version": 1,
        "provenance": {
            "kind": "project_authored",
            "source": "IntervAI career-roles-v1",
            "scope": "Illustrative exploration taxonomy; not universal "
            "hiring requirements or verified labour-market "
            "data.",
        },
    },
]


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "career_roles",
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=600), nullable=False),
        sa.Column("requirements", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("responsibilities", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "career_analyses",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("version > 0", name="ck_career_analysis_version"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "fingerprint", name="uq_career_analysis_snapshot"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_career_analysis_version"),
        sa.UniqueConstraint("id", "candidate_id", name="uq_career_analysis_owner"),
    )
    op.create_index(
        "ix_career_analysis_candidate_time",
        "career_analyses",
        ["candidate_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "career_profiles",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("preferences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dismissed_roles", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("revision >= 0", name="ck_career_profile_revision"),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id"),
    )
    op.create_table(
        "career_advice",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("claim_id", sa.Uuid(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("use_rag", sa.Boolean(), nullable=False),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_status", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("error_code", sa.String(length=40), nullable=True),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('pending','completed','failed') AND attempts BETWEEN 1 AND 3",
            name="ck_career_advice_state",
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id"),
    )
    op.create_table(
        "career_choices",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("role_slug", sa.String(length=80), nullable=False),
        sa.Column("skill", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pursue','dismissed') AND revision >= 0", name="ck_career_choice_state"
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("analysis_id", "role_slug", "skill", name="uq_career_choice"),
    )
    op.create_table(
        "career_requests",
        sa.Column("candidate_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.Uuid(), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=False),
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["analysis_id", "candidate_id"],
            ["career_analyses.id", "career_analyses.candidate_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "request_key", name="uq_career_request_key"),
    )
    role_table = sa.table(
        "career_roles",
        sa.column("slug", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("requirements", postgresql.JSONB),
        sa.column("responsibilities", postgresql.JSONB),
        sa.column("provenance", postgresql.JSONB),
        sa.column("version", sa.Integer),
    )
    op.bulk_insert(role_table, ROLE_SEED)
    op.execute("""CREATE FUNCTION career_preserve_history() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF TG_TABLE_NAME = 'career_advice' THEN
            IF OLD.status <> 'completed' THEN RETURN NEW; END IF;
        END IF;
        RAISE EXCEPTION 'Career snapshot history is immutable';
    END $$""")
    for table in ["career_analyses", "career_requests", "career_advice"]:
        op.execute(
            f"CREATE TRIGGER preserve_career_history BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION career_preserve_history()"
        )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table("career_requests")
    op.drop_table("career_choices")
    op.drop_table("career_advice")
    op.drop_table("career_profiles")
    op.drop_index("ix_career_analysis_candidate_time", table_name="career_analyses")
    op.drop_table("career_analyses")
    op.drop_table("career_roles")
    op.execute("DROP FUNCTION career_preserve_history()")
    # ### end Alembic commands ###
