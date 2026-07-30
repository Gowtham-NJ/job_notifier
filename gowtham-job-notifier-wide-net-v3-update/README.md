# Gowtham Job Notifier

A Slack notifier tailored to Gowtham’s worldwide search for computational chemistry, computational biophysics, molecular simulation, electronic structure, scientific computing, applications-scientist, research-software, and postdoctoral roles.

It checks company career boards and specialist academic job sites, scores each role against `profile.json`, keeps Europe as a ranking preference without rejecting other countries, prevents duplicate alerts with SQLite, and posts matching roles to Slack.

## Main features

- Worldwide matching: `location_mode` is `all`, so a strong role is not rejected because it is outside Europe.
- Europe remains a +2 ranking preference, and truly remote roles receive the same bonus.
- CV-derived matching for computational chemistry, biophysics, molecular modelling, DFT, QM/MM, charge/electron transport, force-field development, free-energy methods, scientific software, HPC, atomistic ML, and related roles.
- High-priority and standard Slack routing.
- Match score and reasons in each Slack message.
- Safe first-run seeding so existing jobs are stored without flooding Slack.
- Safe **per-source seeding**: when a new board is added to an established notifier, its existing vacancies are synchronized once and only later postings are alerted.
- SQLite duplicate prevention persisted through the GitHub Actions cache.
- Configuration validation, dry-run mode, sample data, and parser tests.

## Enabled sources

The current configuration contains **45 enabled sources**. The notifier deliberately mixes
structured ATS APIs, official RSS feeds, specialist scientific boards, and broad academic portals.

### Company and institutional career systems

- Greenhouse, Lever, SmartRecruiters, and Workday employers already configured in `companies.json`.
- **EMBL** through its official Workday careers site.
- **CERN** through its official SmartRecruiters careers site.
- **Inria** scientific-computing and research-engineering vacancies.
- **EMBL Partner Opportunities** for linked European molecular-biology institutes.

### Specialist scientific and research-software sources

- **MolSSI Molecular Sciences Jobs** — curated opportunities in computational molecular science.
- **CECAM Careers** — atomistic and molecular simulation opportunities.
- **CCL.NET Jobs** — computational chemistry, materials modelling, and life-science computing.
- **CHARMM-GUI Jobs and Events** — MD, QM/MM, computational biophysics, and related openings.
- **US-RSE Jobs** — official RSS feed of non-expired research-software vacancies.
- **Society of Research Software Engineering** — worldwide RSE and scientific-software roles.
- **Thomas Young Centre** — theory and simulation of materials and biomolecules.
- **Helmholtz AI Careers** — AI, research-engineering, and scientific-computing roles across Helmholtz centres.
- **ISCB Career Center** — selected structural bioinformatics, protein modelling, computational biology, and scientific-software roles.

### Broad academic and public portals

- **EURAXESS**
- **AcademicTransfer**
- **AcademicJobsOnline**
- **jobs.ac.uk**
- **Jobbnorge**
- **ResearchJobs.cz**
- **Max Planck Society job board**
- **Leibniz Association job portal**
- **Arbeitnow Europe API**

Broad HTML portals are pre-screened by scientific title/department terms before detail pages are
fetched. This keeps the three-hour schedule respectful and avoids hundreds of irrelevant requests.

### Official Varbi university RSS feeds

- Lund University
- KTH Royal Institute of Technology
- Uppsala University
- Stockholm University
- Umeå University
- Jönköping University
- Karolinska Institutet
- University of Oulu
- University of Eastern Finland
- Radboud University
- Karlstad University
- Eindhoven University of Technology

Each source has retry/backoff behavior and conservative page/detail limits. A broken source is logged
without stopping the remaining sources. `location_mode: "all"` means worldwide acceptance, while
Europe remains a ranking preference.

### Quality controls added after the live audit

- Duplicate listings with different tracking URLs are collapsed by source/company/title/location.
- Senior and principal roles remain visible, but are capped at standard priority.
- AcademicJobsOnline deadlines and ISCB expired postings are filtered.
- AcademicTransfer can detect vacancy URLs embedded in script/JSON page data.
- New sources are seeded once, so adding portals does not flood Slack with old vacancies.

For the portal-by-portal research audit, see [`PORTAL_AUDIT.md`](PORTAL_AUDIT.md).

## Intentionally disabled sources

Six entries remain documented but disabled:

- **ScholarshipDB** — repeated live runs from the server returned HTTP 403.
- **FindAPostDoc** — repeated live runs from the server returned HTTP 403.
- **Nature Careers** — its `robots.txt` disallows the relevant search/feed paths.
- **EuroScienceJobs** — published terms restrict automated crawlers.
- **EuroJobs** — published terms restrict automated scraping.
- **Genesis Therapeutics** — the former Lever endpoint returns HTTP 404 and needs a current ATS adapter.

