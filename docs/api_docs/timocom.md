# Timocom API Documentation (Cargo Search)

**Coverage:** Europe / UK
**API Type:** Official REST
**Base URL:** `https://api.timocom.com/v1`

## 1. Get Cargos by Filters

**Endpoint:** `POST /freight-offers/searches`
**Authentication:** `X-API-Key: {your_key}` (Bearer Token also supported)

### Filters:
```json
{
  "origin": "DE, 12345 Berlin",
  "destination": "UA, 01001 Kyiv",
  "minWeight": 1000,
  "maxWeight": 24000,
  "loadingDate": "2026-03-22"
}
```

## 2. Get Cargo Details

**Endpoint:** `GET /freight-offers/{id}`
**Request:** `https://api.timocom.com/v1/freight-offers/T-555666`

## 3. Get Customer Contacts

**Endpoint:** Included in the `company` or `contact` field of the search result/detail object.

### Sample Structure:
```json
"contactPerson": {
  "name": "Greta Müller",
  "phoneNumber": "+49 30 999 001",
  "email": "g.mueller@logix.de"
}
```
*Note: Contacts are only returned for authenticated enterprise users.*

---
**Official Docs:** [timocom.com/interfaces](https://www.timocom.com/marketplace/interfaces)
