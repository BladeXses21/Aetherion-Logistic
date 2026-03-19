# Lardi-Trans Platform — Technical API Reference

> Generated: 2026-03-14 via live reverse-engineering session (authenticated browser + network interception)
> Base URL: `https://lardi-trans.com`
> All API endpoints are prefixed with `/webapi/`

---

## 1. System Overview

Lardi-Trans is a Ukrainian freight exchange platform. The web application is a React SPA that communicates with a REST/JSON backend. All authenticated API calls require a valid session cookie (`LTSID`). The platform uses Cloudflare Bot Management — browser-based login is required to obtain cookies; direct HTTP login is blocked by CF challenge.

**Key architectural facts:**
- Authentication: Cookie-based session (`LTSID` header)
- Real-time updates: Centrifuge WebSocket (`/webapi/centrifuge/token/`)
- Content language: Ukrainian (`UK`) / English (`EN`) switchable
- Cargo proposals are identified by 64-bit numeric IDs (e.g., `206668785705`)
- Distance values in API responses are in **meters** (not km)
- Payment values with `paymentValue: 0` mean "contract price on request"

---

## 2. Authentication Flow

### 2.1 Login Endpoint

```
POST /accounts/ajax/login/?backurl={encoded_backurl}
Content-Type: application/x-www-form-urlencoded

login=user@email.com&password=YourPassword
```

**Response:** HTTP 200 with `Set-Cookie: LTSID=<session_id>; ...`

On success, the browser is redirected to the `backurl`. On Cloudflare-protected environments, this endpoint requires a real browser with a valid CF clearance token.

### 2.2 Session Verification

```
GET /webapi/check-auth/
Cookie: LTSID=<session_id>
```

Returns user auth status. Returns 401 if session is invalid/expired.

### 2.3 Auth Token Exchange (for SPA bootstrap)

```
GET /accounts/token/?backUrl={encoded_url}
```

Used by the SPA to exchange session for a short-lived token after login redirect.

### 2.4 Session Cookies

| Cookie Name     | Purpose                                      |
|-----------------|----------------------------------------------|
| `LTSID`         | **Primary session identifier** (required)    |
| `lardi_login`   | Persisted login email (URL-encoded)          |
| `lardi_device`  | Device fingerprint UUID                      |
| `lardi_mlogin`  | Base64-encoded last login metadata           |
| `__oagr`        | Consent flag                                 |

**Minimum required cookie for API calls:** `LTSID`

### 2.5 Session Limit Handling

If the account has too many active sessions, a modal appears with sessions list. The endpoint to close a session is unknown but the UI shows a delete button per session. After closing, a "Continue" button proceeds.

---

## 3. Cargo Search Page Architecture

**URL:** `/log/search/gruz/`
**Authenticated:** Yes (redirects to login if no session)

After a search is executed, the URL changes to include a `filterCode`:
```
/log/search/gruz/{filterCode}
```

Example: `/log/search/gruz/wf1i640iwt1i640ib34pc4pt1`

### 3.1 FilterCode Encoding (Reverse-Engineered)

The `filterCode` is a compact URL-safe string encoding the current filter state. Format segments:

| Segment           | Meaning                                       | Example                    |
|-------------------|-----------------------------------------------|----------------------------|
| `wf{type}i{id}i`  | Waypoint FROM — type + geo ID                 | `wf5i137i` = town ID 137   |
| `wt{type}i{id}i`  | Waypoint TO — type + geo ID                   | `wt5i1078i` = town ID 1078 |
| `b{id}`           | bodyTypeId (integer)                          | `b34` = Тент               |
| `l{id}i{id}i...`  | loadType IDs (chained)                        | `l25i24i26` = 3 types      |
| `pc{n}`           | paymentCurrencyId                             | `pc4` = UAH                |
| `pt{n}`           | paymentValueType (1=TOTAL, 2=PER_KM, 3=PER_T) | `pt1` = total price        |
| `s{n}`            | page size                                     | `s2` = size 20 (default)   |
| `x1p`             | onlyActual flag                               |                            |

Waypoint type codes:
- `1` = country-level (countrySign only), ID appears to be `640` for UA broad search
- `2` = area (oblast level)
- `3` = region (rayon level)
- `4` = postal zone
- `5` = town (municipality level)

---

## 4. Filters Catalogue

### 4.1 Direction Filters

**Filter name:** `directionFrom` / `directionTo`
**UI type:** Multi-level selector (Country → Oblast → Town/PostalZone)
**Request mapping:** `filter.directionFrom.directionRows[].{field}`

Each direction row supports:

