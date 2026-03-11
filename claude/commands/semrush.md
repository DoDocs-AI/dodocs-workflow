Research SEO keywords, analyze domains, and audit backlinks using the Semrush API. Powers the GTM SEO content strategy.

<boot>
## Load API Key

Check for Semrush API key:
1. Environment variable: `$SEMRUSH_API_KEY`
2. Project config: `.claude/gtm-api-config.md`

Run:
```bash
API_KEY="${SEMRUSH_API_KEY:-}"
if [ -z "$API_KEY" ]; then
  echo "ERROR: SEMRUSH_API_KEY not set. Export it in your shell or add to .claude/gtm-api-config.md"
  echo "Get your key: Semrush > Subscription Info > API units"
fi
```

If no API key is found, STOP and tell the user how to configure it.

## Parse $ARGUMENTS

Supported subcommands:
- `keyword <phrase> [--db us]` — Keyword overview (volume, difficulty, CPC)
- `domain <domain> [--db us]` — Domain overview (traffic, keywords, competitors)
- `organic <domain> [--db us] [--limit 20]` — Top organic keywords for a domain
- `competitors <domain> [--db us]` — Organic competitors for a domain
- `backlinks <domain>` — Backlinks overview
- `keyword-ideas <phrase> [--db us] [--limit 20]` — Related keyword ideas
- `gap <domain1> <domain2> [--db us]` — Keyword gap between two domains
- `help` — Show usage

Default database: `us`. Override with `--db <code>` (us, uk, de, fr, es, pl, etc.)
</boot>

<role>
You are a Semrush API integration skill. You call the Semrush Analytics API to research keywords, analyze domains, and audit competitive SEO positioning. You format results as clean markdown tables.

## API Reference
- Base URL: `https://api.semrush.com/`
- Auth: `key` query parameter
- Response format: TSV (tab-separated values) — first line is headers
- Rate limit: 10 requests/second
- Cost: API units per request (varies by report type)
</role>

<workflow>

## Subcommand: keyword

Keyword overview — volume, difficulty, CPC, competition.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=phrase_this&phrase=<phrase>&database=<db>&export_columns=Ph,Nq,Cp,Co,Nr,Td"
```

Export columns: Ph=phrase, Nq=volume, Cp=CPC, Co=competition, Nr=results, Td=trend

Parse TSV response and display:

| Keyword | Volume | CPC | Competition | Results | Trend |
|---------|--------|-----|-------------|---------|-------|

Cost: 10 API units.

## Subcommand: domain

Domain overview — organic traffic, keywords count, paid traffic.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=domain_ranks&domain=<domain>&database=<db>&export_columns=Db,Dn,Rk,Or,Ot,Oc,Ad,At,Ac"
```

Columns: Db=database, Dn=domain, Rk=rank, Or=organic keywords, Ot=organic traffic, Oc=organic cost, Ad=paid keywords, At=paid traffic, Ac=paid cost

Display:

```
## Domain Overview: <domain>

| Metric | Value |
|--------|-------|
| Domain Rank | [Rk] |
| Organic Keywords | [Or] |
| Organic Traffic | [Ot] |
| Organic Traffic Cost | $[Oc] |
| Paid Keywords | [Ad] |
| Paid Traffic | [At] |
| Paid Traffic Cost | $[Ac] |
```

Cost: 10 API units.

## Subcommand: organic

Top organic keywords for a domain.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=domain_organic&domain=<domain>&database=<db>&display_limit=<limit>&display_sort=tr_desc&export_columns=Ph,Po,Nq,Cp,Ur,Tr,Tc,Co"
```

Columns: Ph=keyword, Po=position, Nq=volume, Cp=CPC, Ur=URL, Tr=traffic, Tc=traffic cost, Co=competition

Display:

| Keyword | Position | Volume | CPC | Traffic | Traffic Cost | URL |
|---------|----------|--------|-----|---------|-------------|-----|

Cost: 10 + 10 per line.

## Subcommand: competitors

Organic competitors for a domain.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=domain_organic_organic&domain=<domain>&database=<db>&display_limit=10&export_columns=Dn,Cr,Np,Or,Ot,Oc,Ad"
```

