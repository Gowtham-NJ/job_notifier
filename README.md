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
- Telegram delivery by default, with optional Slack, Discord, ntfy, and Pushover fallbacks.
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

Create a Telegram bot with `@BotFather`, send the bot `/start`, then copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN` and the numeric `TELEGRAM_CHAT_ID`. Keep this file local; it is ignored by Git.

Validate the files and the Telegram destination without sending a message:

```bash
python main.py --validate
python main.py --check-telegram
python -m unittest discover -s tests -v
python main.py --dry-run --sample sample_jobs.json
python main.py --dry-run
```

## Notification channels

Telegram is required and attempted first. Optional channels may remain configured as fallbacks; a job is considered delivered when at least one configured channel succeeds.

## Interactive bot — Phase 9

The interactive onboarding currently supports:

1. A user sends `/start`.
2. The bot asks their name.
3. The bot asks for science fields and skills.
4. The user confirms the summary before it is saved in `jobs.db`.
5. A user can send `/cv` and upload a text-based PDF CV.
6. The bot deterministically infers a draft name, scientific fields, skills, and current/recent career stage.
7. The user confirms the draft or rejects it and continues through manual onboarding.
8. The bot collects target roles, preferred locations, and remote/on-site/hybrid preferences.
9. The user confirms job preferences before they become active.
10. `/profile` displays all structured data stored for the current Telegram user.
11. `/delete_profile` permanently deletes that user's profile after exact confirmation.
12. Real collector runs maintain a separate science-only shared job catalogue for future matching.
13. `/jobs` ranks and displays up to five catalogue jobs using the user's confirmed profile and preferences.
14. `/schedule` collects and confirms an opt-in daily digest time and IANA timezone.
15. `/pause` disables reminders while retaining the configured time for later reuse.

Run it locally for testing:

```bash
.venv/bin/python interactive_bot.py
```

Keep that process running, open the bot in Telegram, and send `/start`, `/cv`, `/preferences`, `/profile`, `/jobs`, or `/schedule`. Stop it with `Ctrl+C`. PDF files are limited to 8 MB and 30 pages. Neither the PDF nor its raw text is saved; only a confirmed structured profile is retained. Extraction uses a local scientific vocabulary and no external AI service. `/delete_profile` removes the user's structured profile and preferences without touching shared job listings. Real scheduled runs upsert broadly filtered scientific vacancies and descriptions into `job_catalog`; dry-runs and sample runs never write to it. `/jobs` is read-only and returns at most five explainable matches. `/schedule` stores an opt-in daily time and timezone, while `/pause` disables it. This phase does not send automatic personalized reminders yet.

Refresh the shared catalogue without sending notifications or changing notifier state:

```bash
.venv/bin/python main.py --catalog-only
```

### Telegram (primary)

```dotenv
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

For a private chat, open the bot in Telegram and send `/start`. To discover the numeric ID, visit `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` locally and read `message.chat.id`. Group IDs are usually negative; add the bot to the group and send a message first. `python main.py --check-telegram` then verifies the bot and chat without posting anything.

### Slack (optional legacy fallback)

```dotenv
SLACK_WEBHOOK_ALL=https://hooks.slack.com/services/...
SLACK_WEBHOOK_HIGH=
```

### Discord (optional fallback)

Create incoming webhooks for the desired Discord channels:

```dotenv
DISCORD_WEBHOOK_ALL=https://discord.com/api/webhooks/...
DISCORD_WEBHOOK_HIGH=
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

Under **Repository → Settings → Secrets and variables → Actions**, add these two required secrets:

- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`

The local `.env` is not uploaded to GitHub, so these repository secrets must be added separately. The workflow validates both secrets and confirms access to the destination chat before collecting jobs. Optional fallback environment variables supported by the Python code are documented in `.env.example`, but the default workflow intentionally injects only Telegram.

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

The `jobs.db` file contains two separate job datasets: `jobs` preserves the original notifier's seen-job and deduplication behavior, while `job_catalog` stores shared scientific vacancies for future per-user matching.
