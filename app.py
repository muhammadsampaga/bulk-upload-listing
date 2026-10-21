from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify, session
from werkzeug.utils import secure_filename
from openpyxl import Workbook, load_workbook
from openpyxl.utils import get_column_letter
import os
import zipfile
import shutil
import json
import secrets
import re
import tempfile
from io import BytesIO
from datetime import datetime, timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'dev-secret-key')

def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

def validate_csrf_token(token):
    return token == session.get('_csrf_token')

app.jinja_env.globals['csrf_token'] = generate_csrf_token

# Template filter untuk format harga Indonesia (dengan titik)
def format_harga(value):
    """Format harga dengan pemisah titik (Indonesia format)"""
    if not value:
        return '-'
    try:
        harga = float(value)
        # Format dengan 0 desimal dan gunakan titik sebagai pemisah ribuan
        # Python format: {:,.0f} menggunakan comma, jadi kita ganti dengan titik
        formatted = "{:,.0f}".format(harga)
        return formatted.replace(',', '.')
    except (ValueError, TypeError):
        return value

app.jinja_env.filters['format_harga'] = format_harga

UPLOAD_FOLDER = 'uploads'
EXCEL_FILE = os.path.join(UPLOAD_FOLDER, 'mass_upload_template.xlsx')
AREA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'areas.xlsx')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def normalize_area_text(value):
    """Normalize user/AI location text for deterministic matching."""
    return ' '.join(re.sub(r'[^\w]+', ' ', str(value or '').casefold()).split())

def normalize_admin_text(value):
    return re.sub(r'^(kota|kabupaten|kab|provinsi|prov)\s+', '', normalize_area_text(value))

def normalize_area_id(value):
    """Keep numeric Excel IDs stable (for example 449.0 -> 449)."""
    text = str(value or '').strip()
    return text[:-2] if text.endswith('.0') and text[:-2].isdigit() else text

def load_areas():
    """Load the canonical area catalog once at process startup."""
    workbook = load_workbook(AREA_FILE, read_only=True, data_only=True)
    worksheet = workbook.active
    areas = []
    for province, city, area_id, name in worksheet.iter_rows(min_row=2, values_only=True):
        if area_id is None or not name:
            continue
        area = {
            'id': normalize_area_id(area_id),
            'name': str(name).strip(),
            'city': str(city or '').strip(),
            'province': str(province or '').strip(),
        }
        area['label'] = f"{area['name']}, {area['city']}, {area['province']} — ID {area['id']}"
        area['_search'] = normalize_area_text(f"{area['id']} {area['name']} {area['city']} {area['province']}")
        areas.append(area)
    workbook.close()
    return areas

AREAS = load_areas()
AREAS_BY_ID = {area['id']: area for area in AREAS}
AREAS_BY_NAME = {}
for area in AREAS:
    AREAS_BY_NAME.setdefault(normalize_area_text(area['name']), []).append(area)

def public_area(area):
    return {key: area[key] for key in ('id', 'name', 'city', 'province', 'label')}

def resolve_area(area_name='', city='', province=''):
    """Resolve an ID or unique area/city/province combination without guessing."""
    area_id = normalize_area_id(area_name)
    if area_id in AREAS_BY_ID:
        return AREAS_BY_ID[area_id]

    parts = [part.strip() for part in str(area_name).split(',')]
    normalized_name = normalize_area_text(parts[0])
    city = city or (parts[1] if len(parts) > 1 else '')
    province = province or (parts[2] if len(parts) > 2 else '')
    candidates = list(AREAS_BY_NAME.get(normalized_name, ()))
    for value, key in ((city, 'city'), (province, 'province')):
        normalized_value = normalize_admin_text(value)
        if normalized_value:
            candidates = [area for area in candidates if normalize_admin_text(area[key]) == normalized_value]
    return candidates[0] if len(candidates) == 1 else None

def area_display(value):
    area = AREAS_BY_ID.get(normalize_area_id(value))
    return f"{area['name']}, {area['city']} (ID {area['id']})" if area else value

app.jinja_env.filters['area_display'] = area_display

def get_zip_filename():
    """Generate ZIP filename with human-readable timestamp: upl_{DD-MMM-YYYY_HH-MM-SS}"""
    timestamp = datetime.now().strftime('%d-%b-%Y_%H-%M-%S')
    return os.path.join(UPLOAD_FOLDER, f'upl_{timestamp}.zip')

