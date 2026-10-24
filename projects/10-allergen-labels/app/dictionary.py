"""Curated ingredient dictionary: words and products in EN / RU / TR / DE -> Annex II groups.

How to read the word lists
--------------------------
Each list is a comma-separated string. Write words normally ("fındık", "Weizen",
"сливочн"); they are folded to the search form (see app/text.py) when compiled.

Markers:
    word?   the word only *usually* means this allergen ("flour" is usually wheat): the
            allergen is pre-selected but the ingredient is marked "check".
    =word   exact word, no endings and no compounds ("=ei" must not match "Reis").
    word~   (Russian, Turkish, English) may also appear at the end of a longer word.
    !word   (German) never inside a compound word.

How each language is matched (see `build_pattern`)
-------------------------------------------------
- English: whole words, the last word may take a plural ending (-s, -es, -y -> -ies).
- German: words of 4+ letters are also found inside compound words ("Weizenmehl",
  "Haselnusskrokant"); shorter words take the usual endings (-e, -en, -er, -n, -s, -es).
- Russian: Russian words are written as stems ("сливочн", "кревет"); any ending of up to
  six letters may follow, so all cases and adjective forms match.
- Turkish: stems of 4+ letters may take up to 10 suffix letters ("yumurtalı",
  "peynirlerinden"); a final k/p/t/ç also matches its softened form ("fındık" ->
  "fındığı"). Short words (un, süt) take only a list of common suffixes. A "-sız/-siz/
  -suz/-süz" suffix means "without" and is reported as such, never as the allergen.

Limits (also in the README): this is a curated word list, not a morphological analyser.
Rare word forms, spelling mistakes, brand names and house-made products are reported as
"unknown" for a person (or the AI suggestion) to check.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.i18n import Language

EN, RU, TR, DE = Language.EN, Language.RU, Language.TR, Language.DE


class Kind(StrEnum):
    WORD = "word"  # an ingredient word of an allergen group ("almond", "Weizen")
    PRODUCT = "product"  # a composite product with typical allergens ("pesto")
    EXCLUSION = "exclusion"  # looks like an allergen but is not one under Annex II
    SAFE = "safe"  # a common ingredient with none of the 14 allergens, or a filler word


@dataclass(frozen=True)
class Entry:
    kind: Kind
    phrases: tuple[tuple[Language, str], ...]
    contains: tuple[int, ...] = ()
    maybe: tuple[int, ...] = ()
    note: str = ""


# --- 1. Allergen group words ----------------------------------------------------------

GROUP_WORDS: dict[int, dict[Language, str]] = {
    1: {  # cereals containing gluten
        EN: "wheat, wholewheat, wholemeal, spelt, khorasan, kamut, rye, barley, oat, oats, "
        "oatmeal, rolled oats, semolina, durum, farro, freekeh, einkorn, emmer, triticale, "
        "bulgur, bulgar, couscous, seitan, malt, malted, gluten, flour?, plain flour, bread, "
        "breadcrumbs, breadcrumb, breaded, panko, croutons, crouton, pasta, spaghetti, "
        "penne, fusilli, linguine, tagliatelle, fettuccine, lasagne, lasagna, macaroni, "
        "ravioli, tortellini, orzo, noodles?, udon, ramen, pita, pitta, naan, bun, baguette, "
        "ciabatta, focaccia, pastry, filo, phyllo, puff pastry, shortcrust, dough?, "
        "batter?, crackers, cracker, biscuit, sponge?, starch?, bran?, beer, ale, lager, "
        "stout, barley malt, vital wheat gluten, wafer, waffle, pancake, crepe, crumble, "
        "pie crust, tart shell, flatbread, sourdough, rusk, wheat starch",
        RU: "пшениц, пшеничн, =рожь, =ржи, ржан, ячмен, ячнев, перлов, =овёс, =овса, "
        "овсян, спельт, полб, камут, хорасан, мук?, манк, манн, булгур, кускус, хлеб, "
        "лаваш, лапш, макарон, =спагетти, паст?, сухар, панировк?, тест?, солод, пив, "
        "глютен, отруб?, батон, булк, багет, лепёшк, сдоб, вафл, крекер, блин, "
        "оладь, пирог, пирож, торт, кекс, гренк, сушк, баранк, крахмал?, клейковин, "
        "=печенье, =печенья, =печеньем, "
        "манная крупа, крупа манная",
        TR: "buğday, un?, irmik, kepek?, bulgur, kuskus, yulaf, arpa, çavdar, siyez, "
        "kavılca, ekmek, pide, lavaş, yufka, galeta, makarna, erişte, şehriye, kadayıf, "
        "bira, malt, nişasta?, gluten, kruton, bazlama, gözleme, poğaça, açma, lahmacun, "
        "hamur?, bisküvi, kraker, gofret, kurabiye, kete, çörek, krep, buğday nişastası, "
        "pankek, galeta unu, kızartma unu?",
        DE: "weizen, dinkel, khorasan, kamut, roggen, gerste, hafer, grünkern, emmer, "
        "einkorn, mehl?, grieß?, graupen, malz, bulgur, couscous, seitan, brot, semmel, "
        "paniermehl, paniert, nudel, teigwaren, teig?, stärke?, zwieback, keks, kekse, "
        "bier, gluten, croutons, brezel, laugen, knäcke, pfannkuchen, waffel, oblate, "
        "kuchen, torte, mürbeteig, blätterteig, strudel, zwiebelkuchen, schwarzbrot, "
        "toast, baguette, kleie?, spätzle, pudding?",
    },
    2: {  # crustaceans
        EN: "crustacean, crustaceans, shrimp, shrimps, prawn, crab, lobster, crayfish, "
        "crawfish, langoustine, scampi, krill, shrimp paste",
        RU: "ракообразн, кревет, краб, лобстер, омар, лангуст, лангустин, =рак, =раки, "
        "=раков, =раками, =раках, криль, скампи",
        TR: "kabuklular, karides, yengeç, ıstakoz, kerevit, langust, jumbo karides, deniz böceği",
        DE: "krebstier, krebs, garnele, shrimp, krabbe, hummer, languste, langustine, "
        "scampi, flusskrebs, kaisergranat, gamba, gambas, crevette",
    },
    3: {  # eggs
        EN: "egg, eggs, egg yolk, yolk, egg white, albumen, egg wash, omelette, omelet, "
        "frittata, quiche, meringue, scrambled eggs, eggnog",
        RU: "яйц, яич, =яиц, желток, желтк, яичн белок, омлет, глазунь, меренг, безе, "
        "гоголь-моголь, яйцепродукт, меланж, белок?, белк?",
        TR: "yumurta, omlet, beze",
        DE: "!ei, eier, eigelb, eiweiß, eiklar, eidotter, vollei, rührei, spiegelei, "
        "hühnerei, wachtelei, eierlikör, baiser, omelett, eierstich",
    },
    4: {  # fish
        EN: "fish, anchovy, anchovies, salmon, tuna, cod, haddock, hake, pollock, pollack, "
        "mackerel, sardine, herring, trout, sea bass, seabass, bass, sea bream, bream, "
        "dorado, sole, plaice, halibut, turbot, swordfish, tilapia, catfish, carp, pike, "
        "perch, monkfish, snapper, grouper, mullet, red mullet, sprat, whitebait, eel, "
        "caviar, roe, bottarga, kipper, pilchard, coley, whiting, zander, sturgeon, "
        "fish stock, fish fillet",
        RU: "рыб, лосос, сёмг, семг, тунец, тунц, треск, анчоус, сельд, селёдк, "
        "скумбри, сардин, форел, судак, дорадо, дорад, сибас, камбал, палтус, минта, "
        "=хек, =хека, =хеком, кильк, шпрот, икр, =карп, =карпа, =карпом, щук, окун, =сом, "
        "=сома, =сомом, осетр, осётр, горбуш, =кета, =кеты, =кетой, нерк, кижуч, мойв, "
        "корюшк, барабульк, ставрид, пикш, сайр, тилапи, угор, угр, белуг",
        TR: "balık, levrek, çupra, somon, ton balığı, hamsi, sardalya, uskumru, palamut, "
        "lüfer, mezgit, alabalık, kılıç, dil balığı, kalkan, istavrit, çinekop, sinarit, "
        "mercan, orkinos, morina, havyar, ançüez, sazan, turna, kefal, tirsi, lakerda, "
        "=çaça, zargana, kolyoz, iskorpit, fangri",
        DE: "fisch, lachs, thunfisch, kabeljau, dorsch, forelle, hering, sardelle, sardine, "
        "makrele, scholle, zander, barsch, wolfsbarsch, dorade, seelachs, heilbutt, "
        "karpfen, anchovis, kaviar, rogen, sprotte, matjes, rotbarsch, seehecht, "
        "seezunge, steinbutt, aal, hecht, schwertfisch, saibling, !stör, felchen, rollmops",
    },
    5: {  # peanuts
        EN: "peanut, peanuts, groundnut, groundnuts, peanut butter, peanut oil, "
        "groundnut oil, monkey nuts, arachis oil",
        RU: "арахис, земляной орех, землян орех",
        TR: "yer fıstığı, yerfıstığı, yer fıstık, fıstık ezmesi, fıstık yağı",
        DE: "erdnuss, erdnüsse, erdnussbutter, erdnussöl, erdnussmus",
    },
    6: {  # soybeans
        EN: "soy, soya, soybean, soybeans, soya bean, soya beans, soy bean, tofu, "
        "edamame, tempeh, miso, natto, soy lecithin, soya lecithin, soy protein, "
        "soya protein, soy flour, soya flour",
        RU: "=соя, =сои, =сою, =соей, соев, тофу, эдамаме, темпе, =мисо, натто",
        TR: "soya, tofu, edamame, =miso, soya fasulyesi, soya lesitini",
        DE: "soja, sojabohne, tofu, edamame, tempeh, =miso, sojalecithin, sojamehl",
    },
    7: {  # milk
        EN: "milk, cream, butter, buttermilk, cheese, yogurt, yoghurt, kefir, ghee, whey, "
        "casein, caseinate, lactose, curd, quark, ricotta, mozzarella, burrata, parmesan, "
        "parmigiano, pecorino, grana padano, cheddar, feta, halloumi, hellim, mascarpone, "
        "gorgonzola, brie, camembert, emmental, emmentaler, gruyere, gouda, edam, "
        "manchego, roquefort, stilton, labneh, labne, paneer, creme fraiche, sour cream, "
        "double cream, single cream, whipping cream, cream cheese, dairy, milk powder, "
        "skimmed milk, condensed milk, evaporated milk, custard, ice cream, gelato, "
        "bechamel, cheesecake, milk chocolate, kashkaval, kasseri, provolone, taleggio, "
        "fontina, scamorza, stracciatella, raclette, crème brûlée, panna cotta, butterscotch",
        RU: "молок, молочн, сливк, сливочн, сметан, творог, творож, =сыр, =сыра, =сыру, "
        "=сыром, =сыре, =сыры, =сыров, сырн, сырок, кефир, йогурт, простокваш, ряженк, "
        "сгущ, лактоз, сыворотк, казеин, моцарелл, пармезан, =фета, =феты, =фетой, "
        "брынз, маскарпоне, рикотт, сулугуни, пломбир, мороженое, пахт, топлён масл, "
        "=гхи, кисломолочн, айран, =тан, бешамел, чизкейк, адыгейск сыр, творожн, "
        "камамбер, =бри, чеддер, гауд, эмментал",
        TR: "süt, sütlaç, yoğurt, ayran, peynir, kaşar, =lor, çökelek, tulum peyniri, "
        "labne, krema, kaymak, tereyağ, sade yağ, kefir, laktoz, kazein, peynir altı "
        "suyu, süzme, lor peyniri, hellim, mozarella, dil peyniri, kaşkaval, süt tozu, "
        "muhallebi, dondurma, kazandibi, keşkül, güllaç, süttozu, krem şanti, beşamel, "
        "cheddar, parmesan",
        DE: "milch, sahne, rahm, butter, käse, quark, joghurt, jogurt, buttermilch, molke, "
        "kefir, schmand, crème fraîche, mascarpone, mozzarella, parmesan, laktose, "
        "lactose, kasein, ghee, topfen, hüttenkäse, schlagobers, frischkäse, "
        "speiseeis, pudding, sauerrahm, butterschmalz, milchpulver, kondensmilch, "
        "milchschokolade, molkenpulver, sahnesoße, béchamel",
    },
    8: {  # nuts (the eight in Annex II)
        EN: "almond, almonds, hazelnut, filbert, walnut, cashew, cashews, pecan, pecans, "
        "pecan nut, brazil nut, brazil nuts, pistachio, pistachios, macadamia, "
        "queensland nut, nut, nuts, mixed nuts, marzipan, frangipane, gianduja, "
        "almond flour, ground almonds, almond paste, nut butter, hazelnut spread, "
        "almond butter",
        RU: "орех, ореш, миндал, фундук, лесн орех, грецк орех, кешью, пекан, "
        "бразильск орех, фисташ, макадами, марципан, пралине, джандуя, нутелл",
        TR: "badem, fındık, ceviz, kaju, pikan, brezilya fındığı, antep fıstığı, "
        "antep fıstı, şam fıstığı, makadamya, macadamia, kuruyemiş, badem ezmesi, "
        "fındık ezmesi, kaju fıstığı, pikan cevizi",
        DE: "mandel, haselnuss, haselnüsse, walnuss, walnüsse, cashew, kaschu, pekannuss, "
        "paranuss, pistazie, pistazien, macadamia, nuss, nüsse, marzipan, nougat, "
        "gianduja, nussmus, mandelmus, mandelmehl",
    },
    9: {  # celery
        EN: "celery, celeriac, celery salt, celery seed, celery seeds, celery root",
        RU: "сельдере",
        TR: "kereviz, sap kereviz, kök kereviz",
        DE: "sellerie, staudensellerie, knollensellerie, selleriesalz, eppich",
    },
    10: {  # mustard
        EN: "mustard, dijon, mustard seed, mustard seeds, mustard powder, wholegrain mustard",
        RU: "горчиц, горчичн",
        TR: "hardal",
        DE: "senf, senfkörner, senfsaat, senfpulver, mostrich",
    },
    11: {  # sesame
        EN: "sesame, tahini, tahina, gomasio, sesame oil, sesame seeds",
        RU: "кунжут, тахин, сезам",
        TR: "susam, tahin, susamlı",
        DE: "sesam, tahini, tahin, gomasio",
    },
    12: {  # sulphur dioxide and sulphites
        EN: "sulphite, sulphites, sulfite, sulfites, sulphur dioxide, sulfur dioxide, "
        "metabisulphite, metabisulfite, bisulphite, sulphured, sulfured, =e220, =e221, "
        "=e222, =e223, =e224, =e226, =e227, =e228",
        RU: "сульфит, диоксид серы, сернист, метабисульфит",
        TR: "sülfit, kükürt dioksit, kükürtdioksit, metabisülfit",
        DE: "sulfit, sulphit, schwefeldioxid, geschwefelt, schwefel",
    },
    13: {  # lupin
        EN: "lupin, lupine, lupini, lupin flour",
        RU: "люпин",
        TR: "acı bakla, lupin, termiye",
        DE: "lupine, lupinen, lupinenmehl, lupinenprotein",
    },
    14: {  # molluscs
        EN: "mollusc, molluscs, mollusk, mussel, oyster, clam, scallop, squid, calamari, "
        "octopus, cuttlefish, snail, escargot, whelk, cockle, abalone, periwinkle, "
        "razor clam, vongole, sepia",
        RU: "моллюск, миди, устриц, кальмар, осьминог, каракатиц, гребешк, гребешок, "
        "улитк, вонгол, рапан, морск гребеш, трубач, мидий",
        TR: "midye, kalamar, ahtapot, istiridye, salyangoz, mürekkep balığı, "
        "deniz tarağı, yumuşakça, akivades, sübye, deniz salyangozu",
        DE: "muschel, auster, tintenfisch, kalmar, calamari, oktopus, krake, schnecke, "
        "weichtier, sepia, pulpo, vongole, jakobsmuschel, herzmuschel, miesmuschel",
    },
}

# --- 2. Composite products --------------------------------------------------------------
# contains = the allergen is part of what the word means; maybe = typical, depends on the
# recipe or brand. Notes are shown to the chef.


def _p(
    en: str, ru: str, tr: str, de: str, contains: tuple[int, ...] = (), maybe=(), note=""
) -> Entry:
    phrases = tuple(
        (lang, phrase.strip())
        for lang, text in ((EN, en), (RU, ru), (TR, tr), (DE, de))
        for phrase in text.split(",")
        if phrase.strip()
    )
    return Entry(Kind.PRODUCT, phrases, contains, tuple(maybe), note)


PRODUCTS: tuple[Entry, ...] = (
    _p(
        "pesto, pesto genovese",
        "песто",
        "pesto",
        "pesto",
        maybe=(7, 8),
        note="Classic pesto has Parmigiano or Pecorino (milk) and pine nuts, which are not "
        "an Annex II nut; many ready-made pestos use cashews or walnuts instead. List the "
        "pesto's ingredients in brackets or check the label.",
    ),
    _p(
        "soy sauce, soya sauce, shoyu",
        "соевый соус, соев соус",
        "soya sosu, soya sos",
        "sojasoße, sojasauce, sojasosse",
        contains=(6,),
        maybe=(1,),
        note="Most soy sauces are brewed with wheat; tamari is often wheat-free. Check the label.",
    ),
    _p(
        "tamari",
        "тамари",
        "tamari",
        "tamari",
        contains=(6,),
        maybe=(1,),
        note="Tamari is often but not always made without wheat.",
    ),
    _p(
        "teriyaki, teriyaki sauce",
        "терияки",
        "teriyaki",
        "teriyaki",
        contains=(6,),
        maybe=(1,),
        note="Made with soy sauce, which usually contains wheat.",
    ),
    _p(
        "worcestershire sauce, worcestershire, worcester sauce",
        "вустерширский соус, вустерширск",
        "worcestershire sos, worcester sos",
        "worcestersoße, worcestersauce, worcestershiresauce, worcester",
        maybe=(4, 1),
        note="Traditional Worcestershire sauce contains anchovies; many brands also use "
        "barley malt vinegar. Vegan versions exist.",
    ),
    _p(
        "fish sauce, nam pla",
        "рыбный соус, рыбн соус",
        "balık sosu, balık sos",
        "fischsoße, fischsauce, fischsosse",
        contains=(4,),
        maybe=(2,),
        note="Some fish sauces also contain shrimp.",
    ),
    _p(
        "oyster sauce",
        "устричный соус, устричн соус",
        "istiridye sosu, istiridye sos",
        "austernsoße, austernsauce",
        contains=(14,),
        maybe=(1, 6),
    ),
    _p(
        "mayonnaise, mayo",
        "майонез",
        "mayonez",
        "mayonnaise, majonäse, remoulade",
        contains=(3,),
        maybe=(10,),
        note="Mayonnaise often contains mustard.",
    ),
    _p(
        "aioli, garlic mayonnaise",
        "айоли",
        "aioli",
        "aioli",
        maybe=(3,),
        note="Traditional aioli is garlic and oil only; most restaurant aioli uses egg yolk.",
    ),
    _p(
        "hollandaise",
        "голландский соус, голландск соус",
        "hollandez sos",
        "hollandaise",
        contains=(3, 7),
    ),
    _p(
        "caesar dressing",
        "соус цезарь",
        "sezar sos",
        "caesar-dressing, caesardressing",
        maybe=(3, 4, 7, 10),
        note="Usually egg yolk, anchovies, Parmesan and mustard.",
    ),
    _p(
        "tartare sauce, tartar sauce",
        "соус тартар",
        "tartar sos",
        "sauce tartare",
        contains=(3,),
        maybe=(10, 4),
    ),
    _p(
        "hummus, houmous",
        "хумус",
        "humus",
        "hummus",
        contains=(11,),
        note="Hummus is made with tahini (sesame).",
    ),
    _p("tzatziki", "цацики, дзадзики", "cacık", "tsatsiki, zaziki", contains=(7,)),
    _p(
        "satay, satay sauce, peanut sauce",
        "сатай, арахисовый соус",
        "satay",
        "satésoße, erdnusssoße, satay",
        contains=(5,),
        maybe=(6, 1),
    ),
    _p(
        "curry paste, red curry paste, green curry paste",
        "карри паст",
        "köri ezmesi",
        "currypaste",
        maybe=(2, 4),
        note="Thai curry pastes usually contain shrimp paste and sometimes fish sauce.",
    ),
    _p(
        "stock cube, bouillon, bouillon cube, stock, broth",
        "бульонн кубик, бульон",
        "bulyon, et suyu tablet, tavuk suyu tablet",
        "brühwürfel, brühe, bouillon, fond",
        maybe=(9, 1),
        note="Stock cubes and many ready-made stocks contain celery, sometimes wheat. "
        "A home-made stock contains what you put into it.",
    ),
    _p(
        "ketchup",
        "кетчуп",
        "ketçap",
        "ketchup",
        maybe=(9,),
        note="Some ketchups list celery among the spices.",
    ),
    _p(
        "chocolate, cocoa mass",
        "шоколад",
        "çikolata",
        "schokolade",
        maybe=(7, 6, 8),
        note="Chocolate often contains milk and soy lecithin; dark chocolate can too.",
    ),
    _p("ice cream", "мороженое", "dondurma", "eiscreme, =eis", contains=(7,), maybe=(3,)),
    _p("gnocchi", "ньокки", "gnocchi", "gnocchi", maybe=(1, 3)),
    _p(
        "pelmeni, dumplings",
        "пельмен, вареник",
        "mantı",
        "maultasche, pelmeni",
        contains=(1,),
        maybe=(3, 7),
    ),
    _p("borek, burek", "бурек", "börek", "börek", contains=(1,), maybe=(3, 7)),
    _p("simit", "симит", "simit", "simit", contains=(1, 11)),
    _p("croissant", "круассан", "kruvasan", "croissant", contains=(1, 7), maybe=(3,)),
    _p("brioche", "бриошь", "brioş", "brioche", contains=(1, 3, 7)),
    _p("halva, halvah", "халв", "helva, tahin helvası", "halva, halwa", maybe=(11, 8, 1, 7)),
    _p(
        "za'atar, zaatar, zatar",
        "заатар",
        "zahter, zatar",
        "zaatar, za'atar",
        maybe=(11,),
        note="Za'atar blends usually contain sesame seeds.",
    ),
    _p(
        "wine, red wine, white wine, rosé, prosecco, champagne, sherry, port, vermouth, "
        "cider, wine vinegar, balsamic, balsamic vinegar",
        "=вино, =вина, =вином, =вине, винн, херес, вермут, шампанск, бальзамическ",
        "şarap, şarabı, beyaz şarap, kırmızı şarap, şarap sirkesi, balzamik",
        "wein, weißwein, rotwein, sekt, balsamico, wermut, sherry, portwein, cidre",
        maybe=(12,),
        note="Wine and wine vinegar usually contain more than 10 mg/litre of sulphites.",
    ),
    _p(
        "dried apricots, dried apricot",
        "курага",
        "kuru kayısı, kayısı kurusu",
        "getrocknete aprikosen, trockenaprikosen",
        maybe=(12,),
        note="Bright orange dried apricots are usually sulphured.",
    ),
    _p(
        "surimi, crab sticks, crab stick, seafood sticks",
        "крабов палочк, сурими",
        "yengeç çubuğu, surimi",
        "surimi, krebsfleischimitat",
        contains=(4,),
        maybe=(3, 1, 2),
        note="Crab sticks are made of fish; some contain egg white, wheat starch or crab extract.",
    ),
    _p("tempura", "темпура", "tempura", "tempura", contains=(1,), maybe=(3,)),
    _p("cake, gateau, sponge cake", "кекс", "kek", "biskuit", contains=(1,), maybe=(3, 7)),
    _p(
        "lecithin",
        "лецитин",
        "lesitin",
        "lecithin, =e322",
        maybe=(6,),
        note="Lecithin (E322) is often made from soy; sunflower lecithin is not.",
    ),
    _p(
        "tortilla, wrap, tortilla wrap",
        "тортиль",
        "tortilla, dürüm",
        "tortilla, wrap",
        maybe=(1,),
        note="Wheat tortillas contain gluten; pure corn tortillas do not.",
    ),
    _p(
        "nougat, praline, pralines, amaretti, krokant",
        "нуга, пралине",
        "nuga, pralin",
        "nugat, praline, krokant, amarettini",
        maybe=(8, 7, 3),
    ),
    _p("meringue", "меренг, безе", "beze", "baiser", contains=(3,)),
    _p(
        "seafood, shellfish, frutti di mare",
        "морепродукт",
        "deniz ürünleri, deniz ürünü, kabuklu deniz ürünleri",
        "meeresfrüchte, schalentiere",
        maybe=(2, 14, 4),
        note="'Seafood' and 'shellfish' can mean crustaceans, molluscs or fish: name them.",
    ),
    _p(
        "couscous salad, tabbouleh, tabouleh", "табуле", "kısır", "taboulé, tabouleh", contains=(1,)
    ),
    _p(
        "oat milk, oat drink",
        "овсяное молоко, овсян молок",
        "yulaf sütü",
        "hafermilch, haferdrink",
        contains=(1,),
        note="A plant drink: oats, not milk.",
    ),
    _p(
        "almond milk, almond drink",
        "миндальное молоко, миндальн молок",
        "badem sütü",
        "mandelmilch, mandeldrink",
        contains=(8,),
        note="A plant drink: almonds, not milk.",
    ),
    _p(
        "soy milk, soya milk, soya drink, soy drink",
        "соевое молоко, соев молок",
        "soya sütü",
        "sojamilch, sojadrink",
        contains=(6,),
        note="A plant drink: soy, not milk.",
    ),
    _p(
        "roux",
        "ру",
        "meyane",
        "mehlschwitze, einbrenne",
        contains=(1,),
        maybe=(7,),
        note="Flour cooked in fat, usually butter.",
    ),
    _p(
        "tarhana",
        "тархана",
        "tarhana",
        "tarhana",
        contains=(1, 7),
        note="Dried, fermented mix of flour and yogurt.",
    ),
    _p(
        "turkish delight",
        "лукум",
        "lokum",
        "lokum",
        maybe=(8,),
        note="Plain lokum has none of the 14; many kinds contain pistachios, hazelnuts or walnuts.",
    ),
    # Ambiguous words: the allergens are candidates, the chef decides.
    _p(
        "",
        "",
        "fıstık",
        "",
        maybe=(5, 8),
        note="'Fıstık' alone can mean peanuts (yer fıstığı) or pistachios (antep fıstığı); "
        "write which one.",
    ),
    _p(
        "",
        "",
        "barbunya",
        "",
        maybe=(4,),
        note="'Barbunya' is both red mullet (fish) and borlotti beans; write which one.",
    ),
    _p(
        "",
        "масл",
        "",
        "",
        maybe=(7,),
        note="'Масло' alone can be butter (milk) or a vegetable oil; write which one.",
    ),
    _p(
        "",
        "",
        "yağ",
        "",
        maybe=(7,),
        note="'Yağ' alone can be butter (tereyağı) or an oil; write which one.",
    ),
)

# --- 3. Look-alikes that Annex II does not cover ---------------------------------------


def _x(en: str, ru: str, tr: str, de: str, note: str) -> Entry:
    entry = _p(en, ru, tr, de)
    return Entry(Kind.EXCLUSION, entry.phrases, note=note)


EXCLUSIONS: tuple[Entry, ...] = (
    _x(
        "coconut, coconut milk, coconut cream, coconut oil, desiccated coconut, coconut "
        "flakes, coconut flour",
        "кокос, кокосов молок, кокосов сливк, кокосов масл, кокосов стружк",
        "hindistan cevizi, hindistan cevizi sütü, hindistancevizi, hindistan cevizi yağı",
        "kokos, kokosnuss, kokosmilch, kokosöl, kokosraspeln, kokosflocken, kokosmehl",
        "Coconut is not one of the eight nuts in Annex II (and coconut milk is not milk). "
        "Declaring it voluntarily is up to you.",
    ),
    _x(
        "pine nut, pine nuts, pine kernels, pignoli",
        "кедров орех, кедров орешк",
        "çam fıstığı, çam fıstı",
        "pinienkern, pinienkerne",
        "Pine nuts are seeds and not one of the eight nuts in Annex II. Some guests are "
        "allergic to them; declaring them voluntarily is up to you.",
    ),
    _x(
        "nutmeg",
        "мускатн орех, мускатн",
        "muskat, küçük hindistan cevizi",
        "muskatnuss, muskat",
        "Nutmeg is a seed spice, not one of the eight nuts in Annex II.",
    ),
    _x(
        "chestnut, chestnuts, water chestnut, water chestnuts",
        "каштан",
        "kestane",
        "maroni, marone, maronen, esskastanie, kastanie",
        "Chestnuts are not one of the eight nuts in Annex II.",
    ),
    _x(
        "butternut squash, butternut",
        "баттернат",
        "balkabağı",
        "butternusskürbis, butternut",
        "Butternut squash is a pumpkin, not a nut.",
    ),
    _x(
        "buckwheat, buckwheat flour, soba",
        "гречк, гречнев, гречих",
        "karabuğday",
        "buchweizen, buchweizenmehl",
        "Buckwheat is not a cereal containing gluten. Soba noodles are often mixed with "
        "wheat flour: check the label.",
    ),
    _x(
        "glucose syrup, glucose-fructose syrup, dextrose",
        "глюкозн сироп, глюкозно-фруктозн сироп, декстроз",
        "glikoz şurubu, glukoz şurubu, glikoz şurub, dekstroz",
        "glukosesirup, glucosesirup, dextrose, traubenzucker",
        "Annex II excludes wheat-based glucose syrups including dextrose and glucose syrups "
        "based on barley.",
    ),
    _x(
        "maltodextrin",
        "мальтодекстрин",
        "maltodekstrin",
        "maltodextrin",
        "Annex II excludes wheat-based maltodextrins.",
    ),
    _x(
        "lactitol, =e966",
        "лактит",
        "laktitol",
        "lactit, lactitol",
        "Annex II excludes lactitol from milk.",
    ),
    _x(
        "isinglass",
        "рыбий клей, рыб клей",
        "balık tutkalı",
        "hausenblase",
        "Annex II excludes fish gelatine or isinglass used as a fining agent in beer and wine.",
    ),
    _x(
        "soybean oil, soya oil, soy oil, soya bean oil",
        "соевое масло, соев масл",
        "soya yağı, soya fasulyesi yağı",
        "sojaöl, sojabohnenöl",
        "Annex II excludes fully refined soybean oil and fat. Cold-pressed soybean oil is "
        "not excluded: check the label.",
    ),
    _x(
        "tocopherols, mixed tocopherols, =e306",
        "токоферол",
        "tokoferol",
        "tocopherol, tocopherole",
        "Annex II excludes natural mixed tocopherols (E306) from soybean sources.",
    ),
    _x(
        "cocoa butter",
        "какао-масл, масл какао, какао масл",
        "kakao yağı",
        "kakaobutter",
        "Cocoa butter is a plant fat, not milk.",
    ),
    _x(
        "cream of tartar",
        "винн камень",
        "krem tartar",
        "weinstein, weinsteinbackpulver",
        "Cream of tartar is potassium bitartrate, not cream.",
    ),
    _x(
        "eggplant, egg plant, aubergine",
        "баклажан",
        "patlıcan",
        "aubergine",
        "An aubergine (eggplant) is a vegetable, not egg.",
    ),
    _x(
        "whisky, whiskey, vodka, =gin, brandy, cognac, bourbon",
        "водк, виски, коньяк, бренди",
        "votka, viski, konyak, =rakı, =raki",
        "wodka, whisky, whiskey, weinbrand, cognac, korn",
        "Distilled spirits: Annex II excludes cereals, whey and nuts used for making "
        "alcoholic distillates. Liqueurs and flavoured spirits can contain allergens "
        "added after distilling.",
    ),
    _x(
        "rice milk, rice drink",
        "рисов молок",
        "pirinç sütü",
        "reismilch, reisdrink",
        "A rice drink, not milk.",
    ),
    _x(
        "tiger nut, tiger nuts",
        "чуф",
        "yer bademi",
        "erdmandel, erdmandeln",
        "Tiger nuts are tubers, not one of the eight nuts in Annex II.",
    ),
)

# --- 4. Common ingredients and filler words with none of the 14 allergens -------------
# Only words a recipe really contains: every word that is not in the dictionary is
# reported to the chef as "unknown", so this list is what keeps that report short.

SAFE_WORDS: dict[Language, str] = {
    EN: "water, salt, sea salt, pepper, black pepper, white pepper, sugar, brown sugar, "
    "icing sugar, honey, olive oil, extra virgin olive oil, sunflower oil, vegetable oil, "
    "rapeseed oil, canola oil, corn oil, oil, rice, basmati, risotto rice, potato, "
    "potatoes, sweet potato, tomato, tomatoes, cherry tomatoes, tomato paste, tomato "
    "puree, passata, onion, onions, red onion, spring onion, shallot, leek, garlic, "
    "carrot, lemon, lemon juice, lime, orange, apple, pear, banana, strawberry, "
    "raspberry, blueberry, cherry, grape, grapes, raisins, sultanas, currants, dates, "
    "figs, pomegranate, mango, pineapple, melon, watermelon, peach, apricot, plum, "
    "cucumber, lettuce, romaine, rocket, arugula, spinach, cabbage, kale, broccoli, "
    "cauliflower, zucchini, courgette, pumpkin, squash, mushroom, mushrooms, beetroot, "
    "beet, radish, turnip, fennel, artichoke, asparagus, avocado, olive, olives, capers, "
    "corn, sweetcorn, maize, polenta, cornmeal, corn starch, cornstarch, cornflour, "
    "corn flour, potato starch, rice flour, chickpea flour, gram flour, rice noodles, "
    "rice paper, quinoa, millet, sorghum, amaranth, teff, tapioca, beans, green beans, "
    "kidney beans, black beans, chickpeas, chickpea, lentils, red lentils, peas, "
    "parsley, dill, mint, basil, coriander, cilantro, thyme, oregano, rosemary, sage, "
    "tarragon, chives, bay leaf, bay leaves, cumin, paprika, smoked paprika, chilli, "
    "chili, chilli flakes, cayenne, turmeric, ginger, cinnamon, cloves, cardamom, "
    "vanilla, saffron, sumac, allspice, anise, star anise, fenugreek, curry powder, "
    "herbs, spices, bell pepper, red pepper, green pepper, peppers, jalapeno, beef, "
    "veal, lamb, mutton, pork, chicken, chicken breast, chicken thigh, turkey, duck, "
    "goose, rabbit, venison, mince, minced beef, ground beef, steak, fillet, "
    "meat, liver, gelatine, gelatin, agar, yeast, baking soda, bicarbonate, "
    "cocoa, cocoa powder, coffee, tea, espresso, ice, sparkling water, mineral water, "
    "juice, orange juice, rum, tequila, lemonade, cola, syrup, maple syrup, agave, "
    "molasses, jam, vegetables, fruit, salad leaves, microgreens, sunflower seeds, "
    "pumpkin seeds, flaxseed, linseed, chia, poppy seeds, nigella, oyster mushroom, "
    "oyster mushrooms, tapioca starch, rice starch, fermented, "
    "fresh, chopped, grated, sliced, diced, minced, ground, whole, dried, smoked, roasted, "
    "toasted, cooked, boiled, fried, grilled, baked, steamed, sweet, sour, hot, red, "
    "green, white, black, yellow, cherry, zest, leaves, leaf, powder, extra, virgin, of, "
    "and, with, a, the, pinch, to taste, tbsp, tsp, cup, cups, clove, cloves, bunch, "
    "slice, slices, piece, pieces, handful, large, small, medium, finely, roughly, "
    "optional, for, serving, garnish, frying, deep, pan, homemade, house, organic, "
    "free-range, peeled, seeded, pitted, crushed, halved, quartered, plain, natural, "
    "light, dark, unsalted, salted, flat-leaf, juice of, sprig, sprigs, splash, drizzle",
    RU: "вод, сол, перец, перц, сахар, мёд, мед, оливков масл, подсолнечн масл, "
    "растительн масл, рапсов масл, рис, рисов мук, картоф, картошк, томат, помидор, "
    "томатн паст, лук, лучок, чеснок, чесноч, морков, лимон, лайм, апельсин, яблок, "
    "груш, банан, клубник, малин, вишн, черешн, виноград, изюм, финик, инжир, гранат, "
    "огур, салат, шпинат, капуст, брокколи, кабачк, кабачок, тыкв, гриб, шампиньон, "
    "свёкл, свекл, редис, редьк, фенхел, спарж, авокадо, маслин, оливк, каперс, "
    "кукуруз, кукурузн крахмал, картофельн крахмал, кукурузн мук, нутов мук, киноа, "
    "пшен, фасол, нут, чечевиц, горох, горош, петрушк, укроп, мят, базилик, кинз, "
    "тимьян, чабрец, орегано, розмарин, шалфе, лаврушк, лавров лист, зир, кумин, "
    "паприк, чили, куркум, имбир, корица, корицы, гвоздик, кардамон, ванил, шафран, "
    "сумах, специ, пряност, зелен, говядин, говяж, телятин, баранин, свинин, свин, "
    "курин, куриц, индейк, индюш, утк, утин, кролик, фарш, мяс, мясн, "
    "печён, =печень, =печени, желатин, агар, дрожж, сод, какао, кофе, =чай, лёд, =лед, "
    "сок, ром, сироп, варенье, джем, повидл, овощ, фрукт, семечк, семен, мак, "
    "свеж, рублен, тёрт, терт, молот, сушён, сушен, копчён, копчен, жарен, варён, "
    "варен, запечён, запечен, сладк, кисл, остр, красн, зелён, зелен, =белый, =белая, "
    "=белое, =белые, =белого, =белой, чёрн, черн, вешенк, пастернак, пастил, "
    "жёлт, желт, цедр, лист, порош, =и, =с, =для, по вкус, щепотк, =ст, =ч, =л, ложк, "
    "стакан, зубчик, пучок, ломтик, кусоч, мелк, крупн, домашн, натуральн, сырой, "
    "сырая, сырые, сырое, сыров, отварн, тушён, тушен, маринован, солён, солен, квашен",
    TR: "=su, =suyu, =tuz, karabiber, pul biber, isot, kırmızı biber, toz biber, şeker, "
    "pudra şekeri, =bal, zeytinyağı, zeytinyağ, ayçiçek yağı, sıvı yağ, mısır yağı, "
    "pirinç, pirinç unu, pilavlık, patates, domates, domates salçası, salça, biber "
    "salçası, soğan, taze soğan, sarımsak, havuç, limon, limon suyu, misket limonu, "
    "portakal, elma, armut, muz, çilek, ahududu, vişne, kiraz, üzüm, kuru üzüm, kuş "
    "üzümü, hurma, incir, nar, nar ekşisi, mango, ananas, kavun, karpuz, şeftali, "
    "kayısı, erik, arpacık, keten, bezelye, biraz, salatalık, hıyar, marul, roka, "
    "ıspanak, lahana, brokoli, karnabahar, "
    "kabak, bal kabağı, mantar, pancar, turp, rezene, enginar, kuşkonmaz, avokado, "
    "zeytin, kapari, mısır, mısır unu, mısır nişastası, patates nişastası, nohut unu, "
    "kinoa, darı, fasulye, taze fasulye, barbunya fasulyesi, barbunya pilaki, nohut, "
    "mercimek, kırmızı mercimek, "
    "yeşil mercimek, bezelye, maydanoz, dereotu, nane, fesleğen, kişniş, kekik, "
    "biberiye, adaçayı, defne, kimyon, sumak, zerdeçal, zencefil, tarçın, karanfil, "
    "kakule, vanilya, safran, yenibahar, anason, çörek otu, baharat, biber, sivri biber, "
    "çarliston biber, dolmalık biber, köz biber, közlenmiş biber, jalapeno, dana, "
    "dana eti, kuzu, kuzu eti, koyun, tavuk, tavuk göğsü, hindi, ördek, et, kıyma, "
    "dana kıyma, kuşbaşı, biftek, bonfile, ciğer, jelatin, maya, istiridye mantarı, "
    "karbonat, kakao, kahve, çay, buz, soda, maden suyu, meyve suyu, "
    "şurup, pekmez, reçel, sebze, meyve, ayçiçeği, kabak çekirdeği, keten tohumu, chia, "
    "haşhaş, salep, gül suyu, kuru soğan, yeşillik, et suyu, kemik suyu, tavuk suyu, "
    "taze, doğranmış, rendelenmiş, kıyılmış, kuru, kurutulmuş, közlenmiş, kızarmış, "
    "haşlanmış, fırınlanmış, ızgara, =ve, =ile, için, =az, biraz, tatlı, =acı, "
    "kırmızı, yeşil, beyaz, siyah, sarı, =toz, kabuğu, kabuk, rendesi, yaprak, yaprağı, "
    "dilim, adet, =gr, =kg, =ml, yemek kaşığı, çay kaşığı, su bardağı, tutam, demet, "
    "diş, ince, iri, ev yapımı, doğal, sızma, naneli, limonlu, isteğe bağlı, servis, "
    "süslemek, yarım, çeyrek, bütün, tane, dövülmüş, öğütülmüş, ezilmiş, sote, haşlama, "
    "ılık, soğuk, sıcak, bol, lezzetli",
    DE: "wasser, salz, meersalz, pfeffer, zucker, puderzucker, honig, olivenöl, "
    "sonnenblumenöl, rapsöl, pflanzenöl, öl, reis, reismehl, reisnudeln, kartoffel, "
    "kartoffeln, kartoffelstärke, süßkartoffel, tomate, tomaten, tomatenmark, zwiebel, "
    "frühlingszwiebel, schalotte, lauch, porree, knoblauch, karotte, möhre, möhren, "
    "zitrone, zitronensaft, limette, orange, apfel, birne, banane, erdbeere, himbeere, "
    "heidelbeere, kirsche, traube, weintraube, weintrauben, rosinen, datteln, feigen, "
    "granatapfel, mango, ananas, melone, pfirsich, aprikose, pflaume, gurke, salat, "
    "rucola, spinat, kohl, weißkohl, rotkohl, brokkoli, blumenkohl, zucchini, kürbis, "
    "pilz, pilze, champignon, champignons, rote bete, radieschen, rettich, fenchel, "
    "artischocke, spargel, avocado, olive, oliven, kapern, mais, maismehl, maisstärke, "
    "polenta, quinoa, hirse, kichererbsenmehl, bohnen, kichererbsen, linsen, erbsen, "
    "petersilie, dill, minze, basilikum, koriander, thymian, oregano, rosmarin, salbei, "
    "estragon, schnittlauch, lorbeer, kreuzkümmel, kümmel, paprika, chili, kurkuma, "
    "ingwer, zimt, nelken, kardamom, vanille, safran, sumach, piment, anis, gewürze, "
    "kräuter, gemüse, obst, rind, rindfleisch, kalb, kalbfleisch, lamm, lammfleisch, "
    "schwein, schweinefleisch, huhn, hühnchen, hähnchen, hühnerbrust, pute, truthahn, "
    "ente, gans, kaninchen, hackfleisch, fleisch, leber, austernpilz, ein, eine, "
    "einen, einem, einer, "
    "gelatine, agar, hefe, natron, kakao, kaffee, tee, eiswürfel, mineralwasser, saft, "
    "sirup, ahornsirup, marmelade, konfitüre, sonnenblumenkerne, kürbiskerne, leinsamen, "
    "mohn, frisch, gehackt, gerieben, gemahlen, getrocknet, geräuchert, geröstet, "
    "gekocht, gebraten, gegrillt, gebacken, süß, sauer, scharf, rot, grün, weiß, "
    "schwarz, gelb, abrieb, blätter, pulver, und, mit, für, etwas, prise, =el, =tl, "
    "=g, =kg, =ml, stück, bund, zehe, zehen, scheibe, scheiben, fein, grob, hausgemacht, "
    "natur, nach geschmack, zum, zur, servieren, garnieren, frittieren, braten, "
    "zitronenschale, zesten, kalt, warm, halb, ganz",
}

# Words that never mean "this dish is free of X" for the dictionary: a person checks the
# product specification. They are found by `FREE_FROM` patterns in the matcher.
FREE_FROM_NOTE = (
    "A 'free-from' word does not remove an allergen here: products sold as gluten-free or "
    "lactose-free can still contain an Annex II ingredient (lactose-free milk is still "
    "milk). Check the product specification."
)


def _entries_from_words(words: str, lang: Language, kind: Kind, group: int | None) -> list[Entry]:
    entries = []
    for raw in words.split(","):
        phrase = raw.strip()
        if not phrase:
            continue
        maybe = phrase.endswith("?")
        phrase = phrase.rstrip("?")
        if group is None:
            entries.append(Entry(kind, ((lang, phrase),)))
        elif maybe:
            entries.append(Entry(kind, ((lang, phrase),), maybe=(group,)))
        else:
            entries.append(Entry(kind, ((lang, phrase),), contains=(group,)))
    return entries


def all_entries() -> list[Entry]:
    entries: list[Entry] = []
    for group, by_language in GROUP_WORDS.items():
        for lang, words in by_language.items():
            entries.extend(_entries_from_words(words, lang, Kind.WORD, group))
    entries.extend(PRODUCTS)
    entries.extend(EXCLUSIONS)
    for lang, words in SAFE_WORDS.items():
        entries.extend(_entries_from_words(words, lang, Kind.SAFE, None))
    return entries
