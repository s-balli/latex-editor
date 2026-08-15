"""Yaygın LaTeX hataları için insan dili ipuçları — kalıp eşleme (Qt'süz).

Derleyici mesajları yeni kullanıcı için korsan argodur; araştırmada en çok
oylu somut istek "helpful error messages"dı. Bu modül yaygın ~14 kalıbı tanır
ve (ipucu_kimliği, parametreler) döndürür. İpucu METİNLERİ sunum katmanında
durur (GUI'de çevrilir; web'de de aynı kimlikler kullanılabilir).

Eksik paket tespiti ayrıca yapılır (derle.sh önerisi + install komutu);
burada tekrarlanmaz.
"""

import re

# Bağlam satırı "l.42 \\komut kalanı" — tanımsız komudu çıkarmak için
_RE_CTX_CMD = re.compile(r"l\.\d+\s+(\\\w+)")

# (mesaj deseni, ipucu kimliği). Sıra önemli: özgül olan önce.
# Parametreli ipuçlar (ortam adı, komut adı) aşağıda ayrıca işlenir.
_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Undefined control sequence"), "undefined_control"),
    (re.compile(r"Missing \$ inserted"), "missing_math"),
    (re.compile(r"Display math should end with"), "missing_math"),
    (re.compile(r"Text line contains an invalid character"), "invalid_character"),
    (re.compile(r"Missing \} inserted|Too many \}'s|Extra \}"), "brace_mismatch"),
    (re.compile(r"Double subscripts?|Double superscripts?"), "double_subscript"),
    (re.compile(r"File ended while scanning"), "file_ended_scanning"),
    (re.compile(r"Emergency stop"), "emergency_stop"),
    (re.compile(r"Counter too large"), "counter_too_large"),
    (re.compile(r"Misplaced \\noalign|Misplaced \\omit"), "misplaced_noalign"),
    (re.compile(r"Citation `[^']*' undefined|Citation .* undefined"), "citation_undefined"),
    (re.compile(r"Reference `[^']*' .*undefined|Reference .* undefined"), "reference_undefined"),
    (re.compile(r"There were undefined references|Rerun to get cross"), "rerun_needed"),
    (re.compile(r"destination with the same identifier"), "duplicate_label"),
]

_RE_ENV_UNDEFINED = re.compile(r"Environment (\S+) undefined")


def get_hint(message: str, context: str = "") -> tuple[str, dict[str, str]] | None:
    """Hata/uyarı mesajı için (ipucu_kimliği, parametreler); tanınmazsa None.

    ``context``: log_parser'ın yakaladığı "l.42 ..." satırı (tanımsız komutun
    kaynağını çıkarmada kullanılır).
    """
    if not message:
        return None
    m = _RE_ENV_UNDEFINED.search(message)
    if m:
        return "env_undefined", {"env": m.group(1)}
    for pat, hint_id in _PATTERNS:
        if pat.search(message):
            params: dict[str, str] = {}
            if hint_id == "undefined_control" and context:
                cm = _RE_CTX_CMD.search(context)
                if cm:
                    params["cmd"] = cm.group(1)
            return hint_id, params
    return None