# Positional contract from rumah123-listing #7553 (latest mass-upload template).
BOOSTER_COLUMNS = [
    'Status', 'aktivasi premier', 'aktivasi featured', 'aktivasi sundul',
    'jadwal sundul', 'durasi sundul', 'hari sundul', 'jam sundul', 'tanggal akhir sundul'
]
EXCEL_COLUMNS_BY_TYPE = {
    'ruko': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar mandi', 'jumlah lantai',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas ruko'
    ] + BOOSTER_COLUMNS,
    'rumah': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar tidur', 'kamar mandi', 'jumlah lantai', 'carport',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'hadap', 'fasilitas rumah', 'fasilitas perumahan', 'lebar jalan'
    ] + BOOSTER_COLUMNS,
    'apartemen': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar tidur', 'kamar mandi', 'nomor lantai',
        'sertifikat', 'kondisi perabotan', 'kondisi properti',
        'fasilitas lingkungan apartemen', 'selling point',
        'tahun dibangun', 'pemandangan', 'fasilitas apartemen', 'peralatan'
    ] + BOOSTER_COLUMNS,
    'tanah': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'satuan tanah', 'harga', 'satuan harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'sertifikat', 'selling point', 'panjang tanah', 'lebar tanah'
    ] + BOOSTER_COLUMNS,
    'villa': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar tidur', 'kamar mandi', 'jumlah lantai', 'carport',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas kamar villa'
    ] + BOOSTER_COLUMNS,
    'kost': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar tidur', 'kamar mandi', 'jumlah lantai', 'carport',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas kamar kost', 'fasilitas kost'
    ] + BOOSTER_COLUMNS,
    'hotel': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar tidur', 'kamar mandi', 'jumlah lantai',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas sekitar hotel'
    ] + BOOSTER_COLUMNS,
    'pabrik': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar mandi', 'jumlah lantai', 'carport',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas pabrik'
    ] + BOOSTER_COLUMNS,
    'gudang': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar mandi', 'jumlah lantai',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas gudang'
    ] + BOOSTER_COLUMNS,
    'perkantoran': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar mandi', 'jumlah lantai',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas perkantoran'
    ] + BOOSTER_COLUMNS,
    'ruang usaha': [
        'no', 'tipe properti', 'kategori', 'jenis properti', 'id area',
        'luas tanah', 'luas bangunan', 'harga', 'periode sewa',
        'judul iklan', 'deskripsi iklan', 'gambar cover utama',
        'kamar mandi', 'jumlah lantai',
        'sertifikat', 'kondisi properti', 'kondisi perabotan',
        'selling point', 'fasilitas ruang usaha'
    ] + BOOSTER_COLUMNS
}

def get_excel_columns(tipe_properti=None):
    tipe = (tipe_properti or 'ruko').strip().lower().replace('_', ' ')
    if tipe not in EXCEL_COLUMNS_BY_TYPE:
        raise ValueError(f'Tipe properti {tipe} tidak didukung template v3.')
    return EXCEL_COLUMNS_BY_TYPE[tipe]

# Legacy column name for backward compatibility
EXCEL_COLUMNS = get_excel_columns()

ALLOWED_TIPE_PROPERTI = {
    'rumah', 'apartemen', 'ruko', 'tanah', 'villa',
    'kost', 'hotel', 'pabrik', 'gudang', 'perkantoran', 'ruang_usaha', 'ruang usaha'
}

QWEN_KEY_PATTERN = re.compile(r'sk-[A-Za-z0-9._\-]{6,}', re.IGNORECASE)


def get_dashscope_base_url():
    """Read the native DashScope API base URL from the environment."""
    # Take only the URL or host so stray text in the variable never reaches the request or the logs
    raw = QWEN_KEY_PATTERN.sub(' ', os.environ.get('SG_DASHSCOPE_URL', ''))
    match = re.search(r'https?://[^\s\'"]+', raw)
    if match:
        url = match.group(0).rstrip('/')
    else:
        # Bare API host, e.g. "apihost: ws-xxx.ap-southeast-1.maas.aliyuncs.com"
        host = re.search(r'[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+', raw)
        if not host:
            return ''
        url = f'https://{host.group(0)}'
    if url.endswith('/compatible-mode/v1'):
        return f"{url[:-len('/compatible-mode/v1')]}/api/v1"
    if not url.endswith('/api/v1'):
        return f'{url}/api/v1'
    return url


DASHSCOPE_BASE_URL = get_dashscope_base_url()
QWEN_MODEL = 'qwen3.8-max'
DASHSCOPE_GENERATION_URL = f'{DASHSCOPE_BASE_URL}/services/aigc/multimodal-generation/generation'
# Shown to the browser instead of the real error, which may contain key or config details
AI_ERROR_MESSAGE = 'Layanan AI sedang bermasalah. Silakan coba lagi nanti.'


def get_qwen_api_key():
    """Return the sk- key, ignoring any other text pasted into the variable."""
    for name in ('QWEN_API_KEY', 'SG_DASHSCOPE_API_KEY', 'SG_DASHSCOPE_URL'):
        match = QWEN_KEY_PATTERN.search(os.environ.get(name, ''))
        if match:
            return match.group(0)
    return ''


def redact_secrets(text):
    """Mask API keys before an error message is written to the logs."""
    return QWEN_KEY_PATTERN.sub('sk-***', str(text))


