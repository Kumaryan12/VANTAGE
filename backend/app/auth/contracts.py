from typing import Literal

from pydantic import EmailStr, Field

from app.portfolios.schemas import StrictModel

RoleName = Literal["USER", "RESEARCH_REVIEWER", "RESEARCH_ADMIN", "PLATFORM_ADMIN"]


class Credentials(StrictModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)


class PasswordChange(StrictModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class RecoverAccount(StrictModel):
    token: str = Field(min_length=32, max_length=128)
    new_password: str = Field(min_length=15, max_length=128)


class WorkspaceSelection(StrictModel):
    scope_id: str = Field(min_length=64, max_length=64)


class UserStatus(StrictModel):
    active: bool = Field(strict=True)


class RoleChange(StrictModel):
    role: RoleName
    enabled: bool = Field(strict=True)


class ReviewerSelection(StrictModel):
    reviewer_id: str = Field(min_length=36, max_length=36)
    active: bool = Field(True, strict=True)