| Field                | Type    | Description                        |
|----------------------|---------|------------------------------------|
| `countrySign`        | string  | ISO 2-letter country code ("UA")   |
| `areaId`             | integer | Oblast ID (from `/webapi/geo/areas/`) |
| `regionId`           | integer | Rayon ID (from `/webapi/geo/regions/`) |
| `townId`             | integer | Town ID (from geo search API)      |
| `townName`           | string  | Town name (human-readable)         |
| `postalZone`         | string  | 2-digit postal zone code           |
| `postalCode`         | string  | Full postal code                   |
| `pointRadius`        | integer | Radius in km around a point        |
| `pointCountryBorder` | boolean | Cargo near country border          |

Direction exclusion (at direction level):

| Field              | Type      | Description                   |
|--------------------|-----------|-------------------------------|
| `excludeRegionIds` | int[]     | Exclude these region IDs      |
| `excludeAreaIds`   | int[]     | Exclude these oblast IDs      |
| `excludeTowns`     | object[]  | Exclude specific towns        |

### 4.2 Mass / Volume / Dimensions

| Filter         | UI type     | Request field    | Unit  |
|----------------|-------------|------------------|-------|
| Weight from    | number text | `mass1`          | tons  |
| Weight to      | number text | `mass2`          | tons  |
| Volume from    | number text | `volume1`        | m³    |
| Volume to      | number text | `volume2`        | m³    |
| Length from    | number text | `length1`        | m/ldm |
| Length to      | number text | `length2`        | m/ldm |
| Width from     | number text | `width1`         | m     |
| Width to       | number text | `width2`         | m     |
| Height from    | number text | `height1`        | m     |
| Height to      | number text | `height2`        | m     |

### 4.3 Date Filter

| Filter           | UI type    | Request field  | Format               |
|------------------|------------|----------------|----------------------|
| Loading date from| datepicker | `dateFromISO`  | ISO 8601 (`2026-03-14T00:00:00.000+00:00`) |
| Loading date to  | datepicker | `dateToISO`    | ISO 8601             |

### 4.4 Body Type Filter (Vehicle Type)

**Request field:** `bodyTypeIds` (integer array)
**UI type:** Multi-select checkbox dropdown with 50 options

> ⚠️ CRITICAL: The field name is `bodyTypeIds` with **integer IDs**, NOT `bodyTypes` with string codes. String values are silently ignored by the server.

Full list of body types available in UI (50 options total):

**Крита (Covered) group:**
| UI Label         | Notes                    |
|------------------|--------------------------|
| Тент             | bodyTypeId = **34** (confirmed) |
| Цільномет        |                          |
| Бус              |                          |
| Зерновоз         |                          |
| Контейнер        |                          |
| Одяговоз         |                          |
| Ізотерм          |                          |
| Реф.             |                          |
| Реф.-тушевоз     |                          |

**Пасажирський (Passenger) group:**
| UI Label     |
|--------------|
| Мікроавтобус |
| Автобус      |

**Відкрита (Open) group:**
| UI Label                    |
|-----------------------------|
| Бортова / Відкрита          |
| Платформа                   |
| Маніпулятор                 |
| Ломовоз / Металовоз         |
| Контейнеровоз               |
| Трал / Негабарит            |
| Плитовоз                    |
| Самоскид                    |

**Цистерна (Tank) group:**
| UI Label      |
|---------------|
| 40'           |
| 20'           |
| Молоковоз     |
| Бітумовоз     |
| Бензовоз      |
| Газовоз       |
| Кормовоз      |
| Борошновоз    |
| Автоцистерна  |
| Цементовоз    |
| Масловоз      |

**Спеціальна техніка (Special) group:**
| UI Label                 |
|--------------------------|
| Автовоз                  |
| Автовишка                |
| Бетоновоз                |
| Лісовоз                  |
| Коневоз                  |
| Кран                     |
| Сміттєвоз                |
| Навантажувач             |
| Птаховоз                 |
| Скотовоз                 |
| Скловоз                  |
| Трубовоз                 |
| Тягач                    |
| Тягач з маніпулятором    |
| Щеповоз                  |
| Евакуатор                |
| Яхтовоз                  |

**Special modifier prefixes (appear at top of list):**
| UI Label   | Notes                        |
|------------|------------------------------|
| Doubledeck | Applies to multiple base types |
| Jumbo      |                              |
| Mega       |                              |

### 4.5 Loading Type Filter

**Request field:** `loadTypes` (integer array)
**UI type:** Multi-select dropdown

Confirmed string → integer ID mapping from `loadTypes` field in response:

| Ukrainian       | English          | filterCode segment |
|-----------------|------------------|--------------------|
| заднє           | rear             | `l26`              |
| верхнє          | top              | `l25` or `l24`     |
| бічне           | side             | `l24` or `l25`     |
| повне розтентування | full detent | -                  |
| гідроборт       | tail lift        | -                  |

> Note: Saved user filter `l25i24i26` corresponds to top+side+rear loading.

### 4.6 Payment Filters

