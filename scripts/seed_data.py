"""
Seed the GoodFoods database — a Bangalore-based multi-cuisine restaurant chain.

Chain composition (researched against real Bangalore dining patterns):
  • 5 North Indian Kitchens     — butter chicken, dal, paneer, biryani
  • 4 South Indian Tiffin Rooms — dosa, idli, meals, filter coffee
  • 4 Biryani Houses            — Hyderabadi, Donne, Lucknowi
  • 3 Indo-Chinese              — manchurian, chilli chicken, noodles
  • 3 Mughlai Grills            — kebabs, awadhi gravies, sheermal
  • 2 Coastal Kitchens          — Mangalorean, ghee roast, neer dosa
  • 2 Italian Kitchens          — wood-fired pizza, hand-made pasta
  • 2 Continental Cafes         — all-day brunch, burgers, sandwiches
  = 25 branches across 25 Bangalore neighbourhoods

Prices are in INR and reflect 2025 Bangalore market rates. Dish tags drive
the dish-level search (so "manchurian" finds Indo-Chinese branches,
"biryani" finds Biryani Houses and North Indian Kitchens that serve biryani).

Popularity is drawn from a realistic long-tail distribution; rating and
review_count are derived from popularity so "best of" queries return a
stable, defensible ranking.

Run: python scripts/seed_data.py
"""
import random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import init_db, get_db, NEIGHBORHOOD_COORDS

random.seed(42)

NEIGHBORHOODS = list(NEIGHBORHOOD_COORDS.keys())

NEIGHBORHOOD_ABBREV = {
    "Indiranagar": "IND", "Koramangala": "KOR", "HSR Layout": "HSR",
    "Whitefield": "WHF", "Marathahalli": "MAR", "Bellandur": "BEL",
    "Sarjapur Road": "SJR", "JP Nagar": "JPN", "Jayanagar": "JYN",
    "MG Road": "MGR", "Brigade Road": "BRG", "Church Street": "CHS",
    "Lavelle Road": "LAV", "UB City": "UBC", "Ulsoor": "ULS",
    "Frazer Town": "FRZ", "Richmond Town": "RIC", "Domlur": "DOM",
    "Old Airport Road": "OAR", "Malleshwaram": "MLS", "Rajajinagar": "RJN",
    "Hebbal": "HEB", "Yelahanka": "YLK", "Kalyan Nagar": "KLN",
    "New BEL Road": "NBL",
}

# 8 cuisine concepts — Indian-majority, continental as accents
CUISINES = [
    "North Indian", "South Indian", "Biryani", "Indo-Chinese",
    "Mughlai", "Coastal", "Italian", "Continental",
]

CUISINE_LABEL = {
    "North Indian":  "North Indian Kitchen",
    "South Indian":  "South Indian Tiffin Room",
    "Biryani":       "Biryani House",
    "Indo-Chinese":  "Indo-Chinese",
    "Mughlai":       "Mughlai Grill",
    "Coastal":       "Coastal Kitchen",
    "Italian":       "Italian Kitchen",
    "Continental":   "Continental Cafe",
}

BRANCH_DESCRIPTIONS = {
    "North Indian":  "Punjabi-leaning classics — butter chicken, dal makhani, slow-cooked kebabs, fresh tandoor breads. The kind of meal you'd order for a Sunday family lunch.",
    "South Indian":  "Bangalore's staple breakfast and meals spot — crisp dosas off cast-iron tawas, steam-fluffy idlis, filter coffee in steel tumblers. Open from sunrise.",
    "Biryani":       "Hyderabadi dum, Donne (Bangalore-style) and Lucknowi biryanis cooked in sealed handis. Long-grain basmati, slow-rendered fat, served with mirchi ka salan and raita.",
    "Indo-Chinese":  "The Indo-Chinese canon done loud and hot — gobi manchurian, chilli chicken, hakka noodles, schezwan everything. Wok-fired in seconds.",
    "Mughlai":       "Lucknow and Awadh on a plate — galouti kebabs that dissolve on the tongue, kakori seekh, slow-stewed nihari, sheermal fresh from the tandoor.",
    "Coastal":       "Coastal Karnataka and Mangalorean — chicken ghee roast, kane fry, neer dosa with chicken curry. Coconut, kokum, fresh ground masala.",
    "Italian":       "Wood-fired Neapolitan pizzas, hand-rolled pasta, Tuscan-leaning wine list. Hand-stretched mozzarella, San Marzano sauce, 36-hour-proven dough.",
    "Continental":   "All-day European cafe — flaky croissants in the morning, salads and bowls at lunch, pasta and pan-seared mains after sundown.",
}

# Real-sounding Bangalore street names per neighbourhood
STREETS = {
    "Indiranagar":      ["100 Feet Road", "12th Main", "CMH Road", "Old Madras Road", "Defence Colony 7th Main"],
    "Koramangala":      ["80 Feet Road", "5th Block 7th Main", "4th Block 100ft Road", "Sony World Junction", "6th Block 17th Main"],
    "HSR Layout":       ["27th Main", "17th Cross Sector 3", "19th Main Sector 1", "Outer Ring Road", "5th Sector Service Road"],
    "Whitefield":       ["ITPL Main Road", "Whitefield Main Road", "EPIP Zone", "Hope Farm Junction", "Phoenix Marketcity"],
    "Marathahalli":     ["Outer Ring Road", "Marathahalli Bridge", "Spice Garden Road", "Doddanekundi", "Kundalahalli Gate"],
    "Bellandur":        ["Outer Ring Road", "Bellandur Gate", "Ecospace Road", "Iblur Junction", "Devarabisanahalli"],
    "Sarjapur Road":    ["Sarjapur Main Road", "Haralur Road", "Iblur Cross", "Carmelaram", "Choodasandra"],
    "JP Nagar":         ["24th Main 6th Phase", "Ring Road 5th Phase", "Bannerghatta Main Road", "7th Phase Main", "3rd Phase Service Road"],
    "Jayanagar":        ["11th Main 4th Block", "30th Cross 9th Block", "Kanakapura Road", "Tilak Nagar Main", "South End Circle"],
    "MG Road":          ["Mahatma Gandhi Road", "Trinity Circle", "Cauvery Bhavan", "Anil Kumble Circle", "Plaza Theatre Junction"],
    "Brigade Road":     ["Brigade Road", "Rest House Road", "Residency Road", "Magrath Road", "Brigade Gateway"],
    "Church Street":    ["Church Street", "Museum Road", "St Marks Road", "Wood Street", "Coles Road"],
    "Lavelle Road":     ["Lavelle Road", "Vittal Mallya Road", "Kasturba Road", "Cunningham Road Junction", "Prestige Towers"],
    "UB City":          ["Vittal Mallya Road", "UB City Mall", "Kasturba Road", "Lavelle Road End", "Cubbon Park Edge"],
    "Ulsoor":           ["Halasuru Main Road", "MG Road East End", "Cambridge Road", "Lido Mall Road", "Ulsoor Lake Road"],
    "Frazer Town":      ["Mosque Road", "Hayes Road", "Coles Road", "Wheeler Road", "Promenade Road"],
    "Richmond Town":    ["Richmond Road", "Langford Road", "Hosur Road", "Lakkasandra", "Brigade Road South"],
    "Domlur":           ["Domlur Layout 100ft Road", "Old Airport Road", "Indiranagar Boundary", "ESI Domlur", "Domlur Service Road"],
    "Old Airport Road": ["Old Airport Road", "Konena Agrahara", "HAL Old Airport", "Murugeshpalya", "Wind Tunnel Road"],
    "Malleshwaram":     ["8th Cross Sampige Road", "15th Cross", "Margosa Road", "Mantri Mall Road", "11th Main"],
    "Rajajinagar":      ["West of Chord Road", "1st Block Main", "ESI Hospital Road", "Rajajinagar Industrial Town", "6th Block Service Road"],
    "Hebbal":           ["Outer Ring Road", "Manyata Tech Park", "Bellary Road", "Mekhri Circle", "Esteem Mall Road"],
    "Yelahanka":        ["Doddaballapur Road", "Yelahanka New Town", "Kogilu Cross", "Airport Road", "GKVK Campus Road"],
    "Kalyan Nagar":     ["HRBR Layout 5th Main", "Kammanahalli Main Road", "Banaswadi Main Road", "Outer Ring Road", "OMBR Layout"],
    "New BEL Road":     ["New BEL Road", "Mekhri Circle", "RMV 2nd Stage", "Sanjay Nagar", "MS Ramaiah Road"],
}

