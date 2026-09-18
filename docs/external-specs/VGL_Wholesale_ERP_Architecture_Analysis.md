# Vignesh GrowthLab Wholesale ERP Analysis Report

## Overview
**Vignesh GrowthLab (VGL) Wholesale ERP** is a comprehensive, enterprise-grade **Enterprise Resource Planning Application** designed specifically for Indian distribution, multi-warehouse stockists, and trading businesses. It encompasses a wide array of business operations ranging from inventory and purchases to double-entry accounting, billing, and GST compliance. The application is built using a modern full-stack architecture with a FastAPI Python backend and a React (Vite) frontend.

## Features & Modules
The application is structured into **10 core modules**:

1. **Scaffold & Security**
   - Role-based User Management (Admin, Accountant, Sales).
   - JWT-based authentication (access and refresh tokens).
   - Activity logs, 2FA, and session management.
2. **Products & Inventory**
   - Complete inventory management with categories.
   - FIFO (First In First Out) cost tracking and valuation.
   - Bulk upload support.
3. **Purchase Module**
   - Vendor management with GSTIN auto-fetch capabilities.
   - Purchase order tracking and vendor ledger maintenance.
4. **Sales & Billing**
   - Invoice generation (B2B/B2C), receipts, and credit notes.
   - WhatsApp share integration for invoices.
5. **Warehouse Management**
   - Opening balances tracking.
   - Stock movement and deductions mapped directly to purchases and sales.
6. **Accounting**
   - Robust double-entry bookkeeping (auto-posted on transactions).
   - Expense management with approval thresholds.
   - Cheque register, TDS tracking, ageing analysis, and trial balance.
7. **GST / E-Invoice / E-Way Bill**
   - Deep integration with **Cleartax API** (includes a sandbox mode for testing).
   - Automated IRN and E-Way Bill generation based on invoice thresholds.
8. **Reports & Dashboard**
   - Live management dashboard with KPIs.
   - 7 distinct report types available.
9. **Banking**
   - Bank stock statements and Bank Reconciliation.
   - Notification systems.
10. **System Configuration**
   - Multi-year financial year engine (`2026-27`), atomic sequence generators (`VGL/26-27/001`).

## Architecture & Tech Stack
- **Backend**: Python 3.11+ using **FastAPI** for high-performance REST APIs. Data manipulation is handled via **SQLAlchemy** ORM and **Alembic** for migrations.
- **Frontend**: **React 18** paired with **Vite** for fast building. Styling is done via **Tailwind CSS**. State management utilizes **Zustand** (auth) and **React Query** (server state), with **Recharts** for visualizations.
- **Database**: **MariaDB** (10.6+) containing over 65 tables.
- **Design Patterns**: Strict service-layer pattern on the backend to separate business logic from thin API routing.

---

## Local Testing & Execution

The system prerequisites are:
- **Python 3.11+**
- **Node.js 18+**
- **MariaDB 10.6+**

### Steps to Run Locally

1. **Database Setup**
   Ensure MariaDB is running, then verify the database and credentials:
   ```sql
   CREATE DATABASE wholesale_erp CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'erp_user'@'localhost' IDENTIFIED BY 'erp_password';
   GRANT ALL PRIVILEGES ON wholesale_erp.* TO 'erp_user'@'localhost';
   FLUSH PRIVILEGES;
   ```

2. **Backend Setup**
   - Navigate to `backend` folder.
   - Set up the `.env` configuration (set `SECRET_KEY`).
   - Create virtual environment and install requirements (`pip install -r requirements.txt`).
   - Run migrations (`alembic upgrade head`) and seed data (`python seed.py`).
   - Start server (`uvicorn app.main:app --reload`).

3. **Frontend Setup**
   - Navigate to `frontend` folder.
   - Run `npm install` and then `npm run dev`.
   - Access the dashboard at `http://localhost:5173`.
   - Default login: `superadmin` / `Admin@1234`.