| Filter           | UI type          | Request field       | Values                      |
|------------------|------------------|---------------------|-----------------------------|
| Payment min      | number input     | `paymentValue`      | numeric (UAH/USD/EUR)        |
| Payment currency | dropdown         | `paymentCurrencyId` | 4=UAH, 1=USD, 2=EUR, 3=other|
| Payment type     | button group     | `paymentValueType`  | "TOTAL", "PER_KM", "PER_TON"|
| Payment form     | multi-select     | `paymentFormIds`    | integer IDs (see note)       |
| With price only  | checkbox         | `onlyWithStavka`    | boolean                      |

Payment form names observed in responses: `"безготівка"`, `"готівка"`, `"карта"`, `""`
`paymentForms` in response is array of `{name: string, vat: boolean}`

### 4.7 Cargo Filters

| Filter         | UI type      | Request field      | Notes                           |
|----------------|--------------|--------------------|---------------------------------|
| Cargo name     | text search  | `cargos`           | array of string search terms    |
| Exclude cargo  | text search  | `excludeCargos`    | array of string exclusion terms |
| Packaging      | multi-select | `cargoPackagingIds`| integer IDs                     |
| ADR            | dropdown     | `adr`              | boolean or class                |

### 4.8 Document Filters

| Filter                  | UI type      | Request field      |
|-------------------------|--------------|--------------------|
| Documents required      | multi-select | `includeDocuments` |
| Documents not required  | multi-select | `excludeDocuments` |

Document codes observed: `cmr`, `t1`, `tir`, `ekmt`, `frc`, `cmrInsurance`

### 4.9 Display / Behavioral Filters

| Filter                   | UI type  | Request field    | Default |
|--------------------------|----------|------------------|---------|
| Only actual (not expired)| toggle   | `onlyActual`     | `true`  |
| Only new (not repeated)  | toggle   | `onlyNew`        | `null`  |
| With photo               | checkbox | `photos`         | `null`  |
| Partial load (LTL)       | checkbox | `groupage`       | `null`  |
| Show ignored             | toggle   | `showIgnore`     | `false` |
| Company-only filter      | text     | `companyRefId` / `companyName` | `null` |
| Partners only            | toggle   | `onlyPartners`   | `null`  |

### 4.10 User Role Filters (Counterparty Type)

| Filter              | Request field    | Values                |
|---------------------|------------------|-----------------------|
| Shipper only        | `onlyShippers`   | boolean               |
| Carrier only        | `onlyCarrier`    | boolean               |
| Expedition only     | `onlyExpedition` | boolean               |

### 4.11 Distance Filter

| Filter          | Request field    | Unit |
|-----------------|------------------|------|
| Distance from   | `distanceKmFrom` | km   |
| Distance to     | `distanceKmTo`   | km   |

---

## 5. Search API Specification

### 5.1 Execute Search

```
POST /webapi/proposal/search/gruz/
Content-Type: application/json
Cookie: LTSID=<session_id>
```

#### Minimal Request Payload

```json
{
  "page": 1,
  "size": 20,
  "sortByCountryFirst": false,
  "filter": {
    "directionFrom": {
      "directionRows": [
        { "countrySign": "UA" }
      ]
    },
    "directionTo": {
      "directionRows": [
        { "countrySign": "UA" }
      ]
    },
    "onlyActual": true,
    "paymentCurrencyId": 4,
    "paymentValueType": "TOTAL"
  }
}
```

#### Full Filter Payload (All Fields)

```json
{
  "page": 1,
  "size": 20,
  "sortByCountryFirst": false,
  "filter": {
    "directionFrom": {
      "directionRows": [
        {
          "countrySign": "UA",
          "postalZone": null,
          "regionId": null,
          "areaId": null,
          "townId": null,
          "townName": null,
          "postalCode": null,
          "pointRadius": null,
          "pointCountryBorder": null
        }
      ],
      "excludeRegionIds": null,
      "excludeAreaIds": null,
      "excludeTowns": null
    },
    "directionTo": {
      "directionRows": [
        {
          "countrySign": "UA",
          "townId": 1078
        }
      ],
      "excludeRegionIds": null,
      "excludeAreaIds": null,
      "excludeTowns": null
    },
    "mass1": null,
    "mass2": null,
    "volume1": null,
    "volume2": null,
    "dateFromISO": null,
    "dateToISO": null,
    "bodyTypeIds": null,
    "companyRefId": null,
    "companyName": null,
    "length1": null,
    "length2": null,
    "width1": null,
    "width2": null,
    "height1": null,
    "height2": null,
    "includeDocuments": null,
    "excludeDocuments": null,
    "loadTypes": null,
    "adr": null,
    "paymentFormIds": null,
    "paymentCurrencyId": 4,
    "paymentValue": null,
    "paymentValueType": "TOTAL",
    "onlyNew": null,
    "onlyActual": true,
    "onlyRelevant": null,
    "onlyShippers": null,
    "onlyCarrier": null,
    "onlyExpedition": null,
    "onlyWithStavka": null,
    "groupage": null,
    "photos": null,
    "showIgnore": false,
    "distanceKmFrom": null,
    "distanceKmTo": null,
    "onlyPartners": null,
    "partnerGroups": null,
    "cargos": null,
    "cargoPackagingIds": null,
    "excludeCargos": null,
    "cargoBodyTypeProperties": null
  }
}
```

