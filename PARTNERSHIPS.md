# Jobmesh — partner-access requests for the 10 remaining platforms

Of the 78 required platforms, **67 are live**. The 10 below cannot be indexed
through any clean, self-service public route — verified line by line, with
robots.txt proof and live checks (see `COVERAGE.md`). They are **not technical
failures**: each is an *integration pending access*. The right way in is an
official partner / developer / syndication feed, requested with Jobmesh's own
identity — **no DOM scraping, no lifted session tokens, no anti-bot bypass, and
robots.txt is always honoured**. Budget rule: **free, or ≤ €3/month** — never
pay for a third-party backfill API to work around a block.

> *Free to develop ≠ free to redistribute.* The decisive question for every
> provider is multi-tenant **redistribution rights**, not just API access.

**These are drafts. Tatiana sends them herself** — nothing here is auto-sent.
Confirm each provider's current partner-contact address on their site before
sending; the channels below are the researched starting points.

A source only becomes `ACTIVE` when ALL hold: a documented official API/feed ·
Jobmesh authorization confirmed · robots.txt verified for the routes used ·
multi-tenant access authorized · redistribution allowed · title/employer/
location/URL available · cost ≤ €3/month · a successful sync test. HTTP 200
alone is never enough.

---

## 1. Cornerstone (CSOD)

**Status:** Partner request sent **26/11/2026** — awaiting reply.

**Why gated:** the career sites are single-page apps; the `JobPosting` JSON-LD
is rendered client-side, so a plain HTTP fetch returns only the shell — no
token-free route.
**Channel:** Cornerstone OnDemand — Technology / Edge Partner Program
(cornerstoneondemand.com → Partners). Ask for read-only published-jobs access
and a Pilot/Stage test environment.

> **Subject:** Jobmesh — partner access to published job postings
>
> Hello Cornerstone Partnerships team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent, deduplicated index of publicly posted jobs that always links each
> role back to its original application page.
>
> I'd like to index the public roles published through Cornerstone career sites
> the right way — via an official partner feed or API, not scraping. Your
> careersites render their job data client-side, so there is no clean public
> route for an aggregator.
>
> Do you offer a partner/aggregator job feed (REST/JSON, XML or RSS/Atom) with
> read-only access to title, employer, location, posting date and the original
> apply URL, under a multi-tenant partner agreement (no per-employer logins)? I
> don't use DOM scraping or session tokens and I honour robots.txt. Jobmesh
> would display every role with attribution and a link back to the source.
>
> I'm an early-stage solo project, so a free or low-cost integration works best.
> I'm happy to complete any partner onboarding or sandbox test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 2. BrassRing (Infinite / IBM Kenexa)

**Status:** Partner request sent **26/11/2026** — awaiting reply.

**Why gated:** candidate detail pages serve a ~900 KB SPA bundle; the
`JobPosting` JSON-LD is client-rendered, so a plain HTTP fetch parses zero
postings. No token-free HTTP route.
**Channel:** the BrassRing (Infinite Computer Solutions) partner / integration
contact — ask to be accepted as a job-board **aggregation** provider.

> **Subject:** Jobmesh — aggregator access to public BrassRing postings
>
> Hello,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent index of publicly posted jobs that links every role back to its
> original application page.
>
> I'd like to include the public roles posted through BrassRing career sites via
> an official job-board aggregator integration rather than scraping — the
> candidate pages render their data client-side, so there's no clean public
> route.
>
> Do you offer an aggregator or partner feed (REST/JSON, XML or RSS/Atom) giving
> read-only access to title, employer, location, posting date and the original
> apply URL, under a multi-tenant agreement (no per-employer credentials)? I
> don't use DOM scraping or session tokens and I honour robots.txt, and Jobmesh
> shows every role with attribution and a source link.
>
> I'm an early-stage solo project; a free or low-cost integration is ideal.
> Happy to go through any onboarding or sandbox test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 3. UltiPro (UKG)

**Status:** Partner request sent **26/11/2026** — awaiting reply.

**Why gated:** `robots.txt` disallows `*/JobBoardView`, the search/data route —
so it is off-limits to honour.
**Channel:** UKG Developer Portal → partner job-board feed (ukg.com → Developer
/ Partners), which avoids the robots-blocked `JobBoardView`.

