# Mass Upload Properti

## Overview
Website berbasis Python Flask untuk melakukan mass upload data iklan properti. Aplikasi ini memungkinkan pengguna mengisi form data properti, mengunggah gambar, dan sistem otomatis membuat file Excel dan ZIP berisi semua data untuk diupload ke sistem lain.

## Features
- **AI Parser with ChatGPT**: Paste deskripsi properti free text, AI otomatis mengisi semua form
- Form input lengkap dengan 24 field data properti (semua opsional)
- Auto-increment nomor iklan
- Upload gambar cover utama dan gambar tambahan (multiple)
- **Image Preview**: Preview gambar sebelum upload dengan badge "Cover" dan "Foto 1,2,3..."
- Penyimpanan data otomatis ke Excel (mass_upload_template.xlsx)
- Struktur folder terorganisir: uploads/images/{tipe_properti}/{no}/
- Pembuatan ZIP otomatis setelah setiap submit
- Tampilan tabel data properti yang tersimpan
- Download Excel dan ZIP file
- **Reset Semua Data**: Tombol reset untuk menghapus semua data, gambar, dan mereset nomor urut kembali ke 1
- **Modern UI/UX**: Gradient background, icons, better styling, responsive design

## Project Structure
```
.
├── app.py                      # Main Flask application
├── templates/
│   └── index.html             # Main page with form and table
├── uploads/                    # Auto-generated folder
│   ├── mass_upload_template.xlsx
│   ├── r123_mass_upload_new.zip
│   └── images/
│       ├── {tipe_properti}/
│       │   └── {no}/
│       │       ├── cover.jpg
│       │       └── foto1.jpg
├── .gitignore
├── pyproject.toml
└── uv.lock
```

## Technology Stack
- **Backend**: Python 3.11, Flask 3.1.2
- **AI**: OpenAI 2.7.2 (ChatGPT GPT-5)
- **Excel**: openpyxl 3.1.5
- **Frontend**: Bootstrap 5.3.0, Bootstrap Icons, HTML5, CSS3, JavaScript
- **File Handling**: Werkzeug (built-in with Flask), zipfile (Python standard library)

## Installation & Setup
Dependencies are managed with uv and installed automatically:
- Flask
- openpyxl
- openai

Required Environment Variables (add via Replit Secrets):
- `OPENAI_API_KEY`: Your OpenAI API key for ChatGPT integration
- `SESSION_SECRET`: Flask session secret key

## Running the Application
The application runs on port 5000 via the configured workflow:
```bash
python app.py
```

Access the application at the Replit webview URL.

## How It Works

### 1. AI Parser (Optional)
- User can paste free text property description
- AI (ChatGPT GPT-5) automatically extracts information and fills the form
- All extracted fields can be edited manually after parsing

### 2. Data Entry
- User fills out the comprehensive property form manually or via AI parser
- **All fields are optional** - fill in what you have
- Number (no) auto-increments based on existing data

### 3. Image Upload with Preview
- Cover image: Single file upload (optional) with instant preview
- Additional images: Multiple file upload (optional) with numbered previews
- Images saved to: `uploads/{tipe_properti}/{no}/`
- Cover saved as: `cover.{ext}`
- Additional images saved as: `foto1.{ext}`, `foto2.{ext}`, etc.

### 4. Excel Storage
- Data saved to: `uploads/mass_upload_template.xlsx`
- Excel created automatically if doesn't exist
- Each submission adds a new row with all 25 columns

### 5. ZIP Creation
- After each submission, ZIP file is recreated
- Filename: `r123_mass_upload_new.zip`
- Contains: Excel file + entire images folder structure

### 6. Downloads
- Download Excel: Direct download of the template file
- Download ZIP: Complete package ready for upload to external system

## Data Fields (25 columns)
1. no (auto)
2. tipe_properti
3. kategori
4. jenis_properti
5. id_area
6. luas_tanah
7. luas_bangunan
8. harga
9. periode_sewa
10. judul_iklan
11. deskripsi_iklan
12. gambar_cover_utama
13. kamar_tidur
14. kamar_mandi
15. jumlah_lantai
16. carport
17. sertifikat
18. kondisi_properti
19. kondisi_perabotan
20. selling_point
21. status
22. aktivasi_premier
23. aktivasi_featured
24. jadwal_sundul
25. durasi_sundul

## Environment Variables
- `SESSION_SECRET`: Flask session secret key (configured in Replit)

## Recent Changes
- 2025-11-13: Initial project setup and AI integration
  - Created Flask application with complete form
  - Implemented Excel file generation and management
  - Added image upload with organized folder structure
  - Implemented automatic ZIP creation
  - Added download functionality for Excel and ZIP files
  - Added security validation for tipe_properti to prevent path traversal attacks
  - Implemented whitelist validation and absolute path checking
  
- 2025-11-13: AI Parser and UX Improvements
  - Integrated OpenAI ChatGPT (GPT-5) for automatic form filling from free text
  - Added AI parser endpoint that extracts property details from descriptions
  - Removed required validation from all form fields (now fully optional)
  - Implemented image preview functionality for uploaded images
  - Complete UI/UX redesign with gradient background and modern styling
  - Added Bootstrap Icons throughout the interface
  - Enhanced error handling for OpenAI API key validation
  - Improved user feedback with loading spinners and status messages

- 2025-11-13: Added Complete Reset Functionality
  - Implemented /reset-all endpoint to delete all data and reset numbering
  - Added "Reset Semua Data" button with confirmation dialog in UI
  - Reset functionality deletes Excel file, all uploaded images, and ZIP file
  - Numbering system automatically resets to start from 1 after reset
  - Added comprehensive warning dialog to prevent accidental data loss
  - Implemented CSRF protection using session-based tokens to prevent cross-site attacks
  - Added token validation on reset endpoint for security

## Security Features
- Whitelisted tipe_properti values: rumah, apartemen, ruko, tanah, villa, gedung
- Path traversal protection with absolute path validation
- Secure file upload validation with allowed extensions
- Flash message notifications for invalid inputs

## Notes
- The uploads folder is in .gitignore as it contains user-generated content
- LSP warnings for openpyxl are expected and don't affect functionality
- Application uses Flask development server (suitable for Replit environment)
- All user inputs are validated to prevent security vulnerabilities