# ── Menu templates ────────────────────────────────────────────────────────────
# Tuple: (name, description, category, price_INR, veg, vegan, gluten_free, jain, popular, calories, dish_tags)

MENUS = {
    "North Indian": [
        # Starters
        ("Paneer Tikka",          "Cottage cheese cubes in yogurt-spice marinade, charred in the tandoor",         "Starters", 320, True,  False, True,  False, True,  280, "paneer,tikka,starter,north indian,tandoor,vegetarian"),
        ("Tandoori Chicken (Half)","Bone-in chicken, Kashmiri chilli marinade, slow-roasted over coals",            "Starters", 380, False, False, True,  False, True,  420, "tandoori chicken,tandoor,classic,north indian"),
        ("Chicken Tikka",         "Boneless thigh, hung-curd marinade, smoky char from the tandoor",                "Starters", 340, False, False, True,  False, True,  340, "chicken tikka,starter,tandoor,north indian"),
        ("Hara Bhara Kebab",      "Spinach, peas and cashew patties, crisp outside, soft within",                   "Starters", 280, True,  False, False, True,  False, 240, "kebab,vegetarian,jain,spinach,north indian"),
        ("Murgh Malai Tikka",     "Creamy chicken kebab, hung curd, cheese, cardamom — mild and rich",              "Starters", 360, False, False, True,  False, True,  380, "malai tikka,chicken,kebab,creamy,tandoor"),
        # Vegetarian Mains
        ("Paneer Butter Masala",  "Cottage cheese in tomato-cashew gravy, fenugreek, finished with cream",          "Mains",    360, True,  False, True,  False, True,  520, "paneer,butter masala,classic,vegetarian,north indian"),
        ("Dal Makhani",           "Black lentils slow-cooked overnight, butter, cream, smoked finish",              "Mains",    320, True,  False, True,  False, True,  380, "dal makhani,lentil,classic,vegetarian,north indian"),
        ("Kadai Paneer",          "Cottage cheese with peppers and onions in fresh-ground kadai masala",            "Mains",    360, True,  False, True,  False, True,  480, "paneer,kadai,vegetarian,north indian"),
        ("Palak Paneer",          "Fresh spinach gravy with cottage cheese cubes, garlic tadka",                    "Mains",    340, True,  False, True,  False, True,  420, "palak paneer,spinach,vegetarian,north indian"),
        ("Dal Tadka",             "Yellow dal with cumin-garlic tempering, fresh coriander",                        "Mains",    260, True,  False, True,  True,  True,  300, "dal,lentil,jain,vegan,north indian"),
        ("Chana Masala",          "Chickpeas in onion-tomato gravy with kasoori methi",                             "Mains",    280, True,  True,  True,  False, False, 320, "chana,chickpea,vegan,north indian"),
        # Non-veg Mains
        ("Butter Chicken",        "The classic — tandoori chicken in spiced tomato-cream gravy",                    "Mains",    420, False, False, True,  False, True,  580, "butter chicken,murgh makhani,classic,north indian"),
        ("Chicken Tikka Masala",  "Char-grilled chicken in onion-tomato masala, cream finish",                      "Mains",    420, False, False, True,  False, True,  540, "chicken tikka masala,classic,north indian"),
        ("Mutton Rogan Josh",     "Kashmiri lamb in aromatic gravy with whole spices",                              "Mains",    560, False, False, True,  False, True,  680, "mutton,rogan josh,kashmiri,classic,north indian"),
        ("Chicken Korma",         "Almond-cashew gravy with tender chicken pieces",                                 "Mains",    420, False, False, True,  False, False, 540, "korma,chicken,creamy,north indian"),
        ("Chicken Biryani",       "Dum-cooked basmati with chicken, saffron, served with raita and salan",          "Mains",    360, False, False, True,  False, True,  680, "biryani,chicken,dum,rice,north indian"),
        # Breads & Rice
        ("Butter Naan",           "Soft tandoor-baked bread brushed with butter",                                   "Sides",     60, True,  False, False, False, True,  180, "naan,bread,vegetarian"),
        ("Garlic Naan",           "Naan topped with fresh garlic and coriander",                                    "Sides",     80, True,  False, False, False, True,  200, "garlic naan,bread,vegetarian"),
        ("Tandoori Roti",         "Whole-wheat flatbread baked in the tandoor",                                     "Sides",     40, True,  True,  False, True,  False, 140, "roti,bread,vegan,jain,whole wheat"),
        ("Lachha Paratha",        "Layered flaky paratha, crisp and buttery",                                       "Sides",     70, True,  False, False, False, False, 240, "paratha,bread,vegetarian"),
        ("Jeera Rice",            "Basmati rice tempered with cumin and ghee",                                      "Sides",    180, True,  False, True,  False, True,  280, "jeera rice,vegetarian"),
        # Desserts
        ("Gulab Jamun (2 pc)",    "Milk-solid dumplings soaked in cardamom-rose syrup",                             "Desserts", 120, True,  False, False, False, True,  280, "gulab jamun,dessert,classic"),
        ("Rasmalai",              "Cottage cheese dumplings in saffron-cardamom milk",                              "Desserts", 160, True,  False, False, False, True,  260, "rasmalai,dessert,bengali"),
        ("Gajar Halwa",           "Slow-cooked grated carrot pudding with khoya, ghee, almonds",                    "Desserts", 160, True,  False, False, False, False, 320, "gajar halwa,carrot,dessert,winter"),
        # Drinks
        ("Sweet Lassi",           "Thick yogurt drink, sweet, dusted with cardamom",                                "Drinks",   120, True,  False, True,  False, True,  220, "lassi,sweet,yogurt"),
        ("Masala Chai",           "Spiced black tea with cardamom, ginger, milk",                                   "Drinks",    60, True,  False, True,  False, True,   90, "chai,tea,masala"),
        ("Fresh Lime Soda",       "Sweet or salt, served chilled",                                                  "Drinks",    80, True,  True,  True,  True,  False,  60, "lime soda,drink,vegan"),
    ],
    "South Indian": [
        # Tiffin
        ("Masala Dosa",           "Crisp rice-lentil crepe, potato-onion masala, sambar and three chutneys",        "Mains",    140, True,  False, False, False, True,  420, "masala dosa,dosa,classic,south indian"),
        ("Plain Dosa",            "Thin crisp dosa with sambar and chutneys",                                       "Mains",    100, True,  True,  False, False, True,  320, "dosa,plain,vegan,south indian"),
        ("Rava Dosa",             "Lacy semolina dosa with onion, cumin and curry leaves",                          "Mains",    150, True,  False, False, False, True,  340, "rava dosa,dosa,south indian"),
        ("Set Dosa (3 pc)",       "Three thick fluffy dosas with vegetable kurma",                                  "Mains",    130, True,  False, False, False, False, 380, "set dosa,dosa,south indian"),
        ("Idli (2 pc)",           "Steamed rice-lentil cakes, sambar, coconut chutney",                             "Mains",     70, True,  True,  False, True,  True,  180, "idli,classic,vegan,jain,south indian"),
        ("Medu Vada (2 pc)",      "Crisp lentil doughnuts, sambar, chutney",                                        "Mains",     70, True,  True,  False, True,  True,  220, "vada,medu vada,vegan,south indian"),
        ("Idli-Vada Combo",       "Two idlis, one vada, sambar and chutney trio",                                   "Mains",    110, True,  True,  False, True,  True,  300, "idli vada,combo,vegan,south indian"),
        ("Onion Uttapam",         "Thick pancake topped with onion, chillies, coriander",                           "Mains",    130, True,  True,  False, False, True,  360, "uttapam,onion,vegan,south indian"),
        ("Khara Bath",            "Savoury semolina with vegetables and curry leaves",                              "Starters",  90, True,  False, False, False, True,  280, "khara bath,upma,vegetarian,south indian"),
        ("Kesari Bath",           "Sweet saffron-cardamom semolina with ghee, raisins, cashews",                    "Desserts",  90, True,  False, False, False, True,  320, "kesari bath,sweet,dessert,south indian"),
        ("Bisi Bele Bath",        "Spiced rice-lentil-vegetable casserole, Karnataka style",                        "Mains",    160, True,  False, False, False, True,  420, "bisi bele bath,karnataka,vegetarian,classic"),
        # Meals & Mains
        ("South Indian Veg Meals","Rice, sambar, rasam, two veg, curd, papad, pickle, sweet",                       "Mains",    220, True,  False, False, False, True,  680, "meals,thali,vegetarian,south indian"),
        ("South Indian Non-Veg Meals","Rice, sambar, rasam, chicken curry, fish fry, veg side, curd, papad",        "Mains",    320, False, False, False, False, True,  780, "meals,thali,non veg,south indian"),
        ("Curd Rice",             "Cooled rice in tempered curd, pomegranate, curry leaves",                        "Mains",    120, True,  False, False, False, True,  240, "curd rice,vegetarian,south indian"),
        ("Lemon Rice",            "Rice with mustard, turmeric, peanuts, fresh lemon",                              "Mains",    110, True,  True,  False, False, False, 280, "lemon rice,vegan,south indian"),
        ("Sambar Rice",           "Rice cooked in spiced lentil-vegetable broth",                                   "Mains",    130, True,  True,  False, False, False, 320, "sambar rice,vegan,south indian"),
        ("Chettinad Chicken",     "Tamil Nadu-style chicken with roasted spices and curry leaves",                  "Mains",    340, False, False, True,  False, True,  480, "chettinad,chicken,spicy,south indian"),
        ("Andhra Chicken Curry",  "Spicy Andhra-style chicken in red gravy",                                        "Mains",    340, False, False, True,  False, False, 460, "andhra,chicken,spicy,south indian"),
        # Snacks
        ("Mysore Bonda (3 pc)",   "Crisp lentil fritters with coconut chutney",                                     "Starters",  80, True,  True,  False, False, False, 220, "bonda,fritter,vegan,karnataka"),
        # Desserts
        ("Mysore Pak",            "Karnataka classic — gram flour, ghee, sugar, melt-in-mouth",                     "Desserts",  80, True,  False, False, False, True,  240, "mysore pak,sweet,dessert,karnataka"),
        ("Paal Payasam",          "Slow-cooked milk-rice pudding with cardamom",                                    "Desserts", 120, True,  False, False, False, False, 280, "payasam,kheer,dessert,south indian"),
        # Drinks
        ("Filter Coffee",         "Decoction brewed in steel filter, frothy with hot milk",                         "Drinks",    50, True,  False, True,  False, True,   80, "filter coffee,coffee,classic,south indian"),
        ("Masala Buttermilk",     "Spiced cool buttermilk with ginger, curry leaves",                               "Drinks",    50, True,  False, True,  False, False,  60, "buttermilk,chaas,south indian"),
        ("Tender Coconut Water",  "Fresh tender coconut, served with the kernel",                                   "Drinks",    80, True,  True,  True,  True,  False,  40, "tender coconut,coconut water,vegan"),
    ],
    "Biryani": [
        # The core — biryanis
        ("Hyderabadi Chicken Biryani","Long-grain basmati, dum-cooked with marinated chicken, saffron, fried onions","Mains",    340, False, False, True,  False, True,  720, "biryani,chicken,hyderabadi,dum,classic"),
        ("Hyderabadi Mutton Biryani","Goat on the bone, slow-cooked in sealed handi with whole spices",               "Mains",    480, False, False, True,  False, True,  840, "biryani,mutton,hyderabadi,dum,classic"),
        ("Donne Chicken Biryani", "Bangalore-style biryani in palm-leaf cup, jeera samba rice",                     "Mains",    280, False, False, True,  False, True,  680, "biryani,chicken,donne,bangalore,classic"),
        ("Donne Mutton Biryani",  "Bangalore-style mutton biryani, fragrant short-grain rice",                      "Mains",    440, False, False, True,  False, True,  780, "biryani,mutton,donne,bangalore"),
        ("Lucknowi Mutton Biryani","Awadhi-style with mild spices, kewra water, foiled and dum-cooked",             "Mains",    520, False, False, True,  False, False, 820, "biryani,mutton,lucknowi,awadhi"),
        ("Andhra Chicken Biryani","Spicy Andhra-style biryani with extra heat",                                     "Mains",    320, False, False, True,  False, True,  720, "biryani,chicken,andhra,spicy"),
        ("Veg Dum Biryani",       "Mixed vegetables in fragrant basmati, sealed-handi cooked",                      "Mains",    260, True,  False, True,  False, True,  580, "biryani,vegetarian,veg dum"),
        ("Egg Biryani",           "Boiled eggs in spiced basmati with caramelised onions",                          "Mains",    240, False, False, True,  False, False, 560, "biryani,egg"),
        ("Prawn Biryani",         "Marinated prawns in dum biryani, served with raita",                             "Mains",    480, False, False, True,  False, False, 640, "biryani,prawn,seafood"),
        ("Paneer Biryani",        "Cottage cheese in dum biryani with cashew, mint, coriander",                     "Mains",    280, True,  False, True,  False, False, 620, "biryani,paneer,vegetarian"),
        # Sides & Kebabs
        ("Chicken 65",            "Crisp red-batter chicken with curry leaves and green chilli",                    "Starters", 320, False, False, False, False, True,  420, "chicken 65,starter,crispy,south indian"),
        ("Chicken Lollipop (4 pc)","Frenched chicken wing drumettes, hot sauce glaze",                              "Starters", 280, False, False, False, False, True,  360, "chicken lollipop,starter,spicy"),
        ("Apollo Fish",           "Boneless fish fry, Andhra spices, lemon",                                        "Starters", 320, False, False, True,  False, False, 380, "apollo fish,fish fry,andhra,seafood"),
        ("Mutton Pepper Fry",     "Mutton with crushed black pepper, curry leaves",                                 "Starters", 420, False, False, True,  False, True,  480, "mutton pepper fry,starter,spicy"),
        ("Galouti Kebab",         "Lucknowi melt-in-mouth minced mutton patties",                                   "Starters", 420, False, False, True,  False, False, 320, "galouti kebab,kebab,mutton,lucknowi"),
        ("Mirchi ka Salan",       "Peanut-sesame gravy with whole chillies, biryani's traditional partner",         "Sides",    140, True,  True,  True,  False, True,  220, "salan,mirchi,biryani side,vegan"),
        ("Raita",                 "Curd with cucumber, onion, roasted cumin, mint",                                 "Sides",     80, True,  False, True,  False, True,   80, "raita,curd,side"),
        # Desserts
        ("Double ka Meetha",      "Hyderabadi bread pudding in saffron milk",                                       "Desserts", 140, True,  False, False, False, True,  380, "double ka meetha,hyderabadi,dessert"),
        ("Qubani ka Meetha",      "Stewed dried apricots with cream",                                               "Desserts", 160, True,  False, True,  False, False, 280, "qubani,apricot,hyderabadi,dessert"),
        # Drinks
        ("Sulaimani Chai",        "Spiced black tea with lemon, served in glass tumbler",                           "Drinks",    60, True,  True,  True,  True,  True,   30, "sulaimani,chai,tea,vegan"),
        ("Irani Chai",            "Sweet milky tea, Hyderabadi style",                                              "Drinks",    70, True,  False, True,  False, True,  120, "irani chai,tea,hyderabadi"),
        ("Lassi (Sweet)",         "Thick yogurt drink, classic accompaniment",                                      "Drinks",   120, True,  False, True,  False, True,  220, "lassi,yogurt,sweet"),
    ],
    "Indo-Chinese": [
        # Starters
        ("Gobi Manchurian (Dry)", "Cauliflower florets in spicy garlic-soy glaze, the Bangalore staple",            "Starters", 220, True,  True,  False, False, True,  340, "gobi manchurian,manchurian,vegetarian,vegan,classic,indo chinese"),
        ("Paneer Manchurian (Dry)","Cottage cheese cubes in tangy manchurian sauce",                                "Starters", 280, True,  False, False, False, True,  420, "paneer manchurian,manchurian,vegetarian,indo chinese"),
        ("Chilli Paneer (Dry)",   "Crispy paneer in green chilli-soy-garlic toss",                                  "Starters", 280, True,  False, False, False, True,  440, "chilli paneer,paneer,spicy,vegetarian,indo chinese"),
        ("Chilli Chicken (Dry)",  "Battered chicken cubes in green chilli, capsicum, onion",                        "Starters", 320, False, False, False, False, True,  480, "chilli chicken,spicy,classic,indo chinese"),
        ("Chicken Manchurian (Dry)","Crisp chicken balls in dark manchurian sauce",                                 "Starters", 320, False, False, False, False, True,  460, "chicken manchurian,manchurian,classic,indo chinese"),
        ("Crispy Honey Chilli Potato","Sweet-spicy crisp potato fingers in honey-chilli glaze",                     "Starters", 240, True,  False, False, False, True,  420, "honey chilli potato,vegetarian,crispy,indo chinese"),
        ("Dragon Chicken",        "Crisp chicken in dark spicy soy with cashew nuts",                               "Starters", 360, False, False, False, False, True,  520, "dragon chicken,spicy,indo chinese"),
        ("Crispy Corn Pepper Salt","Battered corn kernels, pepper-salt seasoning, fried curry leaves",              "Starters", 240, True,  False, False, False, True,  380, "crispy corn,corn,vegetarian,indo chinese"),
        # Soups
        ("Veg Manchow Soup",      "Thick brown soup with crisp fried noodles on top",                               "Starters", 140, True,  True,  False, False, True,  220, "manchow soup,soup,vegan,vegetarian,indo chinese"),
        ("Chicken Manchow Soup",  "Spicy brown soup with shredded chicken, crisp noodles",                          "Starters", 180, False, False, False, False, True,  280, "manchow soup,chicken,soup,indo chinese"),
        ("Hot & Sour Veg Soup",   "Classic tangy-spicy clear soup with vegetables",                                 "Starters", 140, True,  True,  False, False, True,  180, "hot and sour,soup,vegan,indo chinese"),
        ("Sweet Corn Chicken Soup","Velvety corn soup with shredded chicken",                                       "Starters", 180, False, False, False, False, False, 240, "sweet corn,soup,chicken,indo chinese"),
        # Noodles & Rice
        ("Veg Hakka Noodles",     "Stir-fried noodles with mixed vegetables, soy",                                  "Mains",    220, True,  True,  False, False, True,  520, "hakka noodles,noodles,vegan,vegetarian,classic,indo chinese"),
        ("Chicken Hakka Noodles", "Hakka noodles with shredded chicken, vegetables",                                "Mains",    280, False, False, False, False, True,  580, "hakka noodles,noodles,chicken,indo chinese"),
        ("Schezwan Veg Noodles",  "Noodles tossed in fiery schezwan paste",                                         "Mains",    240, True,  True,  False, False, True,  540, "schezwan noodles,noodles,spicy,vegan,indo chinese"),
        ("Schezwan Chicken Noodles","Spicy schezwan noodles with chicken",                                          "Mains",    300, False, False, False, False, True,  600, "schezwan,noodles,chicken,spicy,indo chinese"),
        ("Veg Fried Rice",        "Wok-fried rice with vegetables, soy, scallions",                                 "Mains",    200, True,  True,  False, False, True,  520, "fried rice,vegan,vegetarian,indo chinese"),
        ("Chicken Fried Rice",    "Wok-fried rice with chicken, egg, vegetables",                                   "Mains",    260, False, False, False, False, True,  580, "fried rice,chicken,classic,indo chinese"),
        ("Triple Schezwan Rice",  "Fried rice topped with noodles, schezwan gravy and crispy garnish",              "Mains",    320, True,  False, False, False, True,  720, "triple schezwan,rice,spicy,indo chinese"),
        ("American Chopsuey",     "Crispy fried noodles topped with sweet-sour vegetable gravy",                    "Mains",    280, True,  False, False, False, True,  680, "chopsuey,american chopsuey,classic,indo chinese"),
        # Gravies
        ("Kung Pao Chicken",      "Diced chicken with peanuts, dried chillies, soy",                                "Mains",    360, False, False, False, False, False, 480, "kung pao,chicken,spicy,indo chinese"),
        ("Schezwan Chicken Gravy","Chicken in dark spicy schezwan gravy",                                           "Mains",    360, False, False, False, False, True,  520, "schezwan chicken,gravy,spicy,indo chinese"),
        ("Manchurian Gravy (Veg)","Veg manchurian balls in dark soy-garlic gravy",                                  "Mains",    260, True,  False, False, False, False, 460, "manchurian gravy,vegetarian,indo chinese"),
        # Drinks
        ("Lemon Iced Tea",        "Chilled black tea with lemon, mint, sugar syrup",                                "Drinks",   120, True,  True,  True,  True,  False,  80, "iced tea,lemon,vegan,drink"),
        ("Fresh Lime Soda",       "Sweet, salt, or mix — chilled and fresh",                                        "Drinks",    80, True,  True,  True,  True,  False,  60, "lime soda,drink,vegan"),
    ],
    "Mughlai": [
        # Kebabs (the heart of the menu)
        ("Galouti Kebab",         "Lucknowi melt-in-mouth minced mutton with 100+ spices",                          "Starters", 440, False, False, True,  False, True,  340, "galouti,kebab,mutton,lucknowi,classic,mughlai"),
        ("Tunday Kebab",          "Lucknow's iconic soft mutton kebab, slow-cooked on griddle",                     "Starters", 420, False, False, True,  False, True,  320, "tunday,kebab,mutton,lucknowi,classic"),
        ("Kakori Kebab",          "Smooth seekh kebab from Awadh, fine-minced mutton",                              "Starters", 460, False, False, True,  False, True,  360, "kakori,seekh,kebab,mutton,awadhi"),
        ("Murgh Reshmi Kebab",    "Silky chicken kebab, cream and cheese marinade",                                 "Starters", 380, False, False, True,  False, True,  380, "reshmi kebab,chicken,creamy,mughlai"),
        ("Boti Kebab",            "Boneless mutton chunks in rich yogurt-saffron marinade",                         "Starters", 440, False, False, True,  False, False, 420, "boti kebab,mutton,kebab,mughlai"),
        ("Burrah Kebab",          "Lamb chops, marinated overnight, charred on coals",                              "Starters", 520, False, False, True,  False, True,  580, "burrah kebab,lamb chop,mughlai"),
        ("Shami Kebab",           "Patty of minced mutton, chana dal, whole spices",                                "Starters", 320, False, False, False, False, False, 280, "shami kebab,kebab,mutton,mughlai"),
        ("Murgh Tikka",           "Bone-in chicken in tandoori marinade",                                           "Starters", 360, False, False, True,  False, True,  340, "chicken tikka,tandoor,mughlai"),
        # Mains
        ("Mughlai Chicken Korma", "Chicken in cashew-yogurt gravy with rose water, saffron",                        "Mains",    440, False, False, True,  False, True,  580, "korma,chicken,mughlai,creamy,classic"),
        ("Mutton Nihari",         "Slow-stewed mutton in marrow-rich gravy, ginger garnish",                        "Mains",    520, False, False, True,  False, True,  680, "nihari,mutton,slow cooked,mughlai,classic"),
        ("Murgh Musallam",        "Whole chicken in saffron-cashew gravy, traditional preparation",                 "Mains",    620, False, False, True,  False, False, 820, "musallam,chicken,whole chicken,mughlai"),
        ("Lamb Korma",            "Lamb in almond-cream-saffron gravy, slow-cooked",                                "Mains",    580, False, False, True,  False, True,  720, "korma,lamb,creamy,mughlai"),
        ("Awadhi Mutton Biryani", "Lucknowi-style biryani, mild and aromatic, dum-cooked",                          "Mains",    520, False, False, True,  False, True,  820, "biryani,mutton,awadhi,lucknowi,dum"),
        ("Murgh Awadhi",          "Chicken in subtle awadhi gravy with saffron and rose",                           "Mains",    460, False, False, True,  False, False, 540, "chicken,awadhi,mughlai"),
        ("Tehari (Veg Biryani)",  "Awadhi vegetarian biryani with potato, peas, whole spices",                      "Mains",    280, True,  False, True,  False, False, 620, "tehari,biryani,vegetarian,awadhi"),
        # Breads
        ("Sheermal",              "Saffron-milk leavened bread, slightly sweet",                                    "Sides",     80, True,  False, False, False, True,  220, "sheermal,bread,saffron,mughlai"),
        ("Roomali Roti",          "Paper-thin wheat bread, traditional accompaniment to kebabs",                    "Sides",     60, True,  True,  False, True,  True,  120, "roomali,bread,thin,vegan,jain"),
        ("Khasta Naan",           "Crisp layered naan with kalonji seeds",                                          "Sides",     90, True,  False, False, False, False, 240, "khasta naan,bread,mughlai"),
        # Desserts
        ("Sheer Khurma",          "Vermicelli pudding with dates, dry fruits — Eid classic",                        "Desserts", 160, True,  False, False, False, True,  340, "sheer khurma,dessert,mughlai,eid"),
        ("Shahi Tukda",           "Saffron-milk-soaked fried bread with rabri and pistachio",                       "Desserts", 160, True,  False, False, False, True,  420, "shahi tukda,dessert,mughlai,classic"),
        ("Phirni",                "Slow-cooked rice flour pudding, cardamom, served in clay pot",                   "Desserts", 140, True,  False, False, False, False, 280, "phirni,dessert,rice pudding,mughlai"),
    ],
    "Coastal": [
        # Mangalorean / coastal Karnataka starters
        ("Chicken Ghee Roast",    "Mangalore classic — chicken in red byadgi chilli-ghee paste",                    "Starters", 380, False, False, True,  False, True,  520, "ghee roast,chicken,mangalorean,classic,coastal"),
        ("Mutton Pepper Fry",     "Mutton tossed with crushed pepper, coconut, curry leaves",                       "Starters", 440, False, False, True,  False, True,  540, "mutton pepper fry,coastal,mangalorean"),
        ("Kane Rava Fry",         "Lady fish in semolina crust, shallow-fried",                                     "Starters", 420, False, False, False, False, True,  380, "kane fish,fish fry,mangalorean,seafood"),
        ("Anjal Tawa Fry",        "Seer fish in coastal masala, griddle-cooked",                                    "Starters", 520, False, False, True,  False, True,  420, "anjal fish,seer fish,tawa fry,mangalorean,seafood"),
        ("Prawn Sukka",           "Dry-roasted prawns with coconut, kokum, ground masala",                          "Starters", 420, False, False, True,  False, True,  380, "prawn sukka,coastal,mangalorean,seafood"),
        ("Chicken Sukka",         "Dry chicken with grated coconut, curry leaves, kokum",                           "Starters", 360, False, False, True,  False, True,  420, "chicken sukka,mangalorean,coastal,classic"),
        # Mains
        ("Mangalorean Fish Curry","Pomfret in coconut-kokum curry with chilli, coriander",                          "Mains",    480, False, False, True,  False, True,  520, "fish curry,coastal,mangalorean,seafood,pomfret"),
        ("Prawn Gassi",           "Mangalore prawn curry in coconut-tamarind gravy",                                "Mains",    460, False, False, True,  False, True,  480, "prawn gassi,coastal,mangalorean,seafood"),
        ("Crab Masala",           "Whole crab in red coastal masala — eat with hands",                              "Mains",    620, False, False, True,  False, False, 540, "crab,coastal,seafood,mangalorean"),
        ("Kori Rotti",            "Mangalorean — chicken curry over crisp rice flake rotis",                        "Mains",    340, False, False, True,  False, True,  580, "kori rotti,mangalorean,classic,chicken"),
        ("Chicken Pulimunchi",    "Tangy-spicy chicken with tamarind and red chillies",                             "Mains",    380, False, False, True,  False, False, 460, "pulimunchi,chicken,coastal,mangalorean"),
        ("Coastal Veg Curry",     "Mixed vegetables in coconut-curry leaf gravy",                                   "Mains",    280, True,  True,  True,  False, False, 320, "coastal veg,vegan,vegetarian,mangalorean"),
        ("Egg Curry (Mangalore)", "Boiled eggs in spicy coconut gravy",                                             "Mains",    260, False, False, True,  False, False, 380, "egg curry,coastal,mangalorean"),
        # Breads & Rice
        ("Neer Dosa (3 pc)",      "Lacy thin rice-water crepes, served with chicken curry or chutney",              "Sides",    130, True,  True,  False, False, True,  280, "neer dosa,mangalorean,vegan,classic,coastal"),
        ("Pundi (Steam Dumplings)","Rice-flour steamed dumplings with chicken curry",                               "Sides",    160, True,  True,  False, False, False, 240, "pundi,mangalorean,vegan,coastal"),
        ("Goli Baje (3 pc)",      "Fluffy maida-curd fritters, an iconic Mangalore tea-time snack",                 "Starters",  80, True,  False, False, False, True,  280, "goli baje,mangalorean,fritter,snack"),
        ("Plain Rice (Brown)",    "Coastal Karnataka short-grain matta rice",                                       "Sides",    120, True,  True,  True,  True,  False, 280, "rice,matta,vegan,coastal"),
        # Desserts
        ("Gadbad Ice Cream",      "Mangalorean multi-layer ice cream with fruits, jelly, nuts — a Bangalore favourite", "Desserts", 240, True, False, False, False, True,  520, "gadbad,ice cream,mangalorean,classic,dessert"),
        ("Halbai",                "Slow-cooked rice flour-jaggery-coconut sweet, ghee-rich",                        "Desserts", 120, True,  False, False, False, False, 320, "halbai,coastal,karnataka,dessert"),
        # Drinks
        ("Solkadhi",              "Chilled coconut-kokum drink, digestive, pink-hued",                              "Drinks",   100, True,  True,  True,  True,  False,  80, "solkadhi,coastal,vegan,drink"),
        ("Filter Coffee",         "Strong decoction with hot milk, frothy",                                         "Drinks",    50, True,  False, True,  False, True,   80, "filter coffee,coffee,south indian"),
    ],
    "Italian": [
        # Starters
        ("Bruschetta al Pomodoro","Toasted ciabatta, San Marzano tomatoes, basil, EVOO",                            "Starters", 320, True,  True,  False, True,  True,  220, "bruschetta,italian,vegetarian,vegan,starter"),
        ("Caprese di Bufala",     "Imported buffalo mozzarella, heirloom tomato, basil",                            "Starters", 460, True,  False, True,  True,  True,  310, "caprese,salad,italian,vegetarian"),
        ("Calamari Fritti",       "Crispy fried calamari, lemon aioli, marinara",                                   "Starters", 440, False, False, False, False, False, 290, "calamari,seafood,italian,fried"),
        ("Funghi al Forno",       "Baked portobello, garlic confit, taleggio, truffle oil",                         "Starters", 420, True,  False, True,  False, False, 280, "mushroom,italian,vegetarian,baked"),
        # Pizza
        ("Margherita Pizza",      "Fior di latte, San Marzano sauce, fresh basil, EVOO",                            "Mains",    420, True,  False, False, True,  True,  720, "pizza,margherita,italian,vegetarian,classic"),
        ("Pepperoni Pizza",       "Spicy chicken pepperoni, mozzarella, oregano",                                   "Mains",    560, False, False, False, False, True,  890, "pizza,pepperoni,italian,meat"),
        ("Funghi e Tartufo Pizza","Mixed mushrooms, mozzarella, truffle oil, rocket",                               "Mains",    620, True,  False, False, False, True,  820, "pizza,mushroom,truffle,italian,vegetarian"),
        ("Quattro Formaggi",      "Mozzarella, gorgonzola, fontina, parmigiano",                                    "Mains",    580, True,  False, False, True,  False, 940, "pizza,cheese,italian,vegetarian,white"),
        # Pasta
        ("Spaghetti Carbonara",   "Guanciale, Pecorino Romano, egg yolk, black pepper — no cream",                  "Mains",    540, False, False, False, False, True,  720, "pasta,carbonara,italian"),
        ("Penne all'Arrabbiata",  "Penne, garlic, chilli, San Marzano tomato, parsley",                             "Mains",    460, True,  True,  False, True,  False, 580, "pasta,penne,arrabbiata,italian,spicy,vegan"),
        ("Pappardelle al Ragù",   "Wide ribbon pasta, slow-cooked ragù, parmigiano",                                "Mains",    580, False, False, False, False, True,  780, "pasta,ragu,italian"),
        ("Mushroom Risotto",      "Carnaroli rice, porcini, parmigiano, white truffle oil",                         "Mains",    580, True,  False, True,  False, True,  680, "risotto,mushroom,italian,vegetarian"),
        # Desserts
        ("Tiramisu",              "Espresso-soaked savoiardi, mascarpone, cocoa, marsala",                          "Desserts", 360, True,  False, False, True,  True,  420, "tiramisu,dessert,italian,coffee"),
        ("Panna Cotta",           "Vanilla cream, wild berry coulis, mint",                                         "Desserts", 320, True,  False, True,  True,  False, 310, "panna cotta,dessert,italian"),
        # Drinks
        ("Aperol Spritz",         "Aperol, Prosecco, soda, orange",                                                 "Drinks",   460, True,  True,  True,  True,  True,  160, "spritz,aperol,cocktail,italian"),
        ("Negroni",               "Campari, gin, sweet vermouth, orange peel",                                      "Drinks",   500, True,  True,  True,  True,  True,  180, "negroni,cocktail,italian"),
        ("Espresso",              "Double-shot Italian espresso",                                                   "Drinks",   180, True,  True,  True,  True,  False,   5, "espresso,coffee,italian"),
    ],
    "Continental": [
        # All-day cafe
        ("Eggs Benedict",         "Poached eggs, ham, hollandaise on English muffin",                               "Mains",    420, False, False, False, False, True,  620, "eggs benedict,brunch,continental,classic"),
        ("Avocado Toast",         "Smashed avocado, sourdough, chilli flakes, poached egg",                         "Mains",    400, False, False, False, False, True,  480, "avocado toast,brunch,continental"),
        ("Belgian Waffle",        "Crisp Liège waffle, maple syrup, berries, whipped cream",                        "Mains",    380, True,  False, False, True,  True,  580, "waffle,brunch,sweet,continental"),
        ("Classic Cheeseburger",  "Beef patty, cheddar, lettuce, tomato, brioche, fries",                           "Mains",    480, False, False, False, False, True,  920, "burger,cheeseburger,american,beef"),
        ("Chicken Burger",        "Buttermilk-fried chicken, slaw, pickles, brioche",                               "Mains",    420, False, False, False, False, True,  860, "burger,chicken,fried"),
        ("Beyond Burger (Vegan)", "Plant-based patty, vegan cheese, avocado, lettuce",                              "Mains",    560, True,  True,  False, True,  False, 720, "burger,vegan,vegetarian,plant based"),
        ("Mediterranean Bowl",    "Quinoa, roasted veg, feta, olives, hummus, lemon-tahini",                        "Mains",    480, True,  False, True,  True,  True,  520, "bowl,quinoa,mediterranean,vegetarian,healthy"),
        ("Buddha Bowl",           "Brown rice, edamame, avocado, chickpeas, pickled veg, tahini",                   "Mains",    460, True,  True,  False, True,  True,  580, "bowl,buddha,vegan,vegetarian,healthy"),
        ("Smoked Salmon Bagel",   "Cured salmon, cream cheese, capers, dill, NY bagel",                             "Mains",    540, False, False, False, False, True,  580, "salmon,bagel,brunch,continental"),
        ("Pesto Pasta",           "Penne, fresh basil pesto, pine nuts, parmesan, cherry tomatoes",                 "Mains",    440, True,  False, False, False, True,  680, "pasta,pesto,continental,vegetarian"),
        ("Grilled Chicken Caesar","Romaine, anchovy dressing, croutons, parmesan, grilled chicken",                 "Mains",    480, False, False, False, False, True,  480, "salad,caesar,chicken,continental"),
        # Sides
        ("Truffle Fries",         "Hand-cut fries, truffle oil, parmesan",                                          "Sides",    280, True,  False, False, True,  True,  480, "fries,truffle,vegetarian,sides"),
        ("Garden Salad",          "Mixed leaves, cucumber, cherry tomato, vinaigrette",                             "Sides",    260, True,  True,  True,  True,  False, 180, "salad,vegan,sides"),
        # Desserts
        ("Chocolate Lava Cake",   "Warm dark chocolate cake, molten centre, vanilla ice cream",                     "Desserts", 360, True,  False, False, True,  True,  680, "lava cake,chocolate,dessert,continental"),
        ("New York Cheesecake",   "Baked vanilla cheesecake, biscuit base, berry compote",                          "Desserts", 360, True,  False, False, True,  True,  520, "cheesecake,dessert,continental,classic"),
        # Drinks
        ("Cappuccino",            "Double espresso, steamed milk, fine foam",                                       "Drinks",   180, True,  False, True,  False, True,  120, "cappuccino,coffee,continental"),
        ("Cold Brew",             "12-hour cold-brewed coffee, single origin, served black",                        "Drinks",   220, True,  True,  True,  True,  True,   10, "cold brew,coffee,continental"),
        ("Fresh Orange Juice",    "Hand-pressed Valencia oranges, no sugar",                                        "Drinks",   200, True,  True,  True,  True,  False, 110, "orange juice,fresh,continental,non alcoholic"),
        ("House White (Glass)",   "Sauvignon Blanc — crisp, citrus and gooseberry",                                 "Drinks",   460, True,  True,  True,  True,  False, 130, "wine,white,continental"),
        ("House Red (Glass)",     "Shiraz — medium-bodied, plum and pepper",                                        "Drinks",   460, True,  True,  True,  True,  False, 140, "wine,red,continental"),
    ],
}