def call_qwen(messages):
    """Call Qwen through the native DashScope endpoint configured in production."""
    api_key = get_qwen_api_key()
    if not api_key:
        raise Exception("Qwen API key tidak tersedia. Silakan tambahkan QWEN_API_KEY di environment variables.")
    if not DASHSCOPE_BASE_URL:
        raise Exception("DashScope URL tidak tersedia atau tidak valid. SG_DASHSCOPE_URL harus berisi URL https://.../api/v1.")

    payload = {
        'model': QWEN_MODEL,
        'input': {
            'messages': [
                {
                    'role': message['role'],
                    'content': [{'text': message['content']}],
                }
                for message in messages
            ]
        },
        'parameters': {
            'result_format': 'message',
            'response_format': {'type': 'json_object'},
        },
    }
    request = Request(
        DASHSCOPE_GENERATION_URL,
        data=json.dumps(payload).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with urlopen(request, timeout=120) as response:
            result = json.load(response)
    except HTTPError as error:
        error_body = error.read().decode('utf-8', errors='replace')[:500]
        raise Exception(f'DashScope API error ({error.code}): {error_body}') from error
    except URLError as error:
        raise Exception(f'DashScope connection error: {error.reason}') from error

    try:
        content = result['output']['choices'][0]['message']['content']
        if isinstance(content, list):
            content = ''.join(item.get('text', '') for item in content if isinstance(item, dict))
        if not isinstance(content, str) or not content.strip():
            raise ValueError('responsenya tidak berisi content')
        return content
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise Exception(f'Respons DashScope tidak valid: {result}') from error

def generate_professional_listing(data, tipe_properti):
    """Generate professional judul_iklan and deskripsi_iklan using AI"""
    try:
        # Build context from form data
        context_parts = [f"Tipe Properti: {tipe_properti}"]
        
        # Add key specifications
        area = AREAS_BY_ID.get(normalize_area_id(data.get('id_area', '')))
        specs = {
            'luas_tanah': data.get('luas_tanah', ''),
            'luas_bangunan': data.get('luas_bangunan', ''),
            'kamar_tidur': data.get('kamar_tidur', ''),
            'kamar_mandi': data.get('kamar_mandi', ''),
            'jumlah_lantai': data.get('jumlah_lantai', ''),
            'carport': data.get('carport', ''),
            'harga': data.get('harga', ''),
            'kategori': data.get('kategori', ''),
            'periode_sewa': data.get('periode_sewa', ''),
            'lokasi': area['label'] if area else '',
            'selling_point': data.get('selling_point', ''),
            'fasilitas_lingkungan': data.get('fasilitas_lingkungan', ''),
            'fasilitas_ruko': data.get('fasilitas_ruko', ''),
            'fasilitas_pabrik': data.get('fasilitas_pabrik', ''),
            'fasilitas_gudang': data.get('fasilitas_gudang', ''),
            'fasilitas_perkantoran': data.get('fasilitas_perkantoran', ''),
            'fasilitas_ruang_usaha': data.get('fasilitas_ruang_usaha', ''),
            'kondisi_properti': data.get('kondisi_properti', ''),
            'sertifikat': data.get('sertifikat', ''),
        }
        
        # Build context string
        for key, value in specs.items():
            if value:
                context_parts.append(f"{key}: {value}")
        
        context = "\n".join(context_parts)
        
        response_content = call_qwen([
                {
                    "role": "system",
                    "content": """Kamu adalah agen properti profesional dan marketer terbaik yang sangat memahami cara menjual properti.
Tugasmu adalah membuat judul listing dan deskripsi yang menarik, profesional, dan persuasif.

ATURAN PENTING:
1. JUDUL LISTING (Maksimal 52 karakter):
   - Maksimalkan informasi penting di 52 karakter pertama
   - Format: [Tipe] [Key Info], [Harga/Keunggulan], [Lokasi Key]
   - Contoh: "Kost 14 Kamar, 400juta/Tahun, ada Laundry"

2. KALIMAT PEMBUKA (Maksimal 82 karakter):
   - Hook untuk membaca lebih lanjut
   - Nyatakan nilai utama properti
   - Contoh: "Kost di Denpasar, 3 lantai, 14 kamar, dengan Laundry, potensi investasi."

3. DESKRIPSI LENGKAP (Struktur: Keunggulan – Spesifikasi – Potensi – Legalitas – Call to Action):
   - GUNAKAN TEXT PLAIN SAJA, TIDAK PERLU MARKDOWN FORMATTING
   - JANGAN GUNAKAN: ###, **, -, 📍, 🌟, atau simbol/emoji lainnya
   - STRUKTUR: Gunakan line break dan paragraf untuk memisahkan bagian
   - Paragraf pembuka yang memikat
   - Spesifikasi Utama (list dengan tanda ketukan sederhana, contoh "- Luas Tanah: 100 m²")
   - Keunggulan khusus (format list sederhana)
   - Perhitungan finansial (jika relevan)
   - Legalitas
   - Call to Action yang kuat
   - Spacing dan line break untuk readability, bukan markdown

Respond ONLY dengan JSON object mengandung:
{
  "judul_iklan": "...",
  "kalimat_pembuka": "...",
  "deskripsi_iklan": "..."
}"""
                },
                {
                    "role": "user",
                    "content": f"Buatkan judul dan deskripsi profesional untuk properti dengan detail berikut:\n\n{context}"
                }
            ])
        
        result = json.loads(response_content)
        return {
            'judul_iklan': result.get('judul_iklan', ''),
            'kalimat_pembuka': result.get('kalimat_pembuka', ''),
            'deskripsi_iklan': result.get('deskripsi_iklan', '')
        }
    except Exception as e:
        print(f"Professional Listing Generator Error: {redact_secrets(e)}")
        return {'error': AI_ERROR_MESSAGE}

def parse_listing_with_ai(description):
    try:
        response_content = call_qwen([
                {
                    "role": "system",
                    "content": """Kamu adalah asisten AI yang membantu mengekstrak informasi properti dari deskripsi teks.
Analisa deskripsi properti dan ekstrak informasi berikut dalam format JSON.
Jika informasi tidak tersedia atau tidak jelas, gunakan string kosong "".

FIELD GLOBAL (Semua Tipe Properti):
- tipe_properti: (rumah, apartemen, tanah, ruko, villa, kost, hotel, pabrik, gudang, perkantoran, ruang_usaha)
- kategori: (dijual, disewa)
- jenis_properti: (baru, second, aset_bank)
- location_area: nama area/kecamatan/kelurahan terkecil yang disebutkan, contoh "Renon"
- location_city: nama kota/kabupaten, contoh "Denpasar"
- location_province: nama provinsi, contoh "Bali"
- harga: angka saja dalam rupiah (misal 5000000 untuk 5 juta)
- periode_sewa: (per hari, per bulan, per tahun) - hanya jika kategori=disewa - TANPA UNDERSCORE
- judul_iklan: max 52 karakter, menarik dan singkat, berisi info tipe + lokasi + harga
- deskripsi_iklan: PENTING! Buat deskripsi yang menarik dan profesional dengan struktur:
  * Kalimat pembuka singkat yang menarik (1-2 kalimat)
  * Spesifikasi detail (LT, LB, KT, KM, lantai, dll)
  * Keunggulan dan fasilitas utama
  * Lokasi strategis
  * Perihal transaksi jika ada
  Gunakan PLAIN TEXT SAJA - JANGAN gunakan markdown, emoji, atau format khusus. Gunakan newline untuk pemisah paragraf.
- sertifikat: (SHM, HGB, HP, HS, HGU, Adat, Girik, PPJB, Strata, Lainnya)
- kondisi_properti: (Bagus, Butuh Minim Renovasi, Butuh Renovasi Total, Terenovasi)
- kondisi_perabotan: (Furnished, Unfurnished, Semi Furnished)
- selling_point: keunggulan utama properti 2-3 kata
- status: (Tayang, Tunda)
- aktivasi_premier: (Yes, No)
- aktivasi_featured: (Yes, No)
- jadwal_sundul: (1 time daily, 2 times daily, 3 times daily)
- durasi_sundul: (7d, 14d, 30d)

FIELD KHUSUS PER TIPE PROPERTI:
Jika tipe_properti adalah RUMAH, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_tidur: angka
- kamar_mandi: angka
- jumlah_lantai: angka
- carport: angka

Jika tipe_properti adalah APARTEMEN, ekstrak juga:
- luas_bangunan: angka saja (m²)
- kamar_tidur: angka
- kamar_mandi: angka
- nomor_lantai: string
- fasilitas_lingkungan: string

Jika tipe_properti adalah TANAH, ekstrak juga:
- luas_tanah: angka saja (m²)
- satuan_tanah: (m2, are, ha)
- satuan_harga: (total, /m2, /are, /ha)

Jika tipe_properti adalah RUKO, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_mandi: angka
- jumlah_lantai: angka
- fasilitas_ruko: string

Jika tipe_properti adalah VILLA, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_tidur: angka
- kamar_mandi: angka
- jumlah_lantai: angka
- carport: angka

Jika tipe_properti adalah KOST, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_tidur: angka
- kamar_mandi: angka
- jumlah_lantai: angka
- carport: angka

Jika tipe_properti adalah HOTEL, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_tidur: angka
- kamar_mandi: angka
- jumlah_lantai: angka
- carport: angka

Jika tipe_properti adalah PABRIK, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_mandi: angka
- jumlah_lantai: angka
- carport: angka
- fasilitas_pabrik: string

Jika tipe_properti adalah GUDANG, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_mandi: angka
- jumlah_lantai: angka
- fasilitas_gudang: string

Jika tipe_properti adalah PERKANTORAN, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_mandi: angka
- jumlah_lantai: angka
- fasilitas_perkantoran: string

Jika tipe_properti adalah RUANG_USAHA, ekstrak juga:
- luas_tanah: angka saja (m²)
- luas_bangunan: angka saja (m²)
- kamar_mandi: angka
- jumlah_lantai: angka
- fasilitas_ruang_usaha: string

PENTING: 
- Pastikan SEMUA field yang relevan diisi dengan nilai yang tepat berdasarkan tipe properti!
- deskripsi_iklan HARUS berisi informasi lengkap dan menarik, bukan hanya ringkasan singkat
- Gunakan PLAIN TEXT tanpa markdown atau emoji
- Respond ONLY with valid JSON object, no additional text."""
                },
                {
                    "role": "user",
                    "content": f"Deskripsi properti: {description}"
                }
            ])
        
        result = json.loads(response_content)
        area = resolve_area(
            result.get('location_area', ''),
            result.get('location_city', ''),
            result.get('location_province', '')
        )
        result['id_area'] = area['id'] if area else ''
        result['area'] = public_area(area) if area else None
        if any(result.get(key) for key in ('location_area', 'location_city', 'location_province')) and not area:
            result['area_warning'] = 'Lokasi AI belum cocok secara unik. Silakan pilih area dari hasil pencarian.'
        return result
    except Exception as e:
        print(f"AI Parser Error: {redact_secrets(e)}")
        return {'error': AI_ERROR_MESSAGE}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def normalize_tipe_properti(tipe_properti):
    """Normalize property type to internal format (with underscores)"""
    tipe_clean = tipe_properti.strip().lower()
    # Convert format with spaces to internal format with underscores
    mapping = {
        'ruang usaha': 'ruang_usaha'
    }
    return mapping.get(tipe_clean, tipe_clean)

def validate_tipe_properti(tipe_properti):
    tipe_clean = tipe_properti.strip().lower()
    if tipe_clean not in ALLOWED_TIPE_PROPERTI:
        return None
    # Return normalized version (with underscores for internal use)
    return normalize_tipe_properti(tipe_clean)

def init_excel(tipe_properti=None):
    """Initialize Excel file with appropriate columns for property type"""
    # Create main file if doesn't exist
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.title = get_sheet_name(tipe_properti or 'ruko')
        columns = get_excel_columns(tipe_properti)
        for idx, col in enumerate(columns, 1):
            ws.cell(row=1, column=idx, value=col)
        save_workbook(wb)

def get_sheet_name(tipe_properti):
    """Get the sheet name based on property type (lowercase)"""
    return normalize_tipe_properti(tipe_properti).replace('_', ' ')

def get_next_no(tipe_properti=None):
    """Get the next number for entry for specific property type"""
    numbers = [int(item['no']) for item in map(listing_fields, read_excel_data())
               if normalize_tipe_properti(str(item['tipe_properti'])) == normalize_tipe_properti(tipe_properti or 'ruko')]
    return max(numbers, default=0) + 1

def read_excel_data():
    """Read all data from all sheets in Excel"""
    init_excel()
    wb = load_workbook(EXCEL_FILE)
    try:
        data = []
        for ws in wb:
            headers = [cell.value for cell in ws[1]]
            names = {field_name(header) for header in headers if header}
            if len(names) != sum(bool(header) for header in headers):
                raise ValueError(f'Sheet {ws.title}: ada nama kolom duplikat.')
            for row in ws.iter_rows(min_row=2, values_only=True):
                if not any(value not in (None, '') for value in row):
                    continue
                if not row[0]:
                    raise ValueError(f'Sheet {ws.title}: ada data tanpa nomor listing.')
                if any(not header and value not in (None, '') for header, value in zip(headers, row)):
                    raise ValueError(f'Sheet {ws.title}: ada data tanpa nama kolom.')
                item = {header: value for header, value in zip(headers, row) if header}
                if not (item.get('tipe properti') or item.get('tipe_properti')):
                    item['tipe properti'] = ws.title
                data.append(item)
        return data
    finally:
        wb.close()

def field_name(header):
    name = str(header).strip().lower().replace(' ', '_')
    return {'luas': 'luas_bangunan', 'periode': 'periode_sewa', 'kamar': 'kamar_tidur',
            'fasilitas': 'fasilitas_lingkungan',
            'fasilitas_lingkungan_apartemen': 'fasilitas_lingkungan'}.get(name, name)

def listing_fields(data):
    return {field_name(key): value for key, value in data.items()}


def normalize_sundul(data):
    """Translate legacy daily schedules and validate the six v3 SUNDUL cells."""
    fields = ('aktivasi_sundul', 'jadwal_sundul', 'durasi_sundul',
              'hari_sundul', 'jam_sundul', 'tanggal_akhir_sundul')
    values = {key: str(data.get(key) or '').strip() for key in fields}
    mode = values['aktivasi_sundul'].casefold()
    if not mode:
        mode = 'frequently' if values['jadwal_sundul'] or values['durasi_sundul'] else 'none'
        if mode == 'none' and any(values[key] for key in fields[3:]):
            raise ValueError('Pilih aktivasi Day Selection untuk jadwal berdasarkan hari.')
    if mode == 'none':
        return dict(zip(fields, ('NONE', '', '', '', '', '')))
    if mode == 'frequently':
        if values['jadwal_sundul'] not in ('1 time daily', '2 times daily', '3 times daily'):
            raise ValueError('Pilih jadwal sundul 1, 2, atau 3 kali sehari.')
        duration = re.fullmatch(r'(7|14|30)\s*(?:d|hari)', values['durasi_sundul'], re.IGNORECASE)
        if not duration:
            raise ValueError('Durasi sundul harus 7d, 14d, atau 30d.')
        return dict(zip(fields, ('Frequently', values['jadwal_sundul'], duration[1] + 'd', '', '', '')))
    if mode == 'day selection':
        days = [day.strip().title() for day in values['hari_sundul'].split(';')]
        if not days or any(day not in ('Senin', 'Selasa', 'Rabu', 'Kamis', 'Jumat', 'Sabtu', 'Minggu') for day in days):
            raise ValueError('Hari sundul harus nama hari dipisahkan titik koma, misalnya Senin;Jumat.')
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', values['jam_sundul']):
            raise ValueError('Jam sundul harus HH:MM, misalnya 09:00.')
        try:
            end = datetime.strptime(values['tanggal_akhir_sundul'], '%Y-%m-%d')
        except ValueError:
            try:
                end = datetime.strptime(values['tanggal_akhir_sundul'], '%d-%m-%Y')
            except ValueError:
                raise ValueError('Tanggal akhir sundul tidak valid.') from None
        today_wib = (datetime.utcnow() + timedelta(hours=7)).date()
        if end.date() < today_wib:
            raise ValueError('Tanggal akhir sundul sudah lewat; perbarui jadwal sebelum export.')
        return dict(zip(fields, ('Day Selection', '', '', ';'.join(dict.fromkeys(days)),
                                 values['jam_sundul'], end.strftime('%d-%m-%Y'))))
    raise ValueError('Aktivasi sundul harus NONE, Frequently, atau Day Selection.')


def export_excel():
    """Build v3 in memory; legacy columns/data remain in the source workbook."""
    wb = Workbook()
    wb.remove(wb.active)
    seen = set()
    for item in read_excel_data():
        data = listing_fields(item)
        tipe = str(data.get('tipe_properti') or '').strip().lower().replace('_', ' ')
        columns = get_excel_columns(tipe)
        no = normalize_area_id(data.get('no'))
        if not no.isdigit() or int(no) < 1 or (tipe, no) in seen:
            raise ValueError(f'{tipe}: nomor listing tidak valid atau duplikat ({no}).')
        seen.add((tipe, no))
        allowed = {field_name(col) for col in columns}
        # ponytail: hotel carport is retained locally; export it when the backend supports it.
        extra = [key for key, value in data.items() if key not in allowed
                 and not (tipe == 'hotel' and key == 'carport') and value not in (None, '')]
        if extra:
            raise ValueError(f'{tipe} no {no}: kolom belum didukung v3: {", ".join(extra)}.')
        try:
            data.update(normalize_sundul(data))
        except ValueError as error:
            raise ValueError(f'{tipe} no {no}: {error}') from error
        data.update(no=int(no), tipe_properti=tipe)
        if tipe not in wb.sheetnames:
            wb.create_sheet(tipe).append(columns)
        wb[tipe].append([data.get(field_name(col), '') for col in columns])
    if not wb.sheetnames:
        wb.create_sheet('ruko').append(get_excel_columns('ruko'))
    output = BytesIO()
    wb.save(output)
    wb.close()
    output.seek(0)
    return output


def form_listing(tipe_properti):
    # ponytail: optional v3 property fields stay blank/preserved; add UI controls when needed.
    fields = [field_name(col) for col in get_excel_columns(tipe_properti)]
    data = {key: request.form[key] for key in fields if key in request.form}
    data['tipe_properti'] = tipe_properti
    data.update(normalize_sundul(data))
    return data


def save_workbook(wb):
    fd, path = tempfile.mkstemp(dir=os.path.dirname(EXCEL_FILE), suffix='.xlsx.tmp')
    os.close(fd)
    try:
        wb.save(path)
        os.replace(path, EXCEL_FILE)
    finally:
        wb.close()
        if os.path.exists(path):
            os.remove(path)


def save_to_excel(data, tipe_properti=None):
    """Save data to Excel in the appropriate sheet based on property type"""
    init_excel(tipe_properti)
    
    # Determine sheet name
    sheet_name = get_sheet_name(tipe_properti) if tipe_properti else "Data Properti"
    
    wb = load_workbook(EXCEL_FILE)
    if sheet_name == 'ruang usaha' and 'ruang_usaha' in wb.sheetnames:
        wb['ruang_usaha'].title = sheet_name
    
    # Create sheet if it doesn't exist
    if sheet_name not in wb.sheetnames:
        ws = wb.create_sheet(sheet_name)
        columns = get_excel_columns(tipe_properti)
        for idx, col in enumerate(columns, 1):
            ws.cell(row=1, column=idx, value=col)
    else:
        ws = wb[sheet_name]
    
    # Append new storage fields without rewriting or dropping legacy columns.
    existing = {field_name(cell.value) for cell in ws[1] if cell.value}
    for column in get_excel_columns(tipe_properti):
        if field_name(column) not in existing:
            ws.cell(row=1, column=ws.max_column + 1, value=column)
    headers = [cell.value for cell in ws[1]]
    data = listing_fields(data)
    ws.append([data.get(field_name(header), '') if header else '' for header in headers])
    save_workbook(wb)

def update_excel_row(tipe_properti, no, updated_data):
    """Update an existing row in Excel"""
    init_excel()
    sheet_name = get_sheet_name(tipe_properti)
    
    wb = load_workbook(EXCEL_FILE)
    if sheet_name == 'ruang usaha' and 'ruang_usaha' in wb.sheetnames:
        wb['ruang_usaha'].title = sheet_name
    if sheet_name not in wb.sheetnames:
        wb.close()
        raise ValueError('Sheet listing tidak ditemukan.')
    
    ws = wb[sheet_name]
    existing = {field_name(cell.value) for cell in ws[1] if cell.value}
    for column in get_excel_columns(tipe_properti):
        if field_name(column) not in existing:
            ws.cell(row=1, column=ws.max_column + 1, value=column)
    
    headers = [cell.value for cell in ws[1]]
    
    # Find and update row
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=False), start=2):
        if row[0].value and str(row[0].value) == str(no):
            for col_idx, header in enumerate(headers, 1):
                if not header:
                    continue
                field = field_name(header)
                if field in updated_data:
                    ws.cell(row=row_idx, column=col_idx, value=updated_data[field])
            break
    else:
        wb.close()
        raise ValueError('Nomor listing tidak ditemukan.')
    
    save_workbook(wb)

