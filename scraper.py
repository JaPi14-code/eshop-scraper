# =============================================================================
# 🛒 UNIVERZÁLNÍ E-SHOP SCRAPER
# =============================================================================
# Stahuje produktová data (název, EAN, cena, dostupnost) z e-shopů
# Optimalizováno pro: Shoptet, WooCommerce, PrestaShop, Shopify
# =============================================================================
# NÁVOD PRO GOOGLE COLAB:
#   1. Buňka 1: Instalace (pip install...)
#   2. Buňka 2: Nastavte URL_WEBU
#   3. Buňka 3: Zkopírujte tento celý soubor
#   4. Buňka 4: Stažení výsledků
#   5. Buňka 5: Reset pro nový web
# =============================================================================

# =============================================================================
# BUŇKA 1: INSTALACE (spusťte jednou)
# =============================================================================
# !pip install requests beautifulsoup4 pandas openpyxl lxml -q
# print("✅ Instalace dokončena")

# =============================================================================
# BUŇKA 2: NASTAVENÍ WEBU
# =============================================================================
# URL_WEBU = "https://aktin.cz"  # Změňte na váš cílový web

# =============================================================================
# BUŇKA 3: HLAVNÍ SCRAPER (zkopírujte celé)
# =============================================================================

import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import json
import random
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ===========================================================================
# GLOBÁLNÍ PROMĚNNÉ - přežijí zastavení!
# ===========================================================================
if 'products_data' not in dir(): products_data = []
if 'all_product_urls' not in dir(): all_product_urls = set()
if 'processed_urls' not in dir(): processed_urls = set()
if 'visited_pages' not in dir(): visited_pages = set()
if 'category_urls' not in dir(): category_urls = set()

# ===========================================================================
# KONFIGURACE
# ===========================================================================
try:
    BASE_URL = URL_WEBU.strip().rstrip('/')
except:
    BASE_URL = "https://aktin.cz"  # Výchozí hodnota

DOMAIN = urlparse(BASE_URL).netloc

# Rozšířené headers pro obcházení blokací
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]

HEADERS = {
    'User-Agent': random.choice(USER_AGENTS),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'cs-CZ,cs;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
}

# Nastavení
DELAY_MIN = 0.5
DELAY_MAX = 1.5
MAX_PAGES = 1000
MAX_PRODUCTS = 100000
MAX_RETRIES = 3

# Známé kategorie pro různé e-shopy (rozšiřitelné)
KNOWN_CATEGORIES = {
    'aktin.cz': [
        '/proteiny', '/aminokyseliny', '/kreatin', '/sacharidy', '/gainery',
        '/spalovace-tuku', '/vitaminy-mineraly', '/zdravi', '/superfood',
        '/orechova-masla', '/snacky', '/napoje', '/potraviny', '/tycinky',
        '/kloubni-vyziva', '/imunita', '/trava-a-bylinky', '/pece-o-telo',
        '/pomucky', '/obleceni', '/balicky', '/novinky', '/sleva', '/vyprodej',
    ],
    'brainmarket.cz': [
        '/brainmax-doplnky-stravy/', '/brainmax-pure/', '/doplnky-stravy/',
        '/potraviny-bm/', '/domov/', '/kosmetika-drogerie/', '/obleceni-3/',
        '/trainmax/', '/wellmax/', '/lauf/', '/blight/', '/usetri/', '/novinky/',
    ],
}

# ===========================================================================
# POMOCNÉ FUNKCE
# ===========================================================================

session = requests.Session()
session.headers.update(HEADERS)

def get_delay():
    """Náhodné zpoždění mezi požadavky"""
    return random.uniform(DELAY_MIN, DELAY_MAX)