Columns: Dn=domain, Cr=competition level, Np=common keywords, Or=organic keywords, Ot=organic traffic, Oc=organic cost, Ad=paid keywords

Display:

| Competitor | Common Keywords | Competition | Organic Keywords | Organic Traffic |
|-----------|----------------|-------------|-----------------|----------------|

Cost: 10 + 10 per line.

## Subcommand: backlinks

Backlinks overview for a domain.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=backlinks_overview&target=<domain>&target_type=root_domain&export_columns=total,domains_num,urls_num,ips_num,follows_num,nofollows_num,score,trust_score"
```

Display:

```
## Backlinks Overview: <domain>

| Metric | Value |
|--------|-------|
| Total Backlinks | [total] |
| Referring Domains | [domains_num] |
| Referring URLs | [urls_num] |
| Referring IPs | [ips_num] |
| Follow Links | [follows_num] |
| Nofollow Links | [nofollows_num] |
| Authority Score | [score] |
| Trust Score | [trust_score] |
```

Cost: 40 API units.

## Subcommand: keyword-ideas

Related keywords for a seed phrase.

```bash
curl -s "https://api.semrush.com/?key=$API_KEY&type=phrase_related&phrase=<phrase>&database=<db>&display_limit=<limit>&export_columns=Ph,Nq,Cp,Co,Nr,Td"
```

Display:

| Related Keyword | Volume | CPC | Competition | Results | Trend |
|----------------|--------|-----|-------------|---------|-------|

Cost: 10 + 40 per line. Warn user about cost before executing if limit > 10.

## Subcommand: gap

Keyword gap analysis between two domains.

Run organic keywords for both domains, then compare:

```bash
# Domain 1 keywords
curl -s "https://api.semrush.com/?key=$API_KEY&type=domain_organic&domain=<domain1>&database=<db>&display_limit=50&export_columns=Ph,Po,Nq,Tr"

# Domain 2 keywords
curl -s "https://api.semrush.com/?key=$API_KEY&type=domain_organic&domain=<domain2>&database=<db>&display_limit=50&export_columns=Ph,Po,Nq,Tr"
```

Parse both TSV results. Find keywords in domain2 but NOT in domain1 (gap opportunities).

Display:

```
## Keyword Gap: <domain1> vs <domain2>

### Keywords <domain2> ranks for but <domain1> does not:
| Keyword | Volume | <domain2> Position | Traffic |
|---------|--------|-------------------|---------|

### Shared keywords where <domain2> outranks <domain1>:
| Keyword | Volume | <domain1> Pos | <domain2> Pos | Opportunity |
|---------|--------|-------------- |---------------|-------------|
```

If `--save <path>` flag present, write results to file.

## Subcommand: help

Print:
```
Semrush API Skill — SEO keyword research and domain analysis

Usage:
  /semrush keyword <phrase> [--db us]
  /semrush domain <domain> [--db us]
  /semrush organic <domain> [--db us] [--limit 20]
  /semrush competitors <domain> [--db us]
  /semrush backlinks <domain>
  /semrush keyword-ideas <phrase> [--db us] [--limit 10]
  /semrush gap <domain1> <domain2> [--db us]

Options:
  --db <code>       Database/country code (default: us). Options: us, uk, de, fr, es, pl, it, br, au, ca, ru
  --limit N         Max results (default: 20)
  --save <path>     Save results to a markdown file

API Unit Costs:
  keyword:        10 units
  domain:         10 units
  organic:        10 + 10/line
  competitors:    10 + 10/line
  backlinks:      40 units
  keyword-ideas:  10 + 40/line (expensive!)
  gap:            20 + 20/line (two domain queries)

Setup:
  Export SEMRUSH_API_KEY in your shell or see claude/skills/gtm-api-config.template.md
```
</workflow>

<rules>
- Never expose the API key in output
- Semrush returns TSV (tab-separated), not JSON — parse accordingly
- Always show API unit cost before expensive operations (keyword-ideas, gap)
- Handle empty results gracefully — "No data found for this query/domain in the [db] database"
- Default database is "us" — always mention which database was used
- Rate limit is 10 req/sec — space out multiple requests
- Format large numbers with commas for readability (1,234,567)
- When using --save, write clean markdown to the file
</rules>

Semrush SEO research: $ARGUMENTS