def create_zip():
    """Create ZIP with structure: {tipe_properti}/{no}/ dengan Excel file"""
    zip_file = get_zip_filename()
    
    excel_data = export_excel().getvalue()
    fd, temporary = tempfile.mkstemp(dir=UPLOAD_FOLDER, suffix='.zip.tmp')
    os.close(fd)
    try:
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr('mass_upload_template.xlsx', excel_data)
            for root, dirs, files in os.walk(UPLOAD_FOLDER):
                for file in files:
                    if allowed_file(file):
                        parts = [p for p in os.path.relpath(root, UPLOAD_FOLDER).split(os.sep) if p != 'images']
                        parts = ['ruang usaha' if p == 'ruang_usaha' else p for p in parts]
                        zipf.write(os.path.join(root, file), '/'.join(parts + [file]))
            exported = load_workbook(BytesIO(excel_data), read_only=True)
            archive_paths = set(zipf.namelist())
            try:
                for ws in exported:
                    columns = get_excel_columns(ws.title)
                    for row in ws.iter_rows(min_row=2, values_only=True):
                        cover = row[columns.index('gambar cover utama')]
                        if not cover or f'{ws.title}/{row[0]}/{cover}' not in archive_paths:
                            raise ValueError(f'{ws.title} no {row[0]}: file cover tidak ditemukan di ZIP.')
            finally:
                exported.close()
        os.replace(temporary, zip_file)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return zip_file