def get_page(url, retries=MAX_RETRIES):
    """Stáhne stránku s opakováním a rotací User-Agent"""
    for i in range(retries):
        try:
            # Rotace User-Agent
            session.headers['User-Agent'] = random.choice(USER_AGENTS)
            
            response = session.get(url, timeout=30, allow_redirects=True)
            
            if response.status_code == 200:
                return response.text
            elif response.status_code == 403:
                print(f"\n    ⚠️ Blokováno (403), zkouším znovu...")
                time.sleep(5 * (i + 1))
            elif response.status_code == 429:
                print(f"\n    ⚠️ Rate limit, čekám...")
                time.sleep(30)
            else:
                time.sleep(2)
        except Exception as e:
            time.sleep(3 * (i + 1))
    return None

def clean_price(text):
    """Vyčistí cenu"""
    if not text:
        return ""
    # Odstraní měnu a mezery
    price = re.sub(r'[^\d,.]', '', str(text))
    # Nahradí čárku tečkou
    price = price.replace(',', '.')
    # Ponechá jen poslední tečku (pro desetinná místa)
    parts = price.rsplit('.', 1)
    if len(parts) == 2 and len(parts[1]) <= 2:
        price = parts[0].replace('.', '') + '.' + parts[1]
    else:
        price = price.replace('.', '')
    return price

def clean_text(text):
    """Odstraní neplatné znaky pro Excel"""
    if not isinstance(text, str):
        return str(text) if text else ""
    # Odstraní kontrolní znaky
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    # Odstraní speciální Unicode znaky které dělají problém
    text = text.encode('utf-8', errors='ignore').decode('utf-8')
    return text.strip()

def is_product_url(url):
    """Heuristika - je to URL produktu?"""
    if not url or not url.startswith(('http://', 'https://')):
        return False
    
    parsed = urlparse(url)
    if DOMAIN not in parsed.netloc:
        return False
    
    path = parsed.path.lower()
    
    # Vyloučit systémové stránky
    excluded_patterns = [
        # Košík a objednávky
        '/kosik', '/cart', '/basket', '/checkout', '/objednavka', '/order', '/pokladna',
        # Účet
        '/login', '/prihlaseni', '/registrace', '/register', '/ucet', '/account', '/profil',
        '/zapomenute-heslo', '/odhlaseni', '/logout',
        # Informační stránky
        '/kontakt', '/contact', '/o-nas', '/about', '/o-spolecnosti', '/firma',
        '/blog', '/clanek', '/article', '/magazin', '/clanky', '/recepty',
        '/podminky', '/terms', '/gdpr', '/cookies', '/ochrana-udaju', '/privacy',
        '/faq', '/pomoc', '/help', '/otazky', '/zakaznicka-podpora',
        '/doprava', '/shipping', '/platba', '/payment', '/reklamace', '/return', '/vraceni',
        '/jak-nakupovat', '/obchodni-podminky', '/vse-o-nakupu',
        # Technické
        '/sitemap', '/feed', '/rss', '/xml', '/json', '/api', '/ajax', '/graphql',
        '/search', '/hledat', '/vyhledavani',
        '/tag', '/znacka', '/brand', '/vyrobce', '/manufacturer',
        '/kategorie', '/category', '/catalog', '/katalog',
        '/page/', '/strana-', '/stranka-', '?page=', '&page=',
        '/wp-admin', '/admin', '/wp-content', '/wp-includes', '/assets', '/static',
        # Soubory
        '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.svg', '.css', '.js', '.xml', '.ico',
        # Speciální
        '/wishlist', '/porovnani', '/compare', '/hodnoceni', '/review',
        '/sluzby', '/services', '/prodejny', '/stores', '/pobocky',
        '/kariera', '/career', '/spoluprace', '/affiliate', '/partneri',
    ]
    
    for excl in excluded_patterns:
        if excl in path or excl in url.lower():
            return False
    
    # URL nesmí být příliš krátká
    if len(path) < 5 or path == '/':
        return False
    
    # Produkt má obvykle delší URL s názvem
    # A neobsahuje více než jeden parametr
    if url.count('?') > 1:
        return False
    
    return True

