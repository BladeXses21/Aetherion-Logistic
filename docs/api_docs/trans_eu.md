# Trans.eu API Documentation (Cargo Search)

**Coverage:** Europe / CIS / Global
**API Type:** Official REST (HAL+JSON)
**Base URL:** `https://api.trans.eu/v2`

## 1. Get Cargos by Filters

**Endpoint:** `POST /freights/searches`
**Authentication:** `Authorization: Bearer {token}` (OAuth 2.0)

### Filters (Request Body):
```json
{
  "place_of_loading": "Krakow, PL",
  "place_of_unloading": "Kyiv, UA",
  "min_weight": 5000,
  "max_weight": 22000,
  "truck_body_type": ["curtain", "frigo"]
}
```

## 2. Get Cargo Details

**Endpoint:** `GET /freights/{id}`
**Request:** `https://api.trans.eu/v2/freights/FR-987654`

### Sample Response:
Returns a full object including route points, cargo description, vehicle requirements, and timestamps.

## 3. Get Customer Contacts

**Endpoint:** `GET /freights/{id}/contact`
**Alternate:** Detailed info found in the `links` or `_embedded` section of the freight object.

### Sample Response:
```json
{
  "first_name": "Andrzej",
  "last_name": "Kowalski",
  "phone_numbers": ["+48 12 345 67 89"],
  "email": "a.kowalski@trans-speed.pl"
}
```
*Note: Requires OAuth scope `freight_details` and valid partnership level.*

---
**Official Docs:** [developers.trans.eu](https://developers.trans.eu/)