#### Response Structure

```json
{
  "filter": { /* echo of normalized filter */ },
  "filterCode": "wf1i640iwt1i640is2pc4pt1",
  "result": {
    "proposals": [ /* array of CargoProposal objects */ ],
    "paginator": {
      "current": 1,
      "perPage": 20,
      "pages": 25,
      "totalSize": 500
    },
    "error": null
  }
}
```

> ⚠️ `totalSize` is capped server-side at **500**. The platform never reveals the true total count beyond 500. `pages` is calculated as `ceil(min(total, 500) / perPage)`.

### 5.2 Search with City-Level Routing

To search from Kyiv (ID 137) to Odesa (ID 1078):

```json
{
  "page": 1,
  "size": 20,
  "sortByCountryFirst": false,
  "filter": {
    "directionFrom": {
      "directionRows": [{ "countrySign": "UA", "townId": 137 }]
    },
    "directionTo": {
      "directionRows": [{ "countrySign": "UA", "townId": 1078 }]
    },
    "onlyActual": true,
    "paymentCurrencyId": 4,
    "paymentValueType": "TOTAL"
  }
}
```

### 5.3 Search with Body Type + Mass Range

```json
{
  "page": 1,
  "size": 20,
  "sortByCountryFirst": false,
  "filter": {
    "directionFrom": { "directionRows": [{ "countrySign": "UA" }] },
    "directionTo":   { "directionRows": [{ "countrySign": "UA" }] },
    "bodyTypeIds": [34],
    "mass1": 5,
    "mass2": 22,
    "onlyActual": true,
    "paymentCurrencyId": 4,
    "paymentValueType": "TOTAL"
  }
}
```

---

## 6. Cargo Entity Schema

### 6.1 Proposal (Search Result List Item)

Returned as elements of `result.proposals[]` from the search endpoint.

```json
{
  "id": 206668785705,
  "status": "PUBLISHED",
  "proposalUser": null,
  "accessType": "PUBLIC",
  "dateCreate": "2026-03-13T09:15:52.000+00:00",
  "dateRepeat": "2026-03-14T18:50:39.000+00:00",
  "dateRepeatAvailable": "2026-03-14T19:50:39.000+00:00",
  "dateEdit": "2026-03-14T18:50:39.000+00:00",
  "dateFrom": "2026-03-14T00:00:00.000+00:00",
  "dateTo": "2026-03-17T00:00:00.000+00:00",
  "bodyType": "Тент, Зерновоз",
  "note": "",
  "ownerPremium": false,
  "groupage": false,
  "photos": [],
  "fromToCountries": "UA - UA",
  "waypointListSource": [
    {
      "country": "Україна",
      "countrySign": "UA",
      "town": "Нова Любомирка",
      "townId": 1549873,
      "region": "Рівненська обл.",
      "postalZones": ["35"],
      "postalCodes": [],
      "address": "",
      "lat": 50.764729,
      "lon": 26.372339,
      "radiusMeters": 0
    }
  ],
  "waypointListTarget": [ /* same structure */ ],
  "payment": "запит вартості",
  "paymentValueDescription": "",
  "paymentDetails": "",
  "paymentForms": [],
  "distance": 214789.392,
  "distanceTime": 11462555,
  "autoCountLine": "1 а/м",
  "permissions": "",
  "loadTypes": "",
  "tempRegime": "",
  "noteItem": null,
  "updated": false,
  "repeated": true,
  "relevanceWarning": false,
  "gruzName": "міндобриво біг бег",
  "gruzMass": "17 т",
  "gruzVolume": "",
  "gruzLength": null,
  "gruzWidth": null,
  "gruzHeight": null,
  "cargoAdr": "",
  "cargoPackaging": [],
  "cargoBodyTypeProperties": []
}
```

**Note:** In search list results, `proposalUser` is `null` (contacts are withheld). Use the detail endpoint to retrieve contacts.

**Distance unit:** meters (divide by 1000 for km).

**Payment formats:**
- `"40 000 грн."` — fixed price in UAH
- `"запит вартості"` — contract price on request (paymentValue = 0)

### 6.2 Full Offer Detail (includes contacts)

Returned by `GET /webapi/proposal/offer/gruz/{id}/awaiting/?currentId={id}`

