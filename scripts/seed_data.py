"""
Seed 75 GoodFoods locations with real menus and 10 corporate accounts.
Run: python scripts/seed_data.py
"""
import json, random, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import init_db, get_db, NEIGHBORHOOD_COORDS

random.seed(42)

NEIGHBORHOODS = list(NEIGHBORHOOD_COORDS.keys())
NEIGHBORHOOD_ABBREV = {
    "Downtown": "DT", "Midtown": "MT", "Uptown": "UP", "West Side": "WS",
    "East Side": "ES", "North End": "NE", "South Bay": "SB", "Harbor View": "HV",
    "Garden District": "GD", "Financial District": "FD", "Arts Quarter": "AQ",
    "University District": "UD", "Riverside": "RV", "Greenwood": "GW", "Lakefront": "LK",
}
CUISINES = [
    "Italian", "Indian", "Mexican", "Japanese", "Chinese",
    "Mediterranean", "Thai", "American", "French", "Korean",
    "Middle Eastern", "Vietnamese",
]
CUISINE_LABEL = {
    "Italian": "Italian Kitchen", "Indian": "Indian Spice", "Mexican": "Mexican Grill",
    "Japanese": "Japanese Kitchen", "Chinese": "Chinese Garden",
    "Mediterranean": "Mediterranean Table", "Thai": "Thai Kitchen",
    "American": "American Grill", "French": "French Bistro", "Korean": "Korean BBQ",
    "Middle Eastern": "Middle Eastern Mezze", "Vietnamese": "Vietnamese Kitchen",
}
BRANCH_DESCRIPTIONS = {
    "Italian": "Authentic Italian cuisine with house-made pastas, wood-fired pizzas, and an extensive wine list sourced from family vineyards across Tuscany and Piedmont.",
    "Indian": "Regional Indian recipes passed down through generations, featuring aromatic curries, tandoor-cooked breads, and a spice selection flown in directly from Kerala.",
    "Mexican": "Contemporary Mexican cooking rooted in tradition — from Oaxacan moles to Baja-style seafood, paired with handcrafted margaritas and an agave spirits selection.",
    "Japanese": "A curated Japanese dining experience spanning ramen, omakase sushi, and robata grills, with seasonal ingredients imported weekly from Tokyo's Tsukiji market.",
    "Chinese": "Cantonese dim sum, Sichuan wok dishes, and Peking specialities served in an elegant setting with private dining available for banquet-style gatherings.",
    "Mediterranean": "Flavours of the Mediterranean coast — Greek mezze, Lebanese mezze, Spanish tapas, and North African tagines under one roof with a terrace view.",
    "Thai": "Street-food energy meets fine dining — bold pad thais, fragrant green curries, and fresh papaya salads prepared with authentic Thai herbs and pastes.",
    "American": "Classic American comfort food elevated — slow-smoked BBQ, gourmet burgers, New England lobster rolls, and craft cocktails from our in-house mixologists.",
    "French": "Parisian bistro classics and contemporary French techniques: duck confit, soufflés, and an award-winning cheese board, complemented by a 200-label wine cellar.",
    "Korean": "Modern Korean table — KBBQ grills at every table, bibimbap, tteokbokki, and a banchan spread that changes with the season.",
    "Middle Eastern": "A journey across the Levant, Arabia, and Persia — mezze platters, slow-roasted shawarma, saffron rice, and mint tea to finish.",
    "Vietnamese": "Vietnamese cooking at its finest — pho broth simmered for 24 hours, bánh mì crafted fresh daily, and a herb garden that supplies every plate.",
}

STREETS = [
    "Main St", "Park Ave", "Broadway", "5th Ave", "Lexington Ave",
    "Madison Ave", "7th Ave", "8th Ave", "Hudson St", "Greenwich Ave",
    "Spring St", "Canal St", "Bleecker St", "Prince St", "Grand St",
]