# ── Realistic popularity distribution ────────────────────────────────────────
def _derive_rating(pop_score: float) -> float:
    base = 3.2 + (pop_score / 100.0) * 1.6
    noise = random.uniform(-0.15, 0.15)
    return round(max(3.0, min(4.9, base + noise)), 1)


def _derive_reviews(pop_score: float) -> int:
    base = 40 + (pop_score / 100.0) ** 1.5 * 2400
    noise = random.uniform(0.7, 1.3)
    return int(max(20, base * noise))


def _draw_popularity() -> float:
    bucket = random.random()
    if bucket < 0.20:
        return round(random.uniform(82, 97), 1)   # flagship
    if bucket < 0.70:
        return round(random.uniform(55, 81), 1)   # middle
    return round(random.uniform(30, 54), 1)       # lower tier


def _build_dish_tags(name: str, cuisine: str, raw_tags: str, veg: bool, vegan: bool, gf: bool) -> str:
    parts = {t.strip().lower() for t in (raw_tags or "").split(",") if t.strip()}
    parts.add(cuisine.lower())
    if veg:   parts.add("vegetarian")
    if vegan: parts.add("vegan")
    if gf:    parts.add("gluten free")
    return ",".join(sorted(parts))


# ── Branch distribution — Indian-majority ──────────────────────────────────────
# 25 branches total. North/South Indian + Biryani dominate; continental is small.
BRANCHES_BY_CUISINE = {
    "North Indian": 5,
    "South Indian": 4,
    "Biryani":      4,
    "Indo-Chinese": 3,
    "Mughlai":      3,
    "Coastal":      2,
    "Italian":      2,
    "Continental":  2,
}
assert sum(BRANCHES_BY_CUISINE.values()) == 25, "branch distribution must total 25"