> **Subject:** Jobmesh — partner job-board feed for public UKG postings
>
> Hello UKG Developer/Partner team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent, deduplicated index of publicly posted jobs that links each role
> back to its source.
>
> I'd like to index the public roles published on UKG/UltiPro career sites
> through an official partner feed. I honour robots.txt, which disallows the
> `JobBoardView` route, so I'm looking for the supported partner interface
> instead of reading that path.
>
> Is there a partner job-board feed (REST/JSON or XML) with read-only access to
> title, employer, location, posting date and the original apply URL, under a
> multi-tenant partner agreement? No DOM scraping, no session tokens; Jobmesh
> attributes every role and links back to the original listing.
>
> Early-stage solo project — a free or low-cost integration works best. Happy to
> onboard or run a sandbox test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 4. Paycom

**Status:** Not contacted — no public technical partner program (sales form only), verified **26/11/2026**.

**Why gated:** no sitemap and no server-rendered JSON-LD on client job pages;
listings load from a client-key'd API with no public anonymous route.
**Channel:** Paycom developer / partner contact (paycom.com → Contact /
Partners). Ask for a partner job-distribution feed.

> **Subject:** Jobmesh — partner access to public Paycom job postings
>
> Hello Paycom team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent index of publicly posted jobs that links each role back to its
> original application page.
>
> I'd like to index the public roles posted through Paycom career sites via an
> official partner feed rather than scraping — the client job pages load from a
> keyed API with no public anonymous route.
>
> Do you offer a partner/aggregator job feed (REST/JSON, XML or RSS/Atom) with
> read-only access to title, employer, location, posting date and the original
> apply URL, under a multi-tenant agreement (no per-employer logins)? I don't
> use DOM scraping or session tokens and I honour robots.txt; Jobmesh shows every
> role with attribution and a source link.
>
> Early-stage solo project — free or low-cost is ideal. Happy to onboard or test
> in a sandbox.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 5. talentReef (Mitratech)

**Status:** Already contacted earlier (before **26/11/2026**) — awaiting reply.

**Why gated:** the sitemap + JSON-LD recipe is ready, but no live public tenant
was found — a syndication feed is the clean multi-tenant route.
**Channel:** Mitratech Partner Programs — `PartnerPrograms@Mitratech.com`
(talentReef is a Mitratech product). *Already contacted.*

> **Subject:** Jobmesh — talentReef job syndication feed
>
> Hello Mitratech Partnerships team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent, deduplicated index of publicly posted jobs that links each role
> back to its source.
>
> I'd like to include the public roles posted through talentReef via an official
> job-distribution / XML syndication feed rather than per-employer accounts.
>
> Is there a partner syndication feed (XML/JSON) giving read-only access to
> title, employer, location, posting date and the original apply URL, under a
> multi-tenant partner agreement? No scraping, no session tokens, robots.txt
> honoured; Jobmesh attributes every role and links back to the listing.
>
> Early-stage solo project — a free or low-cost integration is ideal. Happy to
> complete onboarding or a feed test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 6. Paradox (Workday)

**Status:** Pending — the Workday partner form requires a professional email; to be sent from **contact@jobmesh.world** (as of **26/11/2026**).

**Why gated:** acquired by Workday; no standalone public job surface, and client
sites run on their own domains.
**Channel:** Workday Recruiting partner feed (workday.com → Partners). Ask about
a published-jobs partner feed for former Paradox / McHire tenants.

> **Subject:** Jobmesh — partner feed for public postings (Paradox / Workday)
>
> Hello Workday Partnerships team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent index of publicly posted jobs that links each role back to its
> original application page.
>
> Following Workday's acquisition of Paradox, I'd like to index the relevant
> public roles via an official partner feed rather than scraping. There's no
> standalone public job surface, so a partner interface is the right route.
>
> Do you offer a partner job feed (REST/JSON or XML) with read-only access to
> title, employer, location, posting date and the original apply URL, under a
> multi-tenant partner agreement? No DOM scraping, no session tokens, robots.txt
> honoured; Jobmesh attributes every role and links back to the source.
>
> Early-stage solo project — free or low-cost preferred. Happy to onboard or run
> a sandbox test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 7. Paycor (Paychex)

**Status:** Partner request (Paychex/Paycor) sent **26/11/2026** — awaiting reply.

