# Changelog

## Wide-net v3 — 30 July 2026

- Expanded the notifier from 31 to 45 enabled sources.
- Added US-RSE, MolSSI, CECAM, AcademicJobsOnline, ISCB, Society RSE, Max Planck, Leibniz, EMBL, CERN, Inria, Thomas Young Centre, Helmholtz AI, EMBL partner opportunities, Karlstad University, and TU/e.
- Disabled ScholarshipDB and FindAPostDoc after reproducible HTTP 403 responses in the live server run.
- Fixed AcademicTransfer discovery for vacancy URLs embedded in page scripts/data.
- Added runtime duplicate collapsing for identical listings with different tracking URLs.
- Increased seniority penalties and capped senior/principal matches at standard priority.
- Added expiry/deadline checks for AcademicJobsOnline, ISCB, Inria, TYC, and EMBL partner listings.
- Added scientific pre-screening before requesting detail pages from broad HTML portals.
- Closed SQLite connections explicitly.
- Increased the GitHub Actions timeout ceiling from 20 to 30 minutes.
- Expanded CV-aligned target vocabulary for computational structural biology, scientific software, enhanced sampling, machine-learned potentials, soft matter, surfaces, and computational catalysis.
- Expanded the automated test suite from 21 to 35 tests.
