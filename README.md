# Gowtham Job Notifier

A worldwide job and postdoc monitor tailored to computational chemistry, computational biophysics, molecular simulation, electronic structure, scientific computing, research software, atomistic machine learning, applications-scientist, and adjacent roles.

The notifier fetches public job feeds and career APIs, scores each role against `profile.json`, stores seen jobs in SQLite, and sends new matches through one or more notification services.

## What this version includes

- **58 enabled sources** and 6 documented disabled sources.
- Worldwide acceptance (`location_mode: "all"`) with Europe/UK and genuine remote roles receiving a ranking bonus.
- Profile terms derived from Gowtham's CV: MD, DFT, QM/MM, electronic structure, charge transport, force-field parameterization, free-energy methods, Python/Fortran/C++, HPC, scientific software, structural bioinformatics, and atomistic ML.
- High-priority and standard matching; senior/principal positions remain visible but are capped at standard priority.
- Cross-source duplicate collapsing based on company, title, and location.
- Safe first-run and per-source seeding, preventing old jobs from flooding notification channels.
- GitHub Actions execution every three hours in `Europe/Prague`.
- Slack, Discord, Telegram, ntfy, and Pushover output. Configure any combination.
- Forty-six fixture and logic tests.

## Source coverage

### Structured company ATS feeds

The code supports Greenhouse, Lever, Ashby, SmartRecruiters, Workday, Recruitee, and Workable.

Configured target employers include Schrodinger, Isomorphic Labs, Google DeepMind, AQEMIA, Recursion, 1910 Genetics, SES AI, Eikon Therapeutics, Superluminal Medicines, Flagship Pioneering, QuEra, Genesis Molecular AI, Iambic Therapeutics, Relay Therapeutics, Bicycle Therapeutics, Output Biosciences, Proxima, and Topos Bio.

### Specialist scientific and research-software sources

- CCL.NET Jobs
- CHARMM-GUI Jobs
- MolSSI Molecular Sciences Jobs
- CECAM Careers
- Thomas Young Centre
- Helmholtz AI Careers
- US-RSE Jobs
- Society of Research Software Engineering
- ISCB Career Center
- jobRxiv chemistry and bioinformatics listings
- MathJobs relevant computational listings
- AcademicKeys Science and Engineering RSS feeds

### Broad academic and institutional sources

- EURAXESS
- AcademicTransfer
- AcademicJobsOnline
- jobs.ac.uk
- Jobbnorge
- ResearchJobs.cz
- Arbeitnow Europe
- Max Planck Society
- Leibniz Association
- Inria
- EMBL and EMBL partner opportunities
- CERN

### University RSS feeds

Lund, KTH, Uppsala, Stockholm, Umeå, Jönköping, Karolinska Institutet, Oulu, Eastern Finland, Radboud, Karlstad, and Eindhoven University of Technology.

### Public remote feeds

- Jobicy
- Himalayas

Remotive is implemented but disabled because its public API recommends a lower polling frequency than the main three-hour workflow. It can be enabled in a separate six-hour workflow.

## Disabled sources

- ScholarshipDB and FindAPostDoc: repeated HTTP 403 responses from the server environment.
- Nature Careers: automated access to relevant job paths is disallowed by its robots policy.
- EuroScienceJobs and EuroJobs: published terms restrict automated extraction.
- Remotive: permitted, but disabled in the three-hour workflow to respect its recommended polling frequency.

The notifier does not scrape LinkedIn, Indeed, Glassdoor, or ResearchGate. These sources are fragile, login-gated, or contractually risky for unattended scraping.

## Local setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Configure at least one notification channel in `.env`, then validate:

```bash
python main.py --validate
python -m unittest discover -s tests -v
python main.py --dry-run --sample sample_jobs.json
python main.py --dry-run
```

## Notification channels

Any combination may be enabled. A job is considered delivered when at least one configured channel succeeds.

### Slack

```dotenv
SLACK_WEBHOOK_ALL=https://hooks.slack.com/services/...
SLACK_WEBHOOK_HIGH=
```

### Discord

Create incoming webhooks for the desired Discord channels:

```dotenv
DISCORD_WEBHOOK_ALL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_HIGH=
```

### Telegram

Create a bot with `@BotFather`, send it one message, obtain the chat ID, and configure:

```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

### ntfy

Subscribe to a long, private topic name in the ntfy phone or web app:

```dotenv
NTFY_TOPIC_URL=https://ntfy.sh/your-long-private-topic
NTFY_TOKEN=
```

### Pushover

```dotenv
PUSHOVER_APP_TOKEN=
PUSHOVER_USER_KEY=
```

## GitHub Actions secrets

Under **Repository → Settings → Secrets and variables → Actions**, add only the services you use:

- `SLACK_WEBHOOK_ALL`, `SLACK_WEBHOOK_HIGH`
- `DISCORD_WEBHOOK_ALL`, `DISCORD_WEBHOOK_HIGH`
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `NTFY_TOPIC_URL`, `NTFY_TOKEN`
- `PUSHOVER_APP_TOKEN`, `PUSHOVER_USER_KEY`

The workflow runs at minute 17 every three hours in the Prague timezone. It restores `jobs.db` and `bot_state.json` from the Actions cache.

## Safe upgrade behavior

On the first real run, current matches are stored without being posted. When sources are added later, only those new sources are seeded. Later runs notify only genuinely new matches.

## Adding sources

Edit `companies.json`. Supported source types include:

```text
greenhouse, lever, ashby, smartrecruiters, workday,
recruitee, workable, rss, euraxess, academictransfer,
academicjobsonline, jobs_ac_uk, jobbnorge, arbeitnow,
researchjobs_cz, ccl, charmm_gui, molssi, cecam, iscb,
society_rse, max_planck, leibniz, inria, tyc,
helmholtz_ai, embl_partners, mathjobs, jobrxiv,
jobicy, himalayas, remotive
```

Example Ashby source:

```json
{
  "company": "Example Company",
  "source_type": "ashby",
  "token": "example-company",
  "enabled": true
}
```

Example RSS source:

```json
{
  "company": "Example University",
  "source_type": "rss",
  "url": "https://example.edu/jobs.rss",
  "enabled": true
}
```

## Optional keyed APIs not enabled by default

The source audit also identified USAJOBS, Adzuna, Jooble, Careerjet, Reed, and The Muse. They require account registration, API keys, country-specific setup, attribution, or introduce substantial duplication. They are documented in `PORTAL_AUDIT.md` and should be added only after the no-key sources have been observed for a few weeks.

## Runtime files

- `jobs.db`: previously seen jobs
- `bot_state.json`: initialization and source-seeding state
- `run_log.txt`: fetch/post/error log

These files and `.env` should remain outside Git tracking.