# ── Menu templates ────────────────────────────────────────────────────────────
# Each cuisine: list of (name, desc, category, base_price, veg, vegan, gf, halal, popular, cal)
MENUS = {
    "Italian": [
        ("Bruschetta al Pomodoro",    "Toasted sourdough with San Marzano tomatoes, fresh basil, cold-press olive oil",   "Starters", 9,   True,  True,  False, True,  True,  180),
        ("Burrata e Prosciutto",      "Creamy burrata with Parma ham, truffle honey, rocket salad",                       "Starters", 14,  False, False, True,  False, True,  310),
        ("Calamari Fritti",           "Crispy fried calamari with lemon aioli and nduja dipping sauce",                   "Starters", 13,  False, False, False, False, False, 290),
        ("Zuppa di Pomodoro",         "Slow-cooked tomato soup, basil oil, parmigiano crostini",                          "Starters", 10,  True,  False, True,  True,  False, 220),
        ("Spaghetti Carbonara",       "Guanciale, Pecorino Romano, egg yolk, coarse black pepper",                        "Mains",    19,  False, False, False, False, True,  680),
        ("Margherita Pizza",          "Fior di latte, San Marzano, fresh basil, extra virgin olive oil",                  "Mains",    17,  True,  False, False, True,  True,  620),
        ("Osso Buco alla Milanese",   "Braised veal shank, saffron risotto, gremolata",                                   "Mains",    35,  False, False, True,  False, True,  890),
        ("Risotto ai Funghi Porcini", "Carnaroli rice, dried porcini, truffle oil, parmigiano",                           "Mains",    24,  True,  False, True,  True,  False, 720),
        ("Pappardelle al Cinghiale",  "Wide ribbon pasta, slow-cooked wild boar ragù, pecorino",                          "Mains",    26,  False, False, False, False, False, 750),
        ("Branzino al Forno",         "Whole roasted sea bass, capers, olives, cherry tomatoes, herbs",                   "Mains",    32,  False, False, True,  True,  False, 540),
        ("Tiramisu",                  "Espresso-soaked savoiardi, mascarpone cream, cocoa powder",                        "Desserts", 9,   True,  False, False, True,  True,  420),
        ("Panna Cotta",               "Vanilla bean cream, wild berry coulis, mint",                                      "Desserts", 8,   True,  False, True,  True,  False, 310),
        ("Affogato",                  "Double espresso poured over house-made vanilla gelato",                            "Desserts", 7,   True,  False, True,  True,  False, 210),
        ("Aperol Spritz",             "Aperol, Prosecco DOC, soda water, orange",                                        "Drinks",   12,  True,  True,  True,  True,  True,  160),
        ("Barolo Glass",              "Piedmontese Nebbiolo, 2019 vintage",                                               "Drinks",   14,  True,  True,  True,  True,  False, 130),
        ("Espresso",                  "Double-shot Italian espresso",                                                     "Drinks",   4,   True,  True,  True,  True,  False, 5),
    ],
    "Indian": [
        ("Vegetable Samosa",          "Crispy pastry, spiced potato and pea filling, mint chutney",                       "Starters", 8,   True,  True,  False, True,  True,  220),
        ("Chicken Tikka",             "Tandoor-charred chicken thigh, yogurt marinade, chilli oil",                       "Starters", 13,  False, False, True,  True,  True,  310),
        ("Chaat Papdi",               "Crispy wafers, chickpeas, tamarind, yogurt, sev",                                  "Starters", 9,   True,  False, False, True,  False, 280),
        ("Dal Shorba",                "Slow-cooked lentil soup, cumin tarka, coriander",                                  "Starters", 8,   True,  True,  True,  True,  False, 200),
        ("Butter Chicken",            "Tandoor chicken in rich tomato-cream sauce, served with naan",                     "Mains",    20,  False, False, True,  True,  True,  780),
        ("Dal Makhani",               "Black lentils slow-simmered overnight, cream, fenugreek",                          "Mains",    17,  True,  False, True,  True,  True,  620),
        ("Lamb Rogan Josh",           "Kashmiri-spiced slow-braised lamb shanks, saffron rice",                           "Mains",    26,  False, False, True,  True,  False, 820),
        ("Chicken Biryani",           "Dum-cooked basmati, saffron, whole spices, raita, mirchi ka salan",               "Mains",    24,  False, False, True,  True,  True,  950),
        ("Paneer Tikka Masala",       "Grilled cottage cheese, bell pepper, spiced tomato gravy",                         "Mains",    19,  True,  False, True,  True,  False, 700),
        ("Prawn Malai Curry",         "King prawns in coconut-milk curry, steamed basmati",                               "Mains",    28,  False, False, True,  True,  False, 680),
        ("Gulab Jamun",               "Milk-solid dumplings in rose-cardamom syrup, vanilla ice cream",                  "Desserts", 7,   True,  False, False, True,  True,  380),
        ("Mango Kulfi",               "Traditional frozen cream with Alphonso mango, pistachio",                          "Desserts", 8,   True,  False, True,  True,  False, 290),
        ("Kheer",                     "Rice pudding, cardamom, saffron, rose petals, almonds",                            "Desserts", 6,   True,  False, True,  True,  False, 310),
        ("Mango Lassi",               "Alphonso mango, yogurt, cardamom",                                                 "Drinks",   6,   True,  False, True,  True,  True,  220),
        ("Masala Chai",               "Spiced black tea, ginger, cardamom, whole milk",                                   "Drinks",   4,   True,  False, True,  True,  True,  90),
        ("Kingfisher Beer",           "Premium lager, 330ml bottle",                                                      "Drinks",   6,   True,  True,  True,  True,  False, 150),
    ],
    "Mexican": [
        ("Guacamole & Chips",         "Hass avocados, jalapeño, lime, red onion, fresh-made tortilla chips",              "Starters", 10,  True,  True,  True,  True,  True,  310),
        ("Elote Callejero",           "Street corn, cotija, chipotle mayo, chilli powder, lime",                          "Starters", 9,   True,  False, True,  True,  False, 280),
        ("Queso Fundido",             "Melted Oaxacan cheese, chorizo, roasted peppers, corn tortillas",                  "Starters", 12,  False, False, True,  False, False, 420),
        ("Tortilla Soup",             "Roasted tomato broth, pulled chicken, crispy tortilla strips, avocado",            "Starters", 10,  False, False, True,  True,  False, 320),
        ("Tacos al Pastor",           "Achiote-marinated pork, pineapple, coriander, white onion, corn tortilla",         "Mains",    18,  False, False, True,  False, True,  580),
        ("Enchiladas Verdes",         "Corn tortillas, pulled chicken, tomatillo salsa, crema, queso fresco",             "Mains",    20,  False, False, True,  False, False, 720),
        ("Carnitas Burrito",          "Slow-cooked pork, black beans, rice, pico de gallo, guacamole",                   "Mains",    19,  False, False, False, False, True,  890),
        ("Chiles Rellenos",           "Poblano pepper, Oaxacan cheese stuffing, walnut cream sauce",                      "Mains",    22,  True,  False, True,  True,  False, 680),
        ("Carne Asada",               "Grilled skirt steak, chimichurri, roasted peppers, beans, rice",                  "Mains",    28,  False, False, True,  False, False, 760),
        ("Camarones a la Diabla",     "Seared prawns, guajillo-arbol chilli sauce, lime, rice",                           "Mains",    26,  False, False, True,  True,  False, 520),
        ("Tres Leches",               "Sponge cake soaked in three milks, whipped cream, strawberry",                     "Desserts", 8,   True,  False, False, True,  True,  440),
        ("Churros con Chocolate",     "Cinnamon-dusted churros, Mexican dark chocolate dipping sauce",                    "Desserts", 9,   True,  False, False, True,  True,  380),
        ("Margarita Clasica",         "Espolon Blanco tequila, lime, agave, Cointreau, salt rim",                        "Drinks",   13,  True,  True,  True,  True,  True,  180),
        ("Horchata",                  "House-made rice milk, cinnamon, vanilla, ice",                                     "Drinks",   5,   True,  True,  True,  True,  True,  120),
        ("Modelo Especial",           "Mexican lager, 355ml bottle",                                                      "Drinks",   6,   True,  True,  True,  True,  False, 150),
    ],
    "Japanese": [
        ("Edamame",                   "Steamed salted edamame pods",                                                      "Starters", 6,   True,  True,  True,  True,  True,  120),
        ("Gyoza",                     "Pan-fried pork and cabbage dumplings, ponzu dipping sauce",                        "Starters", 10,  False, False, False, False, True,  280),
        ("Agedashi Tofu",             "Silken tofu in light dashi broth, grated daikon, katsuobushi",                     "Starters", 11,  True,  False, False, True,  False, 210),
        ("Miso Soup",                 "White miso, tofu, wakame, spring onion",                                           "Starters", 5,   True,  True,  False, True,  True,  60),
        ("Tonkotsu Ramen",            "18-hour pork broth, chashu pork belly, soft-boiled egg, nori, bamboo",             "Mains",    20,  False, False, False, False, True,  890),
        ("Salmon Sashimi (8 pcs)",    "Premium Norwegian salmon, wasabi, pickled ginger, soy",                            "Mains",    24,  False, False, True,  True,  True,  320),
        ("Chicken Katsu Curry",       "Panko-breaded chicken, Japanese curry sauce, steamed rice, pickles",               "Mains",    21,  False, False, False, False, True,  820),
        ("Vegetable Tempura Set",     "Seasonal vegetables, light batter, tentsuyu dipping broth, rice",                  "Mains",    19,  True,  True,  False, True,  False, 640),
        ("Wagyu Beef Don",            "A5 Wagyu slices over seasoned rice, truffle tare, onsen egg",                      "Mains",    38,  False, False, True,  False, True,  780),
        ("Omakase Sushi (6 pcs)",     "Chef's selection of nigiri, seasonal and market-dependent",                        "Mains",    32,  False, False, True,  True,  True,  420),
        ("Matcha Lava Cake",          "Dark chocolate and matcha centre, vanilla ice cream, red bean",                    "Desserts", 10,  True,  False, False, True,  True,  380),
        ("Mochi Ice Cream (3 pcs)",   "Choice of matcha, mango, or yuzu filling",                                        "Desserts", 9,   True,  False, False, True,  True,  290),
        ("Japanese Whisky",           "Suntory Toki, neat or on the rocks",                                               "Drinks",   14,  True,  True,  True,  True,  False, 110),
        ("Yuzu Lemonade",             "Fresh yuzu, honey, soda water",                                                    "Drinks",   6,   True,  True,  True,  True,  True,  80),
        ("Sapporo Draft",             "Japanese lager, 500ml",                                                            "Drinks",   7,   True,  True,  True,  True,  False, 180),
    ],
    "Chinese": [
        ("Har Gow (4 pcs)",           "Steamed prawn dumplings, light soy dipping",                                       "Starters", 9,   False, False, False, False, True,  160),
        ("Spring Rolls (3 pcs)",      "Crispy vegetable and pork rolls, sweet chilli sauce",                              "Starters", 8,   False, False, False, False, False, 280),
        ("Wonton Soup",               "Hand-folded pork wontons, clear ginger broth, spring onion",                       "Starters", 9,   False, False, False, False, True,  220),
        ("Edamame with Chilli Salt",  "Steamed edamame, Sichuan chilli salt",                                             "Starters", 6,   True,  True,  True,  True,  False, 120),
        ("Peking Duck (half)",        "Traditional Peking duck, pancakes, cucumber, spring onion, hoisin",               "Mains",    38,  False, False, False, False, True,  1100),
        ("Mapo Tofu",                 "Silken tofu, minced pork, Sichuan doubanjiang, numbing peppercorns",               "Mains",    18,  False, False, False, False, True,  520),
        ("Kung Pao Chicken",          "Sichuan-style wok chicken, peanuts, dried chillies, Shaoxing wine",               "Mains",    21,  False, False, True,  False, True,  680),
        ("Char Siu Pork",             "BBQ pork belly, jasmine rice, pickled vegetables",                                 "Mains",    22,  False, False, True,  False, False, 760),
        ("Vegetable Chow Mein",       "Wok-fried egg noodles, bok choy, shiitake, bean sprouts",                         "Mains",    17,  True,  False, False, True,  False, 580),
        ("Steamed Sea Bass",          "Whole sea bass, ginger, spring onion, sizzling soy oil",                          "Mains",    36,  False, False, True,  True,  False, 420),
        ("Mango Pudding",             "Set mango cream, evaporated milk, fresh mango",                                    "Desserts", 7,   True,  False, True,  True,  True,  280),
        ("Sesame Balls",              "Fried glutinous rice with lotus paste, sesame crust",                              "Desserts", 7,   True,  False, False, True,  False, 320),
        ("Jasmine Tea Pot",           "Premium jasmine green tea, serves two",                                            "Drinks",   6,   True,  True,  True,  True,  True,  5),
        ("Tsingtao Beer",             "Chinese lager, 330ml bottle",                                                      "Drinks",   5,   True,  True,  True,  True,  False, 150),
        ("Lychee Martini",            "Vodka, lychee liqueur, fresh lychee, rose water",                                  "Drinks",   13,  True,  True,  True,  True,  False, 190),
    ],
    "Mediterranean": [
        ("Mezze Platter (for 2)",     "Hummus, baba ganoush, tzatziki, stuffed vine leaves, pita",                       "Starters", 16,  True,  False, False, True,  True,  520),
        ("Falafel",                   "Hand-rolled chickpea falafel, tahini, pomegranate molasses",                       "Starters", 10,  True,  True,  True,  True,  True,  320),
        ("Grilled Halloumi",          "Cypriot halloumi, watermelon, mint, chilli flakes, lemon",                        "Starters", 12,  True,  False, True,  True,  False, 380),
        ("Lentil Soup",               "Red lentil, cumin, lemon, warm pitta",                                            "Starters", 9,   True,  True,  True,  True,  True,  280),
        ("Lamb Kofta",                "Spiced minced lamb skewers, flatbread, harissa, yogurt, salad",                   "Mains",    24,  False, False, True,  True,  True,  720),
        ("Grilled Sea Bream",         "Whole sea bream, chermoula, roasted vegetables, couscous",                        "Mains",    30,  False, False, True,  True,  False, 580),
        ("Chicken Shawarma",          "Slow-rotisserie chicken, garlic sauce, pickles, sumac onions, flatbread",          "Mains",    22,  False, False, False, True,  True,  760),
        ("Moussaka",                  "Layered aubergine, spiced lamb, béchamel, tomato",                                 "Mains",    23,  False, False, False, False, False, 820),
        ("Spanakopita",               "Spinach and feta filo pastry, Greek salad",                                       "Mains",    19,  True,  False, False, True,  False, 680),
        ("Lamb Tagine",               "Moroccan slow-cooked lamb, preserved lemon, olives, couscous",                    "Mains",    28,  False, False, True,  True,  False, 890),
        ("Baklava",                   "Layered filo, pistachio, rose-water honey syrup",                                  "Desserts", 8,   True,  False, False, True,  True,  480),
        ("Greek Yogurt & Honey",      "Strained yogurt, Hymettus honey, candied walnut",                                  "Desserts", 7,   True,  False, True,  True,  False, 280),
        ("Turkish Coffee",            "Traditional copper-pot brewed coffee, lokum",                                      "Drinks",   5,   True,  True,  True,  True,  True,  10),
        ("Pomegranate Spritz",        "Pomegranate juice, rose water, soda, mint",                                       "Drinks",   7,   True,  True,  True,  True,  True,  90),
        ("Ouzo",                      "Greek anise spirit, served neat with ice and water",                               "Drinks",   9,   True,  True,  True,  True,  False, 100),
    ],
    "Thai": [
        ("Satay Skewers (4 pcs)",    "Grilled chicken, peanut sauce, pickled cucumber",                                  "Starters", 11,  False, False, True,  True,  True,  280),
        ("Som Tum",                   "Green papaya salad, cherry tomatoes, dried shrimp, lime, palm sugar",              "Starters", 10,  False, False, True,  False, True,  180),
        ("Tom Kha Soup",              "Coconut milk, galangal, lemongrass, mushroom, chicken",                            "Starters", 11,  False, False, True,  True,  False, 310),
        ("Spring Rolls (3 pcs)",      "Rice paper, vermicelli, prawn, herbs, hoisin-peanut dip",                         "Starters", 9,   False, False, True,  True,  False, 220),
        ("Pad Thai",                  "Wok rice noodles, prawn or chicken, egg, bean sprouts, tamarind, peanuts",        "Mains",    19,  False, False, True,  True,  True,  780),
        ("Green Curry",               "Coconut cream, Thai aubergine, bamboo shoots, kaffir lime, jasmine rice",         "Mains",    20,  True,  False, True,  True,  True,  680),
        ("Massaman Lamb",             "Slow-braised lamb, coconut milk, potatoes, peanuts, cardamom",                    "Mains",    26,  False, False, True,  True,  False, 820),
        ("Pad See Ew",                "Flat rice noodles, soy-glazed chicken, egg, broccoli, wok breath",                "Mains",    18,  False, False, True,  True,  False, 710),
        ("Basil Stir-Fry (Pad Kra Pao)", "Wok minced chicken or pork, Thai basil, chillies, fish sauce, fried egg",   "Mains",    20,  False, False, True,  False, True,  720),
        ("Steamed Sea Bass",          "Whole sea bass in lime-garlic-chilli dressing, lemongrass",                       "Mains",    32,  False, False, True,  True,  False, 420),
        ("Mango Sticky Rice",         "Glutinous rice, coconut cream, fresh Alphonso mango",                             "Desserts", 9,   True,  True,  True,  True,  True,  480),
        ("Black Sesame Ice Cream",    "House-churned black sesame, toasted sesame brittle",                              "Desserts", 8,   True,  False, True,  True,  False, 310),
        ("Thai Iced Tea",             "Ceylon tea, condensed milk, star anise, served over ice",                         "Drinks",   5,   True,  False, True,  True,  True,  180),
        ("Lychee Cooler",             "Fresh lychee, lime, soda, mint",                                                  "Drinks",   6,   True,  True,  True,  True,  True,  90),
        ("Singha Beer",               "Thai lager, 330ml bottle",                                                        "Drinks",   6,   True,  True,  True,  True,  False, 150),
    ],
    "American": [
        ("Loaded Potato Skins",       "Crispy potato skins, cheddar, bacon bits, sour cream, chives",                   "Starters", 11,  False, False, True,  False, False, 420),
        ("Buffalo Wings (8 pcs)",     "Crispy wings, Frank's RedHot sauce, blue cheese dip, celery",                    "Starters", 14,  False, False, True,  False, True,  580),
        ("Clam Chowder",              "New England style, sourdough bread bowl, bacon, chives",                          "Starters", 13,  False, False, False, False, False, 480),
        ("Caesar Salad",              "Romaine, house-made Caesar dressing, parmigiano, focaccia croutons",              "Starters", 12,  True,  False, False, True,  True,  340),
        ("Wagyu Smash Burger",        "Double Wagyu patty, American cheese, pickles, onion, house sauce, brioche bun",  "Mains",    22,  False, False, False, False, True,  1100),
        ("BBQ Baby Back Ribs (half)", "Slow-smoked pork ribs, house bourbon-molasses glaze, coleslaw, fries",           "Mains",    28,  False, False, True,  False, True,  1250),
        ("Lobster Roll",              "Cold Maine lobster, tarragon mayo, butter-toasted brioche, fries",                "Mains",    34,  False, False, False, False, True,  720),
        ("Mac & Cheese",              "Cavatappi pasta, four-cheese béchamel, panko crust, truffle oil",                 "Mains",    19,  True,  False, False, True,  False, 890),
        ("NY Strip Steak (10oz)",     "28-day dry-aged strip, garlic butter, fries, peppercorn sauce",                  "Mains",    42,  False, False, True,  False, True,  920),
        ("Grilled Salmon",            "Atlantic salmon, lemon-caper butter, seasonal vegetables, mashed potatoes",       "Mains",    29,  False, False, True,  False, False, 680),
        ("Banana Pudding",            "Layers of vanilla custard, Nilla wafers, fresh banana, whipped cream",           "Desserts", 9,   True,  False, False, True,  True,  520),
        ("Brownie Sundae",            "Warm fudge brownie, vanilla ice cream, hot fudge, peanuts",                      "Desserts", 11,  True,  False, False, True,  False, 680),
        ("Old Fashioned",             "Woodford Reserve bourbon, Angostura bitters, orange, Luxardo cherry",            "Drinks",   14,  True,  True,  True,  True,  False, 180),
        ("Arnold Palmer",             "Half unsweetened iced tea, half fresh lemonade",                                  "Drinks",   5,   True,  True,  True,  True,  True,  80),
        ("Local Craft IPA",           "Rotating tap selection from local New York breweries",                           "Drinks",   8,   True,  True,  True,  True,  False, 200),
    ],
    "French": [
        ("French Onion Soup",         "Caramelised onion, beef broth, Gruyère crouton, flambéed",                       "Starters", 13,  True,  False, False, False, True,  380),
        ("Escargots de Bourgogne",    "Six snails, garlic-parsley butter, baguette",                                     "Starters", 16,  False, False, True,  False, False, 310),
        ("Steak Tartare",             "Hand-cut beef tenderloin, cornichons, capers, Dijon, quail egg, toast",           "Starters", 18,  False, False, False, False, False, 380),
        ("Vichyssoise",               "Chilled leek and potato soup, crème fraîche, chives",                            "Starters", 11,  True,  False, True,  True,  False, 280),
        ("Duck Confit",               "Slow-cooked duck leg, Puy lentils, lardon, Dijon jus",                           "Mains",    32,  False, False, True,  False, True,  980),
        ("Coq au Vin",                "Free-range chicken, Burgundy red wine, mushrooms, pearl onions, lardons",        "Mains",    29,  False, False, False, False, True,  860),
        ("Bouillabaisse",             "Provençal fish stew, saffron broth, rouille, grilled bread",                     "Mains",    36,  False, False, True,  True,  False, 720),
        ("Ratatouille",               "Slow-roasted Provençal vegetables, herbed olive oil, goat cheese",               "Mains",    22,  True,  True,  True,  True,  False, 480),
        ("Steak Frites",              "250g entrecôte, béarnaise or au poivre, pommes frites",                          "Mains",    38,  False, False, True,  False, True,  1050),
        ("Sole Meunière",             "Dover sole, brown butter, lemon, capers, parsley",                               "Mains",    42,  False, False, True,  True,  False, 580),
        ("Crème Brûlée",              "Madagascan vanilla custard, caramelised sugar crust",                            "Desserts", 10,  True,  False, True,  True,  True,  420),
        ("Profiteroles",              "Choux pastry, Chantilly cream, warm chocolate sauce",                            "Desserts", 9,   True,  False, False, True,  False, 480),
        ("Cheese Board",              "Seasonal selection of five cheeses, quince, walnuts, crackers",                  "Desserts", 18,  True,  False, False, False, False, 520),
        ("Kir Royale",                "Crème de cassis, Champagne",                                                     "Drinks",   14,  True,  True,  True,  True,  False, 130),
        ("Côtes du Rhône Glass",      "Southern Rhône Grenache blend",                                                  "Drinks",   12,  True,  True,  True,  True,  False, 120),
        ("Café au Lait",              "Double espresso, steamed whole milk",                                             "Drinks",   5,   True,  False, True,  True,  False, 80),
    ],
    "Korean": [
        ("Kimchi & Banchan",          "House-fermented kimchi, spinach namul, bean sprouts, seaweed",                   "Starters", 8,   True,  True,  True,  True,  True,  180),
        ("Japchae",                   "Glass noodles, stir-fried vegetables, sesame, soy",                              "Starters", 11,  True,  True,  True,  True,  False, 310),
        ("Korean Fried Chicken (6 pcs)","Double-fried wings in soy-garlic or yangnyeom sauce",                         "Starters", 14,  False, False, False, False, True,  480),
        ("Doenjang Jjigae",           "Fermented soybean paste stew, tofu, mushrooms, courgette",                       "Starters", 9,   True,  False, False, True,  False, 220),
        ("KBBQ Wagyu Short Rib",      "A5 Wagyu, tableside grill, ssam lettuce, perilla, doenjang",                    "Mains",    44,  False, False, True,  False, True,  950),
        ("Bibimbap",                  "Stone pot rice, seasonal vegetables, gochujang, sesame oil, fried egg",          "Mains",    18,  True,  False, True,  True,  True,  720),
        ("Samgyeopsal (Pork Belly)",  "Thick-cut pork belly, tableside grill, kimchi, ssamjang",                       "Mains",    26,  False, False, True,  False, True,  880),
        ("Spicy Seafood Stew (Haemul Jjigae)", "Prawns, squid, clams, tofu, gochugaru broth",                         "Mains",    28,  False, False, True,  False, False, 620),
        ("Dakgalbi",                  "Spicy stir-fried chicken, rice cakes, cabbage, gochujang",                       "Mains",    22,  False, False, False, False, True,  760),
        ("Tofu Sundubu Jjigae",       "Silken tofu, mushrooms, egg, gochugaru, anchovy broth",                         "Mains",    19,  True,  False, True,  False, False, 480),
        ("Patbingsu",                 "Shaved ice, sweetened red bean, tteok, condensed milk, fresh fruit",             "Desserts", 10,  True,  False, False, True,  True,  420),
        ("Hoddeok",                   "Pan-fried sweet pancake, brown sugar, cinnamon, walnut filling",                 "Desserts", 7,   True,  False, False, True,  False, 380),
        ("Soju",                      "Korean rice spirit, 360ml bottle, served chilled",                               "Drinks",   12,  True,  True,  True,  True,  False, 280),
        ("Sikhye",                    "Traditional sweet rice punch, served cold",                                       "Drinks",   5,   True,  True,  True,  True,  True,  110),
        ("Korean Plum Wine (Maesil)", "Semi-sweet plum wine, served over ice",                                         "Drinks",   8,   True,  True,  True,  True,  False, 130),
    ],
    "Middle Eastern": [
        ("Hummus Masabacha",          "Warm whole chickpeas, tahini, lemon, olive oil, paprika, warm pitta",            "Starters", 10,  True,  True,  True,  True,  True,  320),
        ("Fattoush Salad",            "Crispy pitta, tomato, cucumber, sumac dressing, pomegranate",                    "Starters", 11,  True,  True,  True,  True,  True,  280),
        ("Kibbeh (4 pcs)",            "Ground lamb and bulgur shell, pine nuts, cinnamon, yogurt dip",                  "Starters", 12,  False, False, False, True,  False, 380),
        ("Moutabal",                  "Smoky aubergine with tahini, pomegranate seeds, olive oil",                      "Starters", 9,   True,  True,  True,  True,  True,  220),
        ("Mixed Shawarma Platter",    "Chicken and lamb shawarma, garlic sauce, tahini, pickles, flatbread",            "Mains",    26,  False, False, False, True,  True,  920),
        ("Lamb Ouzi",                 "Slow-roasted whole lamb shoulder, saffron rice, toasted nuts, yogurt",           "Mains",    34,  False, False, True,  True,  True,  1050),
        ("Chicken Mansaf",            "Jordanian feast — saffron rice, jameed sauce, almonds, pine nuts",              "Mains",    28,  False, False, True,  True,  False, 880),
        ("Falafel Plate",             "Eight falafels, hummus, tabbouleh, pitta, tahini",                               "Mains",    18,  True,  True,  True,  True,  True,  680),
        ("Grilled Sea Bass",          "Whole sea bass, chermoula, roasted vegetables, couscous",                        "Mains",    32,  False, False, True,  True,  False, 580),
        ("Vegetarian Moghrabieh",     "Lebanese pearl couscous, caramelised onions, chickpeas, warm spices",            "Mains",    20,  True,  True,  True,  True,  True,  620),
        ("Kunafa",                    "Shredded filo, Nabulsi cheese, rose-water syrup, pistachio",                    "Desserts", 9,   True,  False, False, True,  True,  520),
        ("Umm Ali",                   "Egyptian bread pudding, cream, pistachios, coconut",                             "Desserts", 8,   True,  False, False, True,  False, 480),
        ("Mint Tea",                  "Pot of Moroccan mint tea, sugar on the side",                                    "Drinks",   5,   True,  True,  True,  True,  True,  20),
        ("Jallab",                    "Rose water, grape juice, grenadine, pine nuts, raisins",                         "Drinks",   6,   True,  True,  True,  True,  True,  120),
        ("Lebanese Wine",             "Glass of Ksara Réserve du Couvent, Lebanon",                                    "Drinks",   12,  True,  True,  True,  False, False, 120),
    ],
    "Vietnamese": [
        ("Goi Cuon (Fresh Rolls, 2 pcs)", "Rice paper, prawn, pork, vermicelli, herb garden, hoisin-peanut dip",       "Starters", 9,   False, False, True,  False, True,  220),
        ("Cha Gio (Fried Rolls, 3 pcs)", "Pork, vermicelli, wood-ear mushroom, crispy rice paper",                    "Starters", 10,  False, False, False, False, False, 280),
        ("Bun Bo Hue Soup",           "Spicy lemongrass beef broth, pork knuckle, rice noodles",                       "Starters", 11,  False, False, True,  False, False, 380),
        ("Goi Ga",                    "Poached chicken salad, cabbage, carrot, Vietnamese herbs, crispy shallots",     "Starters", 12,  False, False, True,  False, False, 280),
        ("Pho Bo (Beef)",             "24-hour bone broth, rice noodles, brisket, tendon, star anise, cinnamon",       "Mains",    18,  False, False, True,  False, True,  680),
        ("Pho Chay (Vegetarian)",     "Mushroom and vegetable broth, tofu, rice noodles, fresh herbs",                 "Mains",    16,  True,  True,  True,  True,  True,  480),
        ("Banh Mi Thit",              "Baguette, house pâté, char siu pork, pickled daikon, jalapeño, mayo",           "Mains",    14,  False, False, False, False, True,  580),
        ("Bun Cha",                   "Hanoi pork meatballs in dipping broth, vermicelli, herbs, fried spring roll",   "Mains",    20,  False, False, True,  False, True,  720),
        ("Com Tam Suon Nuong",        "Broken rice, grilled pork chop, fried egg, pickles, spring rolls",              "Mains",    22,  False, False, True,  False, False, 880),
        ("Ca Kho To",                 "Caramelised fish claypot, ginger, spring onion, jasmine rice",                  "Mains",    24,  False, False, True,  True,  False, 580),
        ("Che Ba Mau",                "Three-colour dessert — pandan jelly, red bean, mung bean, coconut milk",        "Desserts", 7,   True,  True,  True,  True,  True,  320),
        ("Banh Flan",                 "Vietnamese egg flan, dark caramel, strong coffee drizzle",                      "Desserts", 7,   True,  False, True,  True,  False, 280),
        ("Vietnamese Iced Coffee",    "Robusta drip coffee, sweetened condensed milk, ice",                            "Drinks",   5,   True,  False, True,  True,  True,  120),
        ("Sinh To Xoai",              "Fresh mango smoothie, coconut cream",                                            "Drinks",   6,   True,  True,  True,  True,  True,  180),
        ("Bia Saigon",                "Vietnamese lager, 330ml bottle",                                                "Drinks",   5,   True,  True,  True,  True,  False, 150),
    ],
}


