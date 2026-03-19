# DeGruz API & Integration Strategy

**Coverage:** Ukraine / CIS
**API Type:** Proprietary (1C-Module) / Reverse-Engineerable
**Web Base:** `https://degruz.com`

## 1. Get Cargos by Filters (Web Pattern)

Since DeGruz lacks a public REST API for general search, the most stable integration method is parsing the search result page or using their mobile API.

**URL Pattern:**
`https://degruz.com/gruzy/{country_from}-{region_from}-{city_from}-{country_to}-{region_to}-{city_to}-{mass}-{volume}-{type}`

**Example:**
Ukraine to Poland: `https://degruz.com/gruzy/ua--0--0--0-0-0-0-0-0` (parameters are indices in their proprietary city/region table).

## 2. Get Cargo Details

**Endpoint:** `GET /account_gruz/{id}`
**Example:** `https://degruz.com/account_gruz/12345/`

## 3. Get Customer Contacts

**Technical Constraint:** Requires a valid session cookie with a paid account.
**Method:** The contacts are rendered server-side in the `/account_gruz/{id}` page. 

### Data Format (Scraped):
- **Phone:** `+38(067)XXX-XX-XX` (Needs unmasking via session).
- **Name:** Standard HTML text in the contact block.

---
**Note:** Official integration for large volumes is only available through their **1C-API** module.