@app.route('/')
def index():
    try:
        data = read_excel_data()
    except Exception as error:
        flash(f'Workbook tidak bisa dibaca: {error}', 'danger')
        data = []
    return render_template('index.html', data=data)

@app.route('/areas/search')
def search_areas():
    query = request.args.get('q', '').strip()[:100]
    normalized_query = normalize_area_text(query)
    if len(normalized_query) < 2:
        return jsonify([])

    tokens = normalized_query.split()
    matches = [area for area in AREAS if all(token in area['_search'] for token in tokens)]
    matches.sort(key=lambda area: (
        not normalize_area_text(area['name']).startswith(normalized_query),
        not normalize_area_text(area['city']).startswith(normalized_query),
        len(area['name']),
        int(area['id']) if area['id'].isdigit() else area['id'],
    ))
    return jsonify([public_area(area) for area in matches[:20]])

@app.route('/parse-description', methods=['POST'])
def parse_description():
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Request body harus berupa JSON yang valid'}), 400
        
        description = data.get('description', '')
        
        if not isinstance(description, str) or not description.strip():
            return jsonify({'error': 'Deskripsi tidak boleh kosong'}), 400
        
        parsed_data = parse_listing_with_ai(description)
        
        if 'error' in parsed_data:
            return jsonify(parsed_data), 500
        
        return jsonify(parsed_data)
    except Exception as e:
        return jsonify({'error': f'Terjadi kesalahan: {str(e)}'}), 500

