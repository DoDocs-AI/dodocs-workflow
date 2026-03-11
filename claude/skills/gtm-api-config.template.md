# GTM API Configuration

Copy this file to `.claude/gtm-api-config.md` in your project root and fill in the values.

## Apollo.io
```
APOLLO_API_KEY=your_apollo_api_key_here
```
Get your key: Apollo Settings > Integrations > API > Create Key

## Semrush
```
SEMRUSH_API_KEY=your_semrush_api_key_here
```
Get your key: Semrush > Subscription Info > API units

## Pipedrive
```
PIPEDRIVE_API_TOKEN=your_pipedrive_api_token_here
PIPEDRIVE_DOMAIN=your-company
```
Get your token: Pipedrive > Settings > Personal preferences > API
Your domain is the subdomain in `https://your-company.pipedrive.com`

## Proxycurl (LinkedIn)
```
PROXYCURL_API_KEY=your_proxycurl_api_key_here
```
Get your key: https://nubela.co/proxycurl/ > Dashboard > API Key

## Environment Variables

Set these in your shell profile (~/.zshrc or ~/.bashrc):

```bash
export APOLLO_API_KEY="your_key"
export SEMRUSH_API_KEY="your_key"
export PIPEDRIVE_API_TOKEN="your_token"
export PIPEDRIVE_DOMAIN="your-company"
export PROXYCURL_API_KEY="your_key"
```

Or create a `.env` file (do NOT commit to git):

```bash
# .env — add to .gitignore
APOLLO_API_KEY=your_key
SEMRUSH_API_KEY=your_key
PIPEDRIVE_API_TOKEN=your_token
PIPEDRIVE_DOMAIN=your-company
PROXYCURL_API_KEY=your_key
```
