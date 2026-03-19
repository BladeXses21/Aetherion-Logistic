# Cargo.lt API Documentation

**Coverage:** Baltics (Lithuania, Latvia, Estonia) / Europe
**API Type:** Official REST
**Base URL:** `https://api.cargo.lt/v1`

## 1. Get Cargos by Filters

**Endpoint:** `GET /cargo/search`
**Authentication:** `Token: {your_key}` (in request parameters or header)

### Parameters:
- `countryFrom`: e.g., "ua"
- `countryTo`: e.g., "lt"
- `weightMin`: kg
- `volumeMin`: m3
- `dateFrom`: YYYY-MM-DD

## 2. Get Cargo Details

**Endpoint:** `GET /cargo/{id}`
**Request:** `https://api.cargo.lt/v1/cargo/554433`

## 3. Get Customer Contacts

**Endpoint:** Returned within the `owner` object in the detail response.

### Fields:
- `name`: Contact person name.
- `phones`: Array of phone strings.
- `email`: Contact email.

---
**Official Docs:** [cargo.lt/en/api-for-developers/](https://www.cargo.lt/en/api-for-developers/)