```json
{
  "cargo": {
    "id": 206668785705,
    "status": "PUBLISHED",
    "accessType": "PUBLIC",
    "dateCreate": "...",
    "dateRepeat": "...",
    "dateRepeatAvailable": "...",
    "dateEdit": "...",
    "dateFrom": "...",
    "dateTo": "...",
    "dateColor": "...",
    "repeatCountToday": 6,
    "autoRepeat": false,
    "autoRepeatExpire": null,
    "paymentValue": 0,
    "bodyType": "Тент, Зерновоз",
    "note": "",
    "complaintCount": 0,
    "ownerPremium": false,
    "groupage": false,
    "photos": [],
    "updated": false,
    "repeated": true,
    "relevanceWarning": false,
    "waypointListSource": [
      {
        "townId": 1549873,
        "townName": "Нова Любомирка",
        "townFullName": "Нова Любомирка, Рівненська обл.",
        "areaId": 31,
        "regionId": 0,
        "countrySign": "UA",
        "postalZones": ["35"],
        "postalCodes": [],
        "address": "",
        "lat": 50.764729,
        "lon": 26.372339,
        "radiusMeters": 0
      }
    ],
    "waypointListTarget": [ /* same structure */ ],
    "paymentValueDescription": "",
    "paymentCurrency": "",
    "paymentUnit": "",
    "paymentPrepay": 0,
    "paymentMoment": "",
    "paymentDelay": 0,
    "paymentForms": [],
    "loadTypes": [],
    "cmr": false,
    "cmrInsurance": false,
    "t1": false,
    "tir": false,
    "ekmt": false,
    "frc": false,
    "autoCount": 1,
    "tempRegime": false,
    "tempRegime1": 0,
    "tempRegime2": 0,
    "whoIs": "mobile|178.137.206.159",
    "proposalUser": {
      "refId": 13815098368,
      "address": {
        "townId": 3570,
        "town": "Хмельницкий",
        "country": "",
        "countrySign": "UA",
        "areaId": 36,
        "areaName": "",
        "address": ""
      },
      "contact": {
        "contactId": 0,
        "contactRefId": 0,
        "face": "Брошко Андрій Михайлович",
        "name": "Брошко Андрій Михайлович",
        "nameLang": "UK",
        "nameWithBrand": "Брошко Андрій Михайлович",
        "nameWithoutBrand": "Брошко Андрій Михайлович",
        "phoneItem1": {
          "phone": "+380679078186",
          "linkPhone": "380679078186",
          "messengerTypes": [],
          "verified": true
        },
        "phoneItem2": { "phone": "", "linkPhone": "", "messengerTypes": [], "verified": false },
        "phoneItem3": { "phone": "", "linkPhone": "", "messengerTypes": [], "verified": false },
        "phoneItem4": { "phone": "", "linkPhone": "", "messengerTypes": [], "verified": false },
        "avatarUrls": { "url40x40": null, "url100x100": null }
      },
      "flags": {
        "approvedUa": false,
        "shipper": false,
        "carrier": false,
        "expedition": false,
        "carrierGps": false,
        "approvedContacts": false,
        "profileApproved": true,
        "vip": false
      },
      "ownershipType": "INDIVIDUAL",
      "rating": {
        "goodRespCount": 0,
        "badRespCount": 0,
        "raitingBal": 0,
        "fromRespCount": 0
      },
      "logoUrls": { "url40x40": null, "url100x100": null, "url60x60": "", "url72x72": "", "url170x132": "", "url340x340": "" },
      "deleted": false
    },
    "gruzName": "міндобриво біг бег",
    "cargoAdr": "",
    "medBook": false,
    "customControl": false,
    "autoInterval": "",
    "gruzMass1": 17,
    "gruzVolume1": 0,
    "gruzLength": 0,
    "gruzWidth": 0,
    "gruzHeight": 0,
    "cargoPackaging": [],
    "cargoBodyTypeProperties": []
  },
  "offers": []
}
```

**Difference between list and detail:**
- `gruzMass` (list) = `"17 т"` (string) → `gruzMass1` (detail) = `17` (float, tons)
- `gruzVolume` (list) = `""` (string) → `gruzVolume1` (detail) = `0` (float, m³)
- `waypointListSource[].townFullName` — only in detail (absent in list)
- `proposalUser` with full contact info — **only in detail**

---

## 7. Pagination Mechanism

### 7.1 Paginator Object

```json
{
  "current": 1,
  "perPage": 20,
  "pages": 25,
  "totalSize": 500
}
```

- `current` — current page number (1-indexed)
- `perPage` — items per page (equals the `size` parameter in request)
- `pages` — total pages available = `ceil(totalSize / perPage)`
- `totalSize` — **server-capped at 500** regardless of actual count

### 7.2 Pagination Request

```json
{
  "page": 2,
  "size": 20,
  "sortByCountryFirst": false,
  "filter": { /* same filter as page 1 */ }
}
```

### 7.3 Max Page Size

The `size` parameter accepts values up to at least 50. Standard UI value is 20. Tested with size=50 successfully.

### 7.4 Sorting

`sortByCountryFirst: true` — groups results by country (all domestic UA results first, then international).
`sortByCountryFirst: false` — chronological (most recently repeated first, default).

