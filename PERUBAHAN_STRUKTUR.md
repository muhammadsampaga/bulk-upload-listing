# ✅ Perubahan Struktur Folder & Sheet Name

## 1. Struktur Folder dalam ZIP

### SEBELUMNYA:
```
uploads/
  images/
    rumah/
      1/
        cover.jpg
        foto1.jpg
```

**Dalam ZIP:**
```
images/rumah/1/cover.jpg
images/rumah/1/foto1.jpg
```

---

### SEKARANG:
```
uploads/
  rumah/
    1/
      cover.jpg
      foto1.jpg
```

**Dalam ZIP:**
```
rumah/1/cover.jpg
rumah/1/foto1.jpg
```

---

## 2. Nama Sheet dalam Excel

### SEBELUMNYA:
```
Sheet 1: "Rumah"
Sheet 2: "Apartemen"
Sheet 3: "Tanah"
```

---

### SEKARANG:
```
Sheet 1: "rumah"
Sheet 2: "apartemen"
Sheet 3: "tanah"
```

---

## 3. Struktur Lengkap yang Sekarang

### Folder Structure:
```
uploads/
  mass_upload_template.xlsx
  rumah/
    1/
      cover.jpg
      foto1.jpg
      foto2.jpg
    2/
      cover.png
      ...
  apartemen/
    1/
      cover.jpg
      ...
  tanah/
    1/
      cover.jpg
      ...
```

### ZIP Content:
```
mass_upload_template.xlsx
rumah/1/cover.jpg
rumah/1/foto1.jpg
rumah/1/foto2.jpg
rumah/2/cover.png
apartemen/1/cover.jpg
tanah/1/cover.jpg
```

### Excel Sheets:
```
Sheet: "rumah"     → Semua data properti tipe rumah
Sheet: "apartemen" → Semua data properti tipe apartemen
Sheet: "tanah"     → Semua data properti tipe tanah
...dst
```

---

## Perubahan yang Dilakukan

### File: `app.py`

**1. Function `get_sheet_name()`**
- ❌ Sebelum: Mengembalikan "Rumah", "Apartemen", dst
- ✅ Sekarang: Mengembalikan "rumah", "apartemen", dst

**2. Function `create_zip()`**
- ❌ Sebelum: `images/rumah/1/cover.jpg`
- ✅ Sekarang: `rumah/1/cover.jpg`
- ✅ Filter out folder "images" dari path dalam ZIP

---

## Testing

Untuk verify perubahan:

1. **Check Excel Sheet Names:**
   - Download Excel dari aplikasi
   - Lihat sheet tabs → harus lowercase (rumah, apartemen, dll)

2. **Check ZIP Structure:**
   - Download ZIP dari aplikasi
   - Extract dan lihat struktur folder → harus `{tipe_properti}/{no}/`

---

## Catatan

Folder fisik di server (`uploads/`) sudah structure tanpa `images/` folder:
- Properti akan disimpan langsung di `uploads/{tipe_properti}/{no}/`
- Gambar-gambar akan langsung di dalam folder properti tersebut

Ini akan membuat struktur lebih clean dan direct!
