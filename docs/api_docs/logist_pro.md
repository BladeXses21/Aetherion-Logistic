# Logist Pro (Logist.ua) API Documentation

**Coverage:** Ukraine (Enterprise/Tender focused)
**API Type:** Official REST
**Base URL:** `https://api-docs.logist-pro.com.ua`

## 1. Get Procedures (Cargo Tenders) by Filters

**Endpoint:** `GET /procedures`
**Authentication:** `ApiKey: {token}`

### Parameters:
- `limit`: Number of results (e.g., 20).
- `skip`: Pagination offset.
- `status`: e.g., "active".

## 2. Get Procedure Details

**Endpoint:** `GET /procedures/{id}`
**Request:** `https://api.logist-pro.com.ua/procedures/778899`

## 3. Get Customer Contacts

**Endpoint:** Typically returned in the `creator` or `organizer` object of the procedure.

### Attributes:
- `fullName`: Dispatcher / Manager name.
- `contacts`: JSON string or array with phone/email.

---
**Official Docs:** [api-docs.logist-pro.com.ua](https://www.api-docs.logist-pro.com.ua/)