No other sort parameters were observed on the search endpoint. The UI shows results sorted by `dateRepeat` descending by default.

---

## 8. Network Requests Reference

| Method | Endpoint                                      | Auth | Purpose                              |
|--------|-----------------------------------------------|------|--------------------------------------|
| POST   | `/accounts/ajax/login/`                       | No   | Login, sets LTSID cookie             |
| GET    | `/webapi/check-auth/`                         | Yes  | Verify session validity              |
| GET    | `/webapi/pageinfo/`                           | Yes  | User profile, media URLs, site config|
| GET    | `/webapi/centrifuge/token/`                   | Yes  | WebSocket token for real-time updates|
| POST   | `/webapi/proposal/search/gruz/`               | Yes  | **Main cargo search**                |
| GET    | `/webapi/proposal/search/gruz/`               | Yes  | Initial page load (empty result)     |
| GET    | `/webapi/proposal/offer/gruz/{id}/awaiting/`  | Yes  | Full cargo offer with contacts       |
| GET    | `/webapi/proposal/filters/gruz/`             | Yes  | User's saved search filters list     |
| GET    | `/webapi/proposal/bookmark/gruz/check/`       | Yes  | Check if proposals are bookmarked    |
| GET    | `/webapi/geo/regions/?sign={countrySign}`     | Yes  | Geo regions (macro areas) by country |
| GET    | `/webapi/geo/areas/?sign={countrySign}`       | Yes  | Oblasts/provinces by country         |
| GET    | `/webapi/geo/postalzone/?sign={countrySign}`  | Yes  | Postal zones by country              |
| GET    | `/webapi/geo/region-area-town/?query={q}&sign={s}` | Yes | Town autocomplete search        |
| GET    | `/webapi/tender/filter/count/`                | Yes  | Tender count for given direction     |
| POST   | `/webapi/individuals/freights/count/`         | Yes  | Private cargo count                  |
| POST   | `/uk/webapi/chat/reset-email-notifications/`  | Yes  | Reset unread chat notifications      |
| POST   | `/op.lardi-trans.com/api/track`               | Yes  | Internal analytics/event tracking    |

### 8.1 Offer Detail URL Parameters

```
GET /webapi/proposal/offer/gruz/{id}/awaiting/?currentId={id}
```

Both path and query param use the same offer ID. The `awaiting` path segment indicates the "view before contacting" state.

### 8.2 Bookmark Check

```
GET /webapi/proposal/bookmark/gruz/check/?proposalIds={id1}&proposalIds={id2}&...
```

Repeated query params (not array notation). Returns bookmark status per ID.

### 8.3 Geo — Town Search

```
GET /webapi/geo/region-area-town/?query=Київ&sign=UA
```

Returns array of geo objects:
```json
[
  { "id": 23, "name": "Київська обл.", "type": "AREA" },
  { "id": 137, "name": "Київ, Київська обл.", "type": "TOWN" },
  { "id": 1547215, "name": "Київ, Миколаївська обл.", "type": "TOWN" }
]
```

Types: `AREA`, `TOWN`, `REGION`, `POSTALZONE`

### 8.4 Geo — Areas (Oblasts)

```
GET /webapi/geo/areas/?sign=UA
```

Returns full list of oblasts:
```json
[
  { "id": 15, "name": "Вінницька обл.", "countrySign": "UA" },
  { "id": 16, "name": "Волинська обл.", "countrySign": "UA" },
  ...
]
```

### 8.5 Geo — Regions (Macro Regions)

```
GET /webapi/geo/regions/?sign=UA
```

Returns macro-region groupings (not oblasts):
```json
[
  { "id": 2, "name": "Схід" },
  { "id": 4, "name": "Захід" },
  { "id": 6, "name": "Північ" },
  ...
]
```

---

## 9. Observed Frontend Logic

### 9.1 SPA Routing

The application is a React SPA loaded at `/log/`. After login, all navigation is client-side. The URL `filterCode` suffix is written to `window.history` on each search execution.

### 9.2 Real-Time Updates (Centrifuge WebSocket)

On page load the app fetches `/webapi/centrifuge/token/` and establishes a WebSocket connection via the Centrifuge protocol (using a shared worker at `/staticreact/centrifuge.shared-worker.js`). This is used to push new cargo proposals in real-time without polling.

### 9.3 Search Trigger Behavior

- The "Знайти" (Search) button is **disabled** until at least one direction field (FROM or TO) has a country selected.
- Auto-search feature (`Автопошук`) triggers via the Centrifuge WebSocket when new proposals matching a saved filter arrive.
- The UI debounces country/city input changes before triggering geo autocomplete.

### 9.4 Geo Data Loading

When a country is selected in the direction fields, the app immediately fires 3 parallel GET requests:
- `/webapi/geo/regions/?sign={countrySign}`
- `/webapi/geo/areas/?sign={countrySign}`
- `/webapi/geo/postalzone/?sign={countrySign}`

