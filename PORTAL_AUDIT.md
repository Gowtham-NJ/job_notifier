# Portal Audit

## Requested portals — 2026-09-09

The requested list contains 19 distinct portals: EURAXESS and Euraxess Jobs are the same source. Four were already enabled; Science Careers and University Positions are newly enabled. Every other requested portal is recorded in `companies.json` with a disabled reason. Status reflects the checks below, not a claim that all sites are collected.

| Portal | Status | Evidence / integration |
| --- | --- | --- |
| Academic Positions | Disabled | [Terms](https://academicpositions.com/terms-of-use) require written permission to copy, store or process listings. |
| EURAXESS / Euraxess Jobs | Already enabled | Existing collector uses [official jobs search](https://euraxess.ec.europa.eu/jobs/search); one source, not two. |
| Nature Careers | Disabled | [robots.txt](https://www.nature.com/robots.txt) disallows job-search and job-RSS paths. |
| Science Careers | **Newly enabled** | [Public keyword RSS](https://jobs.sciencecareers.org/jobsrss/?Keywords=computational+chemistry) returned XML; full JobPosting details also returned HTTP 200. [Robots policy](https://jobs.sciencecareers.org/robots.txt) allows these paths. |
| FindAPostDoc | Still disabled | [Requested site](https://www.findapostdoc.com/) again returned HTTP 403 during the audit. Existing adapter retained. |
| jobs.ac.uk | Already enabled | Existing [keyword searches](https://www.jobs.ac.uk/search/?keywords=computational+chemistry) and details collector retained. |
| Times Higher Education Jobs | Disabled | Category pages are accessible, but [website terms](https://www.timeshighereducation.com/website-terms-of-use) prohibit automated data gathering; [robots.txt](https://www.timeshighereducation.com/robots.txt) also disallows job RSS and keyword-search paths. |
| HigherEdJobs | Disabled | [RSS directory](https://www.higheredjobs.com/rss/) returned an Incapsula challenge with HTTP 200, not usable RSS or listing data. |
| ResearchGate Jobs | Disabled | [Terms section 4.2](https://www.researchgate.net/terms-of-service) restrict scripts, robots and scraping. |
| University Positions | **Newly enabled** | [Public listings](https://universitypositions.eu/jobs) and structured details work at the canonical non-www host. Uses keyword filters and respects the one-second delay in [robots.txt](https://universitypositions.eu/robots.txt); the disallowed RSS path is not used. |
| PostdocJobs | Disabled | [Terms](https://www.postdocjobs.com/site/terms) prohibit robots/agents and aggregation or copying without authorization. |
| Postdoc Opportunities | Disabled | [Requested hostname](https://www.postdocopportunities.com/) failed DNS resolution. |
| INOMICS | Disabled | [Terms section 3b](https://inomics.com/terms-and-conditions) prohibit automated access without permission. |
| AcademicTransfer | Already enabled | Existing [keyword searches](https://www.academictransfer.com/en/jobs/?q=computational+chemistry) and details collector retained. |
| Max Planck Institutes | Already enabled | Existing collector uses the [society job board](https://www.mpg.de/jobboard). |
| EMBO Careers | Disabled pending a verifiable feed/adapter | `careers.embo.org` failed DNS resolution. The official [community vacancies page](https://www.embo.org/the-embo-communities/work-with-an-embo-community-member/) currently has no listings; [EMBO staff vacancies](https://www.embo.org/about-embo/work-with-us/) also reports none. EMBL remains a separate enabled source. |
| Society for Neuroscience | Disabled | The [official career page](https://www.sfn.org/careers/neurojobs-career-center) points to `neurojobs.sfn.org`, not the supplied hostname. That host returned an HTTP 202 JavaScript bot challenge. |
| New Scientist Jobs | Closed | The requested jobs host redirects to the [official closure notice](https://www.newscientist.com/jobs-closed/). |
| Indeed Academic Jobs | Disabled | No usable open search feed verified; [robots.txt](https://www.indeed.com/robots.txt) restricts RSS and job-detail query paths for general crawlers. |

Both new collectors deduplicate tracking URLs and read structured JobPosting descriptions, employer and location. Their request counts are bounded by `max_detail_pages`. Withdrawn jobs returning 404/410 are skipped; challenges and missing detail markup produce source errors instead of silently seeding incomplete results. The existing doctoral/experimental exclusions still run before alerts. Each newly enabled source is seeded on its first successful scheduled run, preserving existing notification history.

Live validation collected 60 Science Careers vacancies and 21 University Positions vacancies using the committed configurations. The tailored profile retained two from each source after filtering. These checks did not send notifications or change the database. All 123 fixture and regression tests passed, including new-source seeding, deduplication, empty results, full-description parsing and access-error handling.

The four already-enabled portals above were verified against repository configuration during this audit; they were not subjected to a new full live collection run.

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
- Science Careers (with structured detail enrichment)
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
- University Positions

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

## Other sources not collected

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
