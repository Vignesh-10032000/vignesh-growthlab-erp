# Vignesh GrowthLab Wholesale ERP — Local Setup & Testing Walkthrough

The **Vignesh GrowthLab (VGL) Wholesale ERP** system has been configured for local testing!

## What was configured

1.  **MariaDB**: The database was initialized, and a background service is running on port `3306`.
2.  **Database Seeding**: The core database `wholesale_erp` was created, and all 65+ tables were generated using the system's `reset_db.py` script. The default `superadmin` account was seeded, along with default charts of accounts and sequences.
3.  **Backend (FastAPI)**: A new Python 3.11 environment was set up to bypass the incompatible Python 3.14 installed on your system. All dependencies were successfully downloaded, and the backend API server is running.
4.  **Frontend (React/Vite)**: All Node modules were installed, and the Vite development server is up and running.

## How to access the system

You can now open your web browser and navigate to the following URL to start testing the UI:

**[http://localhost:5173/](http://localhost:5173/)**

> [!IMPORTANT]
> The default login credentials for the admin account are:
> **Username**: `superadmin`
> **Password**: `Admin@1234`

## API Documentation

If you want to test the raw API endpoints or view the FastAPI Swagger documentation, you can access it here:

**[http://localhost:8000/docs](http://localhost:8000/docs)**

> [!NOTE]
> Currently, the backend, frontend, and MariaDB server are running as background tasks. They will remain active for you to test as long as this session remains open.