def seed_branches_and_menus(conn):
    """Wipe and rebuild branches + menus. Idempotent — safe to run repeatedly."""
    conn.execute("DELETE FROM menu_items")
    conn.execute("DELETE FROM reservations")
    conn.execute("DELETE FROM occasion_crm")
    conn.execute("DELETE FROM dropoffs")
    conn.execute("DELETE FROM packages")
    conn.execute("DELETE FROM agent_traces")
    conn.execute("DELETE FROM agent_turns")
    conn.execute("DELETE FROM search_failures")
    conn.execute("DELETE FROM competitor_mentions")
    conn.execute("DELETE FROM branches")

    hood_seq: dict = {}
    all_branch_rows = []
    all_menu_rows = []

    for cuisine in CUISINES:
        count = BRANCHES_BY_CUISINE[cuisine]
        hoods = random.sample(NEIGHBORHOODS, count)

        for hood in hoods:
            hood_seq.setdefault(hood, 0)
            hood_seq[hood] += 1
            code = f"GF-{NEIGHBORHOOD_ABBREV[hood]}-{hood_seq[hood]:02d}"
            name = f"GoodFoods {hood} — {CUISINE_LABEL[cuisine]}"

            # Coordinates: jitter ~400m around the neighbourhood centroid
            base_lat, base_lon = NEIGHBORHOOD_COORDS[hood]
            lat = round(base_lat + random.uniform(-0.004, 0.004), 6)
            lon = round(base_lon + random.uniform(-0.004, 0.004), 6)

            num_str = random.randint(10, 999)
            street  = random.choice(STREETS.get(hood, ["Main Road"]))
            address = f"{num_str} {street}, {hood}, Bangalore"
            phone = f"+91 80 {random.randint(2200,4999)} {random.randint(1000,9999)}"

            # Realistic seating by cuisine
            if cuisine == "South Indian":
                capacity = random.choice([50, 60, 70, 80, 90])   # tiffin rooms — big
            elif cuisine == "Biryani":
                capacity = random.choice([60, 70, 80, 100, 120]) # biryani houses — big
            elif cuisine in ("Italian", "Continental"):
                capacity = random.choice([40, 50, 60, 70])       # smaller, more intimate
            elif cuisine == "Mughlai":
                capacity = random.choice([60, 80, 100])          # mid-upmarket
            else:
                capacity = random.choice([50, 60, 70, 80, 100])
            tables = max(8, capacity // 4)

            popularity = _draw_popularity()
            rating  = _derive_rating(popularity)
            reviews = _derive_reviews(popularity)

            # Price tiers by cuisine — realistic for Bangalore
            if cuisine == "South Indian":
                price = random.choice([1, 1, 2])                 # tiffin places skew cheap
            elif cuisine == "Indo-Chinese":
                price = random.choice([2, 2, 3])
            elif cuisine in ("North Indian", "Biryani", "Coastal"):
                price = random.choice([2, 2, 3])
            elif cuisine == "Mughlai":
                price = random.choice([3, 3, 4])                 # upmarket Indian
            elif cuisine == "Italian":
                price = random.choice([3, 3, 4])
            elif cuisine == "Continental":
                price = random.choice([2, 3, 3])
            else:
                price = random.choice([2, 3])

            # Dietary flags — what's actually true per cuisine
            veg = 1
            # Vegan options
            if cuisine in ("South Indian", "Continental", "Italian"):
                vegan = 1 if random.random() < 0.80 else 0
            elif cuisine in ("North Indian", "Indo-Chinese", "Coastal"):
                vegan = 1 if random.random() < 0.55 else 0
            else:
                vegan = 1 if random.random() < 0.30 else 0
            gf = 1 if random.random() < 0.60 else 0
            # Halal — Mughlai is almost always halal in BLR; biryani very common
            if cuisine == "Mughlai":
                halal = 1
            elif cuisine == "Biryani":
                halal = 1 if random.random() < 0.85 else 0
            elif cuisine in ("North Indian", "Indo-Chinese", "Coastal"):
                halal = 1 if random.random() < 0.55 else 0
            else:
                halal = 1 if random.random() < 0.30 else 0
            kosher = 0
            # Jain — common signal in Bangalore for North Indian, South Indian, Italian
            if cuisine in ("North Indian", "South Indian", "Italian"):
                jain = 1 if random.random() < 0.55 else 0
            else:
                jain = 0

            parking = 1 if random.random() < 0.65 else 0
            outdoor = 1 if random.random() < 0.40 else 0
            valet   = 1 if price >= 3 and random.random() < 0.55 else 0

            # Opening hours by cuisine
            if cuisine == "South Indian":
                opening, closing = "07:00", "22:30"     # breakfast onwards
            elif cuisine == "Continental":
                opening, closing = "08:00", "23:00"     # all-day cafe
            elif cuisine == "Italian":
                opening, closing = "12:00", "23:00"
            elif cuisine == "Mughlai":
                opening, closing = "12:30", "23:30"     # lunch + dinner
            else:
                opening, closing = "12:00", "23:00"

            all_branch_rows.append((
                code, name, hood, address, "Bangalore", lat, lon,
                capacity, tables, cuisine,
                rating, reviews, popularity, price,
                veg, vegan, gf, halal, kosher,
                parking, outdoor, valet,
                opening, closing, phone,
                BRANCH_DESCRIPTIONS[cuisine],
            ))

    conn.executemany(
        """INSERT INTO branches
           (branch_code, name, neighborhood, address, city, latitude, longitude,
            capacity, tables, cuisine, rating, review_count, popularity_score, price_range,
            dietary_vegetarian, dietary_vegan, dietary_gluten_free, dietary_halal, dietary_kosher,
            parking, outdoor_seating, valet, opening_time, closing_time, phone, description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        all_branch_rows,
    )

    # ── Seed menus per branch ──────────────────────────────────────────────────
    branch_rows = conn.execute("SELECT id, cuisine, price_range FROM branches").fetchall()
    for branch in branch_rows:
        template = MENUS.get(branch["cuisine"], [])
        # Smaller price spread for Indian (price-sensitive market) vs continental
        if branch["cuisine"] in ("North Indian", "South Indian", "Biryani",
                                  "Indo-Chinese", "Mughlai", "Coastal"):
            price_factor = {1: 0.85, 2: 1.0, 3: 1.10, 4: 1.20}.get(branch["price_range"], 1.0)
        else:
            price_factor = {1: 0.85, 2: 1.0, 3: 1.15, 4: 1.30}.get(branch["price_range"], 1.0)
        for item in template:
            name, desc, cat, base_price, veg, vegan, gf, jain, popular, cal, raw_tags = item
            price = round(base_price * price_factor, 0)
            tags = _build_dish_tags(name, branch["cuisine"], raw_tags, bool(veg), bool(vegan), bool(gf))
            all_menu_rows.append((
                branch["id"], name, desc, cat, price,
                int(veg), int(vegan), int(gf), 1, int(jain), int(popular), cal, tags,
            ))

    conn.executemany(
        """INSERT INTO menu_items
           (branch_id, name, description, category, price, is_available,
            is_vegetarian, is_vegan, is_gluten_free, is_halal, is_jain, is_popular, calories, dish_tags)
           VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,?)""",
        all_menu_rows,
    )

    return len(all_branch_rows), len(all_menu_rows)


def seed_corporate_accounts(conn):
    """Seed 10 realistic Bangalore-based corporate accounts."""
    conn.execute("DELETE FROM corporate_accounts")
    accounts = [
        ("Infosys Limited",         "Rohit Menon",     "rohit.menon@infosys.com",        "CORP-INFY",  10.0, "Whitefield,Marathahalli",      500000),
        ("Wipro Technologies",      "Anita Desai",     "anita.desai@wipro.com",          "CORP-WIPRO", 12.0, "Sarjapur Road,Bellandur",      400000),
        ("Razorpay",                "Karthik Iyer",    "karthik.iyer@razorpay.com",      "CORP-RZP",   8.0,  "Koramangala,HSR Layout",       250000),
        ("Flipkart",                "Sneha Reddy",     "sneha.reddy@flipkart.com",       "CORP-FK",    10.0, "Bellandur,Sarjapur Road",      450000),
        ("Goldman Sachs Bangalore", "Vikram Chopra",   "vikram.chopra@gs.com",           "CORP-GS",    15.0, "UB City,Lavelle Road",         600000),
        ("Swiggy",                  "Aarav Iyer",      "aarav.iyer@swiggy.in",           "CORP-SWG",   8.0,  "Koramangala,Indiranagar",      300000),
        ("PhonePe",                 "Megha Nair",      "megha.nair@phonepe.com",         "CORP-PPE",   8.0,  "Bellandur,Sarjapur Road",      280000),
        ("Cisco Systems",           "Daniel Pereira",  "daniel.pereira@cisco.com",       "CORP-CSCO",  12.0, "Sarjapur Road,Whitefield",     500000),
        ("EY Bangalore",            "Tanvi Bhatia",    "tanvi.bhatia@ey.com",            "CORP-EY",    10.0, "UB City,MG Road",              400000),
        ("Microsoft India",         "Arjun Kapoor",    "arjun.kapoor@microsoft.com",     "CORP-MSFT",  15.0, "Hebbal,Whitefield",            700000),
    ]
    conn.executemany(
        """INSERT INTO corporate_accounts
           (company_name, contact_name, contact_email, account_code,
            discount_percentage, preferred_branches, credit_limit)
           VALUES (?,?,?,?,?,?,?)""",
        accounts,
    )
    return len(accounts)


def main():
    print("Initialising GoodFoods database (Bangalore multi-cuisine chain)…")
    init_db()
    conn = get_db()
    try:
        nb, nm = seed_branches_and_menus(conn)
        ncorp  = seed_corporate_accounts(conn)
        conn.commit()
        print(f"  ✅ {nb} branches across {len(CUISINES)} cuisines")
        print(f"  ✅ Indian-majority distribution: "
              + ", ".join(f"{c}×{n}" for c, n in BRANCHES_BY_CUISINE.items()))
        print(f"  ✅ {nm} menu items (every dish tagged for dish-level search)")
        print(f"  ✅ {ncorp} corporate accounts")
        print("\nReady to launch:  streamlit run app.py")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
