from rest_framework.throttling import SimpleRateThrottle


class _IPThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": self.get_ident(request)}


class SessionCreateThrottle(_IPThrottle):
    scope = "session_create"


class AnswerThrottle(_IPThrottle):
    scope = "answer"


class NameThrottle(_IPThrottle):
    scope = "name"


class DuelCreateThrottle(_IPThrottle):
    scope = "duel_create"


class DuelStatusThrottle(_IPThrottle):
    scope = "duel_status"


class DuelAnswerThrottle(_IPThrottle):
    scope = "duel_answer"
