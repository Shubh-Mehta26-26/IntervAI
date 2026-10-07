from sqlalchemy import delete, select

from app.core.errors import fail
from app.models.identity import (
    Candidate,
    CandidateGoal,
    CandidatePreferences,
    Education,
    Experience,
)
from app.schemas.identity import (
    EducationInput,
    ExperienceInput,
    GoalInput,
    PreferencesInput,
    ProfileOut,
)


async def get_candidate(db, user_id, lock=False):
    query = select(Candidate).where(Candidate.user_id == user_id)
    if lock:
        query = query.with_for_update()
    candidate = await db.scalar(query)
    if candidate is None:
        fail(404, "profile_not_found", "Your candidate profile was not found.")
    return candidate


async def profile_out(db, user, candidate=None):
    candidate = candidate or await get_candidate(db, user.id)

    async def rows(model, fields, schema):
        records = (
            await db.scalars(
                select(model)
                .where(model.candidate_id == candidate.id)
                .order_by(model.created_at, model.id)
            )
        ).all()
        return [schema(**{field: getattr(row, field) for field in fields}) for row in records]

    prefs = await db.scalar(
        select(CandidatePreferences).where(CandidatePreferences.candidate_id == candidate.id)
    )
    return ProfileOut(
        id=candidate.id,
        user_id=user.id,
        display_name=user.display_name,
        email=user.email,
        **{
            field: getattr(candidate, field)
            for field in (
                "phone",
                "location",
                "headline",
                "biography",
                "timezone",
                "experience_months",
                "revision",
                "career_interests",
                "created_at",
                "updated_at",
            )
        },
        goals=await rows(CandidateGoal, GoalInput.model_fields, GoalInput),
        education=await rows(Education, EducationInput.model_fields, EducationInput),
        experience=await rows(Experience, ExperienceInput.model_fields, ExperienceInput),
        preferences=PreferencesInput(
            **{field: getattr(prefs, field) for field in PreferencesInput.model_fields}
        ),
    )


async def update_profile(db, user, payload):
    candidate = await get_candidate(db, user.id, lock=True)
    if candidate.revision != payload.expected_revision:
        fail(409, "profile_conflict", "Your profile changed in another tab. Reload before saving.")
    # Only omit unset top-level fields; nested records still need their schema defaults.
    data = {
        key: value for key, value in payload.model_dump().items() if key in payload.model_fields_set
    }
    data.pop("expected_revision")
    if "display_name" in data:
        user.display_name = data.pop("display_name")
    for key, model in [
        ("goals", CandidateGoal),
        ("education", Education),
        ("experience", Experience),
    ]:
        if key in data:
            await db.execute(delete(model).where(model.candidate_id == candidate.id))
            db.add_all([model(candidate_id=candidate.id, **record) for record in data.pop(key)])
    if "preferences" in data:
        prefs = await db.scalar(
            select(CandidatePreferences).where(CandidatePreferences.candidate_id == candidate.id)
        )
        for key, value in data.pop("preferences").items():
            setattr(prefs, key, value)
    for key, value in data.items():
        setattr(candidate, key, value)
    candidate.revision += 1
    await db.flush()
    await db.refresh(candidate)
    result = await profile_out(db, user, candidate)
    await db.commit()
    return result
