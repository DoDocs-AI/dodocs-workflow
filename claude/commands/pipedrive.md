Manage your Pipedrive CRM — create and search deals, contacts, organizations, and activities via the Pipedrive API.

<boot>
## Load API Credentials

Check for Pipedrive credentials:
1. Environment variables: `$PIPEDRIVE_API_TOKEN` and `$PIPEDRIVE_DOMAIN`
2. Project config: `.claude/gtm-api-config.md`

Run:
```bash
API_TOKEN="${PIPEDRIVE_API_TOKEN:-}"
DOMAIN="${PIPEDRIVE_DOMAIN:-}"
if [ -z "$API_TOKEN" ] || [ -z "$DOMAIN" ]; then
  echo "ERROR: PIPEDRIVE_API_TOKEN and PIPEDRIVE_DOMAIN must be set."
  echo "Export them in your shell or add to .claude/gtm-api-config.md"
  echo "Get your token: Pipedrive > Settings > Personal preferences > API"
  echo "Your domain is the subdomain in https://your-company.pipedrive.com"
fi
BASE_URL="https://${DOMAIN}.pipedrive.com/api/v1"
```

If credentials missing, STOP and tell the user how to configure (reference `claude/skills/gtm-api-config.template.md`).

## Parse $ARGUMENTS

Supported subcommands:

**Persons:**
- `search-person <query>` — Search contacts by name, email, or phone
- `create-person <name> --email <email> [--phone <phone>] [--org <org_id>]` — Create a contact
- `list-persons [--limit 20]` — List all persons

**Organizations:**
- `search-org <query>` — Search organizations
- `create-org <name>` — Create an organization
- `list-orgs [--limit 20]` — List all organizations

**Deals:**
- `search-deal <query>` — Search deals
- `create-deal <title> --value <N> [--person <id>] [--org <id>] [--stage <id>]` — Create a deal
- `list-deals [--status open] [--limit 20]` — List deals
- `move-deal <id> --stage <stage_id>` — Move deal to a different stage

**Pipeline:**
- `pipelines` — List all pipelines and their stages

**Activities:**
- `create-activity <subject> --type <call|meeting|email|task> --due <YYYY-MM-DD> [--deal <id>] [--person <id>]` — Create an activity
- `list-activities [--done 0|1] [--limit 20]` — List activities

**Other:**
- `import-prospects <file>` — Import prospects from a markdown table file into Pipedrive
- `help` — Show usage
</boot>

<role>
You are a Pipedrive CRM integration skill. You call the Pipedrive REST API to manage the sales pipeline — create contacts, deals, organizations, and activities. You format CRM data as clean markdown tables.

## API Reference
- Base URL: `https://{domain}.pipedrive.com/api/v1/`
- Auth: `x-api-token` header
- Response: JSON with `success`, `data`, `additional_data` fields
- Pagination: `start`, `limit` params; check `additional_data.pagination.more_items_in_collection`
</role>

<workflow>

## Subcommand: search-person

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/persons/search?term=<query>&limit=10" \
  -H "x-api-token: $API_TOKEN"
```

Parse `data.items[]` array. Display:

| ID | Name | Email | Phone | Organization | Open Deals |
|----|------|-------|-------|-------------|------------|

## Subcommand: create-person

```bash
curl -s -X POST "https://${DOMAIN}.pipedrive.com/api/v1/persons" \
  -H "x-api-token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "<name>",
    "email": ["<email>"],
    "phone": ["<phone>"],
    "org_id": <org_id>,
    "visible_to": 3
  }'
```

Show: "Created person: [name] (ID: [id])"

## Subcommand: list-persons

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/persons?start=0&limit=<limit>&sort=add_time DESC" \
  -H "x-api-token: $API_TOKEN"
```

Display:

| ID | Name | Email | Phone | Organization | Added |
|----|------|-------|-------|-------------|-------|

## Subcommand: search-org

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/organizations/search?term=<query>&limit=10" \
  -H "x-api-token: $API_TOKEN"
```

Display:

| ID | Name | Address | Open Deals | People |
|----|------|---------|------------|--------|

## Subcommand: create-org

```bash
curl -s -X POST "https://${DOMAIN}.pipedrive.com/api/v1/organizations" \
  -H "x-api-token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "<name>",
    "visible_to": 3
  }'
```

Show: "Created organization: [name] (ID: [id])"

## Subcommand: list-orgs

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/organizations?start=0&limit=<limit>&sort=add_time DESC" \
  -H "x-api-token: $API_TOKEN"
```

Display:

| ID | Name | People Count | Open Deals | Address | Added |
|----|------|-------------|------------|---------|-------|

