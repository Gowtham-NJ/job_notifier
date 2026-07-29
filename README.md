# Gowtham Job Notifier

A Slack notifier tailored to computational chemistry, computational biophysics, molecular simulation, electronic-structure, scientific-computing, applications-scientist, and postdoctoral roles.

It checks configured career boards, scores each role against `profile.json`, filters to preferred European/remote locations, avoids duplicate alerts with SQLite, and posts matching roles to Slack.

## What changed from the original VLSI bot

- Replaced VLSI/US filters with a scored computational-science profile.
- Added high-priority versus standard Slack routing.
- Added rich Slack messages with match score and reasons.
- Added safe first-run seeding, so existing jobs are stored without flooding Slack.
- Replaced fragile repository commits with cached state in GitHub Actions.
- Replaced the UTF-16, over-pinned dependency file with a normal UTF-8 file.
- Removed the original repository history and its old job database.
- Added configuration validation, dry-run mode, sample data, and unit tests.

## 1. Test locally

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py --validate
python main.py --dry-run --sample sample_jobs.json
python -m unittest discover -s tests -v
```

The dry run should retain the relevant Vienna, Mannheim, and unknown-location postdoc examples, while rejecting sales, leadership, and Canada-only examples.

## 2. Create the Slack webhook

Create a Slack app, enable incoming webhooks, and create a webhook for the channel that should receive jobs.

For local use:

```bash
cp .env.example .env
```

Then place the webhook URL in `.env`:

```dotenv
SLACK_WEBHOOK_ALL=https://hooks.slack.com/services/...
SLACK_WEBHOOK_HIGH=https://hooks.slack.com/services/...
```

`SLACK_WEBHOOK_HIGH` is optional. When absent, all matches go to `SLACK_WEBHOOK_ALL`.

Never commit `.env` or a webhook URL.

## 3. Put it on GitHub

Create a new private GitHub repository and upload this directory. Do not reuse the included archive's old `.git` directory.

In the repository:

1. Open **Settings → Secrets and variables → Actions**.
2. Add repository secret `SLACK_WEBHOOK_ALL`.
3. Optionally add `SLACK_WEBHOOK_HIGH` for the strongest matches.
4. Open **Actions**, select **Gowtham Job Notifier**, and run it manually once.

The first real run uses `initial_run_mode: "seed"`: it records all currently open matching jobs but does not post them. New jobs found on later runs are posted.

To deliberately post existing matches on a local first run:

```bash
python main.py --post-existing
```

## 4. Adjust your profile

Edit `profile.json`.

Most useful sections:

- `title_core_terms`: highly specific target titles.
- `title_role_terms`: acceptable generic role types.
- `method_terms`: MD, QM/MM, DFT, molecular docking, atomistic ML, and similar methods.
- `domain_terms`: computational biophysics, materials science, drug discovery, charge transfer, and related domains.
- `background_terms`: GROMACS, CP2K, Gaussian, Python, Linux, HPC, and similar skills.
- `preferred_location_terms`: countries and cities that pass the location filter.
- `hard_negative_title_terms`: sales, internships, leadership, wet-lab-only roles, and other unwanted titles.
- `minimum_score` and `high_priority_score`: alert sensitivity.

After changes, run:

```bash
python main.py --validate
python main.py --dry-run --sample sample_jobs.json
```

## 5. Add or remove companies

Edit `companies.json`. Supported source types are:

### Greenhouse

```json
{
  "company": "Example Company",
  "source_type": "greenhouse",
  "token": "examplecompany",
  "enabled": true
}
```

For a URL such as `https://job-boards.greenhouse.io/examplecompany`, the token is `examplecompany`.

### Lever

```json
{
  "company": "Example Company",
  "source_type": "lever",
  "token": "examplecompany",
  "enabled": true
}
```

For a URL such as `https://jobs.lever.co/examplecompany`, the token is `examplecompany`.

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

Workday sites change frequently. A source failure is logged and does not stop other companies.

### RSS or Atom

```json
{
  "company": "Academic jobs feed",
  "source_type": "rss",
  "url": "https://example.org/jobs.rss",
  "enabled": true
}
```

This is useful for universities or academic job portals that expose a genuine RSS/Atom feed.

## Scheduling

The included GitHub workflow runs at 07:17, 11:17, 15:17, 19:17, and 23:17 in the `Europe/Prague` timezone. Edit `.github/workflows/job-notifier.yml` to change it.

## State and duplicate prevention

`jobs.db` stores job URLs already seen, and `bot_state.json` records whether the initial seed has happened. GitHub Actions restores and saves both through its cache. If the cache is eventually evicted, the next run safely seeds current jobs again instead of posting all of them.

## Useful commands

```bash
# Validate JSON and supported source types
python main.py --validate

# Test filtering without network or Slack
python main.py --dry-run --sample sample_jobs.json

# Fetch live sources and print only new matches, without posting or changing state
python main.py --dry-run

# Limit one run to five posts
python main.py --max-posts 5
```

## Current limitation

This version handles company boards well, but academic portals without RSS/API access need a portal-specific source adapter. Do not use broad HTML scraping unless the site's terms permit it and the parser is tested against that site.
