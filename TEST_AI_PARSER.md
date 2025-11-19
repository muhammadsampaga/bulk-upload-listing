# Test AI Parser - Field Khusus Rumah

## Contoh Deskripsi untuk Test

Coba masukkan deskripsi ini ke dalam field "Deskripsi Properti" di AI Parser:

```
Rumah mewah dijual di Denpasar, Bali. Properti ini memiliki luas tanah 500 m², luas bangunan 350 m², 
3 kamar tidur, 2 kamar mandi, 2 lantai dengan 1 carport. 

Rumah baru dengan kondisi sangat bagus, fully furnished. Akses jalan lebar dan mudah. 
Dekat dengan pusat kota, akses ke mall dan sekolah internasional. 
Memiliki sertifikat SHM. Harga jual Rp 1.500.000.000. Nego sampai laku.
```

## Field yang Seharusnya Terisi

Setelah AI Parser, field berikut HARUS terisi:

### Global Fields:
- ✅ Tipe Properti: Rumah
- ✅ Kategori: Dijual
- ✅ Jenis Properti: Baru
- ✅ ID Area: Denpasar
- ✅ Harga: 1500000000
- ✅ Judul Iklan: (auto-generated)
- ✅ Deskripsi Iklan: (auto-generated)
- ✅ Sertifikat: SHM
- ✅ Kondisi Properti: Bagus
- ✅ Kondisi Perabotan: Furnished
- ✅ Selling Point: (auto-generated)

### Field Khusus Rumah:
- ✅ Luas Tanah: 500
- ✅ Luas Bangunan: 350
- ✅ Kamar Tidur: 3
- ✅ Kamar Mandi: 2
- ✅ Jumlah Lantai: 2
- ✅ Carport: 1

## Troubleshooting Jika Field Tidak Terisi

1. **Check Browser Console** (F12 → Console):
   - Lihat apakah ada JavaScript error
   - Cek response dari `/parse-description` endpoint

2. **Jika field khusus tidak ada di form**:
   - Pastikan sudah select "Rumah" di Tipe Properti dropdown
   - Field khusus harus muncul SETELAH pilih tipe properti

3. **Jika response AI tidak include field khusus**:
   - Check OpenAI API key sudah set
   - Lihat response di browser developer tools (Network tab)

## Perbaikan yang Sudah Dilakukan

✅ Updated AI prompt untuk mendukung semua 11 property types
✅ Added field mapping untuk semua field khusus
✅ Added setTimeout untuk memastikan field di-render sebelum diisi
✅ Updated submit route untuk collect semua field khusus

## Testing Recommended

1. Test dengan Rumah
2. Test dengan Apartemen
3. Test dengan Tanah
4. Test dengan Ruko
5. Test dengan property type lainnya
