#!/usr/bin/env python3
import html
import hashlib
import json
import os
import random
import re
import shutil
import sys
import threading
import textwrap
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

if os.name == "nt":
    import msvcrt
else:
    import termios
    import tty

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


BASE_URL = os.environ.get("TAMBLOX_BASE_URL", "https://tamblox.net").rstrip("/")
PROXY_URL = os.environ.get("TAMBLOX_PROXY_URL", "").strip().rstrip("/")
LICENSE_KEY = os.environ.get("TAMBLOX_LICENSE_KEY", "").strip()
LICENSE_HAS_API_KEY = False
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
DEVICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".tamblox_device")
LOCAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".dominancia")
LOCAL_CONFIG_FILE = os.path.join(LOCAL_CONFIG_DIR, "config.local.json")
LOCAL_DEVICE_FILE = os.path.join(LOCAL_CONFIG_DIR, ".tamblox_device")
DEFAULT_INTERVAL = 2.0
USER_AGENT = "TambloxStockBuyer/1.0"
SITEMAP_REFRESH_SECONDS = float(os.environ.get("TAMBLOX_SITEMAP_REFRESH", "120"))
MIN_REQUEST_INTERVAL = float(os.environ.get("TAMBLOX_MIN_REQUEST_INTERVAL", "2.2"))
LOOP_JITTER_SECONDS = float(os.environ.get("TAMBLOX_LOOP_JITTER", "0.35"))
TARGET_API_LIMIT = int(os.environ.get("TAMBLOX_TARGET_API_LIMIT", "3"))
PRICE_ENRICH_WORKERS = int(os.environ.get("TAMBLOX_PRICE_ENRICH_WORKERS", "4"))
BLOCK_COOLDOWN_SECONDS = float(os.environ.get("TAMBLOX_BLOCK_COOLDOWN", "300"))
BALANCE_REFRESH_SECONDS = float(os.environ.get("TAMBLOX_BALANCE_REFRESH", "10"))
RESTOCK_TIMER_REFRESH_SECONDS = float(os.environ.get("TAMBLOX_RESTOCK_TIMER_REFRESH", "3"))
GLOBAL_RESTOCK_REFRESH_SECONDS = float(os.environ.get("TAMBLOX_GLOBAL_RESTOCK_REFRESH", "60"))
RESTOCK_READY_SECONDS = float(os.environ.get("TAMBLOX_RESTOCK_READY_SECONDS", "5"))
RESTOCK_READY_REQUEST_INTERVAL = float(os.environ.get("TAMBLOX_RESTOCK_READY_INTERVAL", "1.35"))
RESTOCK_PREPARE_SECONDS = float(os.environ.get("TAMBLOX_RESTOCK_PREPARE_SECONDS", "10"))
USE_API_PRODUCTS = os.environ.get("TAMBLOX_USE_API_PRODUCTS", "1").lower() in ("1", "true", "yes", "sim")
SITE_FALLBACK = os.environ.get("TAMBLOX_SITE_FALLBACK", "0").lower() in ("1", "true", "yes", "sim")
SUPPLEMENT_KITSUNE_WEB = os.environ.get("TAMBLOX_SUPPLEMENT_KITSUNE_WEB", "1").lower() in ("1", "true", "yes", "sim")
USE_API_PRICE_OVERRIDES = os.environ.get("TAMBLOX_USE_PRICE_OVERRIDES", "0").lower() in ("1", "true", "yes", "sim")
_SITEMAP_CACHE: Tuple[float, List["Product"]] = (0.0, [])
_RESTOCK_TIMER_CACHE: Dict[str, Tuple[float, Optional[float]]] = {}
_GLOBAL_RESTOCK_CACHE: Tuple[float, Optional[float]] = (0.0, None)
_SELECTED_PRODUCTS_CACHE: List["Product"] = []
_API_SKIP_UNTIL = 0.0
API_RETRY_SECONDS = 60.0
_LAST_REQUEST_AT = 0.0
_REQUEST_LOCK = threading.Lock()
_BLOCKED_UNTIL = 0.0
_RESTOCK_READY_UNTIL = 0.0

API_PRICE_OVERRIDES = {
    "24": 0.20,
    "30": 0.20,
    "32": 0.14,
    "48": 0.42,
    "169": 0.17,
    "170": 0.48,
    "171": 0.27,
    "172": 0.51,
    "173": 0.52,
    "175": 0.23,
    "176": 0.16,
    "177": 0.22,
    "179": 0.16,
    "180": 0.16,
    "181": 0.16,
    "183": 0.14,
    "210": 0.18,
    "211": 0.20,
    "216": 0.18,
    "217": 0.18,
    "218": 0.44,
    "223": 1.92,
    "224": 1.68,
}

ASCII_ART = r"""
                                  |>>>
                                  |
                    |>>>      _  *|*  _         |>>>
                    |        |;| |;| |;|        |
                _  *|*  _    \\.    .  /    _  *|*  _
               |;|*|;|*|;|    \\:. ,  /    |;|*|;|*|;|
               \\..      /    ||;   . |    \\.    .  /
                \\.  ,  /     ||:  .  |     \\:  .  /
                 ||:   |_   _ ||_ . _ | _   _||:   |
                 ||:  .|||*|;|*|;|*|;|*|;|_|;||:.  |
                 ||:   ||.    .     .      . ||:  .|
                 ||: . || .     . .   .  ,   ||:   |       \,/
                 ||:   ||:  ,  _______   .   ||: , |            /`\
                 ||:   || .   /+++++++\    . ||:   |
                 ||:   ||.    |+++++++| .    ||: . |
              __ ||: . ||: ,  |+++++++|.  . *||*   |
     ____--`~    '--~~**|.    |+++++**|----~    ~`---,              ___
-~--~                   ~---__|,--~'                  ~~----_____-~'   `~----~~
""".strip("\n")


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLOOD = "\033[38;5;196m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"


THEMES: Dict[str, Dict[str, str]] = {
    "default": {},
    "neon": {
        "RED": "\033[95m",
        "GREEN": "\033[92m",
        "YELLOW": "\033[93m",
        "BLUE": "\033[94m",
        "MAGENTA": "\033[35m",
        "CYAN": "\033[96m",
        "WHITE": "\033[97m",
        "DIM": "\033[2m",
    },
    "hacker": {
        "RED": "\033[91m",
        "GREEN": "\033[92m",
        "YELLOW": "\033[32m",
        "BLUE": "\033[36m",
        "MAGENTA": "\033[32m",
        "CYAN": "\033[92m",
        "WHITE": "\033[97m",
        "DIM": "\033[2m",
    },
    "amber": {
        "RED": "\033[91m",
        "GREEN": "\033[93m",
        "YELLOW": "\033[33m",
        "BLUE": "\033[37m",
        "MAGENTA": "\033[35m",
        "CYAN": "\033[93m",
        "WHITE": "\033[97m",
        "DIM": "\033[2m",
    },
    "mono": {
        "RED": "\033[37m",
        "GREEN": "\033[37m",
        "YELLOW": "\033[37m",
        "BLUE": "\033[37m",
        "MAGENTA": "\033[37m",
        "CYAN": "\033[37m",
        "WHITE": "\033[37m",
        "DIM": "\033[2m",
    },
}


def apply_theme(config: Dict[str, Any]) -> str:
    theme = str(os.environ.get("TAMBLOX_THEME") or config.get("theme") or "default").strip().lower()
    if theme not in THEMES:
        theme = "default"
    for key, value in THEMES[theme].items():
        setattr(C, key, value)
    return theme


class TambloxBlockedError(RuntimeError):
    pass


@dataclass
class Product:
    id: str
    name: str
    price: Optional[float] = None
    stock: Optional[int] = None
    option_id: str = ""
    category: str = ""
    raw: Optional[Dict[str, Any]] = None
    auto_target: Optional[str] = None
    restock_at: Optional[float] = None
    store: str = "tamblox"
    currency: str = "USD"

    @property
    def has_stock(self) -> bool:
        return self.stock is None or self.stock > 0

    @property
    def price_text(self) -> str:
        if self.price is None:
            return "?"
        if self.currency.upper() == "VND":
            return f"{int(self.price):,}đ"
        return f"${self.price:.2f}"

    @property
    def stock_text(self) -> str:
        return "?" if self.stock is None else str(self.stock)


@dataclass
class Target:
    label: str
    quantity: int
    product_id: Optional[str] = None
    option_id: str = ""
    name_contains: Optional[str] = None
    price_equals: Optional[float] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    bought: bool = False
    bought_quantity: int = 0
    store: str = "tamblox"


def clear() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def banner() -> None:
    width = content_width()
    title = "DOMINANCIA 7"
    line = "=" * width
    print(f"{C.BLOOD}{C.BOLD}{center_block(ASCII_ART)}{C.RESET}")
    print(center_text(line, C.BLOOD + C.BOLD))
    print(center_text(title, C.BLOOD + C.BOLD, width))
    print(center_text(line, C.BLOOD + C.BOLD))


def terminal_width() -> int:
    return max(80, min(120, shutil.get_terminal_size((100, 30)).columns))


def content_width() -> int:
    return min(terminal_width(), 96)


def visible_len(value: str) -> int:
    return len(re.sub(r"\033\[[0-9;]*m", "", value))


