"""Candidate Bangla grapheme clusters to pre-render.

Every string here should be ONE screen cell in Neovim. build_font.py checks
that with Neovim itself and drops anything that is not.
"""

VIRAMA = "্"   # ্ hasanta
ZWNJ = "‌"
ZWJ = "‍"

CONSONANTS = list("কখগঘঙচছজঝঞটঠডঢণতথদধনপফবভমযরলশষসহ") + [
    "ড়", "ঢ়", "য়",              # ড় ঢ় য় (precomposed)
    "ড়", "ঢ়", "য়",  # ড় ঢ় য় (NFC: base + nukta)
]

VOWELS = list("অআইঈউঊঋএঐওঔ")

# Vowel signs, plus the decomposed spellings of ো and ৌ.
SIGNS = ["", "া", "ি", "ী", "ু", "ূ", "ৃ", "ে", "ৈ", "ো", "ৌ",
         "ো", "ৌ"]

MODIFIERS = ["", "ঁ", "ং", "ঃ"]

OTHERS = list("ৎ০১২৩৪৫৬৭৮৯৳ঽ।॥")

CONJUNCTS = """
ক্ক ক্ট ক্ত ক্ব ক্ম ক্য ক্র ক্ল ক্ষ ক্স খ্য খ্র গ্গ গ্ধ গ্ন গ্ব গ্ম গ্য গ্র গ্ল
ঘ্ন ঘ্য ঘ্র ঙ্ক ঙ্খ ঙ্গ ঙ্ঘ চ্চ চ্ছ চ্ঞ চ্য ছ্য ছ্র জ্জ জ্ঝ জ্ঞ জ্ব জ্য জ্র ঞ্চ ঞ্ছ
ঞ্জ ঞ্ঝ ট্ট ট্ব ট্ম ট্য ট্র ঠ্য ড্ড ড্য ড্র ঢ্য ণ্ট ণ্ঠ ণ্ড ণ্ঢ ণ্ণ ণ্ব ণ্ম ণ্য
ত্ত ত্থ ত্ন ত্ব ত্ম ত্য ত্র থ্য থ্র দ্গ দ্ঘ দ্দ দ্ধ দ্ব দ্ভ দ্ম দ্য দ্র ধ্ন ধ্ব ধ্ম
ধ্য ধ্র ন্ট ন্ঠ ন্ড ন্ত ন্থ ন্দ ন্ধ ন্ন ন্ব ন্ম ন্য ন্স প্ট প্ত প্ন প্প প্য প্র প্ল
প্স ফ্র ফ্ল ব্জ ব্দ ব্ধ ব্ব ব্য ব্র ব্ল ভ্য ভ্র ম্ন ম্প ম্ফ ম্ব ম্ভ ম্ম ম্য ম্র ম্ল
য্য ল্ক ল্গ ল্ট ল্ড ল্প ল্ফ ল্ব ল্ম ল্য ল্ল শ্চ শ্ছ শ্ন শ্ব শ্ম শ্য শ্র শ্ল ষ্ক
ষ্ট ষ্ঠ ষ্ণ ষ্প ষ্ফ ষ্ম ষ্য স্ক স্খ স্ট স্ত স্থ স্ন স্প স্ফ স্ব স্ম স্য স্র স্ল
হ্ণ হ্ন হ্ব হ্ম হ্য হ্র হ্ল
ক্ষ্ণ ক্ষ্ম ক্ষ্য ঙ্ক্ষ ঙ্ক্ত ঙ্ক্য চ্ছ্ব চ্ছ্র জ্জ্ব ত্ত্ব ত্ত্র দ্দ্ব দ্ধ্ব দ্ভ্র ন্ত্ব
ন্ত্য ন্ত্র ন্দ্ব ন্দ্য ন্দ্র ন্ধ্য ন্ধ্র ম্প্র ম্ভ্র ষ্ক্র ষ্ট্য ষ্ট্র ষ্প্র স্ক্র স্ট্র
স্ত্ব স্ত্য স্ত্র স্প্র স্প্ল ন্ট্র ক্ট্র ক্ত্র ঞ্জ্য
""".split()


def builtin_clusters():
    out = []
    add = out.append

    for v in VOWELS:
        for m in MODIFIERS:
            add(v + m)
    out.extend(OTHERS)
    for s in SIGNS[1:] + ["ঁ", "ং", "ঃ", VIRAMA]:
        add(s)                                   # lone sign (drawn on ◌)

    for c in CONSONANTS:
        add(c + VIRAMA)                          # explicit hasanta: ক্
        add(c + VIRAMA + ZWNJ)
        for s in SIGNS:
            for m in MODIFIERS:
                add(c + s + m)

    # Every consonant pair, bare.
    for a in CONSONANTS[:32]:
        for b in CONSONANTS[:32]:
            add(a + VIRAMA + b)

    # Conjuncts, phala forms and reph, with every vowel sign.
    bases = list(CONJUNCTS)
    for c in CONSONANTS:
        bases += [c + VIRAMA + "য", c + VIRAMA + "র", c + VIRAMA + "ব",
                  "র" + VIRAMA + c]
    bases.append("র" + ZWJ + VIRAMA + "য")       # র‍্য
    for b in bases:
        for s in SIGNS[:11]:
            for m in ("", "ং"):
                add(b + s + m)

    seen = set()
    return [c for c in out if not (c in seen or seen.add(c))]
