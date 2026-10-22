# SamacSys direct acquisition: feasibility review

Reviewed: 2026-10-22. Status: research complete for the public sources below; provider access and a supported download interface remain unconfirmed. No direct-download implementation is enabled.

## Decision

Keep browser search, explicit ZIP loading and optional Downloads list auto-refresh as the working acquisition flow. Retain direct acquisition on the roadmap, with confirmation of a supported interface and applicable integration permission as its next prerequisite. Do not treat publicly reachable website routes or third-party download clients as a documented provider API.

This is an engineering integration decision based on the inspected material, not a claim that no API exists or a determination of all applicable legal rights.

## What the official sources establish

| Finding | Evidence | Implication for this application |
| --- | --- | --- |
| Component Search Engine advertises free model downloads through a registered account and support for KiCad among its CAD formats. | [Component Search Engine: Learn more](https://componentsearchengine.com/learn-more) | An ordinary account supports the browser workflow; public documentation inspected does not establish application API access. |
| The preferred Mouser portal documents Library Loader installation and delivery to an ECAD tool. | [Mouser portal: PCB Libraries](https://ms.componentsearchengine.com/pcb-libraries.php) | This documents the vendor's integration, without supplying a third-party client contract. |
| Supplyframe described Component Search Engine integration via Supplyframe APIs in a September 2020 announcement. | [Supplyframe announcement](https://intelligence.supplyframe.com/supplyframe-designsense-accelerates-growth-with-new-customers-product-capabilities-and-engineering-user-engagement/) | Integration exists in its ecosystem. The announcement is historical and is not current API documentation, authentication instructions or an offer of access for this app. |
| Section 4.2(e) of the published Component Search Engine terms includes restrictions on automated searches, requests, queries and data mining. | [Component Search Engine Terms of Service](https://componentsearchengine.com/TermsOfUse.html) | Do not assume the ordinary website account authorizes a scripted downloader. Confirm the intended integration with the provider. |
| Supplyframe publishes an official contact route linked from its current SamacSys page. | [SamacSys overview](https://supplyframe.com/samacsys), [Contact](https://supplyframe.com/contact) | Use this route to ask for supported integration options. No message or form has been sent. |

The inspected public material did not provide a self-service CAD-download API specification, client-registration procedure, authentication contract, rate limits or clear distribution terms for a public standalone integration. This is a bounded research finding, not proof that such access is unavailable. A paid offering, partner arrangement or separately granted access may exist; none is confirmed here.

## Questions to resolve with SamacSys / Supplyframe

Describe the project as a planned public Python/Tkinter KiCad library manager, potentially followed by a KiCad plugin. Assets remain local to each user's libraries; application releases contain no vendor assets. Ask:

1. Is there a supported interface for an independent desktop application to search model availability and download native KiCad symbols/footprints and STEP models?
2. Is an individual account sufficient, or are application registration, a partner agreement, fees or specific permission required? Is public/open-source client distribution supported?
3. What are the documented authentication flow, scopes and credential-storage requirements? Can each user authorize their own account without embedding a shared secret in the client?
4. What identifiers distinguish manufacturer, exact MPN, package and model revision? Can results be displayed for explicit user selection rather than downloading an inferred first match?
5. What are the rate limits, supported endpoints/hosts, error responses, download-expiry rules, size limits and format guarantees? Are test credentials or a sandbox available?
6. What attribution, licence/notice retention, local caching, offline reuse and internal KiCad-reference adjustment conditions apply? Can users keep downloaded CAD data in their own private library repositories?

Do not send personal credentials, browser cookies or library contents with an initial enquiry. There is no need to collect credentials in this application before an authentication contract is established.

## Intended flow if supported access is confirmed

1. Search by MPN or keyword using an explicit action.
2. Show manufacturer, exact part, package/variant and separately known availability for symbol/footprint/STEP. Do not infer missing package or geometry data.
3. Let the user select a result and choose Download. Provide progress, cancellation and actionable authentication/network errors without freezing Tk.
4. Download to a unique local temporary file with bounded size, timeouts and permitted redirects. Use the provider's documented hosts and authentication rules. Keep partial files out of the selectable archive list.
5. Validate the completed archive through the existing safe ZIP extractor. Preserve required notices and record the provider, selected result/revision, retrieval time and archive hash. Never record tokens, signed URL secrets or passwords in preferences/history/logs.
6. Hand off extracted native assets to existing independent selection, previews, naming, category and KiCad 9/10 output validation. Downloading does not import automatically or bypass collision/update/restore protections.

Keep online acquisition separate from local-file scanning and library writes. `scripts/providers.py` currently supplies local adapters and browser search URLs only; it is not an HTTP transport. The eventual online adapter should implement the confirmed provider contract and feed the existing native intake pipeline, without changing the meaning of saved source identifiers.

**Search online remains permanently available**, even when direct acquisition is supported, for alternative packages, variants, unavailable providers and browser-only workflows.

## What remains untested or unconfirmed

- No supported API contract, commercial access, partner permission or authentication method was obtained.
- No private endpoint probing, automated model search/download, account login or user browser-session access was performed.
- Existing local ZIP validation does not certify an online service contract. An HTTP client or disabled Download button would not resolve the missing information.
- Real LCSC/EasyEDA acquisition and conversion remain a separate future integration; this review does not establish their feasibility.

## Next steps

Obtain the provider's integration response and documentation before implementing its network client. Once access is confirmed, first validate one explicit part/variant download into a temporary local cache, with mocked cancellation/error tests and an opt-in live check. Then connect result selection and download status to the GUI. If suitable access is not available, retain the supported manual browser/ZIP flow and evaluate other providers separately.

Public-alpha preparation, installation/versioning, documentation and manual KiCad workflow validation can proceed independently while the provider-access question is unresolved.