def center_text(value: str, color: str = "", width: Optional[int] = None) -> str:
    width = width or content_width()
    padding = max(0, (terminal_width() - width) // 2)
    text_padding = max(0, (width - visible_len(value)) // 2)
    text = (" " * text_padding) + value
    return f"{' ' * padding}{color}{text}{C.RESET if color else ''}"


def center_block(value: str) -> str:
    lines = value.splitlines()
    art_width = max((visible_len(line) for line in lines), default=0)
    padding = max(0, (terminal_width() - art_width) // 2)
    return "\n".join((" " * padding) + line for line in lines)


def short_text(value: str, max_len: int) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= max_len:
        return value
    return value[: max_len - 3].rstrip() + "..."


def source_label(source: str) -> str:
    if "API PRODUCTS.PHP" in source.upper():
        return "Tamblox"
    if source == "api":
        return "API"
    if source.startswith("publico"):
        return "SITE"
    source = source.replace("WEB", "SITE").replace("SITEMAP", "OCULTOS")
    return short_text(source, 32)


def is_mobile_controller() -> bool:
    return os.environ.get("DOMINANCIA_MOBILE_CONTROLLER", "").strip().lower() in ("1", "true", "yes", "sim", "on")


def product_title(name: str) -> str:
    name = html.unescape(str(name))
    name = re.sub(r"\s*[lI]?\s*\[IP\s+GLOBAL\]\s*", " ", name, flags=re.I).strip()
    return re.sub(r"\s+", " ", name)


def compact_product_title(name: str) -> str:
    title = product_title(name)
    compact = re.sub(r"\s*\([^)]{18,}\)", "", title).strip()
    compact = re.sub(r"\s+", " ", compact)
    return compact or title


def clean_target_label(name: str) -> str:
    name = product_title(name)
    name = re.sub(r"\s+\$\d+(?:\.\d{1,2})?(?=[\s.,;:!?)]|$)", "", name).strip()
    return name


def rule(char: str = "-", color: str = "") -> str:
    width = content_width()
    return f"{color}{char * width}{C.RESET if color else ''}"


def progress_bar(done: int, total: int, width: int = 28) -> str:
    filled = int(width * done / max(1, total))
    return f"{C.GREEN}{'#' * filled}{C.BLOOD}{'-' * (width - filled)}{C.RESET}"


def scan_bar(frame: int, width: int = 34) -> str:
    if width < 6:
        width = 6
    pos = 1 + (frame % (width - 1))
    bar = ["-"] * width
    bar[(pos - 1) % width] = "="
    bar[pos] = ">"
    raw = "".join(bar)
    marker = raw.find("=>")
    if marker >= 0:
        return f"{C.BLOOD}{raw[:marker]}{C.WHITE}=>{C.BLOOD}{raw[marker + 2:]}{C.RESET}"
    return f"{C.BLOOD}{raw}{C.RESET}"


def is_kitsune_inventory_name(name: str) -> bool:
    normalized = product_title(name).lower()
    return "kitsune inventory" in normalized and "ate kitsune" not in normalized


def should_hide_product(product: Product) -> bool:
    normalized = product_title(product.name).lower()
    return normalized == "god test" or "god test" in normalized


def wrapped_lines(prefix: str, text: str, width: int, color: str = "") -> List[str]:
    available = max(24, width - visible_len(prefix) - 2)
    parts = textwrap.wrap(text, width=available, break_long_words=False, replace_whitespace=True) or [""]
    reset = C.RESET if color else ""
    lines = [f"{prefix}{color}{parts[0]}{reset}"]
    lines.extend(f"{' ' * visible_len(prefix)}{color}{part}{reset}" for part in parts[1:])
    return lines


def clear_current_line() -> None:
    print("\r\033[2K", end="", flush=True)


def animated_wait(message: str, future: Any) -> Any:
    frames = ["|", "/", "-", "\\"]
    start = time.time()
    index = 0
    while not future.done():
        elapsed = time.time() - start
        dots = "." * ((index % 3) + 1)
        frame = frames[index % len(frames)]
        print(
            f"\r{C.BLOOD}{C.BOLD}{frame}{C.RESET} "
            f"{C.BLOOD}{message}{dots:<3}{C.RESET} "
            f"{C.WHITE}{elapsed:4.1f}s{C.RESET}",
            end="",
            flush=True,
        )
        time.sleep(0.12)
        index += 1
    clear_current_line()
    return future.result()


def run_with_animation(message: str, func: Any, *args: Any, **kwargs: Any) -> Any:
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(func, *args, **kwargs)
        return animated_wait(message, future)


def read_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def load_config() -> Dict[str, Any]:
    config = read_json_file(CONFIG_FILE)
    config.update(read_json_file(LOCAL_CONFIG_FILE))
    return config


def save_config_value(key: str, value: Any) -> None:
    save_config_values({key: value})


def save_config_values(values: Dict[str, Any]) -> None:
    config = load_config()
    config.update(values)
    tmp_file = LOCAL_CONFIG_FILE + ".tmp"
    try:
        os.makedirs(LOCAL_CONFIG_DIR, exist_ok=True)
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_file, LOCAL_CONFIG_FILE)
    except Exception:
        try:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        except Exception:
            pass
        pass


def load_or_create_device_id() -> str:
    try:
        for path in (LOCAL_DEVICE_FILE, DEVICE_FILE):
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                value = f.read().strip()
            if re.fullmatch(r"[a-f0-9]{64}", value):
                try:
                    os.makedirs(LOCAL_CONFIG_DIR, exist_ok=True)
                    if path != LOCAL_DEVICE_FILE:
                        with open(LOCAL_DEVICE_FILE, "w", encoding="utf-8") as out:
                            out.write(value)
                except Exception:
                    pass
                return value
    except Exception:
        pass
    seed = "|".join(
        [
            os.environ.get("COMPUTERNAME", ""),
            os.environ.get("USERNAME", ""),
            os.environ.get("PROCESSOR_IDENTIFIER", ""),
            os.path.expanduser("~"),
            str(random.getrandbits(256)),
        ]
    )
    device_id = hashlib.sha256(seed.encode("utf-8", errors="ignore")).hexdigest()
    try:
        os.makedirs(LOCAL_CONFIG_DIR, exist_ok=True)
        with open(LOCAL_DEVICE_FILE, "w", encoding="utf-8") as f:
            f.write(device_id)
    except Exception:
        pass
    return device_id


def wait_for_request_slot() -> None:
    global _LAST_REQUEST_AT
    with _REQUEST_LOCK:
        elapsed = time.time() - _LAST_REQUEST_AT
        interval = RESTOCK_READY_REQUEST_INTERVAL if time.time() < _RESTOCK_READY_UNTIL else MIN_REQUEST_INTERVAL
        wait = interval + random.uniform(0.05, 0.25) - elapsed
        if wait > 0:
            time.sleep(wait)
        _LAST_REQUEST_AT = time.time()


def enable_restock_ready_mode(seconds: float) -> None:
    global _RESTOCK_READY_UNTIL
    _RESTOCK_READY_UNTIL = max(_RESTOCK_READY_UNTIL, time.time() + max(1.0, seconds))


def set_block_cooldown() -> None:
    global _BLOCKED_UNTIL
    _BLOCKED_UNTIL = time.time() + BLOCK_COOLDOWN_SECONDS


def request(url: str, method: str = "GET", fields: Optional[Dict[str, Any]] = None, timeout: int = 20, throttle: bool = True) -> Tuple[int, str, str]:
    if time.time() < _BLOCKED_UNTIL:
        remaining = int(_BLOCKED_UNTIL - time.time())
        raise TambloxBlockedError(f"Cooldown ativo por bloqueio do Tamblox. Aguarde {remaining}s.")
    if PROXY_URL:
        return proxy_request(url, method, fields, timeout, throttle)
    data = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.9, */*;q=0.8"}
    if fields is not None:
        encoded = urllib.parse.urlencode({k: v for k, v in fields.items() if v is not None}).encode("utf-8")
        if method.upper() == "GET":
            sep = "&" if "?" in url else "?"
            url = url + sep + encoded.decode("utf-8")
        else:
            data = encoded
            headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    if throttle:
        wait_for_request_slot()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            if resp.status in (429,) or 520 <= resp.status <= 527 or looks_like_block_page(body):
                set_block_cooldown()
            return resp.status, resp.headers.get("content-type", ""), body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code in (429,) or 520 <= e.code <= 527 or looks_like_block_page(body):
            set_block_cooldown()
        return e.code, e.headers.get("content-type", ""), body


def proxy_request(url: str, method: str = "GET", fields: Optional[Dict[str, Any]] = None, timeout: int = 20, throttle: bool = True) -> Tuple[int, str, str]:
    if not LICENSE_KEY:
        raise RuntimeError("TAMBLOX_LICENSE_KEY/license_key obrigatoria quando proxy_url esta ativo.")
    if throttle:
        wait_for_request_slot()
    proxied_url = url
    try:
        parsed_url = urllib.parse.urlparse(url)
        base_host = urllib.parse.urlparse(BASE_URL).netloc.lower()
        if parsed_url.scheme and parsed_url.netloc.lower() in {base_host, "tamblox.net", "www.tamblox.net"}:
            proxied_url = urllib.parse.urlunparse(("", "", parsed_url.path or "/", parsed_url.params, parsed_url.query, ""))
    except Exception:
        proxied_url = url
    payload = {
        "url": proxied_url,
        "method": method.upper(),
        "fields": fields or {},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json, text/html;q=0.9, */*;q=0.8",
        "Content-Type": "application/json",
        "X-License-Key": LICENSE_KEY,
        "X-Device-Id": load_or_create_device_id(),
    }
    req = urllib.request.Request(f"{PROXY_URL}/proxy", data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout + 10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            try:
                wrapped = json.loads(body)
            except json.JSONDecodeError:
                return resp.status, resp.headers.get("content-type", ""), body
            status = int(wrapped.get("status", resp.status))
            response_body = str(wrapped.get("body", ""))
            content_type = str(wrapped.get("content_type", ""))
            if status in (429,) or 520 <= status <= 527 or looks_like_block_page(response_body):
                set_block_cooldown()
            return status, content_type, response_body
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            wrapped = json.loads(body)
            status = int(wrapped.get("status", e.code))
            response_body = str(wrapped.get("body", body))
            content_type = str(wrapped.get("content_type", e.headers.get("content-type", "")))
            return status, content_type, response_body
        except Exception:
            return e.code, e.headers.get("content-type", ""), body


def error_from_json(body: str, fallback: str) -> str:
    try:
        payload = json.loads(body)
    except Exception:
        return fallback
    if isinstance(payload, dict):
        code = payload.get("code")
        if code:
            return str(code)
        message = payload.get("error") or payload.get("message") or payload.get("msg")
        if message:
            return str(message)
    return fallback


def friendly_error(error: Any) -> str:
    text = str(error)
    lowered = text.lower()
    uppered = text.upper()
    if "RATE_LIMITED" in uppered:
        return "Muitas tentativas em pouco tempo. Aguarde um pouco e tente novamente."
    if "UNAUTHORIZED" in uppered:
        return "Nao foi possivel validar o acesso. Confira sua license key."
    if "FORBIDDEN" in uppered:
        return "Solicitacao recusada pelo servidor."
    if "BAD_REQUEST" in uppered:
        return "Os dados enviados nao foram aceitos. Confira e tente novamente."
    if "SERVER_ERROR" in uppered:
        return "Servidor indisponivel no momento. Tente novamente em instantes."
    if "RECONNECT_REQUIRED" in uppered:
        return "Sua conexao precisa ser renovada. Abra novamente e cadastre sua API key."
    if "licenca revogada" in lowered:
        return "Esta license key foi revogada. Digite uma nova licenca."
    if "licenca expirada" in lowered:
        return "Esta license key expirou. Digite uma nova licenca."
    if "licenca invalida" in lowered or "http 401" in lowered:
        return "License key invalida. Confira e tente novamente."
    if "dispositivo" in lowered:
        return "Esta license key ja foi registrada em outro dispositivo."
    if "api key nao cadastrada" in lowered:
        return "API key da Tamblox ainda nao foi cadastrada para esta licenca."
    if "api_key invalida" in lowered or "api key invalida" in lowered:
        return "API key da Tamblox invalida. Confira e tente novamente."
    if "rate limit" in lowered or "http 429" in lowered:
        return "Muitas tentativas em pouco tempo. Aguarde um pouco e tente novamente."
    if "endpoint nao permitido" in lowered or "campo nao permitido" in lowered or "target host not allowed" in lowered:
        return "Solicitacao recusada pelo servidor."
    if "http 403" in lowered:
        return "Acesso recusado pelo servidor. Verifique a licenca e a API key cadastrada."
    if "timed out" in lowered or "timeout" in lowered or "urlopen error" in lowered:
        return "Nao foi possivel conectar ao servidor agora. Tente novamente em instantes."
    return text


def validate_proxy_license() -> Dict[str, Any]:
    global LICENSE_HAS_API_KEY
    if not PROXY_URL:
        return {}
    if not LICENSE_KEY:
        raise RuntimeError("Configure license_key no config.json ou TAMBLOX_LICENSE_KEY.")
    data = json.dumps({"license_key": LICENSE_KEY, "device_id": load_or_create_device_id()}).encode("utf-8")
    req = urllib.request.Request(
        f"{PROXY_URL}/license/validate",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, "X-Device-Id": load_or_create_device_id()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(error_from_json(detail, f"HTTP {e.code}")) from e
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error") or "Licenca invalida."))
    license_info = payload.get("license") if isinstance(payload, dict) else {}
    LICENSE_HAS_API_KEY = bool(isinstance(license_info, dict) and license_info.get("has_api_key"))
    return license_info if isinstance(license_info, dict) else {}


def register_proxy_api_key(api_key: str) -> None:
    global LICENSE_HAS_API_KEY
    api_key = clean_api_key(api_key)
    if not PROXY_URL or not LICENSE_KEY:
        return
    if not api_key:
        raise RuntimeError("API key obrigatoria.")
    data = json.dumps({"license_key": LICENSE_KEY, "api_key": api_key, "device_id": load_or_create_device_id()}).encode("utf-8")
    req = urllib.request.Request(
        f"{PROXY_URL}/license/api-key",
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT, "X-Device-Id": load_or_create_device_id()},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(error_from_json(detail, f"HTTP {e.code}")) from e
    if not payload.get("ok"):
        raise RuntimeError(str(payload.get("error") or "Nao foi possivel registrar API key."))
    LICENSE_HAS_API_KEY = True
    save_config_value("license_has_api_key", True)


def http_error_message(status: int, body: str = "") -> str:
    if PROXY_URL:
        if status == 401:
            return "Nao foi possivel validar o acesso."
        if status == 403:
            return "Solicitacao recusada pelo servidor."
        if status == 429:
            return "Muitas tentativas em pouco tempo."
        if status >= 500:
            return "Servidor indisponivel no momento."
        return "A solicitacao nao foi aceita."
    if status == 525:
        return "Cloudflare 525: falha temporaria de SSL entre Cloudflare e Tamblox"
    if 520 <= status <= 527:
        return f"Cloudflare {status}: site temporariamente instavel"
    return f"HTTP {status}: {strip_tags(body)[:120]}"


def looks_like_block_page(body: str) -> bool:
    raw = body.lower()
    text = strip_tags(body).lower()
    return (
        "ip bá»‹ cháº·n" in raw
        or "ip bi chan" in text
        or ("ip b" in text and "ch" in text and "blocked" not in text)
        or "ip bloqueado" in text
        or "access denied" in text
    )


def is_optional_api_error(error: Optional[Exception]) -> bool:
    if not error:
        return False
    text = str(error).lower()
    return "http 404" in text and "/products=" in text and "/api/products=" in text


def parse_money(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = html.unescape(str(value)).strip()
    text = re.sub(r"[^\d,.\-]", "", text)
    if not text:
        return None
    if "," in text and "." in text:
        text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def parse_tamblox_api_price(value: Any) -> Optional[float]:
    price = parse_money(value)
    if price is None:
        return None
    # /api/products.php returns prices in VND (ex: 5500), while the shop UI uses USD.
    if price > 100:
        return round(price / 25000.0, 4)
    return price


def parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = html.unescape(str(value))
    text = re.sub(r"[^\d]", "", text)
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None



def parse_restock_seconds(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    now = time.time()
    if isinstance(value, (int, float)):
        number = float(value)
        if number <= 0:
            return None
        if number > 1_000_000_000:
            return max(0.0, number - now)
        return number

    text = strip_tags(str(value)).lower()
    if not text:
        return None
    if re.search(r"\b(every|cada)\b", text):
        return None

    iso_match = re.search(r"\b(\d{4})-(\d{1,2})-(\d{1,2})t(\d{1,2}):(\d{2})(?::(\d{2}))?z?\b", text)
    if iso_match:
        year, month, day, hour, minute, second = iso_match.groups()
        try:
            target_time = time.mktime((
                int(year),
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                int(second or 0),
                0,
                0,
                -1,
            ))
            if text.endswith("z"):
                target_time -= time.timezone
            return max(0.0, target_time - now)
        except Exception:
            pass

    date_match = re.search(r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})(?:\s+(\d{1,2}):(\d{2})(?::(\d{2}))?)?\b", text)
    if date_match:
        year, month, day, hour, minute, second = date_match.groups()
        try:
            target_time = time.mktime((
                int(year),
                int(month),
                int(day),
                int(hour or 0),
                int(minute or 0),
                int(second or 0),
                0,
                0,
                -1,
            ))
            return max(0.0, target_time - now)
        except Exception:
            pass

    timestamp = parse_money(text)
    if timestamp and timestamp > 1_000_000_000:
        return max(0.0, timestamp - now)

    match = re.search(r"\b(\d{1,2}):(\d{2}):(\d{2})\b", text)
    if match:
        hours, minutes, seconds = (int(part) for part in match.groups())
        return float(hours * 3600 + minutes * 60 + seconds)

    match = re.search(r"\b(\d{1,2}):(\d{2})\b", text)
    if match:
        minutes, seconds = (int(part) for part in match.groups())
        return float(minutes * 60 + seconds)

    total = 0
    patterns = [
        (r"(\d+)\s*(?:d|day|days|dia|dias)", 86400),
        (r"(\d+)\s*(?:h|hour|hours|hora|horas)", 3600),
        (r"(\d+)\s*(?:m|min|mins|minute|minutes|minuto|minutos)", 60),
        (r"(\d+)\s*(?:s|sec|secs|second|seconds|seg|segundo|segundos)", 1),
    ]
    for pattern, multiplier in patterns:
        found = re.findall(pattern, text)
        if found:
            total += sum(int(value) * multiplier for value in found)
    return float(total) if total > 0 else None


def restock_at_from_value(value: Any) -> Optional[float]:
    seconds = parse_restock_seconds(value)
    if seconds is None:
        return None
    return time.time() + seconds


def first_restock_at(obj: Dict[str, Any]) -> Optional[float]:
    keys = [
        "restock",
        "restock_time",
        "restockTime",
        "next_restock",
        "nextRestock",
        "next_stock",
        "nextStock",
        "countdown",
        "timer",
        "restock_timer",
        "restockTimer",
        "restock_in",
        "restockIn",
        "restock_seconds",
        "restockSeconds",
        "timer_seconds",
        "timerSeconds",
        "countdown_seconds",
        "countdownSeconds",
        "time_left",
        "timeLeft",
        "time_left_seconds",
        "timeLeftSeconds",
    ]
    for key in keys:
        value = first_value(obj, [key])
        restock_at = restock_at_from_value(value)
        if restock_at:
            return restock_at
    return None


def extract_restock_at_from_html(fragment: str) -> Optional[float]:
    candidates = [
        r'targetTime\s*=\s*new\s+Date\(\s*["\']([^"\']+)["\']\s*\)',
        r'data-(?:countdown|timer|restock|date|time)\s*=\s*["\']([^"\']+)["\']',
        r'(?:id|class)\s*=\s*["\'][^"\']*(?:countdown|timer|restock)[^"\']*["\'][^>]*>(.*?)</[^>]+>',
        r'(?:restock|countdown|timer|next[_ -]?stock)[^>"\']*["\']?\s*[:=]\s*["\']?([^"\'<>\n]+)',
        r'(?:restock|next stock|countdown|timer)[^<]{0,80}',
        r'\b\d{1,2}:\d{2}:\d{2}\b',
        r'\b\d{1,2}:\d{2}\b',
    ]
    for pattern in candidates:
        for match in re.finditer(pattern, fragment, flags=re.I | re.S):
            value = match.group(1) if match.groups() else match.group(0)
            restock_at = restock_at_from_value(value)
            if restock_at:
                return restock_at
    return None


def fetch_global_restock_at() -> Optional[float]:
    urls = [f"{BASE_URL}/", "https://www.tamblox.net/"]
    for url in dict.fromkeys(urls):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "text/html, */*;q=0.8"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                body = resp.read().decode("utf-8", errors="replace")
            restock_at = extract_restock_at_from_html(body)
            if restock_at:
                return restock_at
        except Exception:
            continue
    return None


def global_restock_at(force: bool = False) -> Optional[float]:
    global _GLOBAL_RESTOCK_CACHE
    now = time.time()
    fetched_at, cached = _GLOBAL_RESTOCK_CACHE
    if not force and fetched_at and now - fetched_at < GLOBAL_RESTOCK_REFRESH_SECONDS:
        return cached
    try:
        cached = fetch_global_restock_at()
    except Exception:
        cached = None
    _GLOBAL_RESTOCK_CACHE = (now, cached)
    return cached


def apply_global_restock_timer(products: List[Product]) -> None:
    restock_at = global_restock_at()
    if not restock_at:
        return
    for product in products:
        if not product.has_stock and not product.restock_at:
            product.restock_at = restock_at


def first_value(obj: Dict[str, Any], keys: Iterable[str]) -> Any:
    lowered = {str(k).lower(): v for k, v in obj.items()}
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
        lk = key.lower()
        if lk in lowered and lowered[lk] not in (None, ""):
            return lowered[lk]
    return None


def walk_dicts(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for item in value:
            yield from walk_dicts(item)


def products_from_api_json(data: Any) -> List[Product]:
    products: List[Product] = []
    seen = set()
    categories = data.get("categories") if isinstance(data, dict) else None
    if isinstance(categories, list):
        for category_item in categories:
            if not isinstance(category_item, dict):
                continue
            category = str(first_value(category_item, ["name", "category", "category_name"]) or "").strip()
            category_products = category_item.get("products")
            if not isinstance(category_products, list):
                continue
            for item in category_products:
                if not isinstance(item, dict):
                    continue
                pid = first_value(item, ["id", "product_id", "productId"])
                name = first_value(item, ["name", "title", "product_name", "productName"])
                if pid in (None, "") or not name:
                    continue
                key = str(pid)
                if key in seen:
                    continue
                seen.add(key)
                price = parse_tamblox_api_price(first_value(item, ["price", "sale_price", "salePrice", "money", "gia"]))
                stock = parse_int(first_value(item, ["amount", "stock", "quantity", "qty", "available", "amount_available", "soluong"]))
                option_id = first_value(item, ["option_id", "optionId", "variant_id", "variantId"]) or ""
                products.append(Product(str(pid), str(name).strip(), price, stock, str(option_id), category, item, restock_at=first_restock_at(item)))
        if products:
            return products

    for item in walk_dicts(data):
        if isinstance(item.get("products"), list):
            continue
        pid = first_value(item, ["id", "product_id", "productId"])
        name = first_value(item, ["name", "title", "product_name", "productName"])
        if pid in (None, "") or not name:
            continue
        if first_value(item, ["price", "sale_price", "salePrice", "money", "gia"]) in (None, "") and first_value(item, ["stock", "quantity", "qty", "available", "amount_available", "soluong"]) in (None, ""):
            continue
        key = str(pid)
        if key in seen:
            continue
        seen.add(key)
        price = parse_tamblox_api_price(first_value(item, ["price", "sale_price", "salePrice", "money", "gia"]))
        stock = parse_int(first_value(item, ["amount", "stock", "quantity", "qty", "available", "amount_available", "soluong"]))
        option_id = first_value(item, ["option_id", "optionId", "variant_id", "variantId"]) or ""
        category = first_value(item, ["category", "category_name", "categoryName"]) or ""
        products.append(Product(str(pid), str(name).strip(), price, stock, str(option_id), str(category), item, restock_at=first_restock_at(item)))
    return products


def fetch_products_api(api_key: str) -> List[Product]:
    errors = []
    for path in ("/api/products.php", "/products", "/api/products"):
        status, ctype, body = request(f"{BASE_URL}{path}", "GET", {"api_key": api_key})
        if status >= 400:
            errors.append(f"{path}={http_error_message(status, body)}")
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError as e:
            errors.append(f"{path}=JSON invalido: {e}")
            continue
        products = products_from_api_json(data)
        if products:
            return products
        errors.append(f"{path}=sem produtos reconhecidos")
    raise RuntimeError("; ".join(errors))


def apply_api_price_overrides(products: List[Product]) -> None:
    if not USE_API_PRICE_OVERRIDES:
        return
    for product in products:
        price = API_PRICE_OVERRIDES.get(str(product.id))
        if price is not None:
            product.price = price


def product_from_api_product_item(item: Dict[str, Any]) -> Optional[Product]:
    pid = first_value(item, ["id", "product_id", "productId"])
    name = first_value(item, ["name", "title", "product_name", "productName"])
    if pid in (None, "") or not name:
        return None
    stock = parse_int(first_value(item, ["amount", "stock", "quantity", "qty", "available", "amount_available", "soluong"]))
    category = first_value(item, ["category", "category_name", "categoryName"]) or ""
    price = parse_tamblox_api_price(first_value(item, ["price", "sale_price", "salePrice", "money", "gia"]))
    return Product(
        id=str(pid),
        name=str(name).strip(),
        price=price,
        stock=stock,
        category=str(category),
        raw={"api_product": item},
        restock_at=first_restock_at(item),
    )


def fetch_product_api(api_key: str, product_id: str) -> Optional[Product]:
    status, ctype, body = request(f"{BASE_URL}/api/product.php", "GET", {"api_key": api_key, "product": product_id}, timeout=12)
    if status >= 400:
        raise RuntimeError(f"/api/product.php={http_error_message(status, body)}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"/api/product.php=JSON invalido: {e}")
    products = data.get("product") if isinstance(data, dict) else None
    if isinstance(products, dict):
        products = [products]
    if not isinstance(products, list) or not products:
        return None
    for item in products:
        if isinstance(item, dict):
            product = product_from_api_product_item(item)
            if product:
                return product
    return None


def fetch_product_restock_at(product_id: str) -> Optional[float]:
    status, ctype, body = request(f"{BASE_URL}/ajaxs/client/modal/view-product.php", "GET", {"id": product_id}, timeout=12)
    if status >= 400:
        raise RuntimeError(f"modal produto {product_id}: {http_error_message(status, body)}")
    return extract_restock_at_from_html(body)


def extract_view_price_from_html(body: str) -> Optional[float]:
    block = re.search(r'class=["\']view-price["\'][^>]*>(.*?)</h3>', body, flags=re.I | re.S)
    if block:
        prices = re.findall(r"<span>\s*\$?([^<]+)</span>", block.group(1), flags=re.I | re.S)
        if prices:
            return parse_money(prices[-1])
    prices = re.findall(r"<span>\s*\$?([^<]+)</span>", body, flags=re.I | re.S)
    return parse_money(prices[-1]) if prices else None


def fetch_product_modal_price(product_id: str) -> Optional[float]:
    status, ctype, body = request(
        f"{BASE_URL}/ajaxs/client/modal/view-product.php",
        "GET",
        {"id": product_id},
        timeout=12,
        throttle=False,
    )
    if status >= 400:
        return None
    return extract_view_price_from_html(body)


def needs_modal_price(product: Product) -> bool:
    return bool(product.id) and product.price is not None and product.price > 100


def enrich_modal_prices(products: List[Product]) -> None:
    targets = [product for product in products if needs_modal_price(product)]
    if not targets:
        return

    def load_price(product: Product) -> Tuple[str, Optional[float]]:
        try:
            return product.id, fetch_product_modal_price(product.id)
        except Exception:
            return product.id, None

    workers = max(1, min(PRICE_ENRICH_WORKERS, len(targets)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(load_price, product) for product in targets]
        prices = {pid: price for pid, price in (future.result() for future in as_completed(futures)) if price is not None}
    for product in targets:
        if product.id in prices:
            product.price = prices[product.id]


def refresh_product_restock_timer(product: Product) -> None:
    if not product.id or product.has_stock:
        return
    now = time.time()
    cached = _RESTOCK_TIMER_CACHE.get(product.id)
    if cached and now - cached[0] < RESTOCK_TIMER_REFRESH_SECONDS:
        product.restock_at = cached[1]
        return
    try:
        restock_at = fetch_product_restock_at(product.id)
    except Exception:
        restock_at = None
    _RESTOCK_TIMER_CACHE[product.id] = (now, restock_at)
    product.restock_at = restock_at


def fetch_target_products_api(api_key: str, targets: List[Target]) -> List[Product]:
    products: List[Product] = []
    seen = set()
    for target in targets:
        if target.bought or not target.product_id:
            continue
        product_id = str(target.product_id)
        if product_id in seen:
            continue
        seen.add(product_id)
        product = fetch_product_api(api_key, product_id)
        if product:
            refresh_product_restock_timer(product)
            products.append(product)
    return products


def strip_tags(value: str) -> str:
    value = re.sub(r"<script\b[^<]*(?:(?!</script>)<[^<]*)*</script>", "", value, flags=re.I)
    value = re.sub(r"<style\b[^<]*(?:(?!</style>)<[^<]*)*</style>", "", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def fetch_products_public() -> List[Product]:
    status, ctype, body = request(f"{BASE_URL}/ajaxs/client/load_products.php", "GET", {"type": "categories"})
    if status >= 400:
        raise RuntimeError(f"Listagem publica: {http_error_message(status, body)}")
    if looks_like_block_page(body):
        raise TambloxBlockedError("Tamblox bloqueou o IP desta conexao")
    products: List[Product] = []
    starts = [m.start() for m in re.finditer(r'<div class="feature-content"', body, flags=re.I)]
    cards = [body[start:(starts[i + 1] if i + 1 < len(starts) else len(body))] for i, start in enumerate(starts)]
    for card in cards:
        button = re.search(r'data-id=["\'](\d+)["\']|openModal_\s*(\d+)|openModal\(`[^`]*`,\s*`(\d+)`', card, flags=re.I)
        pid = next((g for g in button.groups() if g), "") if button else ""
        name_match = re.search(r'class="feature-name".*?<a[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', card, flags=re.I | re.S)
        if not pid or not name_match:
            continue
        stock_match = re.search(r"Stock:\s*<b>(.*?)</b>", card, flags=re.I | re.S)
        price_block = re.search(r'class="feature-price"[^>]*>(.*?)</h6>', card, flags=re.I | re.S)
        prices = re.findall(r"<span>\s*\$?([^<]+)</span>", price_block.group(1), flags=re.I | re.S) if price_block else []
        products.append(
            Product(
                id=pid,
                name=strip_tags(name_match.group(2)),
                price=parse_money(prices[-1]) if prices else None,
                stock=parse_int(stock_match.group(1)) if stock_match else None,
                raw={"url": name_match.group(1)},
                restock_at=extract_restock_at_from_html(card),
            )
        )
    if not products:
        raise RuntimeError("Listagem publica: nenhum card de produto foi retornado")
    return products


def sitemap_product_urls() -> List[str]:
    status, ctype, body = request(f"{BASE_URL}/sitemap.xml", "GET")
    if status >= 400:
        raise RuntimeError(f"sitemap.xml: {http_error_message(status, body)}")
    urls = []
    for match in re.finditer(r"<loc>(.*?)</loc>", body, flags=re.I | re.S):
        loc = html.unescape(match.group(1)).strip()
        if "/product/" not in loc:
            continue
        parsed = urllib.parse.urlparse(loc)
        path = parsed.path
        urls.append(BASE_URL + path)
    return sorted(set(urls))


def parse_product_page(body: str, url: str) -> Optional[Product]:
    pid_match = re.search(r'id=["\']product_id["\']\s+value=["\']([^"\']+)["\']', body, flags=re.I)
    if not pid_match:
        pid_match = re.search(r"openModal\(`[^`]*`,\s*`(\d+)`", body, flags=re.I)
    title_match = re.search(r"<title>(.*?)\s*(?:\||</title>)", body, flags=re.I | re.S)
    name = strip_tags(title_match.group(1)) if title_match else ""
    if not pid_match or not name:
        return None
    stock_match = re.search(r"Stock:\s*(?:<[^>]+>\s*)*<strong>(.*?)</strong>", body, flags=re.I | re.S)
    if not stock_match:
        stock_match = re.search(r"Stock:\s*(?:<[^>]+>\s*)*<b>(.*?)</b>", body, flags=re.I | re.S)
    price_match = re.search(r'class=["\'](?:details-price|view-price|feature-price)["\'][^>]*>(.*?)</h[36]>', body, flags=re.I | re.S)
    prices = re.findall(r"<span>\s*\$?([^<]+)</span>", price_match.group(1), flags=re.I | re.S) if price_match else []
    return Product(
        id=str(pid_match.group(1)).strip(),
        name=name,
        price=parse_money(prices[-1]) if prices else None,
        stock=parse_int(stock_match.group(1)) if stock_match else None,
        raw={"url": url},
        restock_at=extract_restock_at_from_html(body),
    )


def fetch_products_sitemap(force: bool = False, exclude_paths: Optional[set] = None) -> List[Product]:
    global _SITEMAP_CACHE
    now = time.time()
    cached_at, cached_products = _SITEMAP_CACHE
    if cached_products and not force and now - cached_at < SITEMAP_REFRESH_SECONDS:
        return cached_products
    products: List[Product] = []
    urls = sitemap_product_urls()
    if exclude_paths:
        urls = [url for url in urls if urllib.parse.urlparse(url).path not in exclude_paths]

    def load_one(url: str) -> Optional[Product]:
        try:
            status, ctype, body = request(url, "GET", timeout=6)
            if status >= 400:
                return None
            return parse_product_page(body, url)
        except Exception:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(load_one, url) for url in urls]
        for future in as_completed(futures):
            product = future.result()
            if product:
                products.append(product)

    if products:
        _SITEMAP_CACHE = (now, products)
    return products


def merge_products(groups: Iterable[List[Product]], include_auto_target: bool = True) -> List[Product]:
    merged: Dict[str, Product] = {}
    order: List[str] = []
    for group in groups:
        for product in group:
            if should_hide_product(product):
                continue
            key = f"{product.store}:{product.id or product.name.lower()}"
            if key not in merged:
                merged[key] = product
                order.append(key)
                continue
            current = merged[key]
            if current.stock in (None, 0) and product.stock not in (None, 0):
                current.stock = product.stock
            elif current.stock is None and product.stock is not None:
                current.stock = product.stock
            if current.price is None and product.price is not None:
                current.price = product.price
            elif product.price is not None and current.price is not None and current.price > 100 and product.price < 100:
                current.price = product.price
            if len(product.name) > len(current.name):
                current.name = product.name
            if not current.option_id and product.option_id:
                current.option_id = product.option_id
            if not current.category and product.category:
                current.category = product.category
            if not current.restock_at and product.restock_at:
                current.restock_at = product.restock_at
    products = [merged[k] for k in order]
    has_kitsune_inventory = any(is_kitsune_inventory_name(p.name) for p in products)
    if include_auto_target and products and not has_kitsune_inventory:
        products.append(
            Product(
                id="",
                name="Kitsune Inventory",
                price=1.80,
                stock=0,
                category="Kitsune Inventory",
                raw={"manual": True},
                auto_target="kitsune_inventory",
            )
        )
    return sorted(products, key=product_sort_key)


def supplement_kitsune_from_web(products: List[Product]) -> Tuple[List[Product], bool]:
    real_products = [p for p in products if not p.auto_target]
    if not SUPPLEMENT_KITSUNE_WEB or any(is_kitsune_inventory_name(p.name) for p in real_products):
        return products, False
    try:
        web_products = [p for p in fetch_products_public() if is_kitsune_inventory_name(p.name)]
    except Exception:
        return products, False
    if not web_products:
        return products, False
    merged = merge_products([real_products, web_products])
    return merged, True


def product_sort_key(product: Product) -> Tuple[int, int, str]:
    name = product_title(product.name).lower()
    if product.auto_target == "kitsune_inventory" or is_kitsune_inventory_name(product.name):
        priority = 0
    elif "t-rex inventory" in name or "t_rex inventory" in name:
        priority = 1
    elif "tiger inventory" in name:
        priority = 2
    elif "yeti inventory" in name:
        priority = 3
    elif "gas inventory" in name:
        priority = 4
    elif "lightning inventory" in name:
        priority = 5
    elif "kitsune" in name:
        priority = 6
    else:
        priority = 7
    stock_rank = 0 if product.has_stock else 1
    return priority, stock_rank, name


def fetch_products(api_key: str) -> Tuple[List[Product], str]:
    global _API_SKIP_UNTIL
    api_products: List[Product] = []
    public_products: List[Product] = []
    sitemap_products: List[Product] = []
    api_error = None
    public_error = None
    sitemap_error = None

    if USE_API_PRODUCTS and time.time() >= _API_SKIP_UNTIL:
        try:
            api_products = fetch_products_api(api_key)
            apply_api_price_overrides(api_products)
        except Exception as e:
            api_error = e
            _API_SKIP_UNTIL = time.time() + API_RETRY_SECONDS

    if not SITE_FALLBACK:
        products = merge_products([api_products])
        if products:
            products, added_kitsune = supplement_kitsune_from_web(products)
            apply_global_restock_timer(products)
            return products, "API products.php + Kitsune WEB" if added_kitsune else "API products.php"
        if api_error:
            raise RuntimeError(f"API products.php indisponivel: {api_error}")
        raise RuntimeError("API products.php nao retornou produtos.")

    try:
        public_products = fetch_products_public()
    except Exception as e:
        public_error = e
        public_products = []
    if isinstance(public_error, TambloxBlockedError):
        raise public_error

    try:
        public_paths = {
            urllib.parse.urlparse(str(p.raw.get("url"))).path
            for p in public_products
            if p.raw and p.raw.get("url")
        }
        sitemap_products = fetch_products_sitemap(exclude_paths=public_paths)
    except Exception as e:
        sitemap_error = e
        sitemap_products = []

    products = merge_products([api_products, public_products, sitemap_products])
    enrich_modal_prices(products)
    if products:
        apply_global_restock_timer(products)
        parts = []
        if api_products:
            parts.append("API")
        if public_products:
            parts.append("WEB")
        if sitemap_products:
            parts.append("SITEMAP")
        if api_error and not api_products and not is_optional_api_error(api_error):
            parts.append("API indisponivel")
        return products, " + ".join(parts)

    for error in (public_error, sitemap_error):
        if isinstance(error, TambloxBlockedError):
            raise error
    errors = [str(e) for e in (public_error, sitemap_error) if e]
    if api_error and not is_optional_api_error(api_error):
        errors.append(str(api_error))
    if errors:
        raise RuntimeError("Nao foi possivel carregar produtos reais: " + " | ".join(errors))
    raise RuntimeError("Nenhuma fonte retornou produtos reais.")


def fetch_products_fast() -> Tuple[List[Product], str]:
    public_error = None
    try:
        public_products = fetch_products_public()
    except Exception as e:
        public_error = e
        public_products = []
    cached_products = _SITEMAP_CACHE[1]
    products = merge_products([public_products, cached_products])
    source = "SITE"
    if cached_products:
        source += " + OCULTOS cache"
    if public_error:
        if products:
            source += " + Cloudflare instavel"
        else:
            raise RuntimeError(str(public_error))
    apply_global_restock_timer(products)
    return products, source


def fetch_products_fast_api(api_key: str) -> Tuple[List[Product], str]:
    products = fetch_products_api(api_key)
    apply_api_price_overrides(products)
    merged = merge_products([products])
    apply_global_restock_timer(merged)
    return merged, "API products.php"


def fetch_target_products_fast(api_key: str, targets: List[Target]) -> Tuple[List[Product], str]:
    api_products: List[Product] = []
    public_products: List[Product] = []
    api_error = None
    public_error = None
    needs_public = any((not t.bought) and not t.product_id for t in targets)

    try:
        api_products = fetch_target_products_api(api_key, targets)
        apply_api_price_overrides(api_products)
    except Exception as e:
        api_error = e

    if not SITE_FALLBACK:
        if api_products:
            products = merge_products([api_products])
            return products, "API produto"
        if api_error:
            raise RuntimeError(f"API produto instavel: {api_error}")
        return [], "API produto"

    if needs_public:
        try:
            public_products = fetch_products_public()
        except Exception as e:
            public_error = e
            public_products = []

    cached_products = _SITEMAP_CACHE[1]
    products = merge_products([api_products, public_products, cached_products])
    if products:
        apply_global_restock_timer(products)
        parts = []
        if api_products:
            parts.append("API produto")
        if public_products:
            parts.append("SITE")
        if cached_products:
            parts.append("OCULTOS cache")
        if api_error and not api_products:
            parts.append("API produto instavel")
        if public_error and not public_products:
            parts.append("SITE instavel")
        return products, " + ".join(parts)

    errors = [str(e) for e in (api_error, public_error) if e]
    if errors:
        raise RuntimeError("Nao foi possivel carregar alvos: " + " | ".join(errors))
    return products, "API produto"


def pending_targets(targets: List[Target]) -> List[Target]:
    return [target for target in targets if not target.bought]


def should_fetch_targets_individually(targets: List[Target]) -> bool:
    pending = pending_targets(targets)
    ids = {str(target.product_id) for target in pending if target.product_id}
    if not ids:
        return False
    if any(not target.product_id for target in pending):
        return False
    return len(ids) <= TARGET_API_LIMIT


def fetch_monitor_products(api_key: str, targets: List[Target]) -> Tuple[List[Product], str]:
    if should_fetch_targets_individually(targets):
        return fetch_target_products_fast(api_key, targets)
    if not SITE_FALLBACK:
        return fetch_products_fast_api(api_key)
    return fetch_products_fast()


def needs_hidden_refresh(targets: List[Target]) -> bool:
    if not SITE_FALLBACK:
        return False
    cached_products = _SITEMAP_CACHE[1]
    cached_zero_ids = {p.id for p in cached_products if p.stock in (None, 0)}
    for target in targets:
        if target.bought:
            continue
        if target.store != "tamblox":
            continue
        if target.product_id and target.product_id in cached_zero_ids:
            return True
        if not target.product_id and target.name_contains:
            return True
    return False


def print_products(products: List[Product], source: str) -> None:
    clear()
    banner()
    width = terminal_width()
    in_stock = sum(1 for p in products if p.has_stock)
    waiting = len(products) - in_stock
    print(f"{C.BLOOD}{C.BOLD}Escolha os produtos{C.RESET} {C.BLOOD}({len(products)} itens | {in_stock} com estoque | {waiting} aguardando | fonte: {source_label(source)}){C.RESET}")
    print(rule("-", C.BLOOD))

    if is_mobile_controller():
        for i, p in enumerate(products, 1):
            stock_value = p.stock_text if p.has_stock else "0"
            status_text = "ESTOQUE" if p.has_stock else "SEM"
            status_color = C.GREEN if p.has_stock else C.BLOOD
            name = short_text(compact_product_title(p.name), max(18, width - 8))
            meta = f"{status_text} | qtd {stock_value} | {p.price_text}"
            restock = restock_text(p)
            if restock not in ("-", "...") and visible_len(meta) + visible_len(restock) + 3 <= max(18, width - 4):
                meta += f" | {restock}"
            print(f"{C.BLOOD}{i:>2}{C.RESET} {status_color}{name}{C.RESET}")
            print(f"   {C.WHITE}{meta}{C.RESET}")
        print(rule("-", C.BLOOD))
        print(f"\n{C.BLOOD}Como escolher:{C.RESET} digite os numeros separados por virgula. Exemplo: 1,4,7")
        print(f"{C.BLOOD}Intervalo:{C.RESET} tambem aceita faixa. Exemplo: 2-5")
        print(f"{C.BLOOD}Sem estoque:{C.RESET} pode selecionar; o bot fica aguardando voltar.")
        return

    print(f"{C.BLOOD}{'N':>3}  {'LOJA':<8} {'STATUS':<12} {'ESTOQUE':>7} {'RESTOCK':>8} {'PRECO':>10}  PRODUTO{C.RESET}")
    print(rule("-", C.BLOOD))
    for i, p in enumerate(products, 1):
        name = compact_product_title(p.name)
        inline_width = max(18, width - 62)
        show_inline_name = visible_len(name) <= inline_width
        inline_name = name if show_inline_name else ""
        stock_value = p.stock_text if p.has_stock else "0"
        if p.has_stock:
            status_text = "EM ESTOQUE"
            status_color = C.GREEN
        else:
            status_text = "SEM ESTOQUE"
            status_color = C.BLOOD
        print(
            f"{C.BLOOD}{i:>3}{C.RESET}  "
            f"{C.WHITE}{p.store.upper():<8}{C.RESET} "
            f"{status_color}{status_text:<12}{C.RESET} "
            f"{C.WHITE}{stock_value:>7}{C.RESET} "
            f"{C.WHITE}{restock_text(p):>8}{C.RESET} "
            f"{C.WHITE}{p.price_text:>10}{C.RESET}  "
            f"{C.WHITE}{inline_name}{C.RESET}"
        )
        if not show_inline_name:
            for line in wrapped_lines(" " * 48 + "Nome: ", name, width, C.WHITE):
                print(line)

    print(f"\n{C.BLOOD}Como escolher:{C.RESET} digite os numeros separados por virgula. Exemplo: 1,4,7")
    print(f"{C.BLOOD}Intervalo:{C.RESET} tambem aceita faixa. Exemplo: 2-5")
    print(f"{C.BLOOD}Sem estoque:{C.RESET} pode selecionar; o bot fica aguardando voltar.")


def parse_selection(text: str, total: int) -> List[int]:
    result = []
    for part in re.split(r"\s*,\s*", text.strip()):
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            for n in range(int(start), int(end) + 1):
                if 1 <= n <= total and n not in result:
                    result.append(n)
        else:
            n = int(part)
            if 1 <= n <= total and n not in result:
                result.append(n)
    return result


def ask_quantity(label: str) -> int:
    while True:
        text = input(f"{C.BLOOD}Quantidade para {C.BOLD}{short_text(product_title(label), 58)}{C.RESET}{C.BLOOD}: {C.RESET}").strip()
        try:
            qty = int(text)
            if qty > 0:
                return qty
        except ValueError:
            pass
        print(f"{C.RED}Informe um numero inteiro maior que zero.{C.RESET}")


def choose_targets(products: List[Product]) -> List[Target]:
    global _SELECTED_PRODUCTS_CACHE
    targets: List[Target] = []
    selected_products: List[Product] = []
    while True:
        raw = input(f"\n{C.BLOOD}{C.BOLD}Numeros dos produtos{C.RESET}{C.BLOOD} (ex: 1,2,5): {C.RESET}").strip()
        if not raw:
            continue
        cleaned = raw.strip(" ,")
        if cleaned:
            try:
                indexes = parse_selection(cleaned, len(products))
            except Exception:
                print(f"{C.RED}Selecao invalida.{C.RESET}")
                continue
            for idx in indexes:
                p = products[idx - 1]
                selected_products.append(p)
                qty = ask_quantity(p.name)
                if p.auto_target == "kitsune_inventory":
                    targets.append(Target(label="Kitsune Inventory", quantity=qty, name_contains="kitsune inventory", price_min=1.80, price_max=2.20, store=p.store))
                elif p.id:
                    targets.append(Target(label=p.name, product_id=p.id, option_id=p.option_id, quantity=qty, store=p.store))
                else:
                    targets.append(Target(label=p.name, quantity=qty, name_contains=product_title(p.name).lower(), price_equals=p.price, store=p.store))
        if targets:
            _SELECTED_PRODUCTS_CACHE = selected_products
            return targets


def print_targets(targets: List[Target]) -> None:
    width = terminal_width()
    print(f"{C.BLOOD}{C.BOLD}Alvos selecionados{C.RESET}")
    print(rule("-", C.BLOOD))
    print(f"{C.BLOOD}{'N':>2}  {'LOJA':<8} {'QTD':>4}  {'PRECO':>10}  PRODUTO{C.RESET}")
    print(rule("-", C.BLOOD))
    for i, target in enumerate(targets, 1):
        if target.price_min is not None and target.price_max is not None:
            price = f"${target.price_min:.2f}-${target.price_max:.2f}"
        elif target.price_equals is None:
            price = "-"
        else:
            price = f"${target.price_equals:.2f}"
        label = compact_product_title(clean_target_label(target.label))
        inline_width = max(18, width - 28)
        show_inline_label = visible_len(label) <= inline_width
        inline_label = label if show_inline_label else ""
        print(f"{C.BLOOD}{i:>2}{C.RESET}  {C.WHITE}{target.store.upper():<8}{C.RESET} {C.WHITE}{target.quantity:>4}{C.RESET}  {C.WHITE}{price:>10}{C.RESET}  {C.WHITE}{inline_label}{C.RESET}")
        if not show_inline_label:
            for line in wrapped_lines(" " * 18 + "Produto: ", label, width, C.WHITE):
                print(line)
    print(rule("-", C.BLOOD))


def find_target_product(target: Target, products: List[Product], require_stock: bool = True) -> Optional[Product]:
    if target.product_id:
        for p in products:
            if p.store == target.store and str(p.id) == str(target.product_id) and (p.has_stock or not require_stock):
                return p
        return None
    needle = (target.name_contains or "").lower()
    if not needle:
        return None
    for p in products:
        if p.store != target.store:
            continue
        if require_stock and not p.has_stock:
            continue
        if p.auto_target and require_stock:
            continue
        if needle == "kitsune inventory" and not is_kitsune_inventory_name(p.name):
            continue
        pname = product_title(p.name).lower()
        if needle not in pname and pname not in needle:
            continue
        if target.price_equals is not None:
            if p.price is None or abs(p.price - target.price_equals) > 0.001:
                continue
        if target.price_min is not None or target.price_max is not None:
            if p.price is None:
                continue
            if target.price_min is not None and p.price < target.price_min - 0.001:
                continue
            if target.price_max is not None and p.price > target.price_max + 0.001:
                continue
        return p
    return None


def purchase_quantity(target: Target, product: Product) -> int:
    if product.stock is None:
        return target.quantity
    return max(1, min(target.quantity, product.stock))


def seconds_until_restock(product: Optional[Product]) -> Optional[float]:
    if not product or not product.restock_at:
        return None
    return max(0.0, product.restock_at - time.time())


def format_duration(seconds: float) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def restock_text(product: Product) -> str:
    if product.has_stock:
        return "-"
    remaining = seconds_until_restock(product)
    if remaining is None:
        return "..."
    return format_duration(remaining)


def format_clock(timestamp: float) -> str:
    return time.strftime("%H:%M", time.localtime(timestamp))


def restock_poll_delay(products: List[Product], targets: List[Target], default_interval: float) -> Tuple[float, str]:
    restocks: List[Tuple[float, Target, Product]] = []
    waiting_timer: List[str] = []
    for target in targets:
        if target.bought:
            continue
        product = find_target_product(target, products, require_stock=False)
        remaining = seconds_until_restock(product)
        if remaining is not None:
            restocks.append((remaining, target, product))
        elif product and not product.has_stock:
            waiting_timer.append(product_title(product.name or target.label))
    if not restocks:
        if waiting_timer:
            name = short_text(waiting_timer[0], 36)
            return max(default_interval, RESTOCK_TIMER_REFRESH_SECONDS), f"Sem estoque. Aguardando cronometro de restock aparecer para {name}."
        return default_interval, ""

    remaining, target, product = min(restocks, key=lambda item: item[0])
    name = short_text(product_title(product.name or target.label), 36)
    if remaining <= RESTOCK_READY_SECONDS:
        enable_restock_ready_mode(remaining + 8)
        return RESTOCK_READY_REQUEST_INTERVAL, f"Restock iminente: {name} em {format_duration(remaining)}. Modo compra rapida ligado."
    if remaining <= 8:
        return max(default_interval, MIN_REQUEST_INTERVAL), f"Restock perto: {name} em {format_duration(remaining)}. Procurando com limite seguro."
    if remaining <= 30:
        return max(default_interval, MIN_REQUEST_INTERVAL), f"Restock chegando: {name} em {format_duration(remaining)}."
    delay = max(default_interval, remaining - RESTOCK_PREPARE_SECONDS)
    clock = format_clock(product.restock_at) if product.restock_at else "?"
    return delay, f"Sem estoque. Proximo stock {clock} ({format_duration(remaining)}) para {name}."


def buy_product(api_key: str, product: Product, quantity: int, target: Target) -> Tuple[bool, str]:
    option_id = target.option_id or product.option_id
    fields = {
        "action": "buyProduct",
        "id": product.id,
        "amount": quantity,
        "quantity": quantity,
        "option_id": option_id,
        "songay_dichvu": "",
        "yeucau_dichvu": "",
        "coupon": "",
        "api_key": api_key,
    }
    responses = []
    for path in ("/buy_product", "/api/buy_product"):
        status, ctype, body = request(f"{BASE_URL}{path}", "POST", fields, timeout=20)
        responses.append((path, status, body))
        if status < 400:
            break
        if status in (429,) or 520 <= status <= 527:
            break
    path, status, body = responses[-1]
    if status >= 400:
        return False, http_error_message(status, body)
    try:
        data = json.loads(body)
        msg = data.get("msg") or data.get("message") or body
        ok = str(data.get("status", "")).lower() in ("success", "ok", "true") or bool(data.get("trans_id"))
        return ok, json.dumps(data, ensure_ascii=False)
    except Exception:
        ok = 200 <= status < 300 and "success" in body.lower()
        return ok, body[:1000]


def clear_status_lines(count: int) -> None:
    if count <= 0:
        return
    for _ in range(count):
        print("\033[F\033[2K", end="")


def monitor_line(label: str, value: str, color: str = "") -> str:
    return f"{C.BLOOD}{label:<10}{C.RESET} {color or C.BLOOD}{value}{C.RESET}"


def render_monitor_status(
    targets: List[Target],
    attempt: int,
    source: str,
    elapsed: float,
    last_event: str,
    frame: int = 0,
    next_tick: Optional[float] = None,
) -> List[str]:
    width = terminal_width()
    bought = [t for t in targets if t.bought]
    pending = [t for t in targets if not t.bought]
    total_units = sum(max(0, target.quantity) for target in targets)
    bought_units = sum(max(0, target.bought_quantity or (target.quantity if target.bought else 0)) for target in targets)
    spinner = "|/-\\"[(attempt + frame) % 4]
    bar = progress_bar(len(bought), len(targets))

    lines = [
        rule("=", C.BLOOD),
        f"{C.BLOOD}{C.BOLD}MONITOR TAMBLOX{C.RESET} {spinner} {C.BLOOD}{time.strftime('%H:%M:%S')}{C.RESET}",
        rule("-", C.BLOOD),
        f"{monitor_line('Tentativa', str(attempt), C.WHITE)}   {monitor_line('Fonte', source_label(source), C.WHITE)}   {monitor_line('Resposta', f'{elapsed:.1f}s', C.WHITE)}",
    ]
    lines.append(monitor_line("Alvos", f"[{bar}] {len(bought)}/{len(targets)} finalizados", C.WHITE))
    lines.append(monitor_line("Unidades", f"{bought_units}/{total_units} compradas", C.WHITE))
    if pending:
        if next_tick is None:
            wait_text = "varrendo estoque"
        elif next_tick >= 60:
            wait_text = f"modo espera, volta em {format_duration(next_tick)}"
        else:
            wait_text = f"proxima busca em {next_tick:.1f}s"
        lines.append(monitor_line("Scan", f"[{scan_bar(frame)}] {wait_text}", C.WHITE))
    if last_event:
        color = C.GREEN if "comprado" in last_event.lower() else C.WHITE
        lines.append(monitor_line("Aviso", short_text(clean_target_label(last_event), width - 16), color))

    lines.append(rule("-", C.BLOOD))
    lines.append(f"{C.BLOOD}{'STATUS':<11} {'QTD':>7}  PRODUTO{C.RESET}")
    for target in targets:
        if target.bought:
            status = f"{C.GREEN}{C.BOLD}COMPRADO{C.RESET}"
            qty_text = f"{target.bought_quantity or target.quantity}/{target.quantity}"
        else:
            status = f"{C.BLOOD}{C.BOLD}BUSCANDO {C.RESET}"
            qty_text = str(target.quantity)
        label = compact_product_title(clean_target_label(target.label))
        inline_width = max(18, width - 31)
        show_inline_label = visible_len(label) <= inline_width
        inline_label = label if show_inline_label else ""
        lines.append(f"{status:<20} {C.WHITE}{qty_text:>7}{C.RESET}  {C.WHITE}{inline_label}{C.RESET}")
        if not show_inline_label:
            lines.extend(wrapped_lines(" " * 21 + "Produto: ", label, width, C.WHITE))

    if pending:
        searching = ", ".join(compact_product_title(clean_target_label(t.label)) for t in pending[:3])
        if len(pending) > 3:
            searching += f" +{len(pending) - 3}"
        lines.append(rule("-", C.BLOOD))
        lines.extend(wrapped_lines(f"{C.BLOOD}Buscando{C.RESET}  ", searching, width, C.WHITE))
    else:
        lines.append(rule("-", C.BLOOD))
        lines.append(monitor_line("Buscando", "nenhum produto pendente", C.GREEN))
    return lines


def animated_monitor_wait(
    targets: List[Target],
    attempt: int,
    source: str,
    elapsed: float,
    last_event: str,
    sleep_for: float,
    status_lines: int,
) -> int:
    if sleep_for <= 0:
        return status_lines
    started = time.time()
    frame = 0
    while True:
        remaining = sleep_for - (time.time() - started)
        if remaining <= 0:
            break
        clear_status_lines(status_lines)
        lines = render_monitor_status(
            targets,
            attempt,
            source,
            elapsed,
            last_event,
            frame=frame,
            next_tick=max(0.0, remaining),
        )
        print("\n".join(lines), flush=True)
        status_lines = len(lines)
        time.sleep(min(0.25, remaining))
        frame += 1
    return status_lines


def monitor(api_key: str, targets: List[Target], interval: float) -> None:
    attempt = 0
    status_lines = 0
    last_event = ""
    last_full_refresh = time.time()
    error_streak = 0
    buy_fail_streak = 0
    source = "iniciando"
    cached_wait_products = merge_products([_SELECTED_PRODUCTS_CACHE], include_auto_target=False)
    apply_global_restock_timer(cached_wait_products)
    while not all(t.bought for t in targets):
        cycle_started = time.time()
        sleep_delay = interval
        bought_this_cycle = False
        if cached_wait_products:
            preview_delay, preview_hint = restock_poll_delay(cached_wait_products, targets, interval)
            if preview_delay > interval:
                attempt += 1
                source = "cronometro do site"
                last_event = preview_hint
                elapsed = time.time() - cycle_started
                clear_status_lines(status_lines)
                lines = render_monitor_status(targets, attempt, source, elapsed, last_event)
                print("\n".join(lines), flush=True)
                status_lines = len(lines)
                status_lines = animated_monitor_wait(targets, attempt, source, elapsed, last_event, preview_delay, status_lines)
                cached_wait_products = []
                continue
            cached_wait_products = []
        attempt += 1
        try:
            now = time.time()
            if needs_hidden_refresh(targets) and now - last_full_refresh >= SITEMAP_REFRESH_SECONDS:
                products, source = fetch_monitor_products(api_key, targets)
                last_full_refresh = now
            else:
                products, source = fetch_monitor_products(api_key, targets)
            error_streak = 0

            for target in targets:
                if target.bought:
                    continue
                product = find_target_product(target, products)
                if not product:
                    continue
                if not target.product_id and product.id:
                    target.product_id = product.id
                    target.option_id = product.option_id
                last_event = f"Estoque encontrado: {product_title(product.name)}"
                qty = purchase_quantity(target, product)
                ok, response = buy_product(api_key, product, qty, target)
                if ok:
                    target.bought = True
                    target.bought_quantity = qty
                    bought_this_cycle = True
                    if qty < target.quantity:
                        last_event = f"O produto {product_title(product.name)} foi comprado: {qty}/{target.quantity} disponiveis. Verifique o site."
                    else:
                        last_event = f"O produto {product_title(product.name)} foi comprado. Verifique o site."
                    buy_fail_streak = 0
                else:
                    buy_fail_streak += 1
                    sleep_delay = max(sleep_delay, min(30.0, 5.0 * buy_fail_streak))
                    last_event = f"Falha ao comprar {product_title(product.name)}: {short_text(response, 70)}. Continuando monitoramento."

            if not bought_this_cycle:
                sleep_delay, restock_hint = restock_poll_delay(products, targets, interval)
                if restock_hint:
                    last_event = restock_hint

            elapsed = time.time() - cycle_started
            clear_status_lines(status_lines)
            lines = render_monitor_status(targets, attempt, source, elapsed, last_event)
            print("\n".join(lines), flush=True)
            status_lines = len(lines)
        except KeyboardInterrupt:
            clear_status_lines(status_lines)
            print(f"{C.YELLOW}Interrompido pelo usuario.{C.RESET}")
            return
        except TambloxBlockedError as e:
            sleep_delay = min(BLOCK_COOLDOWN_SECONDS, max(interval, 60.0))
            last_event = f"Tamblox bloqueou temporariamente esta conexao. Pausando {int(sleep_delay)}s."
            clear_status_lines(status_lines)
            lines = render_monitor_status(targets, attempt, "bloqueado", 0.0, last_event)
            print("\n".join(lines), flush=True)
            status_lines = len(lines)
        except Exception as e:
            error_streak += 1
            sleep_delay = min(30.0, max(interval, 2.0 * error_streak))
            last_event = f"Erro na tentativa {attempt}: {e}"
            clear_status_lines(status_lines)
            lines = render_monitor_status(targets, attempt, "erro", 0.0, last_event)
            print("\n".join(lines), flush=True)
            status_lines = len(lines)
        elapsed = time.time() - cycle_started
        if elapsed < sleep_delay:
            jitter = random.uniform(0.0, LOOP_JITTER_SECONDS) if LOOP_JITTER_SECONDS > 0 else 0.0
            status_lines = animated_monitor_wait(
                targets,
                attempt,
                source,
                elapsed,
                last_event,
                (sleep_delay - elapsed) + jitter,
                status_lines,
            )

    clear_status_lines(status_lines)
    lines = render_monitor_status(targets, attempt, "finalizado", 0.0, "Todos os produtos selecionados foram comprados. Verifique o site.")
    print("\n".join(lines), flush=True)
    print(f"\n{C.GREEN}{C.BOLD}Todos os alvos foram processados.{C.RESET}")


def split_api_key_candidates(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[\s,;]+", str(value))
    keys: List[str] = []
    for item in raw_items:
        key = clean_api_key(item)
        if key and key not in keys:
            keys.append(key)
    return keys


def first_api_key(value: Any) -> str:
    keys = split_api_key_candidates(value)
    return keys[0] if keys else ""


def config_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "sim", "on")


def get_api_key() -> str:
    if PROXY_URL:
        if LICENSE_HAS_API_KEY:
            return "__cloudflare_license_api_key__"
        for _attempt in range(3):
            print(f"{C.BLOOD}Licenca valida. Agora cole sua API key da Tamblox para registrar no servidor.{C.RESET}")
            api_key = clean_api_key(masked_input("API key Tamblox: "))
            try:
                register_proxy_api_key(api_key)
                print(f"{C.GREEN}API key registrada no Cloudflare para esta licenca.{C.RESET}")
                return "__cloudflare_license_api_key__"
            except Exception as e:
                print(f"{C.RED}{friendly_error(e)}{C.RESET}")
        return ""

    config = load_config()
    key = first_api_key(os.environ.get("TAMBLOX_API_KEY") or config.get("api_key"))
    if key:
        return key
    print(f"{C.BLOOD}Cole sua API key da Tamblox abaixo.{C.RESET}")
    return clean_api_key(masked_input("API key: "))


def ensure_proxy_url_for_controller() -> bool:
    global PROXY_URL
    if PROXY_URL:
        save_config_value("proxy_url", PROXY_URL)
        return True
    print(f"{C.BLOOD}Modo Tamblox pelo controller precisa da URL do Cloudflare Worker.{C.RESET}")
    print(f"{C.DIM}Exemplo: https://seu-worker.sua-conta.workers.dev{C.RESET}")
    value = input(f"{C.BLOOD}Proxy URL: {C.RESET}").strip().rstrip("/")
    if not value:
        print(f"{C.RED}proxy_url obrigatorio para usar Tamblox pelo controller.{C.RESET}")
        return False
    PROXY_URL = value
    save_config_value("proxy_url", PROXY_URL)
    return True


def get_license_key(force_prompt: bool = False) -> str:
    key = clean_api_key(LICENSE_KEY)
    if not key:
        key = clean_api_key(str(load_config().get("license_key") or ""))
    if key and not force_prompt:
        return key
    print(f"{C.BLOOD}Digite sua license key para liberar o CMD.{C.RESET}")
    return clean_api_key(masked_input("License key: "))


def remember_valid_license(license_info: Dict[str, Any]) -> None:
    values: Dict[str, Any] = {
        "license_key": LICENSE_KEY,
        "proxy_url": PROXY_URL,
        "license_device_id": load_or_create_device_id(),
        "license_validated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if license_info:
        values["license_expires_at"] = license_info.get("expires_at")
        values["license_has_api_key"] = bool(license_info.get("has_api_key"))
        values["license_device_registered"] = bool(license_info.get("device_registered"))
        if license_info.get("device_registered_at"):
            values["license_device_registered_at"] = license_info.get("device_registered_at")
    save_config_values(values)


def looks_like_license_rejection(error: Any) -> bool:
    text = str(error).lower()
    return any(
        part in text
        for part in (
            "unauthorized",
            "http 401",
            "licenca invalida",
            "license key invalida",
            "licenca revogada",
            "licenca expirada",
            "dispositivo",
        )
    )


def validate_or_prompt_proxy_license(max_attempts: int = 3) -> bool:
    global LICENSE_KEY
    last_error = ""
    for attempt in range(max_attempts):
        had_saved_key = bool(clean_api_key(LICENSE_KEY) or clean_api_key(str(load_config().get("license_key") or "")))
        LICENSE_KEY = get_license_key(force_prompt=attempt > 0 or not LICENSE_KEY)
        try:
            license_info = run_with_animation("Validando licenca Cloudflare", validate_proxy_license)
            remember_valid_license(license_info)
            return True
        except Exception as e:
            last_error = friendly_error(e)
            print(f"{C.RED}Nao foi possivel validar a licenca: {last_error}{C.RESET}")
            if had_saved_key and not looks_like_license_rejection(e):
                print(f"{C.YELLOW}Mantive a license key salva. Parece falha temporaria de conexao/servidor, nao key errada.{C.RESET}")
                return False
            LICENSE_KEY = ""
    return False


def masked_input(prompt: str) -> str:
    print(prompt, end="", flush=True)
    chars: List[str] = []
    if os.name == "nt":
        while True:
            char = msvcrt.getwch()
            if char in ("\r", "\n"):
                print()
                return "".join(chars)
            if char == "\003":
                raise KeyboardInterrupt
            if char == "\b":
                if chars:
                    chars.pop()
                    print("\b \b", end="", flush=True)
                continue
            chars.append(char)
            print("*", end="", flush=True)

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            char = sys.stdin.read(1)
            if char in ("\r", "\n"):
                print()
                return "".join(chars)
            if char == "\003":
                raise KeyboardInterrupt
            if char in ("\x7f", "\b"):
                if chars:
                    chars.pop()
                    print("\b \b", end="", flush=True)
                continue
            chars.append(char)
            print("*", end="", flush=True)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clean_api_key(value: str) -> str:
    return re.sub(r"\s+", "", value.strip().strip("\"'"))


def main() -> int:
    global SITE_FALLBACK, PROXY_URL, LICENSE_KEY
    if os.name == "nt":
        os.system("")
    config = load_config()
    if "site_fallback" in config:
        SITE_FALLBACK = config_bool(config.get("site_fallback"), SITE_FALLBACK)
    PROXY_URL = str(config.get("proxy_url") or PROXY_URL).strip().rstrip("/")
    LICENSE_KEY = str(config.get("license_key") or LICENSE_KEY).strip()
    apply_theme(config)
    clear()
    banner()
    controller_mode = config_bool(os.environ.get("DOMINANCIA_CONTROLLER_MODE"), False) or config_bool(config.get("controller_mode"), False)
    if controller_mode and not PROXY_URL:
        if not ensure_proxy_url_for_controller():
            return 1

    if PROXY_URL:
        if not validate_or_prompt_proxy_license():
            return 1
    clear()
    banner()
    if PROXY_URL:
        print(f"{C.GREEN}Licenca Cloudflare validada.{C.RESET}")
        print(f"{C.BLOOD}Proxy ativo:{C.RESET} {C.WHITE}{PROXY_URL}{C.RESET}")
        print()
    api_key = get_api_key()
    if not api_key:
        print(f"{C.RED}API key obrigatoria.{C.RESET}")
        return 1
    print(f"{C.BLOOD}API key Tamblox carregada.{C.RESET}")
    print()

    targets: List[Target] = []
    try:
        products, source = run_with_animation("Carregando Tamblox", fetch_products, api_key)
    except TambloxBlockedError as e:
        print(f"{C.RED}Tamblox bloqueou esta conexao/IP.{C.RESET}")
        print(f"{C.YELLOW}Abra o site no navegador para confirmar. Se tambem estiver bloqueado, espere alguns minutos ou use outra rede confiavel.{C.RESET}")
        print(f"{C.DIM}Detalhe: {e}{C.RESET}")
        return 1
    except Exception as e:
        print(f"{C.RED}Nao foi possivel carregar produtos Tamblox: {friendly_error(e)}{C.RESET}")
        return 1
    print_products(products, source)
    targets.extend(choose_targets(products))

    clear()
    banner()
    print_targets(targets)
    interval = DEFAULT_INTERVAL
    print(f"\n{C.BLOOD}Busca rapida configurada em {interval:.1f}s por tentativa perto do restock.{C.RESET}")
    print(f"{C.BLOOD}Se o proximo stock estiver longe, o programa fica em espera e evita requests ate perto do horario.{C.RESET}")
    print(f"{C.BLOOD}Ao continuar, o programa vai enviar compra automaticamente quando achar estoque dos alvos.{C.RESET}")
    confirm = input(f"{C.BLOOD}Digite BUY para iniciar (maiusculo ou minusculo): {C.RESET}").strip()
    if confirm.upper() != "BUY":
        print("Cancelado.")
        return 0
    clear()
    banner()
    monitor(api_key, targets, interval)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print(f"\n{C.YELLOW}Interrompido.{C.RESET}")
        raise SystemExit(130)




