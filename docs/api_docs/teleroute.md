# Teleroute (Alpega) API Documentation

**Coverage:** Western & Central Europe
**API Type:** REST (T-Interface)
**Base URL:** `https://api.teleroute.alpega.com/api/v1`

## 1. Get Cargos by Filters

**Endpoint:** `POST /freight/search`
**Authentication:** `Authorization: Bearer {JWT}`

### Filters:
```json
{
  "pickup": "FR-75 Paris",
  "delivery": "ES-08 Barcelona",
  "weight": {"min": 5000, "max": 20000},
  "loadingDate": "2026-03-24"
}
```

## 2. Get Cargo Details

**Endpoint:** `GET /freight/{id}`
**Request:** `GET /api/v1/freight/TR-443322`

## 3. Get Customer Contacts

**Endpoint:** Included in the freight detail object under the `publisher` or `contact` key.

### Attributes:
- `phone`: Direct contact number.
- `name`: Dispatcher name.
- `language`: Preferred communication language.

---
**Official Docs:** [teleroute.com](https://teleroute.com/en/tms-integration/)
