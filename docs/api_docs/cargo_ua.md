# Cargo.ua (GetCargo.io) API Documentation

**Coverage:** Ukraine / Global
**API Type:** Modern REST (OpenAPI 3.0)
**Base URL:** `https://api.getcargo.io/v1`

## 1. Get Cargos by Filters

**Endpoint:** `GET /loads`
**Authentication:** `Authorization: Bearer {apiKey}`

### Parameters:
- `pickup_location`: City/Zip.
- `delivery_location`: City/Zip.
- `min_weight`: in kg.
- `max_weight`: in kg.
- `body_types`: Array of strings (e.g., `["curtain", "flatbed"]`).

## 2. Get Cargo Details

**Endpoint:** `GET /loads/{id}`
**Request:** `https://api.getcargo.io/v1/loads/LG-889900`

## 3. Get Customer Contacts

**Endpoint:** Returned directly in the load object within the `contact` or `dispatcher` field.

### Sample Response:
```json
{
  "id": "LG-889900",
  "contact": {
    "name": "Oleg Petrenko",
    "phone": "+380501112233",
    "email": "o.petrenko@cargoua.com"
  }
}
```

---
**Official Docs:** [api.getcargo.io/v1/docs](https://api.getcargo.io/v1/docs)
