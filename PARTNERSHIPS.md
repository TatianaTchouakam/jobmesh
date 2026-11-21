# JobMesh — Partnership backlog for the 12 remaining required platforms

The 12 platforms below cannot be indexed through any clean, self-service public
channel (verified line-by-line, with robots.txt proof, by four independent
analyses + live checks on 2026-11-21). They are **not technical failures** —
each is an **integration pending access**: an official partner / developer /
syndication program, requested with JobMesh's own credentials, no DOM scraping,
no lifted session tokens. Budget rule: **free, or ≤ €3/month**. Never pay for a
third-party data API (e.g. CareerSiteCloud's $1,000/mo backfill) to work around
a block.

> **Key caveat (applies to all):** *free to develop ≠ free to redistribute.*
> The decisive question for every provider is multi-tenant **redistribution
> rights**, not just technical API access.

## Status

| # | Platform | Workflow state | Program / channel to request |
|---|---|---|---|
| 1 | **Polymer** | DIAGNOSTIC_PENDING | Public API documented but 403 anti-bot → ask `support@polymer.co` to whitelist JobmeshBot as an aggregator |
| 2 | **Cornerstone (CSOD)** | PARTNERSHIP_PENDING | Technology Partner Program (free Pilot/Stage env for tests); read-only published-jobs access |
| 3 | **BrassRing (IBM)** | PARTNERSHIP_PENDING | "Job Board Aggregator Integration" — ask to be accepted as an aggregation provider |
| 4 | **UltiPro / UKG** | PARTNERSHIP_PENDING | UKG Developer Portal → Partner job-board feed (avoids robots-blocked `JobBoardView`) |
| 5 | **Paycom** | API_REQUEST_PENDING | Developer/partner API (robots *allows* `/api/ats/job-postings/`; only lock is a 2 h page-JWT) |
| 6 | **talentReef** | SYNDICATION_PENDING | Job Posting / XML distribution syndication feed (not per-employer accounts) |
| 7 | **Paradox** | PARTNERSHIP_PENDING | Workday Recruiting (acquired Paradox, Oct 2025). McHire tenant exists but detail pages are anti-bot (202 empty) |
| 8 | **Paycor** | PARTNERSHIP_PENDING | Paychex (acquired Paycor, Apr 2025) partner job API/feed |
| 9 | **Talenetic** | PARTNERSHIP_PENDING | XML/JSON syndication partnership (FeedOuts) — customer-authorized ads |
| 10 | **JobBoardFire** | SYNDICATION_PENDING | Ask for a centralized/syndicated published-jobs feed (not the per-owner mgmt API) |
| 11 | **eJobBoard** | PARTNERSHIP_PENDING | Active vendor (~$49/mo), no public tenant, site unreachable from test IP → only a negotiated XML feed |
| 12 | **CareerSiteCloud** | PROVIDER_CHECK_PENDING | Service 502 (daily health-check); ask for a free partner XML export; do NOT buy a $1000/mo backfill |

## The email to send (adapt the provider name)

**Subject:** JobMesh – Request for Official Job Posting API / Syndication Partnership

> Hello,
>
> We are developing **JobMesh**, an independent multi-source job indexer that
> aggregates publicly available job opportunities into a unified, deduplicated
> search index.
>
> We would like to establish an **official integration** with your platform.
> Our technical requirements are:
> - An officially supported **REST/JSON API, XML feed, RSS/Atom feed, or partner
>   job-distribution interface**.
> - Access using **our own developer credentials** or an approved partner
>   integration.
> - **Read-only** access to published job listings, retrieving: job title,
>   employer name, location, publication date, original job URL, and job status
>   where available.
> - Permission to **index, normalize, deduplicate and display** the permitted
>   job metadata, **with attribution and a link to the original listing**.
> - **Multi-tenant access** through an authorized partner agreement, **without
>   requiring individual employer credentials** for every customer.
>
> We do **not** use DOM scraping, session-token extraction, or unauthorized
> access methods.
>
> Could you please clarify:
> 1. Do you offer a public or partner Job Posting API?
> 2. Is XML/JSON job-feed syndication available?
> 3. Can an independent job aggregator become an approved integration partner?
> 4. Is multi-tenant access supported?
> 5. What are the commercial costs and redistribution conditions?
> 6. Is there a sandbox or test environment?
>
> Our preference is a free integration or a partnership costing **no more than
> €3/month**.
>
> Thank you,
> JobMesh Integration Team

## Activation gate (before any connector goes ACTIVE)

A source becomes ACTIVE only when ALL hold:
documented official API/feed · JobMesh authorization confirmed · robots.txt
verified for the routes used · multi-tenant access authorized (if needed) ·
commercial redistribution allowed · title/employer/location/URL available ·
cost ≤ €3/month · a successful sync test. HTTP 200 alone is never enough.