def is_category_url(url):
    """Je to URL kategorie?"""
    if not url or not url.startswith(('http://', 'https://')):
        return False
    
    parsed = urlparse(url)
    if DOMAIN not in parsed.netloc:
        return False
    
    path = parsed.path.lower()
    
    # Vyloučit systémové stránky (striktnější filtr)
    excluded = [
        '/kosik', '/cart', '/checkout', '/login', '/registrace', '/account',
        '/kontakt', '/blog', '/clanek', '/podminky', '/gdpr', '/faq', '/sitemap',
        '.pdf', '.jpg', '.png', '/wp-admin', '/admin', '/api',
        '/objednavka', '/order', '/prihlaseni', '/odhlaseni',
    ]
    
    for excl in excluded:
        if excl in path:
            return False
    
    return True

def get_known_categories():
    """Vrátí známé kategorie pro daný web"""
    for domain, categories in KNOWN_CATEGORIES.items():
        if domain in DOMAIN:
            return [BASE_URL + cat for cat in categories]
    return []

def find_product_links(soup, base_url):
    """Najde odkazy na produkty na stránce"""
    urls = set()
    
    # Shoptet specifické selektory
    shoptet_selectors = [
        'a.p-name', 'a.p-item-title', '.p-item a.p-name',
        '.p-info a', '.product-name a', 'a.product-name',
        '.p h2 a', '.p h3 a', '.p-item h2 a',
        'a[data-product-name]', '[data-product] a',
    ]
    
    # WooCommerce selektory
    woo_selectors = [
        '.woocommerce-loop-product__link',
        '.woocommerce-LoopProduct-link',
        'ul.products li.product a',
        '.product-item-link', '.product a.product-item-link',
    ]
    
    # PrestaShop selektory
    presta_selectors = [
        '.product-title a', '.product_name a',
        '.product-miniature a.thumbnail',
        '.product-container a.product-name',
    ]
    
    # Shopify selektory
    shopify_selectors = [
        '.product-card a', '.product-card__link',
        '.product-item a', '.product-link',
        '.grid-product__link', '.card__link',
    ]
    
    # Obecné selektory
    generic_selectors = [
        '.product a', '.products a', '[class*="product"] a',
        '.item a', '.card a', '.grid-item a',
        'h2 a', 'h3 a', 'h4 a',
        'article a', '.product-list a',
        '.collection-product a', '.product-grid a',
    ]
    
    all_selectors = (shoptet_selectors + woo_selectors + 
                     presta_selectors + shopify_selectors + generic_selectors)
    
    for selector in all_selectors:
        try:
            for link in soup.select(selector):
                href = link.get('href', '')
                if href and not href.startswith('#') and not href.startswith('javascript:'):
                    full_url = urljoin(base_url, href)
                    # Odstranit fragment a normalizovat
                    full_url = full_url.split('#')[0]
                    if is_product_url(full_url):
                        urls.add(full_url)
        except:
            pass
    
    # Záložní metoda - všechny odkazy
    if len(urls) < 3:
        for a in soup.find_all('a', href=True):
            href = a.get('href', '')
            if href and not href.startswith('#'):
                full_url = urljoin(base_url, href)
                full_url = full_url.split('#')[0]
                if is_product_url(full_url):
                    urls.add(full_url)
    
    return urls

def find_category_links(soup, base_url):
    """Najde odkazy na kategorie a podkategorie"""
    urls = set()
    
    category_selectors = [
        # Navigace
        'nav a', '.menu a', '.navigation a', '.navbar a', 'header a',
        '.main-menu a', '.primary-menu a', '.site-nav a',
        # Kategorie
        '.category a', '.categories a', '[class*="category"] a',
        '.cat-item a', '.product-category a', '.subcategory a',
        # Sidebar
        '.sidebar a', '.widget a', '.aside a',
        # Shoptet
        '.category-tree a', '.p-category-list a', '.navigation-categories a',
        # Obecné
        '.nav a', 'ul.menu a', 'li.menu-item a', '.dropdown a',
    ]
    
    for selector in category_selectors:
        try:
            for link in soup.select(selector):
                href = link.get('href', '')
                if href and not href.startswith('#'):
                    full_url = urljoin(base_url, href)
                    full_url = full_url.split('#')[0]
                    if is_category_url(full_url) and full_url not in visited_pages:
                        urls.add(full_url)
        except:
            pass
    
    return urls

