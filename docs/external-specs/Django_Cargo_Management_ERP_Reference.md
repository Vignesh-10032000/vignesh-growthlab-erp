# Vignesh GrowthLab (VGL) Cargo Management ERP — Quick Reference

## 🚀 Quick Start

### Start the Server
```bash
cd c:\Users\L E N O V O\django
python manage.py runserver
```

### Access the Application
- **Main App**: http://127.0.0.1:8000
- **Admin Panel**: http://127.0.0.1:8000/admin/

### Login Credentials
- **Admin**: `admin` / `admin123`
- **New Users**: Register at http://127.0.0.1:8000/register/

---

## 📋 URL Routes

| Feature | URL | Description |
|---------|-----|-------------|
| Login | `/` | User login page |
| Register | `/register/` | New user registration |
| Dashboard | `/dashboard/` | Main dashboard |
| Add Customer | `/customers/add/` | Create new customer |
| View Customers | `/customers/` | List all customers |
| Edit Customer | `/customers/add/?id=<id>` | Edit existing customer |
| Add DC | `/dc/add/` | Create delivery challan |
| View DCs | `/dc/` | List all delivery challans |
| Download DC PDF | `/dc/download/<id>/` | Download DC as PDF |
| Add Spare | `/spares/add/` | Add spare serial mapping |
| View Spares | `/spares/` | List all spare serials |

---

## 🗄️ Database Models

### Customer
```python
customer_id     # Auto: CUST001, CUST002...
name           # String
email          # Unique email
phone          # String
address        # Text
created_at     # Auto timestamp
```

### DeliveryChallan
```python
dc_number      # Auto: DC001, DC002...
customer       # Foreign key
date           # Date field
products       # JSON array of products
total_amount   # Decimal
created_at     # Auto timestamp
```

### SpareSerialMapping
```python
sno                  # Auto: SNO001, SNO002...
customer             # Foreign key
serial_no            # Unique string
warranty_months      # Integer
warranty_end_date    # Auto-calculated
spare_type           # String
part_code            # String
created_at           # Auto timestamp
```

---

## 🛠️ Common Commands

### Database Management
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Open Django shell
python manage.py shell
```

### Server Management
```bash
# Run development server
python manage.py runserver

# Run on specific port
python manage.py runserver 8080

# Run on all interfaces
python manage.py runserver 0.0.0.0:8000
```

### Static Files
```bash
# Collect static files
python manage.py collectstatic
```

---

## 📦 Project Structure

```
django/
├── cargo/                    # Project settings
├── authentication/           # Main app
│   ├── models.py            # Database models
│   ├── views.py             # Business logic
│   ├── forms.py             # Form definitions
│   ├── urls.py              # URL routing
│   ├── templates/           # HTML templates
│   └── static/              # CSS/JS files
├── db.sqlite3               # Database
├── manage.py                # Django CLI
└── requirements.txt         # Dependencies
```

---

## 🎨 Features at a Glance

### ✅ User Authentication
- Registration with email validation
- Secure login/logout
- Session management

### ✅ Customer Management
- Auto-generated customer IDs
- Full CRUD operations
- Email uniqueness validation

### ✅ Delivery Challan
- Multi-product support
- Dynamic product rows
- Auto-calculation of amounts
- PDF generation

### ✅ Spare Serial Mapping
- Auto-generated SNO
- Warranty tracking
- Auto-calculated end dates

### ✅ Dashboard
- Statistics cards
- Quick actions
- Recent activity feed

---

## 🔧 Configuration Files

### settings.py Key Settings
```python
DEBUG = True                    # Development mode
ALLOWED_HOSTS = []             # Add domains for production
DATABASES = {...}              # SQLite by default
STATIC_URL = 'static/'
MEDIA_URL = '/media/'
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
TIME_ZONE = 'Asia/Kolkata'
```

---

## 📝 Sample Data

### Sample Customer
```
Name: John Doe
Email: john@example.com
Phone: 1234567890
Address: 123 Main Street, City, State
```

### Sample DC Product
```
Product Name: Widget A
Quantity: 10
Price: 100.00
Amount: 1000.00 (auto-calculated)
```

### Sample Spare Serial
```
Customer: John Doe
Serial No: SN123456789
Warranty Months: 12
Spare Type: Motor
Part Code: MT-001
```

---

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Find process using port 8000
netstat -ano | findstr :8000

# Kill the process
taskkill /PID <process_id> /F
```

### Migration Issues
```bash
# Delete migrations (except __init__.py)
# Then recreate
python manage.py makemigrations
python manage.py migrate
```

### Static Files Not Loading
```bash
# Collect static files
python manage.py collectstatic --noinput
```

---

## 📚 Dependencies

```
Django>=4.2,<5.0
WeasyPrint>=60.0
Pillow>=10.0.0
```

Install with:
```bash
pip install -r requirements.txt
```

---

## 🔐 Security Notes

### For Production:
1. Change `SECRET_KEY`
2. Set `DEBUG = False`
3. Configure `ALLOWED_HOSTS`
4. Use environment variables
5. Enable HTTPS
6. Use strong passwords
7. Regular backups

---

## 📞 Support

### Common Issues

**Q: PDF generation fails?**
A: Install GTK+ libraries for WeasyPrint

**Q: Can't login?**
A: Check username/password, ensure migrations are applied

**Q: Customer ID not auto-generating?**
A: Check model save() method, ensure no manual ID assignment

**Q: Products not saving in DC?**
A: Ensure JavaScript is enabled, check browser console

---

## 🎯 Next Steps

1. **Test the application** with sample data
2. **Customize templates** to match your branding
3. **Add more features** as needed
4. **Deploy to production** when ready

---

**Server Status**: ✅ Running at http://127.0.0.1:8000

**Ready to use!** Open your browser and start exploring the application.
