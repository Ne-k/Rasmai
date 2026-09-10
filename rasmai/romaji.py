import re
import unicodedata
from typing import List

_BASE = {
    "ア": "a", "イ": "i", "ウ": "u", "エ": "e", "オ": "o",
    "カ": "ka", "キ": "ki", "ク": "ku", "ケ": "ke", "コ": "ko",
    "ガ": "ga", "ギ": "gi", "グ": "gu", "ゲ": "ge", "ゴ": "go",
    "サ": "sa", "シ": "shi", "ス": "su", "セ": "se", "ソ": "so",
    "ザ": "za", "ジ": "ji", "ズ": "zu", "ゼ": "ze", "ゾ": "zo",
    "タ": "ta", "チ": "chi", "ツ": "tsu", "テ": "te", "ト": "to",
    "ダ": "da", "ヂ": "ji", "ヅ": "zu", "デ": "de", "ド": "do",
    "ナ": "na", "ニ": "ni", "ヌ": "nu", "ネ": "ne", "ノ": "no",
    "ハ": "ha", "ヒ": "hi", "フ": "fu", "ヘ": "he", "ホ": "ho",
    "バ": "ba", "ビ": "bi", "ブ": "bu", "ベ": "be", "ボ": "bo",
    "パ": "pa", "ピ": "pi", "プ": "pu", "ペ": "pe", "ポ": "po",
    "マ": "ma", "ミ": "mi", "ム": "mu", "メ": "me", "モ": "mo",
    "ヤ": "ya", "ユ": "yu", "ヨ": "yo",
    "ラ": "ra", "リ": "ri", "ル": "ru", "レ": "re", "ロ": "ro",
    "ワ": "wa", "ヰ": "wi", "ヱ": "we", "ヲ": "wo", "ン": "n",
    "ヴ": "vu", "ヵ": "ka", "ヶ": "ke",
}
_SMALL = {"ァ": "a", "ィ": "i", "ゥ": "u", "ェ": "e", "ォ": "o", "ャ": "ya", "ュ": "yu", "ョ": "yo", "ヮ": "wa"}
_GLIDE = {"shi": "sh", "chi": "ch", "ji": "j"}   # shi + ya -> sha, not shya
_VOWELS = "aeiou"
_CONSONANTS = "[bcdfghjklmnprstvwxz]"


def has_kana(text: str) -> bool:
    return any("぀" <= ch <= "ヿ" for ch in text or "")


def to_katakana(text: str) -> str:
    out = []
    for ch in unicodedata.normalize("NFKC", text or ""):
        code = ord(ch)
        if 0x3041 <= code <= 0x3096:
            out.append(chr(code + 0x60))
        else:
            out.append(ch)
    return "".join(out)


def romanize(text: str) -> str:
    """Hepburn romaji for the kana in `text`; other characters pass through.

    :param text: The text to work on.
    :type text: str
    :rtype: str
    """
    kana = to_katakana(text)
    out: List[str] = []
    double_next = False
    i = 0
    while i < len(kana):
        ch = kana[i]
        nxt = kana[i + 1] if i + 1 < len(kana) else ""
        if ch == "ッ":
            double_next = True
            i += 1
            continue
        if ch == "ー":
            for prev in reversed(out):
                if prev and prev[-1] in _VOWELS:
                    out.append(prev[-1])
                    break
            i += 1
            continue
        if ch in _BASE:
            syllable = _BASE[ch]
            if nxt in _SMALL:
                small = _SMALL[nxt]
                if small.startswith("y") and syllable.endswith("i"):
                    stem = _GLIDE.get(syllable, syllable[:-1])
                    syllable = stem + small[1:] if stem in _GLIDE.values() else stem + small
                elif len(syllable) >= 2:
                    syllable = syllable[:-1] + small
                else:
                    syllable = syllable + small
                i += 1
            if double_next and syllable and syllable[0] not in _VOWELS:
                syllable = syllable[0] + syllable
            double_next = False
            out.append(syllable)
        elif ch in _SMALL:
            out.append(_SMALL[ch])
        else:
            out.append(ch)
        i += 1
    return "".join(out)


_LONG = (("ou", "o"), ("oo", "o"), ("uu", "u"), ("aa", "a"), ("ii", "i"), ("ee", "e"), ("ei", "e"))


def skeleton(text: str) -> str:
    """Reduce romaji (or kana) to a form where spelling variants and lost dakuten collide.

    The database readings are sort kana - dakuten dropped and small kana enlarged - so
    "obenkyoutaimu" and the stored reading "ohenkiyoutaimu" both become "ohenkotaimu".

    :param text: The text to work on.
    :type text: str
    :rtype: str
    """
    s = romanize(text).lower()
    s = re.sub(r"[^a-z0-9]+", "", s)
    s = s.replace("sh", "s").replace("ch", "t").replace("ts", "t").replace("j", "s").replace("f", "h")
    s = s.translate(str.maketrans({"b": "h", "p": "h", "g": "k", "z": "s", "d": "t", "v": "h"}))
    s = s.replace("mh", "nh")
    # enlarged small kana: kiyo -> kyo; then glides go: kyo -> ko
    s = re.sub(_CONSONANTS + "iy", lambda m: m.group(0)[0] + "y", s)
    s = re.sub(_CONSONANTS + "y", lambda m: m.group(0)[0], s)
    for long, short in _LONG:
        s = s.replace(long, short)
    s = re.sub(r"([a-z])\1", lambda m: m.group(1), s)
    return s


# English spellings that katakana renders with one sound
_ENGLISH = (("tch", "c"), ("ph", "f"), ("th", "s"), ("sh", "s"), ("ch", "c"), ("ck", "k"), ("wh", "w"), ("qu", "k"), ("dg", "j"), ("gh", ""),
            ("x", "ks"), ("mb", "nb"), ("mp", "np"))


def loanword(text: str) -> str:
    """A consonant skeleton on which an English word and its katakana rendering collide.

    :param text: The text to work on.
    :type text: str
    :rtype: str
    """
    words = []
    for word in re.split(r"[^a-z]+", romanize(text).lower()):
        if not word:
            continue
        for a, b in _ENGLISH:
            word = word.replace(a, b)
        word = re.sub(r"c(?=[eiy])", "s", word).replace("c", "k")
        word = word.replace("l", "r").replace("v", "b").replace("f", "h")
        word = re.sub(r"y(?=[aeiou])", "", word).replace("y", "i")
        word = re.sub(r"(?<=[aeiou])r(?=e?$|[^aeiou])", "", word)
        words.append(word)
    s = "".join(words)
    s = s.translate(str.maketrans({"b": "h", "p": "h", "g": "k", "z": "s", "d": "t", "j": "s"}))
    s = re.sub(r"([a-z])\1", lambda m: m.group(1), s)
    return re.sub("[aeiou]", "", s)