def find_pagination_links(soup, base_url):
    """Najde odkazy na další stránky"""
    urls = set()
    
    pagination_selectors = [
        # Přímé next odkazy
        'a.next', 'a[rel="next"]', '.next a', '.pagination-next a',
        'a[title*="další"]', 'a[title*="Další"]', 'a[title*="Next"]',
        'a[aria-label*="next"]', 'a[aria-label*="další"]',
        # Stránkování
        '.pagination a', '.paging a', '.page-numbers a',
        '.paginator a', '.pages a', '.page-link',
        # Shoptet
        '.paging-list a', '.pagination-list a',
        # WooCommerce
        '.woocommerce-pagination a',
    ]
    
    for selector in pagination_selectors:
        try:
            for link in soup.select(selector):
                href = link.get('href', '')
                if href and not href.startswith('#'):
                    full_url = urljoin(base_url, href)
                    full_url = full_url.split('#')[0]
                    if DOMAIN in full_url and full_url not in visited_pages:
                        urls.add(full_url)
        except:
            pass
    
    return urls

def extract_product_data(url):
    """Extrahuje data z produktové stránky"""
    html = get_page(url)
    if not html:
        return None
    
    soup = BeautifulSoup(html, 'html.parser')
    
    data = {
        'nazev': '',
        'ean': '',
        'cena': '',
        'cena_puvodni': '',
        'sleva': '',
        'dostupnost': '',
        'url': url,
    }
    
    # === NÁZEV ===
    name_selectors = [
        'h1', 'h1.product-title', 'h1.product-name', 'h1.product_title',
        '[itemprop="name"]', '.p-detail-title', '.p-detail-inner h1',
        '.product-title', '.product-name', '.entry-title',
        '.product-detail h1', '.product-info h1', '.product-header h1',
        'h1.title', 'h1.name', '[data-product-name]',
    ]
    
    for sel in name_selectors:
        try:
            el = soup.select_one(sel)
            if el:
                # Preferuj atribut nebo přímý text
                text = el.get('content') or el.get('data-product-name') or el.get_text(strip=True)
                if text and len(text) > 2 and len(text) < 500:
                    data['nazev'] = clean_text(text)
                    break
        except:
            pass
    
    if not data['nazev']:
        return None
    
    # === EAN / GTIN ===
    # 1. JSON-LD strukturovaná data
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            json_text = script.string or ''
            if not json_text.strip():
                continue
            json_data = json.loads(json_text)
            
            def find_ean_recursive(obj):
                if isinstance(obj, dict):
                    for key in ['gtin13', 'gtin', 'gtin8', 'gtin12', 'gtin14', 'ean', 'mpn', 'sku', 'productID']:
                        if key in obj and obj[key]:
                            val = str(obj[key]).strip()
                            if re.match(r'^\d{8,14}$', val):
                                return val
                    for v in obj.values():
                        result = find_ean_recursive(v)
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_ean_recursive(item)
                        if result:
                            return result
                return None
            
            ean = find_ean_recursive(json_data)
            if ean:
                data['ean'] = ean
                break
        except:
            pass
    
    # 2. Meta tagy
    if not data['ean']:
        meta_selectors = [
            'meta[itemprop="gtin13"]', 'meta[itemprop="gtin"]', 'meta[itemprop="gtin8"]',
            'meta[itemprop="ean"]', 'meta[property="product:ean"]', 'meta[property="og:ean"]',
            'meta[name="ean"]', 'meta[name="gtin"]',
        ]
        for sel in meta_selectors:
            try:
                el = soup.select_one(sel)
                if el and el.get('content'):
                    val = el.get('content').strip()
                    if re.match(r'^\d{8,14}$', val):
                        data['ean'] = val
                        break
            except:
                pass
    
    # 3. Data atributy
    if not data['ean']:
        for attr in ['data-ean', 'data-gtin', 'data-gtin13', 'data-barcode', 'data-product-ean']:
            try:
                el = soup.select_one(f'[{attr}]')
                if el:
                    val = el.get(attr, '').strip()
                    if re.match(r'^\d{8,14}$', val):
                        data['ean'] = val
                        break
            except:
                pass
    
    # 4. Tabulka parametrů
    if not data['ean']:
        param_containers = soup.select('table, .params, .product-params, .parameters, '
                                        '.specifications, .attributes, dl, .p-params, '
                                        '.product-properties, .product-attributes')
        for container in param_containers:
            try:
                text = container.get_text(separator=' ')
                match = re.search(r'(?:EAN|GTIN|Čárový\s*kód|Barcode)[:\s]*(\d{8,14})', text, re.I)
                if match:
                    data['ean'] = match.group(1)
                    break
            except:
                pass
    
    # 5. Regex v celém HTML
    if not data['ean']:
        patterns = [
            r'"gtin13"\s*:\s*"?(\d{13})"?',
            r'"gtin"\s*:\s*"?(\d{8,14})"?',
            r'"ean"\s*:\s*"?(\d{8,14})"?',
            r'data-ean="(\d{8,14})"',
            r'data-gtin="(\d{8,14})"',
            r'>EAN[:\s]*(\d{8,14})<',
        ]
        for pattern in patterns:
            try:
                match = re.search(pattern, html)
                if match:
                    data['ean'] = match.group(1)
                    break
            except:
                pass
    
    # === CENA ===
    price_selectors = [
        '[itemprop="price"]', 'meta[itemprop="price"]',
        '.price-final', '.p-final', '.p-detail-price', '.p-main-price',
        '.current-price', '.product-price', '.price', '.price-box .price',
        '.woocommerce-Price-amount', '.amount', 
        '.price-new', '.special-price', '.offer-price', '.sale-price',
        'ins .amount', '.price ins', '.final-price',
        '[data-price]', '.product-price-value',
    ]
    
    for sel in price_selectors:
        try:
            el = soup.select_one(sel)
            if el:
                # Zkus content atribut, data atribut, nebo text
                price = el.get('content') or el.get('data-price') or el.get_text(strip=True)
                cleaned = clean_price(price)
                if cleaned:
                    try:
                        if float(cleaned) > 0:
                            data['cena'] = cleaned
                            break
                    except:
                        pass
        except:
            pass
    
    # === PŮVODNÍ CENA ===
    orig_selectors = [
        '.price-standard', '.p-standard', '.p-before-price',
        '.original-price', '.old-price', '.price-old', '.was-price',
        '.regular-price', '.list-price', '.compare-price',
        'del .amount', '.price del', 'del.price', 's.price', 's .amount',
        '.price-before-discount', '.crossed-price',
    ]
    
    for sel in orig_selectors:
        try:
            el = soup.select_one(sel)
            if el:
                price = clean_price(el.get_text(strip=True))
                if price:
                    try:
                        if float(price) > 0:
                            data['cena_puvodni'] = price
                            break
                    except:
                        pass
        except:
            pass
    
    # === SLEVA ===
    if data['cena'] and data['cena_puvodni']:
        try:
            curr = float(data['cena'])
            orig = float(data['cena_puvodni'])
            if orig > curr > 0:
                discount = ((orig - curr) / orig) * 100
                data['sleva'] = f"{discount:.0f}%"
        except:
            pass
    
    # === DOSTUPNOST ===
    avail_selectors = [
        '.availability', '.p-availability', '.stock', '.stock-status',
        '[itemprop="availability"]', '.in-stock', '.out-of-stock',
        '.product-availability', '.delivery-info', '.skladem', '.dostupnost',
        '.stock-info', '.availability-status', '.product-stock',
        '[data-availability]', '.inventory-status',
    ]
    
    for sel in avail_selectors:
        try:
            el = soup.select_one(sel)
            if el:
                text = el.get('content') or el.get('data-availability') or el.get_text(strip=True)
                if text:
                    data['dostupnost'] = clean_text(text)[:100]  # Omezit délku
                    break
        except:
            pass
    
    return data

