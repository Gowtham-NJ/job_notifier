# Changelog

## 2026-09-09

- Exclude doctoral training variants and experimental duties before tailored job scoring.
- Apply the same exclusions to personalized catalogue matches and digests, respecting doctoral opt-ins and experimental users' preferences.
- Preserve existing-PhD qualifications, postdoctoral fellowships, computational analysis of experimental data, and notification history.
- Add regression coverage for both notification paths and run the test suite before scheduled notifications.

## v4 — 2026-07-30

- Expanded from 45 to 58 enabled sources.
- Added Ashby, Recruitee and Workable ATS adapters.
- Added Genesis Molecular AI, Iambic Therapeutics, Relay Therapeutics, Bicycle Therapeutics, Output Biosciences, Proxima and Topos Bio.
- Added MathJobs, jobRxiv, AcademicKeys Science/Engineering, Jobicy and Himalayas.
- Implemented Remotive but left it disabled for a lower-frequency workflow.
- Added Slack, Discord, Telegram, ntfy and Pushover multi-channel delivery.
- Changed runtime duplicate fingerprinting to collapse matching jobs across different sources.
- Added 11 tests; 46 tests now pass.

## v3 — 2026-07-30

- Added broad scientific, institutional and research-software sources.
- Disabled repeatedly blocked sources.
- Added duplicate, seniority and AcademicTransfer fixes.
