from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.identity import Input


class VisionInput(Input):
    enabled: bool
    expected_revision: int = Field(ge=0)


class CameraNotice(Input):
    revision: int = Field(ge=0)
    notice: Literal["interrupted", "orientation_changed"]


class Detection(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    persons: int = Field(ge=0, le=100)
    person_confidence: float | None = Field(default=None, ge=0, le=1)
    phone: bool
    phone_confidence: float | None = Field(default=None, ge=0, le=1)
    detector: Literal[
        "ssd-mobilenet-v2-coco-2018-03-29", "ssd-mobilenet-v2-coco-2018-03-29-face-crops-v1"
    ] = "ssd-mobilenet-v2-coco-2018-03-29"