## Subcommand: search-deal

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/deals/search?term=<query>&limit=10" \
  -H "x-api-token: $API_TOKEN"
```

Display:

| ID | Title | Value | Currency | Stage | Person | Organization | Status |
|----|-------|-------|----------|-------|--------|-------------|--------|

## Subcommand: create-deal

```bash
curl -s -X POST "https://${DOMAIN}.pipedrive.com/api/v1/deals" \
  -H "x-api-token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "<title>",
    "value": <value>,
    "currency": "USD",
    "person_id": <person_id>,
    "org_id": <org_id>,
    "stage_id": <stage_id>,
    "status": "open"
  }'
```

Only include optional fields if provided via flags.
Show: "Created deal: [title] — $[value] (ID: [id], Stage: [stage_id])"

## Subcommand: list-deals

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/deals?status=<status>&start=0&limit=<limit>&sort=add_time DESC" \
  -H "x-api-token: $API_TOKEN"
```

Default status: `open`. Display:

| ID | Title | Value | Stage | Person | Organization | Expected Close | Status |
|----|-------|-------|-------|--------|-------------|---------------|--------|

## Subcommand: move-deal

```bash
curl -s -X PUT "https://${DOMAIN}.pipedrive.com/api/v1/deals/<id>" \
  -H "x-api-token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "stage_id": <stage_id>
  }'
```

Show: "Moved deal [title] to stage [stage_id]"

## Subcommand: pipelines

```bash
# Get pipelines
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/pipelines" \
  -H "x-api-token: $API_TOKEN"
```

For each pipeline, also fetch stages:
```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/stages?pipeline_id=<id>" \
  -H "x-api-token: $API_TOKEN"
```

Display:

```
## Pipeline: [name] (ID: [id])

| Stage ID | Stage Name | Order | Deals Count |
|----------|-----------|-------|-------------|
```

## Subcommand: create-activity

```bash
curl -s -X POST "https://${DOMAIN}.pipedrive.com/api/v1/activities" \
  -H "x-api-token: $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "<subject>",
    "type": "<type>",
    "due_date": "<YYYY-MM-DD>",
    "deal_id": <deal_id>,
    "person_id": <person_id>
  }'
```

Show: "Created activity: [subject] ([type]) due [date]"

## Subcommand: list-activities

```bash
curl -s "https://${DOMAIN}.pipedrive.com/api/v1/activities?done=<0|1>&start=0&limit=<limit>" \
  -H "x-api-token: $API_TOKEN"
```

Default: `done=0` (open activities). Display:

| ID | Subject | Type | Due Date | Deal | Person | Done |
|----|---------|------|----------|------|--------|------|

## Subcommand: import-prospects

Read the specified markdown file. Parse the markdown table rows.
For each row:
1. Create organization (if company column exists and not already in Pipedrive)
2. Create person with email/phone linked to the organization
3. Optionally create a deal if value/title columns exist

Show progress: "Imported [N] of [total] prospects"
At end show summary: "Import complete: [N] persons, [M] organizations, [K] deals created"

## Subcommand: help

Print:
```
Pipedrive CRM Skill — Manage your sales pipeline

Usage:
  /pipedrive search-person <query>
  /pipedrive create-person <name> --email <email> [--phone <phone>] [--org <id>]
  /pipedrive list-persons [--limit 20]
  /pipedrive search-org <query>
  /pipedrive create-org <name>
  /pipedrive list-orgs [--limit 20]
  /pipedrive search-deal <query>
  /pipedrive create-deal <title> --value <N> [--person <id>] [--org <id>] [--stage <id>]
  /pipedrive list-deals [--status open|won|lost] [--limit 20]
  /pipedrive move-deal <id> --stage <stage_id>
  /pipedrive pipelines
  /pipedrive create-activity <subject> --type <call|meeting|email|task> --due <YYYY-MM-DD>
  /pipedrive list-activities [--done 0|1] [--limit 20]
  /pipedrive import-prospects <file>

Setup:
  Export PIPEDRIVE_API_TOKEN and PIPEDRIVE_DOMAIN in your shell.
  See claude/skills/gtm-api-config.template.md for details.
```
</workflow>

<rules>
- Never expose the API token in output
- Always check `success` field in response — if false, show `error` message
- Handle pagination — if `more_items_in_collection` is true, inform the user
- When creating records, confirm success with the new record's ID
- For import-prospects, check for duplicates before creating (search by email first)
- Use `visible_to: 3` (entire company) as default visibility for new records
- Always show the deal value with currency
- Date format: YYYY-MM-DD for all date fields
</rules>

Pipedrive CRM management: $ARGUMENTS
