"""Typed records. The schema is the contract between harvest and everything after it."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field, field_validator


class Author(BaseModel):
    keyname: str
    forenames: str | None = None

    def display(self) -> str:
        return f"{self.forenames} {self.keyname}".strip() if self.forenames else self.keyname


class Paper(BaseModel):
    """One arXiv record, normalised.

    `arxiv_id` is the versionless id (2401.00001). Versions are tracked by
    `updated` so a re-harvest overwrites rather than duplicates.
    """

    arxiv_id: str
    title: str
    abstract: str
    categories: list[str] = Field(default_factory=list)
    primary_category: str
    authors: list[Author] = Field(default_factory=list)
    created: date
    updated: date | None = None
    doi: str | None = None
    license: str | None = None

    @field_validator("title", "abstract")
    @classmethod
    def _collapse_whitespace(cls, v: str) -> str:
        # OAI records wrap text at arbitrary column widths; unwrapped text is
        # what the chunkers and the embedder should see.
        return " ".join(v.split())

    @property
    def abs_url(self) -> str:
        return f"https://arxiv.org/abs/{self.arxiv_id}"

    def has_category(self, category: str) -> bool:
        return category in self.categories