@app.route('/generate-listing', methods=['POST'])
def generate_listing():
    """Generate professional judul_iklan and deskripsi_iklan from form data"""
    try:
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Request body harus berupa JSON yang valid'}), 400
        
        tipe_properti = data.get('tipe_properti', '')
        if not tipe_properti:
            return jsonify({'error': 'Tipe properti harus ditentukan'}), 400
        
        result = generate_professional_listing(data, tipe_properti)
        
        if 'error' in result:
            return jsonify(result), 500
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f'Terjadi kesalahan: {str(e)}'}), 500

@app.route('/submit', methods=['POST'])
def submit():
    try:
        tipe_properti_raw = request.form.get('tipe_properti', '').strip()
        id_area = normalize_area_id(request.form.get('id_area', ''))
        
        tipe_properti = validate_tipe_properti(tipe_properti_raw) if tipe_properti_raw else None
        if tipe_properti_raw and not validate_tipe_properti(tipe_properti_raw):
            flash(f'Tipe properti tidak valid: {tipe_properti_raw}', 'danger')
            return redirect(url_for('index'))
        
        if not tipe_properti:
            flash('Tipe properti harus dipilih', 'danger')
            return redirect(url_for('index'))

        if id_area and id_area not in AREAS_BY_ID:
            flash('ID area tidak valid. Silakan pilih area dari hasil pencarian.', 'danger')
            return redirect(url_for('index'))

        data = form_listing(tipe_properti)
        
        # Get next number for this specific property type
        no = get_next_no(tipe_properti)
        
        property_folder = os.path.join(UPLOAD_FOLDER, tipe_properti, str(no))
        property_folder = os.path.abspath(property_folder)
        upload_folder_abs = os.path.abspath(UPLOAD_FOLDER)
        
        if not property_folder.startswith(upload_folder_abs):
            flash('Operasi tidak diizinkan: path tidak valid', 'danger')
            return redirect(url_for('index'))
        
        os.makedirs(property_folder, exist_ok=True)
        
        cover_filename = ''
        if 'gambar_cover' in request.files:
            cover_file = request.files['gambar_cover']
            if cover_file and cover_file.filename and allowed_file(cover_file.filename):
                ext = cover_file.filename.rsplit('.', 1)[1].lower()
                cover_filename = f'cover.{ext}'
                cover_file.save(os.path.join(property_folder, cover_filename))
        
        if 'gambar_lainnya' in request.files:
            other_files = request.files.getlist('gambar_lainnya')
            for idx, file in enumerate(other_files, 1):
                if file and file.filename and allowed_file(file.filename):
                    ext = file.filename.rsplit('.', 1)[1].lower()
                    filename = f'foto{idx}.{ext}'
                    file.save(os.path.join(property_folder, filename))
        
        data.update(no=no, id_area=id_area, gambar_cover_utama=cover_filename)
        
        save_to_excel(data, tipe_properti)
        create_zip()
        
        flash(f'Iklan tipe {tipe_properti.upper()} berhasil disimpan dan ZIP diperbarui', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/download/excel')
def download_excel():
    try:
        return send_file(export_excel(), as_attachment=True, download_name='mass_upload_template.xlsx')
    except Exception as error:
        flash(f'Export dibatalkan: {error}', 'danger')
    return redirect(url_for('index'))

@app.route('/download/zip')
def download_zip():
    try:
        zip_file = create_zip()
        filename = os.path.basename(zip_file)
        return send_file(zip_file, as_attachment=True, download_name=filename)
    except Exception as error:
        flash(f'Export dibatalkan: {error}', 'danger')
    return redirect(url_for('index'))

@app.route('/load-data/<tipe>/<no>', methods=['GET'])
def load_data(tipe, no):
    """Load property data for editing"""
    try:
        tipe = validate_tipe_properti(tipe) if validate_tipe_properti(tipe) else tipe
        data = read_excel_data()
        
        # Find the data matching tipe and no
        for item in data:
            item_tipe = item.get('tipe properti') or item.get('tipe_properti', '')
            item_no = str(item.get('no', ''))
            
            if normalize_tipe_properti(item_tipe) == normalize_tipe_properti(tipe) and item_no == str(no):
                # Convert spaces to underscores in keys for JavaScript
                result = listing_fields(item)
                try:
                    result.update(normalize_sundul(result))
                    if result['tanggal_akhir_sundul']:
                        result['tanggal_akhir_sundul'] = datetime.strptime(result['tanggal_akhir_sundul'], '%d-%m-%Y').strftime('%Y-%m-%d')
                except ValueError:
                    pass  # Keep invalid legacy values editable so the user can repair them.
                area = AREAS_BY_ID.get(normalize_area_id(result.get('id_area', '')))
                result['area'] = public_area(area) if area else None
                return jsonify(result)
        
        return jsonify({'error': f'Data tidak ditemukan untuk {tipe} nomor {no}'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/update-data', methods=['POST'])
def update_data():
    """Update existing property data"""
    try:
        tipe_properti_raw = request.form.get('tipe_properti', '').strip()
        no = request.form.get('no', '').strip()
        id_area = normalize_area_id(request.form.get('id_area', ''))
        
        tipe_properti = validate_tipe_properti(tipe_properti_raw) if tipe_properti_raw else None
        if tipe_properti_raw and not validate_tipe_properti(tipe_properti_raw):
            flash(f'Tipe properti tidak valid: {tipe_properti_raw}', 'danger')
            return redirect(url_for('index'))
        
        if not tipe_properti or not no:
            flash('Tipe properti dan nomor harus ada', 'danger')
            return redirect(url_for('index'))

        if id_area and id_area not in AREAS_BY_ID:
            flash('ID area tidak valid. Silakan pilih area dari hasil pencarian.', 'danger')
            return redirect(url_for('index'))
        
        updated_data = form_listing(tipe_properti)
        updated_data.update(no=no, id_area=id_area)
        
        # Update Excel - remove old row and add new one
        update_excel_row(tipe_properti, no, updated_data)
        create_zip()
        
        flash(f'Data {tipe_properti} nomor {no} berhasil diperbarui', 'success')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

@app.route('/delete-data', methods=['POST'])
def delete_data():
    """Delete a specific property listing"""
    try:
        # Check CSRF token from header
        csrf_token = request.headers.get('X-CSRF-Token')
        if not csrf_token or not validate_csrf_token(csrf_token):
            return jsonify({'success': False, 'error': 'Invalid CSRF token'}), 403
        
        data = request.get_json()
        tipe_properti = data.get('tipe_properti', '').strip()
        no = str(data.get('no', '')).strip()
        
        if not tipe_properti or not no:
            return jsonify({'success': False, 'error': 'Missing tipe_properti or no'}), 400
        
        # Delete from Excel
        if os.path.exists(EXCEL_FILE):
            wb = load_workbook(EXCEL_FILE)
            sheet_name = get_sheet_name(tipe_properti)
            if sheet_name not in wb.sheetnames and tipe_properti in wb.sheetnames:
                sheet_name = tipe_properti
            
            if sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                
                # Find and delete the row with matching no
                # The first column is 'no' (with index 1 in openpyxl, 0-based is cell column A)
                rows_to_delete = []
                for row_idx in range(2, ws.max_row + 1):  # Start from row 2 (skip header)
                    cell_value = ws.cell(row=row_idx, column=1).value  # Column A is 'no'
                    if cell_value and str(cell_value).strip() == no:
                        rows_to_delete.append(row_idx)
                
                # Delete rows in reverse order to maintain correct indices
                for row_idx in sorted(rows_to_delete, reverse=True):
                    ws.delete_rows(row_idx, 1)
                
                if rows_to_delete:
                    save_workbook(wb)
            
            wb.close()
        
        # Delete property folder with images
        property_folder = os.path.join(UPLOAD_FOLDER, tipe_properti, str(no))
        if os.path.exists(property_folder):
            try:
                shutil.rmtree(property_folder)
            except Exception as e:
                print(f"Warning: Could not delete property folder: {str(e)}")
        
        # Recreate ZIP file with remaining data
        try:
            create_zip()
        except Exception as e:
            print(f"Warning: Could not recreate ZIP file: {str(e)}")
        
        return jsonify({'success': True, 'message': f'Data {tipe_properti} No. {no} berhasil dihapus'})
    
    except Exception as e:
        import traceback
        print(f"Error in delete_data: {str(e)}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/reset-all', methods=['POST'])
def reset_all():
    csrf_token = request.form.get('csrf_token')
    if not csrf_token or not validate_csrf_token(csrf_token):
        flash('Invalid CSRF token. Operasi dibatalkan untuk keamanan.', 'danger')
        return redirect(url_for('index'))
    
    try:
        # Remove Excel file
        if os.path.exists(EXCEL_FILE):
            try:
                os.remove(EXCEL_FILE)
            except Exception as e:
                print(f"Warning: Could not remove Excel file: {str(e)}")
        
        # Only proceed if upload folder exists
        if os.path.exists(UPLOAD_FOLDER):
            # Remove property type folders
            try:
                for item in os.listdir(UPLOAD_FOLDER):
                    item_path = os.path.join(UPLOAD_FOLDER, item)
                    if os.path.isdir(item_path) and item in ALLOWED_TIPE_PROPERTI:
                        try:
                            shutil.rmtree(item_path)
                        except Exception as e:
                            print(f"Warning: Could not remove folder {item}: {str(e)}")
            except Exception as e:
                print(f"Warning: Error listing upload folder: {str(e)}")
            
            # Remove all ZIP files matching upl_*.zip pattern
            try:
                zip_files = [f for f in os.listdir(UPLOAD_FOLDER) if f.startswith('upl_') and f.endswith('.zip')]
                for zf in zip_files:
                    try:
                        os.remove(os.path.join(UPLOAD_FOLDER, zf))
                    except Exception as e:
                        print(f"Warning: Could not remove ZIP file {zf}: {str(e)}")
            except Exception as e:
                print(f"Warning: Error removing ZIP files: {str(e)}")
        
        # Ensure upload folder exists
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # Reinitialize Excel
        init_excel()
        
        flash('✅ Semua data berhasil direset! Nomor dan data kembali ke awal.', 'success')
    except Exception as e:
        flash(f'❌ Terjadi kesalahan saat reset: {str(e)}', 'danger')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