Do not repeatedly retry a board that explicitly blocks the runner. The notifier favors stable, public,
and maintainable access rather than brittle scraping.

## 1. Test locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --validate
python main.py --dry-run --sample sample_jobs.json
python -m unittest discover -s tests -v
```

To check the live boards without posting or modifying state:

```bash
python main.py --dry-run
```

## 2. Slack webhook

Create a Slack app, enable incoming webhooks, and create a webhook for the channel that should receive jobs.

For local use:

```bash
cp .env.example .env
```

Place the webhook URL in `.env`:

```dotenv
SLACK_WEBHOOK_ALL=https://hooks.slack.com/services/...
SLACK_WEBHOOK_HIGH=https://hooks.slack.com/services/...
```

`SLACK_WEBHOOK_HIGH` is optional. When absent, all matches use `SLACK_WEBHOOK_ALL`.

Never commit `.env` or a webhook URL.

## 3. GitHub setup

In the repository:

1. Open **Settings → Secrets and variables → Actions**.
2. Add repository secret `SLACK_WEBHOOK_ALL`.
3. Optionally add `SLACK_WEBHOOK_HIGH`.
4. Open **Actions**, choose **Gowtham Job Notifier**, and run it manually once.

### What happens after this upgrade

If the cached state was created by the older notifier, the first run with this version performs a safe state upgrade. It synchronizes current matching jobs and registers the source list without posting existing vacancies. The log will contain a message similar to:

```text
Notifier state upgraded safely: synchronized current matches and registered 45 sources without posting existing jobs.
```

Later runs post only genuinely new matches. If you add another source in the future, that source alone is seeded once.

## 4. Schedule

The included workflow runs every three hours at minute 17 in the `Europe/Prague` timezone:

```yaml
on:
  schedule:
    - cron: "17 */3 * * *"
      timezone: "Europe/Prague"
  workflow_dispatch:
```

The approximate local run times are 00:17, 03:17, 06:17, 09:17, 12:17, 15:17, 18:17, and 21:17. GitHub may start a scheduled run a few minutes late.

## 5. Adjust your profile

Edit `profile.json`.

The most useful sections are:

- `title_core_terms`
- `title_role_terms`
- `method_terms`
- `domain_terms`
- `background_terms`
- `preferred_location_terms`
- `hard_negative_title_terms`
- `minimum_score`
- `high_priority_score`

After changes:

```bash
python main.py --validate
python main.py --dry-run --sample sample_jobs.json
```

## 6. Add or remove sources

Edit `companies.json`.

### Greenhouse

```json
{
  "company": "Example Company",
  "source_type": "greenhouse",
  "token": "examplecompany",
  "enabled": true
}
```

### Lever

```json
{
  "company": "Example Company",
  "source_type": "lever",
  "token": "examplecompany",
  "enabled": true
}
```

### SmartRecruiters

```json
{
  "company": "Example Company",
  "source_type": "smartrecruiters",
  "token": "CompanySlug",
  "enabled": true
}
```

### Workday

```json
{
  "company": "Example Company",
  "source_type": "workday",
  "token": "https://company.wd3.myworkdayjobs.com/Careers",
  "enabled": true
}
```

### RSS or Atom

```json
{
  "company": "Academic jobs feed",
  "source_type": "rss",
  "url": "https://example.org/jobs.rss",
  "enabled": true
}
```

The specialist and broad adapters are already configured. They include `euraxess`, `academictransfer`, `academicjobsonline`, `jobs_ac_uk`, `jobbnorge`, `arbeitnow`, `researchjobs_cz`, `ccl`, `charmm_gui`, `molssi`, `cecam`, `iscb`, `society_rse`, `max_planck`, `leibniz`, `inria`, `tyc`, `helmholtz_ai`, and `embl_partners`. Varbi and US-RSE use official RSS feeds.

## State and duplicate prevention

- `jobs.db` stores jobs already seen.
- `bot_state.json` records initialization and which sources have been seeded.
- GitHub Actions restores and saves both through its cache.
- If the cache is evicted, the next run safely synchronizes current jobs rather than posting all of them.

## Useful commands

```bash
# Validate JSON and source configuration
python main.py --validate

# Test filtering without network or Slack
python main.py --dry-run --sample sample_jobs.json

# Fetch live sources and show new matches without posting or state changes
python main.py --dry-run

# Limit one live run to five Slack posts
python main.py --max-posts 5

# Run all tests
python -m unittest discover -s tests -v
```
