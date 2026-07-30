# Portal Audit — Wide Net v4

## Integrated and enabled

### Public ATS/API access

- Greenhouse
- Lever
- Ashby
- SmartRecruiters
- Workday
- Arbeitnow
- Jobbnorge
- Jobicy
- Himalayas

### Official RSS/low-maintenance feeds

- AcademicKeys Science and Engineering
- US-RSE
- Twelve Varbi university feeds

### Specialist/public pages with conservative parsers

- EURAXESS
- AcademicTransfer
- AcademicJobsOnline
- jobs.ac.uk
- ResearchJobs.cz
- CCL.NET
- CHARMM-GUI
- MolSSI
- CECAM
- ISCB
- Society-RSE
- Max Planck
- Leibniz
- Inria
- Thomas Young Centre
- Helmholtz AI
- EMBL partners
- MathJobs
- jobRxiv

## Implemented but disabled

- Remotive: public access is permitted, but its documentation recommends only a few requests per day. Use a separate six-hour workflow before enabling it.

## Disabled after live verification

- ScholarshipDB: HTTP 403 from the server environment.
- FindAPostDoc: HTTP 403 from the server environment.
- Nature Careers: automated access to job-search/feed paths is disallowed by its robots policy.
- EuroScienceJobs: published terms restrict automated crawlers.
- EuroJobs: published terms restrict automated scraping.

## Keyed APIs considered for a later stage

- USAJOBS: useful for NIH, NIST, DOE and national-laboratory roles, but many positions impose US citizenship requirements. Requires a free API key and registered email headers.
- Adzuna: broad country coverage; requires app ID/key and attribution/usage review.
- Jooble: broad international aggregation; requires an API key and can duplicate first-party listings.
- Careerjet: broad international coverage; affiliate ID and attribution requirements.
- Reed: UK-focused; requires recruiter/developer registration.
- The Muse: industry-oriented; requires app registration and adds less chemistry-specific coverage.

These are intentionally not enabled until the first-party/no-key source set is evaluated. Aggregator APIs can increase volume faster than useful recall and need stronger stale-job and cross-source deduplication.

## Not integrated

- LinkedIn, Indeed, Glassdoor, ZipRecruiter: no suitable open public search API; unattended scraping is fragile and may conflict with platform terms.
- ResearchGate: aggressive anti-bot controls.
- General Google Jobs scraping: no official public search API.
- JobSpy/JSearch: useful only as optional gap fillers; they add legal/maintenance risk or paid API dependence.
- EURES: extremely broad general-employment volume and no simple public feed suitable for this targeted three-hour monitor.

## Operating principles

1. Prefer first-party APIs, ATS JSON endpoints and official RSS.
2. Poll conservatively and use retries/backoff.
3. Do not bypass logins, bot challenges or access controls.
4. Store only fields needed for personal matching and do not republish listings.
5. Seed each new source before notifications begin.
6. Keep aggregators supplementary to first-party sources.
