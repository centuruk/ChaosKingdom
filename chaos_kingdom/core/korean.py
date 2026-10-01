"""Small particle helpers for generated Korean event sentences."""


def attach(text: str, consonant: str, vowel: str, *, rieul_is_vowel: bool = False) -> str:
    if not text:
        return text
    code = ord(text[-1]) - 0xAC00
    final = code % 28 if 0 <= code < 11172 else 0
    suffix = consonant if final and not (rieul_is_vowel and final == 8) else vowel
    return text + suffix


def subject(text: str) -> str:
    return attach(text, "이", "가")


def together(text: str) -> str:
    return attach(text, "과", "와")


def as_role(text: str) -> str:
    return attach(text, "으로", "로", rieul_is_vowel=True)