**Why gated:** a public per-client ATOM feed exists, but `recruitingbypaycor.com`
(and `newton.newtonsoftware.com`, which redirects to it) serve
`robots.txt: Disallow: /`. Honouring robots (RFC 9309), the feed is off-limits.
**Channel:** Paychex partner job API/feed (paychex.com → Partners; Paychex
acquired Paycor). Ask for a partner feed on a host whose robots.txt permits it.

> **Subject:** Jobmesh — partner job feed for public Paycor postings
>
> Hello Paychex / Paycor team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent, deduplicated index of publicly posted jobs that links each role
> back to its source.
>
> Paycor publishes a per-client ATOM feed, but the host's robots.txt disallows
> it, so I will not read it. I'd rather integrate properly: is there a partner
> job feed (REST/JSON, XML or Atom) — ideally on a host whose robots.txt permits
> aggregator access — with read-only title, employer, location, posting date and
> the original apply URL, under a multi-tenant partner agreement?
>
> No scraping, no session tokens, robots.txt honoured; Jobmesh attributes every
> role and links back to the listing. Early-stage solo project — free or
> low-cost is ideal. Happy to onboard or test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 8. Talenetic

**Status:** Partner request sent **26/11/2026** — awaiting reply.

**Why gated:** no active client board found on the public web — a syndication
partnership is the multi-tenant route.
**Channel:** Talenetic — XML/JSON syndication / FeedOuts partnership
(talenetic.com → Contact).

> **Subject:** Jobmesh — Talenetic job syndication feed
>
> Hello Talenetic team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent index of publicly posted jobs that links each role back to its
> source.
>
> I'd like to include the public roles posted on Talenetic-powered boards via an
> official XML/JSON syndication feed (e.g. FeedOuts) rather than scraping.
>
> Do you offer a partner syndication feed giving read-only access to title,
> employer, location, posting date and the original apply URL, for
> customer-authorized ads under a multi-tenant agreement? No scraping, no session
> tokens, robots.txt honoured; Jobmesh attributes every role and links back.
>
> Early-stage solo project — free or low-cost preferred. Happy to onboard or run
> a feed test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 9. CareerSiteCloud

**Status:** Partner request sent **26/11/2026** — awaiting reply.

**Why gated:** the service returns HTTP 502 across repeated checks (offline).
**Channel:** CareerSiteCloud — free partner XML export (careersitecloud.com →
Contact). Do **not** buy the ~$1,000/mo backfill; ask only for a free partner
export once the service is back up.

> **Subject:** Jobmesh — free partner XML export for public postings
>
> Hello CareerSiteCloud team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent, deduplicated index of publicly posted jobs that links each role
> back to its source.
>
> I'd like to index the public roles on CareerSiteCloud-powered boards via an
> official partner XML export rather than scraping. (On my side your service has
> been returning 502 on repeated checks — flagging it in case it helps.)
>
> Is there a free or low-cost partner feed (XML/JSON) with read-only access to
> title, employer, location, posting date and the original apply URL, under a
> multi-tenant agreement? No scraping, no session tokens, robots.txt honoured;
> Jobmesh attributes every role and links back to the listing.
>
> Early-stage solo project — a free or ≤ €3/month option works best. Happy to
> onboard or run a test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world

---

## 10. eJobBoard

**Status:** Cannot contact — ejobboard.com is a parked GoDaddy domain with no reachable vendor, verified **26/11/2026**.

**Why gated:** no client names or live tenant are published anywhere — only a
negotiated feed can give multi-tenant access.
**Channel:** eJobBoard vendor contact (ejobboard.com → Contact). Ask for a
negotiated XML feed of published jobs.

> **Subject:** Jobmesh — negotiated job feed for public eJobBoard postings
>
> Hello eJobBoard team,
>
> I'm Tatiana Tchouakam Chouacheu, building Jobmesh (jobmesh.world), an
> independent index of publicly posted jobs that links each role back to its
> source.
>
> I'd like to include the public roles on eJobBoard-powered sites via an official
> feed rather than scraping — I couldn't find a public tenant, so a negotiated
> partner feed looks like the right route.
>
> Do you offer a partner XML/JSON feed with read-only access to title, employer,
> location, posting date and the original apply URL, under a multi-tenant
> agreement? No scraping, no session tokens, robots.txt honoured; Jobmesh
> attributes every role and links back.
>
> Early-stage solo project — free or ≤ €3/month preferred. Happy to onboard or
> run a feed test.
>
> Thank you,
> Tatiana Tchouakam Chouacheu — Jobmesh — jobmesh.world