def save_progress():
    """Uloží průběžné výsledky"""
    if products_data:
        try:
            df = pd.DataFrame(products_data)
            df.to_excel('/content/eshop_prubezne.xlsx', index=False)
        except:
            pass

# ===========================================================================
# HLAVNÍ SCRAPING
# ===========================================================================

print("=" * 70)
print("🛒 UNIVERZÁLNÍ E-SHOP SCRAPER")
print("=" * 70)
print(f"🎯 Web: {BASE_URL}")
print(f"📊 Již staženo: {len(products_data)} produktů")
print(f"🔗 URL v paměti: {len(all_product_urls)}")
print(f"📁 Navštíveno stránek: {len(visited_pages)}")
print("=" * 70)
print("💡 Pro ZASTAVENÍ klikněte ⏹️ Stop")
print("💡 Po zastavení spusťte BUŇKU 4 pro stažení")
print("💡 Pro pokračování znovu spusťte tuto buňku")
print("=" * 70)

try:
    # =========================================================================
    # FÁZE 1: Objevování stránek a URL produktů
    # =========================================================================
    if len(all_product_urls) == 0:
        print(f"\n📁 FÁZE 1: Prozkoumávání webu\n")
        
        # Začneme od hlavní stránky a známých kategorií
        pages_to_visit = {BASE_URL}
        
        # Přidáme známé kategorie
        known_cats = get_known_categories()
        if known_cats:
            print(f"   📂 Nalezeno {len(known_cats)} známých kategorií")
            pages_to_visit.update(known_cats)
        
        pages_visited_this_run = 0
        
        while pages_to_visit and len(visited_pages) < MAX_PAGES:
            url = pages_to_visit.pop()
            
            if url in visited_pages:
                continue
            
            pages_visited_this_run += 1
            print(f"   [{pages_visited_this_run}|{len(visited_pages)+1}] {url[:65]}...", end=" ", flush=True)
            
            html = get_page(url)
            if not html:
                print("❌")
                visited_pages.add(url)
                time.sleep(get_delay())
                continue
            
            soup = BeautifulSoup(html, 'html.parser')
            visited_pages.add(url)
            
            # Najdi produkty
            new_products = find_product_links(soup, url)
            before = len(all_product_urls)
            all_product_urls.update(new_products)
            added = len(all_product_urls) - before
            
            # Najdi další stránky k prozkoumání
            cat_links = find_category_links(soup, url)
            pag_links = find_pagination_links(soup, url)
            
            new_pages = (cat_links | pag_links) - visited_pages
            pages_to_visit.update(new_pages)
            
            print(f"✅ +{added} (celkem: {len(all_product_urls)}, fronta: {len(pages_to_visit)})")
            
            time.sleep(get_delay())
            
            if len(all_product_urls) >= MAX_PRODUCTS:
                print(f"\n   ⚠️ Dosažen limit {MAX_PRODUCTS} produktů")
                break
        
        print(f"\n{'='*70}")
        print(f"📊 FÁZE 1 DOKONČENA")
        print(f"   Navštíveno stránek: {len(visited_pages)}")
        print(f"   Nalezeno URL produktů: {len(all_product_urls)}")
        print("=" * 70)
    else:
        print(f"\n📊 Pokračuji - {len(all_product_urls)} URL v paměti\n")
    
    # =========================================================================
    # FÁZE 2: Stahování detailů produktů
    # =========================================================================
    print(f"\n📦 FÁZE 2: Stahování detailů produktů\n")
    
    urls_to_process = list(all_product_urls - processed_urls)
    total = len(urls_to_process)
    
    print(f"   Ke zpracování: {total}")
    print(f"   Již hotovo: {len(processed_urls)}")
    print(f"   Staženo produktů: {len(products_data)}\n")
    
    if total == 0:
        print("   ✅ Všechny URL již zpracovány!")
    
    start_time = time.time()
    
    for i, url in enumerate(urls_to_process, 1):
        elapsed = time.time() - start_time
        rate = i / elapsed if elapsed > 0 else 0
        eta = (total - i) / rate if rate > 0 else 0
        
        print(f"\r   [{i}/{total}] {(i/total)*100:.1f}% | "
              f"Produktů: {len(products_data)} | "
              f"ETA: {int(eta//60)}m {int(eta%60)}s   ", end="", flush=True)
        
        try:
            data = extract_product_data(url)
            if data and data['nazev']:
                products_data.append(data)
        except Exception as e:
            pass
        
        processed_urls.add(url)
        time.sleep(get_delay())
        
        # Průběžné ukládání každých 50 produktů
        if i % 50 == 0:
            save_progress()

