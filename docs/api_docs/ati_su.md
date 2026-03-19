# Ati.su API Documentation (Cargo Search)

**Coverage:** Ukraine / CIS / Europe
**API Type:** Official REST JSON
**Base URL:** `https://api.ati.su/v1.0`

## 1. Get Cargos by Filters

**Endpoint:** `POST /loads/search` (or `GET` with parameters)
**Authentication:** `Authorization: Bearer {token}`

### Filters (Request Body):
```json
{
  "From": {
    "CityId": 123,
    "RegionId": 456
  },
  "To": {
    "CityId": 789
  },
  "Weight": {
    "Min": 20,
    "Max": 22
  },
  "Volume": {
    "Min": 80,
    "Max": 90
  },
  "BodyTypeIds": [1, 2],
  "LoadingDate": {
    "From": "2026-03-20",
    "To": "2026-03-25"
  }
}
```

## 2. Get Cargo Details

**Endpoint:** `GET /loads/{id}`
**Request:** `https://api.ati.su/v1.0/loads/12345678`

### Sample Response:
Returns a full object including description, exact dimensions, payment terms, and metadata.

## 3. Get Customer Contacts

**Endpoint:** Included in the load object or via:
`GET /loads/{id}/contacts`

### Sample Response:
```json
{
  "ContactName": "Ivan Ivanov",
  "Phones": ["+380671112233"],
  "CompanyName": "Best Logistics UA"
}
```
*Note: Full contacts require a subscription (Ati.su "All Loads" or "Your Region").*

---
**Official Docs:** [api.ati.su](https://api.ati.su/v1.0/docs/)