def seed_branches_and_menus(conn):
    conn.execute("DELETE FROM menu_items")
    conn.execute("DELETE FROM reservations")
    conn.execute("DELETE FROM occasion_crm")
    conn.execute("DELETE FROM dropoffs")
    conn.execute("DELETE FROM branches")

    hood_seq: dict = {}
    all_branch_rows = []
    all_menu_rows = []

    cuisine_counts = {c: 6 for c in CUISINES}
    for c in CUISINES[-3:]:
        cuisine_counts[c] = 7

    for cuisine, count in cuisine_counts.items():
        hoods = random.sample(NEIGHBORHOODS, min(count, len(NEIGHBORHOODS)))
        if count > len(NEIGHBORHOODS):
            hoods += random.sample(NEIGHBORHOODS, count - len(NEIGHBORHOODS))

        for hood in hoods:
            hood_seq.setdefault(hood, 0)
            hood_seq[hood] += 1
            code = f"GF-{NEIGHBORHOOD_ABBREV[hood]}-{hood_seq[hood]:02d}"
            name = f"GoodFoods {hood} — {CUISINE_LABEL[cuisine]}"

            base_lat, base_lon = NEIGHBORHOOD_COORDS[hood]
            lat = round(base_lat + random.uniform(-0.008, 0.008), 6)
            lon = round(base_lon + random.uniform(-0.008, 0.008), 6)

            num_str = random.randint(10, 999)
            street = random.choice(["Main St","Park Ave","Broadway","5th Ave","Lexington Ave",
                                    "Madison Ave","7th Ave","Hudson St","Greenwich Ave","Spring St"])
            address = f"{num_str} {street}, {hood}"
            phone = f"+1 (212) {random.randint(200,999)}-{random.randint(1000,9999)}"

            capacity = random.choice([30, 40, 50, 60, 70, 80, 90, 100, 110, 120])
            tables = capacity // 4
            rating = round(random.uniform(3.8, 4.8), 1)
            reviews = random.randint(80, 1200)
            price = random.randint(1, 4)

            veg = int(random.random() < 0.65)
            vegan = int(veg and random.random() < 0.5)
            gf = int(random.random() < 0.45)
            halal = int(random.random() < (0.80 if cuisine in ("Middle Eastern","Indian") else 0.20))
            kosher = int(random.random() < 0.10)
            park = int(random.random() < 0.50)
            outdoor = int(random.random() < 0.45)
            valet = int(price >= 3 and random.random() < 0.4)

            all_branch_rows.append((
                code, name, hood, address, lat, lon,
                capacity, tables, cuisine,
                rating, reviews, price,
                veg, vegan, gf, halal, kosher,
                park, outdoor, valet,
                1, "11:00", "22:30", phone,
                BRANCH_DESCRIPTIONS.get(cuisine, ""),
            ))

    conn.executemany(
        """INSERT INTO branches
           (branch_code, name, neighborhood, address, latitude, longitude,
            capacity, tables, cuisine, rating, review_count, price_range,
            dietary_vegetarian, dietary_vegan, dietary_gluten_free,
            dietary_halal, dietary_kosher, parking, outdoor_seating, valet,
            is_active, opening_time, closing_time, phone, description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        all_branch_rows,
    )

    # Seed menus
    branch_rows = conn.execute("SELECT id, cuisine, price_range FROM branches").fetchall()
    for branch in branch_rows:
        template = MENUS.get(branch["cuisine"], [])
        for item in template:
            name, desc, cat, base_price, veg, vegan, gf, halal, popular, cal = item
            # Adjust price slightly by branch price_range tier
            price_factor = {1: 0.8, 2: 1.0, 3: 1.2, 4: 1.5}.get(branch["price_range"], 1.0)
            price = round(base_price * price_factor, 2)
            all_menu_rows.append((
                branch["id"], name, desc, cat, price,
                1, int(veg), int(vegan), int(gf), int(halal), int(popular), cal,
            ))

    conn.executemany(
        """INSERT INTO menu_items
           (branch_id, name, description, category, price,
            is_available, is_vegetarian, is_vegan, is_gluten_free,
            is_halal, is_popular, calories)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        all_menu_rows,
    )
    return len(all_branch_rows), len(all_menu_rows)