### 9.5 After Search Execution

After a search, the app fires these requests in parallel:
1. `POST /webapi/proposal/search/gruz/` — main results
2. `GET /webapi/proposal/bookmark/gruz/check/?proposalIds=...` — bookmark status for all result IDs
3. `GET /webapi/tender/filter/count/?countrySignsFrom=UA&countrySignsTo=UA` — tender count banner
4. `POST /webapi/individuals/freights/count/` — private cargo count banner

### 9.6 Saved Filters

Saved filters are stored server-side. The saved filter payload has the structure:
```json
{
  "id": "685abca535da7761751f0a31",
  "name": "1",
  "filter": "wf1i640iwt1i640il25i24i26x1pl2",
  "selected": false,
  "settingsMessengerNotifications": false
}
```

The `filter` field here is the same `filterCode` format used in the URL.

---

## 10. Integration Opportunities

### 10.1 Programmatic Cargo Search

Full automation is possible using only the `LTSID` session cookie:

```python
import aiohttp

async def search_cargo(session_cookie: str, from_town_id: int, to_town_id: int, page: int = 1):
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"LTSID={session_cookie}",
        "Referer": "https://lardi-trans.com/log/search/gruz/",
        "Origin": "https://lardi-trans.com",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
    }
    payload = {
        "page": page,
        "size": 20,
        "sortByCountryFirst": False,
        "filter": {
            "directionFrom": {"directionRows": [{"countrySign": "UA", "townId": from_town_id}]},
            "directionTo":   {"directionRows": [{"countrySign": "UA", "townId": to_town_id}]},
            "onlyActual": True,
            "paymentCurrencyId": 4,
            "paymentValueType": "TOTAL"
        }
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://lardi-trans.com/webapi/proposal/search/gruz/",
            headers=headers,
            json=payload
        ) as resp:
            return await resp.json()
```

### 10.2 Town ID Resolution

Before searching by city, resolve city names to town IDs:

```
GET /webapi/geo/region-area-town/?query=Київ&sign=UA
→ First result with type="TOWN" gives the canonical town ID
```

Known key city IDs:
- Київ (Kyiv): **137**
- Одеса (Odesa): **1078**
- Львів (Lviv): resolve via API
- Харків (Kharkiv): resolve via API

### 10.3 Session Refresh Strategy

1. Store `LTSID` cookie to file
2. Before each request batch, call `GET /webapi/check-auth/`
3. If 401 — trigger browser-based re-login via `undetected-chromedriver`
4. Save new `LTSID` cookie and retry

### 10.4 Offer Contact Retrieval

Two-step process:
1. Search returns `id` per proposal
2. Fetch detail: `GET /webapi/proposal/offer/gruz/{id}/awaiting/?currentId={id}`
3. Extract from `cargo.proposalUser.contact.phoneItem1.phone`

---

## 11. Risks and Limitations

| Risk | Severity | Detail |
|------|----------|--------|
| Cloudflare Bot Management | High | Direct HTTP login blocked. Requires real browser with CF clearance |
| Session expiry | Medium | `LTSID` expires after ~1-2 hours of inactivity. Auto-refresh required |
| Result cap at 500 | Medium | `totalSize` is always ≤ 500 even if more results exist. Use filter narrowing |
| No public API | Medium | No official API key system. All integration is via reverse-engineered endpoints |
| bodyTypeIds integer mapping | Medium | Body type string codes (e.g. `covered_wagon`) are silently ignored. Integer IDs required. Тент = 34 (confirmed), others need discovery |
| Rate limiting | Low-Medium | No explicit rate-limit headers observed, but concurrent abuse may trigger CF |
| Contact visibility | Low | `proposalUser` is null in search results; detail endpoint required for phone numbers |
| Centrifuge WS | Low | Real-time updates via WebSocket not easily replicable in simple HTTP clients |
| `whoIs` field | Low | Records client IP and platform (`mobile|IP`). Rapid searching from same IP may trigger flags |

---

## 12. Practical Examples of Requests

### Example 1: Basic Country-Level Search

```bash
curl -X POST https://lardi-trans.com/webapi/proposal/search/gruz/ \
  -H "Content-Type: application/json" \
  -H "Cookie: LTSID=YOUR_SESSION_ID" \
  -H "Referer: https://lardi-trans.com/log/search/gruz/" \
  -d '{
    "page": 1,
    "size": 20,
    "sortByCountryFirst": false,
    "filter": {
      "directionFrom": {"directionRows": [{"countrySign": "UA"}]},
      "directionTo":   {"directionRows": [{"countrySign": "UA"}]},
      "onlyActual": true,
      "paymentCurrencyId": 4,
      "paymentValueType": "TOTAL"
    }
  }'
```

### Example 2: City-to-City Search (Kyiv → Odesa)

