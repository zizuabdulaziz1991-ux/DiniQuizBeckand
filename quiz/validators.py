import re

from django.core.exceptions import ValidationError

# Basit bir başlangıç listesi; admin ve ihtiyaç doğrultusunda genişletilmeli.
BANNED_WORDS = {"amk", "aq", "orospu", "piç", "sik", "siktir", "yarrak", "göt", "kahpe"}

NAME_RE = re.compile(r"^[A-Za-zÇĞİıÖŞÜçğöşü0-9 ._-]+$")


def validate_player_name(value: str) -> str:
    name = " ".join((value or "").split())
    if not 2 <= len(name) <= 20:
        raise ValidationError("İsim 2 ile 20 karakter arasında olmalıdır.")
    if not NAME_RE.match(name):
        raise ValidationError("İsim yalnızca harf, rakam, boşluk ve . _ - içerebilir.")
    lowered = name.casefold().replace("ı", "i")
    tokens = re.split(r"[ ._-]+", lowered)
    for word in BANNED_WORDS:
        w = word.casefold().replace("ı", "i")
        if w in tokens or (len(w) > 3 and w in lowered):
            raise ValidationError("Bu isim kullanılamaz.")
    return name
