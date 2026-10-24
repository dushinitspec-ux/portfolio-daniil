from app.text import analyze, analyze_groups, fold, stem, words


def test_fold_removes_case_and_accents_in_every_language() -> None:
    assert fold("Gäste") == "gaste"
    assert fold("Straße") == "strasse"
    assert fold("ŞİFRE") == "sifre"  # dotted capital İ must not leave a combining dot
    assert fold("Yazıcı") == "yazici"  # dotless ı
    assert fold("Ёлка") == "елка"
    assert fold("can’t") == "can't"  # typographic apostrophe


def test_words_keep_hyphenated_words_together_and_split_compounds() -> None:
    assert words("Wi-Fi") == ["wifi"]
    assert words("WLAN-Passwort") == ["wlanpasswort", "wlan", "passwort"]
    assert words("OneDrive'da") == ["onedrive", "da"]


def test_stem_meets_word_forms() -> None:
    assert {stem(w) for w in ["print", "prints", "printing", "printed"]} == {"print"}
    assert stem("files") == stem("file")
    assert stem("deleted") == stem("delete")
    assert stem("dropping") == "drop"
    assert stem("installed") == "install"
    assert stem("access") == "access"  # not a plural
    assert stem("пароль") == "пароль"  # other alphabets are left to the glossary


def test_contractions_are_stopwords() -> None:
    # Regression (BUGFIX.md, bug 1): "wasn't" splits into "wasn" + "t", and "wasn" used to
    # stay in the query as an unknown word that lowered the confidence of the answer.
    assert analyze("I wasn't logging in and I don't know why", synonyms=False) == ["log", "know"]


def test_glossary_translates_german_russian_turkish() -> None:
    vocabulary = {"print", stem("queue"), "password", "laptop", "lost", "wifi", "guest"}
    assert "print" in analyze("Mein Druckauftrag hängt", vocabulary=vocabulary)
    assert stem("queue") in analyze("in der Warteschlange", vocabulary=vocabulary)
    assert "password" in analyze("Забыл пароль", vocabulary=vocabulary)
    assert analyze("WLAN für Gäste", vocabulary=vocabulary) == ["wifi", "guest"]


def test_unknown_word_falls_back_to_a_known_prefix() -> None:
    # Turkish suffixes on an English word: "laptopumu" = "my laptop" (accusative).
    terms = analyze("Şirket laptopumu kaybettim", vocabulary={"laptop", "lost"})
    assert terms == ["sirket", "laptop", "lost"]


def test_chat_synonyms_are_alternatives_of_one_word() -> None:
    groups = analyze_groups("how do I log in", vocabulary={"sign"})
    assert groups == [("log", "sign")]
    assert analyze_groups("how do I log in", synonyms=False, vocabulary={"sign"}) == [("log",)]