```bash
curl -X POST https://lardi-trans.com/webapi/proposal/search/gruz/ \
  -H "Content-Type: application/json" \
  -H "Cookie: LTSID=YOUR_SESSION_ID" \
  -d '{
    "page": 1, "size": 20, "sortByCountryFirst": false,
    "filter": {
      "directionFrom": {"directionRows": [{"countrySign": "UA", "townId": 137}]},
      "directionTo":   {"directionRows": [{"countrySign": "UA", "townId": 1078}]},
      "onlyActual": true, "paymentCurrencyId": 4, "paymentValueType": "TOTAL"
    }
  }'
```

### Example 3: Filter by Body Type (Тент = 34)

```bash
curl -X POST https://lardi-trans.com/webapi/proposal/search/gruz/ \
  -H "Content-Type: application/json" \
  -H "Cookie: LTSID=YOUR_SESSION_ID" \
  -d '{
    "page": 1, "size": 20, "sortByCountryFirst": false,
    "filter": {
      "directionFrom": {"directionRows": [{"countrySign": "UA"}]},
      "directionTo":   {"directionRows": [{"countrySign": "UA"}]},
      "bodyTypeIds": [34],
      "mass1": 5,
      "mass2": 22,
      "onlyActual": true, "paymentCurrencyId": 4, "paymentValueType": "TOTAL"
    }
  }'
```

### Example 4: Resolve City Name to ID

```bash
curl "https://lardi-trans.com/webapi/geo/region-area-town/?query=Харків&sign=UA" \
  -H "Cookie: LTSID=YOUR_SESSION_ID"
```

### Example 5: Fetch Full Offer with Contact

```bash
curl "https://lardi-trans.com/webapi/proposal/offer/gruz/206668785705/awaiting/?currentId=206668785705" \
  -H "Cookie: LTSID=YOUR_SESSION_ID" \
  -H "Referer: https://lardi-trans.com/log/search/gruz/"
```

### Example 6: Get Oblasts for Country

```bash
curl "https://lardi-trans.com/webapi/geo/areas/?sign=UA" \
  -H "Cookie: LTSID=YOUR_SESSION_ID"
```

### Example 7: Page 2 of Results

```bash
curl -X POST https://lardi-trans.com/webapi/proposal/search/gruz/ \
  -H "Content-Type: application/json" \
  -H "Cookie: LTSID=YOUR_SESSION_ID" \
  -d '{
    "page": 2,
    "size": 20,
    "sortByCountryFirst": false,
    "filter": {
      "directionFrom": {"directionRows": [{"countrySign": "UA"}]},
      "directionTo":   {"directionRows": [{"countrySign": "UA"}]},
      "onlyActual": true, "paymentCurrencyId": 4, "paymentValueType": "TOTAL"
    }
  }'
```

---

## Appendix A: Known Geographic IDs

### UA Oblasts (areas)

| Oblast           | ID |
|------------------|----|
| Вінницька обл.   | 15 |
| Волинська обл.   | 16 |
| Дніпропетровська | 17 |
| Донецька обл.    | 18 |
| Житомирська обл. | 19 |
| Закарпатська обл.| 20 |
| Київська обл.    | 23 |
| (full list from `/webapi/geo/areas/?sign=UA`) |

### Key Town IDs

| City          | townId |
|---------------|--------|
| Київ          | 137    |
| Одеса         | 1078   |
| Хмельницький  | 3570   |
| Нова Любомирка| 1549873|

### Confirmed bodyTypeIds

| Vehicle Type | bodyTypeId |
|--------------|------------|
| Тент         | **34**     |
| (others need mapping) | — |

---

## Appendix B: Existing Codebase Integration Notes

### Critical Bugs in Current Implementation

1. **`agent/lardi/client.py` line 96**: Uses `filters.body_types` mapped to string values (`covered_wagon`, `ref`, etc.) sent as `bodyTypes` request field. **The server silently ignores this field.** Must use `bodyTypeIds` with integer IDs.

2. **`agent/lardi/models.py` CargoFilter**: The `body_types` field is typed as `List[str]` with alias `bodyTypes`. This is incorrect. Should be `List[int]` with alias `bodyTypeIds`.

3. **`agent/tools/lardi_tools.py` BODY_TYPES_MAP**: Maps Ukrainian strings to English codes like `covered_wagon`. This mapping needs to be updated to integer IDs.

### Required Field Name Corrections

| Current (wrong)      | Correct              | Type     |
|----------------------|----------------------|----------|
| `bodyTypes: ['covered_wagon']` | `bodyTypeIds: [34]` | int[] |
| `paymentForms: ['beznal']` | `paymentFormIds: [int]` | int[] |
| `loadTypes: ['back']` | `loadTypes: [26]`    | int[]    |

### Session Cookie String Format

Current implementation correctly uses `LTSID` as the primary session cookie. The `get_cookie_string()` method in `CookieManager` builds a full cookie header string — only `LTSID` is strictly required for API calls.
