from __future__ import annotations

import re
from typing import Any

from db import save_catalog_jobs


SCIENCE_JOB_TERMS = (
    "academic",
    "astronomy",
    "bioinformatics",
    "biology",
    "biomedical",
    "biophysics",
    "biotechnology",
    "cell culture",
    "chemical",
    "chemistry",
    "clinical research",
    "computational",
    "crystallography",
    "data science",
    "drug discovery",
    "ecology",
    "environmental science",
    "genetics",
    "genomics",
    "geology",
    "immunology",
    "laboratory",
    "machine learning",
    "materials science",
    "microbiology",
    "microscopy",
    "molecular",
    "neuroscience",
    "pharmacology",
    "physics",
    "postdoc",
    "proteomics",
    "quantum",
    "research engineer",
    "research fellow",
    "research software",
    "rna sequencing",
    "scientific computing",
    "structural biology",
    "toxicology",
)


def is_science_job(job: dict[str, Any]) -> bool:
    searchable = " ".join(
        str(job.get(field) or "") for field in ("title", "description", "company", "source")
    ).casefold()
    normalized = re.sub(r"[^a-z0-9+#.-]+", " ", searchable)
    return any(term in normalized for term in SCIENCE_JOB_TERMS)


def catalog_science_jobs(jobs: list[dict[str, Any]], persist: bool) -> int:
    """Filter the shared catalogue; dry/sample callers pass persist=False."""
    science_jobs = [job for job in jobs if is_science_job(job)]
    if not persist:
        return len(science_jobs)
    return save_catalog_jobs(science_jobs)
