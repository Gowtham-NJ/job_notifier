# Portal coverage audit

This audit records portals reviewed for the worldwide notifier. The goal is broad coverage without relying on sources that consistently block automated requests, expose no stable vacancy list, or duplicate a stronger official source.

## Enabled

The active configuration contains 45 sources across:

- public ATS APIs: Greenhouse, Lever, Workday and SmartRecruiters;
- international academic portals: EURAXESS, jobs.ac.uk, AcademicTransfer, AcademicJobsOnline, Jobbnorge and ResearchJobs.cz;
- computational chemistry, molecular simulation and scientific-software communities: CCL.NET, CHARMM-GUI, MolSSI, CECAM, US-RSE, Society of Research Software Engineering and Thomas Young Centre;
- research organisations and infrastructures: Max Planck, Leibniz, Inria, EMBL, CERN and Helmholtz AI;
- official university RSS feeds, primarily Varbi portals in Sweden, Finland and the Netherlands;
- selected industry career boards and a broad European API aggregator.

See `companies.json` for the authoritative machine-readable list.

## Disabled after live failures or access-policy review

- **ScholarshipDB** — returned HTTP 403 during the live server run.
- **FindAPostDoc** — returned HTTP 403 during the live server run.
- **Genesis Therapeutics (legacy Lever endpoint)** — the old endpoint returns HTTP 404.
- **Nature Careers** — automated careers/search access is restricted by the site's robots policy.
- **EuroScienceJobs** — published terms restrict automated crawler use.
- **EuroJobs** — published terms restrict scraping/crawling and unauthorized automated collection.

Disabled sources remain documented in `companies.json`; they do not create recurring warnings.

## Reviewed but not enabled in this release

- **ELIXIR vacancies** — highly relevant bioinformatics board, but direct automated access intermittently presents a verification/challenge page. It is a candidate for a future API/feed-based adapter.
- **Biophysical Society Job Board** — highly relevant, but the external career-site endpoint returned HTTP 403 during verification.
- **EIROforum jobs** — useful directory of member career sites rather than an aggregate vacancy feed. CERN and EMBL are already integrated directly; other members require separate adapters.
- **EURES** — extremely broad general-employment portal. It overlaps with stronger research-specific sources and requires especially conservative request handling; it was not added as a scraper.
- **Psi-k opportunities** — the visible listings found during review were stale, so enabling it would add noise rather than current opportunities.
- **EMBO fellowship pages** — valuable funding opportunities but not a continuously changing vacancy board. They are better handled by a separate fellowship/deadline notifier.
- **ESRF, ESS, European XFEL and ILL** — official career pages are relevant, but their vacancy tables are embedded or vendor-specific. These are good candidates for future dedicated adapters after live endpoint identification and tests.

## Coverage limits

No automated notifier can guarantee discovery of every opening. Some jobs are posted only on individual laboratory pages, mailing lists, LinkedIn, closed community boards, or pages that block automation. The current design therefore prioritizes maintainable official feeds and public vacancy pages, logs source failures independently, and makes it straightforward to add a tested adapter later.