except KeyboardInterrupt:
    print("\n\n⏹️ ZASTAVENO UŽIVATELEM")
    save_progress()

# Závěrečná statistika
print(f"\n\n{'='*70}")
print("📊 AKTUÁLNÍ STAV")
print("="*70)
print(f"   Web:                 {BASE_URL}")
print(f"   Staženo produktů:    {len(products_data)}")
print(f"   S EAN kódem:         {len([p for p in products_data if p.get('ean')])}")
print(f"   S cenou:             {len([p for p in products_data if p.get('cena')])}")
print(f"   Ve slevě:            {len([p for p in products_data if p.get('sleva')])}")
print(f"   Zpracováno URL:      {len(processed_urls)}/{len(all_product_urls)}")
print(f"   Zbývá:               {len(all_product_urls) - len(processed_urls)}")
print("="*70)
print("\n✅ Spusťte BUŇKU 4 pro stažení Excel souboru")
print("💡 Nebo znovu tuto buňku pro pokračování")

session.close()


# =============================================================================
# BUŇKA 4: STAŽENÍ VÝSLEDKŮ (spusťte kdykoliv)
# =============================================================================
"""
from google.colab import files
from datetime import datetime
from urllib.parse import urlparse
import pandas as pd
import re

def clean_for_excel(text):
    if not isinstance(text, str):
        return str(text) if text else ""
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)
    return text.strip()

if 'products_data' in dir() and products_data:
    # Vyčistit data
    clean_data = []
    for p in products_data:
        clean_p = {k: clean_for_excel(v) for k, v in p.items()}
        clean_data.append(clean_p)
    
    df = pd.DataFrame(clean_data)
    df = df.rename(columns={
        'nazev': 'Název produktu',
        'ean': 'EAN',
        'cena': 'Cena',
        'cena_puvodni': 'Původní cena',
        'sleva': 'Sleva',
        'dostupnost': 'Dostupnost',
        'url': 'URL'
    })
    
    # Odstranit duplikáty
    df = df.drop_duplicates(subset=['Název produktu', 'URL'])
    df = df.sort_values('Název produktu')
    
    # Název souboru podle domény
    domain = urlparse(BASE_URL).netloc.replace('www.', '').replace('.', '_')
    filename = f'{domain}_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    
    print("="*70)
    print("📊 SOUHRN EXPORTU")
    print("="*70)
    print(f"   Web:              {BASE_URL}")
    print(f"   Celkem produktů:  {len(df)}")
    print(f"   S EAN kódem:      {len(df[df['EAN'].astype(str).str.len() > 0])}")
    print(f"   S cenou:          {len(df[df['Cena'].astype(str).str.len() > 0])}")
    print(f"   Ve slevě:         {len(df[df['Sleva'].astype(str).str.len() > 0])}")
    print("="*70)
    
    df.to_excel(filename, index=False)
    files.download(filename)
    print(f"\n✅ Stahuji: {filename}")
else:
    print("❌ Žádná data - nejdřív spusťte BUŇKU 3")
"""


# =============================================================================
# BUŇKA 5: RESET (pro nový web)
# =============================================================================
"""
products_data = []
all_product_urls = set()
processed_urls = set()
visited_pages = set()
category_urls = set()
print("🔄 Reset dokončen - změňte URL_WEBU v BUŇCE 2 a spusťte BUŇKU 3")
"""
