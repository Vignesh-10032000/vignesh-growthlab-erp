# Vignesh GrowthLab (VGL) — ERP Features & Documentation Hub
> **Storage Location:** `D:\erp features\`  
> **Brand Identity:** **Vignesh GrowthLab** (Short: **VGL**)  
> **Consolidated on:** September 9, 2026

This directory contains the official technical documentation, module inventories, architectural specifications, setup guides, and UI screenshots for the **Vignesh GrowthLab (VGL)** Enterprise Resource Planning platforms.

---

## 📑 Document Catalog

### 1. [Wholesale_ERP_Features_and_Future_Roadmap.html](./Wholesale_ERP_Features_and_Future_Roadmap.html)
* **Format:** Standalone Interactive HTML Document (open directly in any browser)
* **Contents:**
  * Complete 10-module functional breakdown for Vignesh GrowthLab Wholesale ERP
  * System architecture (React 18 + FastAPI + MariaDB 12.3 + ClearTax)
  * Statutory Indian GST, HSN, and E-Invoicing / E-Way bill rules
  * Database schema outline (65+ relational tables)
  * Phase 1 to Phase 4 future feature roadmap

### 2. [Wholesale_ERP_Master_Feature_Walkthrough.md](./Wholesale_ERP_Master_Feature_Walkthrough.md)
* **Format:** Markdown Technical Specification
* **Contents:**
  * In-depth specification of all 10 core enterprise modules:
    1. Master Settings & System Configuration (Row-locked atomic sequence generator `VGL/26-27/001`, FY engine)
    2. Products & Inventory Management (True FIFO cost layer tracking, bulk CSV upload)
    3. Purchases & Vendor Operations (Purchase orders, vendor ledgers, GRPO)
    4. Sales, B2B Billing & Dispatch (B2B/B2C invoices, Delivery Challans, WhatsApp PDF sharing)
    5. Customer Management & Credit Controls (Payment terms, ageing buckets, credit limits)
    6. Financial Accounting & General Ledger (Automated double-entry journals, Cheque register)
    7. GST Compliance & E-Invoicing (ClearTax API integration, sandbox/live modes)
    8. Logistics & Dispatch Operations (Transporter tracking, vehicle numbers, dispatch statuses)
    9. Business Intelligence & Reports (Gross profit margins, stock movement, sales summaries)
    10. Security, Authentication & User Management (OAuth2 JWT, RBAC permissions matrix)

### 3. [VGL_Wholesale_ERP_Architecture_Analysis.md](./VGL_Wholesale_ERP_Architecture_Analysis.md)
* **Format:** Markdown Technical Analysis
* **Contents:**
  * Technical architecture of the Vignesh GrowthLab Wholesale ERP
  * FastAPI Python backend & React 18 / Vite frontend specifications
  * Design patterns (Service-layer separation, SQLAlchemy ORM, Alembic migrations)
  * Database prerequisites and local environment configuration

### 4. [Wholesale_ERP_Local_Setup_and_Testing.md](./Wholesale_ERP_Local_Setup_and_Testing.md)
* **Format:** Markdown Setup Guide
* **Contents:**
  * MariaDB initialization and schema seeding instructions
  * Default Superadmin credentials (`superadmin` / `Admin@1234`)
  * Frontend Vite testing URL (`http://localhost:5173/`)
  * FastAPI interactive Swagger documentation URL (`http://localhost:8000/docs`)

### 5. [VGL_Brand_Identity_and_UI_Specification.md](./VGL_Brand_Identity_and_UI_Specification.md)
* **Format:** Markdown Brand Specification
* **Contents:**
  * Official brand identity, typography, and corporate color palette
  * Sequence codes and corporate database settings (`VGL-INV-`, `VGL-DC-`, `VGL-PO-`)
  * UI application standards for page titles, headers, and login screens

### 6. [Django_Cargo_Management_ERP_Reference.md](./Django_Cargo_Management_ERP_Reference.md)
* **Format:** Markdown Quick Reference
* **Contents:**
  * Vignesh GrowthLab Cargo & Dispatch Management ERP documentation
  * URL routing table (Customers, Delivery Challans, Spare Serials)
  * Database models and administration panel reference (`http://127.0.0.1:8000/admin/`)

---

## 🖼️ UI Screenshots (`./screenshots/`)
Original application screenshots showing the active interface of the Wholesale ERP (unmodified as requested):
* `media__1782450275368.png` — Login / Auth Screen
* `media__1782450671520.png` — Dashboard Overview & KPI Metrics
* `media__1782450763688.png` — Product & Inventory Management
* `media__1782450974653.png` — Purchase Order & Vendor Workflow
* `media__1782451126776.png` — Sales Invoice & B2B Billing
* `media__1782451688989.png` — Accounting & General Ledger Entries
* `media__1782451963143.png` — Reports & GST E-Invoice Status