COMPANIES = [
    ("Apex Consulting",     "Alice Brown",  "alice@apex.com",       "CORP001", 15.0, 50000),
    ("NovaTech Solutions",  "Bob Chen",     "bob@novatech.io",      "CORP002", 10.0, 30000),
    ("Meridian Law LLP",    "Carol Davis",  "carol@meridianlaw.com","CORP003", 12.0, 40000),
    ("BlueWave Capital",    "David Evans",  "david@bluewave.com",   "CORP004", 20.0, 75000),
    ("Orion Media Group",   "Emma Foster",  "emma@orionmedia.com",  "CORP005",  8.0, 20000),
    ("Vertex Analytics",    "Frank Gupta",  "frank@vertex.ai",      "CORP006", 10.0, 25000),
    ("Pinnacle Pharma",     "Grace Huang",  "grace@pinnaclerx.com", "CORP007", 18.0, 60000),
    ("Sterling Architects", "Harry Ito",    "harry@sterling.arch",  "CORP008", 12.0, 35000),
    ("Summit Engineering",  "Iris Johnson", "iris@summit.eng",      "CORP009", 10.0, 30000),
    ("Catalyst Ventures",   "Jack Kim",     "jack@catalystvc.com",  "CORP010", 25.0, 100000),
]


def main():
    print("Initialising schema…")
    init_db()
    conn = get_db()
    try:
        nb, nm = seed_branches_and_menus(conn)
        conn.execute("DELETE FROM corporate_accounts")
        conn.executemany(
            """INSERT INTO corporate_accounts
               (company_name,contact_name,contact_email,account_code,
                discount_percentage,preferred_branches,credit_limit)
               VALUES (?,?,?,?,?,?,?)""",
            [(n,c,e,code,d,json.dumps([]),cr) for n,c,e,code,d,cr in COMPANIES],
        )
        conn.commit()
    finally:
        conn.close()
    print(f"Seeded {nb} GoodFoods locations with {nm} menu items.")
    print(f"Seeded {len(COMPANIES)} corporate accounts.")


if __name__ == "__main__":
    main()
