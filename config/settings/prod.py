from .base import *  # noqa: F401,F403

DEBUG = False

# Render, TLS'i proxy'de sonlandırır
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)  # noqa: F405
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_CONTENT_TYPE_NOSNIFF = True

# Render dış adresi otomatik tanınır
_render_host = env("RENDER_EXTERNAL_HOSTNAME", default="")  # noqa: F405
if _render_host:
    ALLOWED_HOSTS = [*ALLOWED_HOSTS, _render_host]  # noqa: F405
    CSRF_TRUSTED_ORIGINS = [f"https://{_render_host}"]

# Üretimde SECRET_KEY zorunlu (varsayılan yok)
SECRET_KEY = env("SECRET_KEY")  # noqa: F405
# Render sağlık kontrolü HTTPS yönlendirmesine takılmasın
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health/$"]
