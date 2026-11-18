import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_bazaar.settings')
django.setup()

from apps.shops.models import Shop
from apps.products.models import Category, Product, ProductBarcode
from apps.inventory.models import Inventory, StockTransaction

def seed_200_products():
    shop = Shop.objects.first()
    if not shop:
        print("Error: No shop found. Run seed_data.py first.")
        return

    print(f"Adding 200 products with 500 quantity each to '{shop.name}'...")

    catalog = [
        # 1. Grocery & Staples (25 items)
        ("Aashirvaad Shudh Chakki Atta 5kg", "Grocery & Staples", 235.0, 260.0, "KG", "Aashirvaad"),
        ("Aashirvaad Select Sharbati Atta 5kg", "Grocery & Staples", 310.0, 345.0, "KG", "Aashirvaad"),
        ("Fortune Chakki Fresh Atta 5kg", "Grocery & Staples", 215.0, 240.0, "KG", "Fortune"),
        ("Pillsbury Chakki Fresh Atta 5kg", "Grocery & Staples", 225.0, 250.0, "KG", "Pillsbury"),
        ("Daawat Rozana Gold Basmati Rice 5kg", "Grocery & Staples", 410.0, 480.0, "KG", "Daawat"),
        ("India Gate Basmati Rice Feast Rozzana 5kg", "Grocery & Staples", 440.0, 520.0, "KG", "India Gate"),
        ("Fortune Everyday Basmati Rice 1kg", "Grocery & Staples", 85.0, 105.0, "KG", "Fortune"),
        ("Kohinoor Super Silver Basmati Rice 1kg", "Grocery & Staples", 130.0, 160.0, "KG", "Kohinoor"),
        ("Tata Sampann Unpolished Toor Dal 1kg", "Grocery & Staples", 175.0, 195.0, "KG", "Tata Sampann"),
        ("Tata Sampann Unpolished Moong Dal 1kg", "Grocery & Staples", 135.0, 155.0, "KG", "Tata Sampann"),
        ("Tata Sampann Unpolished Chana Dal 1kg", "Grocery & Staples", 98.0, 115.0, "KG", "Tata Sampann"),
        ("Tata Sampann Masoor Dal 1kg", "Grocery & Staples", 105.0, 120.0, "KG", "Tata Sampann"),
        ("Tata Sampann Urad Whole 1kg", "Grocery & Staples", 145.0, 165.0, "KG", "Tata Sampann"),
        ("Tata Sampann Kabuli Chana 1kg", "Grocery & Staples", 160.0, 185.0, "KG", "Tata Sampann"),
        ("Tata Sampann Rajma Red 1kg", "Grocery & Staples", 150.0, 175.0, "KG", "Tata Sampann"),
        ("Tata Salt Vacuum Evaporated 1kg", "Grocery & Staples", 28.0, 30.0, "KG", "Tata"),
        ("Tata Salt Lite Low Sodium 1kg", "Grocery & Staples", 45.0, 50.0, "KG", "Tata"),
        ("Aashirvaad Iodised Salt 1kg", "Grocery & Staples", 25.0, 28.0, "KG", "Aashirvaad"),
        ("Madhur Pure & Hygienic Sugar 1kg", "Grocery & Staples", 52.0, 60.0, "KG", "Madhur"),
        ("Madhur Pure & Hygienic Sugar 5kg", "Grocery & Staples", 255.0, 290.0, "KG", "Madhur"),
        ("Tata Sampann Poha 500g", "Grocery & Staples", 45.0, 55.0, "PACK", "Tata Sampann"),
        ("Rajdhani Sooji (Semolina) 500g", "Grocery & Staples", 38.0, 45.0, "PACK", "Rajdhani"),
        ("Rajdhani Besan 500g", "Grocery & Staples", 58.0, 68.0, "PACK", "Rajdhani"),
        ("Rajdhani Maida 500g", "Grocery & Staples", 35.0, 42.0, "PACK", "Rajdhani"),
        ("Catch Sabzi Masala 100g", "Grocery & Staples", 48.0, 55.0, "PCS", "Catch"),

        # 2. Edible Oils & Ghee (20 items)
        ("Fortune Sunlite Refined Sunflower Oil 1L", "Edible Oils & Ghee", 125.0, 145.0, "LTR", "Fortune"),
        ("Fortune Sunlite Refined Sunflower Oil 5L", "Edible Oils & Ghee", 610.0, 720.0, "LTR", "Fortune"),
        ("Fortune Kachi Ghani Mustard Oil 1L", "Edible Oils & Ghee", 145.0, 165.0, "LTR", "Fortune"),
        ("Fortune Kachi Ghani Mustard Oil 5L", "Edible Oils & Ghee", 720.0, 825.0, "LTR", "Fortune"),
        ("Emami Healthy & Tasty Mustard Oil 1L", "Edible Oils & Ghee", 140.0, 160.0, "LTR", "Emami"),
        ("Dhara Kachi Ghani Mustard Oil 1L", "Edible Oils & Ghee", 142.0, 162.0, "LTR", "Dhara"),
        ("Saffola Gold Pro Healthy Lifestyle Oil 1L", "Edible Oils & Ghee", 165.0, 190.0, "LTR", "Saffola"),
        ("Saffola Gold Pro Healthy Lifestyle Oil 5L", "Edible Oils & Ghee", 810.0, 945.0, "LTR", "Saffola"),
        ("Saffola Total Pro Heart Oil 1L", "Edible Oils & Ghee", 195.0, 225.0, "LTR", "Saffola"),
        ("Fortune Premium Kachi Ghani Mustard Oil Pouch 1L", "Edible Oils & Ghee", 138.0, 155.0, "LTR", "Fortune"),
        ("Fortune Rice Bran Health Oil 1L", "Edible Oils & Ghee", 130.0, 150.0, "LTR", "Fortune"),
        ("Gemini Pure Edible Sunflower Oil 1L", "Edible Oils & Ghee", 122.0, 140.0, "LTR", "Gemini"),
        ("Sundrop Superlite Advanced Oil 1L", "Edible Oils & Ghee", 155.0, 180.0, "LTR", "Sundrop"),
        ("Amul Pure Ghee 1L Tin", "Edible Oils & Ghee", 585.0, 650.0, "LTR", "Amul"),
        ("Amul Pure Ghee 500ml Pouch", "Edible Oils & Ghee", 295.0, 325.0, "ML", "Amul"),
        ("Mother Dairy Pure Cow Ghee 1L", "Edible Oils & Ghee", 610.0, 675.0, "LTR", "Mother Dairy"),
        ("Gowardhan Pure Cow Ghee 1L", "Edible Oils & Ghee", 630.0, 699.0, "LTR", "Gowardhan"),
        ("Patanjali Cow Ghee 1L", "Edible Oils & Ghee", 590.0, 650.0, "LTR", "Patanjali"),
        ("Borges Extra Virgin Olive Oil 1L", "Edible Oils & Ghee", 980.0, 1250.0, "LTR", "Borges"),
        ("Figaro Pure Olive Oil 500ml", "Edible Oils & Ghee", 540.0, 675.0, "ML", "Figaro"),

        # 3. Dairy & Breakfast (20 items)
        ("Amul Taaza Homogenised Toned Milk 1L", "Dairy & Breakfast", 72.0, 75.0, "LTR", "Amul"),
        ("Amul Gold Homogenised Standardised Milk 1L", "Dairy & Breakfast", 80.0, 84.0, "LTR", "Amul"),
        ("Amul Pasteurized Butter 100g", "Dairy & Breakfast", 56.0, 60.0, "PCS", "Amul"),
        ("Amul Pasteurized Butter 500g", "Dairy & Breakfast", 270.0, 285.0, "PACK", "Amul"),
        ("Amul Processed Cheese Cubes 200g", "Dairy & Breakfast", 135.0, 145.0, "PACK", "Amul"),
        ("Amul Cheese Slices 200g (10 Slices)", "Dairy & Breakfast", 145.0, 155.0, "PACK", "Amul"),
        ("Amul Malai Paneer 200g", "Dairy & Breakfast", 90.0, 95.0, "PACK", "Amul"),
        ("Mother Dairy Classic Dahi 400g", "Dairy & Breakfast", 35.0, 40.0, "PACK", "Mother Dairy"),
        ("Epigamia Greek Yogurt Natural 85g", "Dairy & Breakfast", 45.0, 50.0, "PCS", "Epigamia"),
        ("Kellogg's Corn Flakes Original 500g", "Dairy & Breakfast", 185.0, 210.0, "PACK", "Kellogg's"),
        ("Kellogg's Chocos Chocolate Cereal 385g", "Dairy & Breakfast", 175.0, 195.0, "PACK", "Kellogg's"),
        ("Quaker Rolled Oats 1kg", "Dairy & Breakfast", 170.0, 199.0, "KG", "Quaker"),
        ("Saffola Masala Oats Classic Masala 500g", "Dairy & Breakfast", 165.0, 190.0, "PACK", "Saffola"),
        ("Kissan Mixed Fruit Jam 500g", "Dairy & Breakfast", 155.0, 175.0, "PCS", "Kissan"),
        ("Nutella Hazelnut Spread with Cocoa 350g", "Dairy & Breakfast", 340.0, 390.0, "PCS", "Nutella"),
        ("Pintola All Natural Peanut Butter Creamy 1kg", "Dairy & Breakfast", 390.0, 499.0, "KG", "Pintola"),
        ("Dr. Oetker Funfoods Mayonnaise 250g", "Dairy & Breakfast", 75.0, 89.0, "PCS", "Funfoods"),
        ("Britannia Brown Bread 400g", "Dairy & Breakfast", 48.0, 50.0, "PACK", "Britannia"),
        ("English Oven 100% Atta Bread 400g", "Dairy & Breakfast", 50.0, 55.0, "PACK", "English Oven"),
        ("Amul Whipping Cream 250ml", "Dairy & Breakfast", 110.0, 120.0, "ML", "Amul"),

        # 4. Tea, Coffee & Health Drinks (20 items)
        ("Tata Tea Gold Rich Taste 500g", "Tea, Coffee & Health Drinks", 295.0, 340.0, "PACK", "Tata Tea"),
        ("Tata Tea Premium Desh Ki Chai 1kg", "Tea, Coffee & Health Drinks", 475.0, 540.0, "KG", "Tata Tea"),
        ("Red Label Natural Care Tea 500g", "Tea, Coffee & Health Drinks", 285.0, 325.0, "PACK", "Red Label"),
        ("Wagh Bakri Premium Leaf Tea 500g", "Tea, Coffee & Health Drinks", 265.0, 300.0, "PACK", "Wagh Bakri"),
        ("Taj Mahal Rich Tea 500g", "Tea, Coffee & Health Drinks", 360.0, 410.0, "PACK", "Taj Mahal"),
        ("Twinings Green Tea Lemon & Honey 25 Bags", "Tea, Coffee & Health Drinks", 220.0, 260.0, "BOX", "Twinings"),
        ("Tetley Green Tea Lemon & Honey 25 Bags", "Tea, Coffee & Health Drinks", 165.0, 190.0, "BOX", "Tetley"),
        ("Nescafe Classic 100% Pure Coffee 100g Jar", "Tea, Coffee & Health Drinks", 295.0, 340.0, "PCS", "Nescafe"),
        ("Nescafe Classic Pure Instant Coffee 50g", "Tea, Coffee & Health Drinks", 160.0, 185.0, "PCS", "Nescafe"),
        ("Bru Instant Coffee 100g", "Tea, Coffee & Health Drinks", 195.0, 225.0, "PCS", "Bru"),
        ("Bru Gold 100% Pure Instant Coffee 100g", "Tea, Coffee & Health Drinks", 290.0, 335.0, "PCS", "Bru"),
        ("Davidoff Cafe Rich Aroma Instant Coffee 100g", "Tea, Coffee & Health Drinks", 495.0, 600.0, "PCS", "Davidoff"),
        ("Horlicks Classic Malt Drink 500g", "Tea, Coffee & Health Drinks", 235.0, 260.0, "PACK", "Horlicks"),
        ("Bournvita Chocolate Health Drink 1kg", "Tea, Coffee & Health Drinks", 410.0, 460.0, "KG", "Bournvita"),
        ("Boost Energy & Health Drink 500g", "Tea, Coffee & Health Drinks", 255.0, 280.0, "PACK", "Boost"),
        ("Complan Royal Chocolate Flavour 500g", "Tea, Coffee & Health Drinks", 275.0, 305.0, "PACK", "Complan"),
        ("Ensure Complete Nutrition Drink Vanilla 400g", "Tea, Coffee & Health Drinks", 660.0, 730.0, "PACK", "Ensure"),
        ("Protinex High Protein Drink Chocolate 400g", "Tea, Coffee & Health Drinks", 595.0, 675.0, "PACK", "Protinex"),
        ("MTR Badam Drink Mix 200g", "Tea, Coffee & Health Drinks", 125.0, 140.0, "PACK", "MTR"),
        ("Rooh Afza Sharbat 750ml", "Tea, Coffee & Health Drinks", 175.0, 190.0, "LTR", "Hamdard"),

        # 5. Beverages & Cold Drinks (20 items)
        ("Coca-Cola Soft Drink 750ml Bottle", "Beverages & Cold Drinks", 40.0, 40.0, "PCS", "Coca-Cola"),
        ("Coca-Cola Soft Drink 2L Bottle", "Beverages & Cold Drinks", 95.0, 100.0, "PCS", "Coca-Cola"),
        ("Thums Up Carbonated Beverage 750ml", "Beverages & Cold Drinks", 40.0, 40.0, "PCS", "Thums Up"),
        ("Thums Up Charged 2.25L", "Beverages & Cold Drinks", 95.0, 100.0, "PCS", "Thums Up"),
        ("Sprite Lemon Flavour Soft Drink 750ml", "Beverages & Cold Drinks", 40.0, 40.0, "PCS", "Sprite"),
        ("Sprite Soft Drink 2.25L", "Beverages & Cold Drinks", 95.0, 100.0, "PCS", "Sprite"),
        ("Fanta Orange Flavoured Drink 750ml", "Beverages & Cold Drinks", 40.0, 40.0, "PCS", "Fanta"),
        ("Limca Lemon Flavoured Drink 750ml", "Beverages & Cold Drinks", 40.0, 40.0, "PCS", "Limca"),
        ("Maaza Mango Drink 1.2L", "Beverages & Cold Drinks", 75.0, 80.0, "PCS", "Maaza"),
        ("Frooti Mango Drink 1.2L", "Beverages & Cold Drinks", 70.0, 75.0, "PCS", "Frooti"),
        ("Slice Thickest Mango Drink 1.2L", "Beverages & Cold Drinks", 72.0, 78.0, "PCS", "Slice"),
        ("Real Fruit Power Mixed Fruit Juice 1L", "Beverages & Cold Drinks", 115.0, 130.0, "LTR", "Real"),
        ("Real Fruit Power Cranberry Juice 1L", "Beverages & Cold Drinks", 125.0, 140.0, "LTR", "Real"),
        ("Real Fruit Power Pomegranate Juice 1L", "Beverages & Cold Drinks", 130.0, 145.0, "LTR", "Real"),
        ("Tropicana 100% Orange Juice 1L", "Beverages & Cold Drinks", 135.0, 150.0, "LTR", "Tropicana"),
        ("Bisleri Mineral Water 1L Bottle", "Beverages & Cold Drinks", 20.0, 20.0, "PCS", "Bisleri"),
        ("Kinley Mineral Water 1L", "Beverages & Cold Drinks", 20.0, 20.0, "PCS", "Kinley"),
        ("Aquafina Packaged Drinking Water 1L", "Beverages & Cold Drinks", 20.0, 20.0, "PCS", "Aquafina"),
        ("Red Bull Energy Drink Can 250ml", "Beverages & Cold Drinks", 125.0, 125.0, "PCS", "Red Bull"),
        ("Monster Energy Drink Can 350ml", "Beverages & Cold Drinks", 120.0, 125.0, "PCS", "Monster"),

        # 6. Snacks, Biscuits & Namkeen (25 items)
        ("Parle-G Gold Glucose Biscuits 1kg", "Snacks & Biscuits", 95.0, 105.0, "PACK", "Parle"),
        ("Britannia Marie Gold Biscuits 1kg", "Snacks & Biscuits", 120.0, 135.0, "PACK", "Britannia"),
        ("Britannia Good Day Cashew Biscuits 600g", "Snacks & Biscuits", 130.0, 150.0, "PACK", "Britannia"),
        ("Britannia Good Day Butter Biscuits 600g", "Snacks & Biscuits", 125.0, 145.0, "PACK", "Britannia"),
        ("Oreo Vanilla Creme Biscuits 300g", "Snacks & Biscuits", 75.0, 85.0, "PACK", "Oreo"),
        ("Sunfeast Dark Fantasy Choco Fills 300g", "Snacks & Biscuits", 125.0, 150.0, "PACK", "Sunfeast"),
        ("Britannia Bourbon Chocolate Cream Biscuits 300g", "Snacks & Biscuits", 65.0, 75.0, "PACK", "Britannia"),
        ("Sunfeast Mom's Magic Cashew & Almond 600g", "Snacks & Biscuits", 130.0, 150.0, "PACK", "Sunfeast"),
        ("Britannia NutriChoice Digestive Biscuits 1kg", "Snacks & Biscuits", 195.0, 225.0, "PACK", "Britannia"),
        ("Britannia 50-50 Maska Chaska Biscuits 300g", "Snacks & Biscuits", 60.0, 70.0, "PACK", "Britannia"),
        ("Lay's India's Magic Masala Potato Chips 90g", "Snacks & Biscuits", 38.0, 40.0, "PACK", "Lay's"),
        ("Lay's Spanish Tomato Tango Potato Chips 90g", "Snacks & Biscuits", 38.0, 40.0, "PACK", "Lay's"),
        ("Lay's Classic Salted Potato Chips 90g", "Snacks & Biscuits", 38.0, 40.0, "PACK", "Lay's"),
        ("Kurkure Masala Munch 90g", "Snacks & Biscuits", 20.0, 20.0, "PACK", "Kurkure"),
        ("Kurkure Solid Masti Twistee Masala 90g", "Snacks & Biscuits", 20.0, 20.0, "PACK", "Kurkure"),
        ("Bingo Mad Angles Achaari Masti 70g", "Snacks & Biscuits", 20.0, 20.0, "PACK", "Bingo"),
        ("Haldiram's Nagpur Aloo Bhujia 400g", "Snacks & Biscuits", 110.0, 125.0, "PACK", "Haldiram's"),
        ("Haldiram's Nagpur Bhujia Sev 400g", "Snacks & Biscuits", 110.0, 125.0, "PACK", "Haldiram's"),
        ("Haldiram's Khatta Meetha Mixture 400g", "Snacks & Biscuits", 105.0, 120.0, "PACK", "Haldiram's"),
        ("Haldiram's All in One Mixture 400g", "Snacks & Biscuits", 115.0, 130.0, "PACK", "Haldiram's"),
        ("Haldiram's Panchrattan Mixture 400g", "Snacks & Biscuits", 145.0, 165.0, "PACK", "Haldiram's"),
        ("Haldiram's Moong Dal Salted 400g", "Snacks & Biscuits", 130.0, 145.0, "PACK", "Haldiram's"),
        ("Act II Butter Lovers Microwave Popcorn 85g", "Snacks & Biscuits", 40.0, 45.0, "PACK", "Act II"),
        ("Pringles Sour Cream & Onion Potato Crisps 107g", "Snacks & Biscuits", 110.0, 125.0, "PCS", "Pringles"),
        ("Doritos Cheese Supreme Nachos 82g", "Snacks & Biscuits", 48.0, 50.0, "PACK", "Doritos"),

        # 7. Instant & Packaged Foods (20 items)
        ("Maggi 2-Minute Masala Noodles 840g (12-Pack)", "Instant & Packaged Foods", 145.0, 168.0, "PACK", "Maggi"),
        ("Maggi 2-Minute Special Masala Noodles 280g (4-Pack)", "Instant & Packaged Foods", 65.0, 72.0, "PACK", "Maggi"),
        ("Yippee Magic Masala Noodles 480g (8-Pack)", "Instant & Packaged Foods", 88.0, 96.0, "PACK", "Sunfeast Yippee"),
        ("Ching's Secret Schezwan Noodles 240g", "Instant & Packaged Foods", 55.0, 60.0, "PACK", "Ching's"),
        ("Top Ramen Fiery Chilli Noodles 280g", "Instant & Packaged Foods", 50.0, 56.0, "PACK", "Top Ramen"),
        ("Knorr Classic Mixed Vegetable Soup 43g", "Instant & Packaged Foods", 35.0, 40.0, "PACK", "Knorr"),
        ("Knorr Classic Hot & Sour Chicken Soup 43g", "Instant & Packaged Foods", 40.0, 45.0, "PACK", "Knorr"),
        ("Ching's Secret Schezwan Chutney 250g Bottle", "Instant & Packaged Foods", 75.0, 85.0, "PCS", "Ching's"),
        ("Kissan Fresh Tomato Ketchup 950g Squeezo", "Instant & Packaged Foods", 125.0, 145.0, "PCS", "Kissan"),
        ("Maggi Rich Tomato Ketchup 1kg", "Instant & Packaged Foods", 130.0, 150.0, "PCS", "Maggi"),
        ("Del Monte Sweet Corn Whole Kernel 420g Can", "Instant & Packaged Foods", 85.0, 99.0, "PCS", "Del Monte"),
        ("MTR Ready to Eat Paneer Butter Masala 300g", "Instant & Packaged Foods", 125.0, 145.0, "PACK", "MTR"),
        ("MTR Ready to Eat Dal Makhani 300g", "Instant & Packaged Foods", 105.0, 120.0, "PACK", "MTR"),
        ("Gits Instant Gulab Jamun Dessert Mix 200g", "Instant & Packaged Foods", 115.0, 130.0, "PACK", "Gits"),
        ("Bambino Vermicelli Roasted 400g", "Instant & Packaged Foods", 42.0, 48.0, "PACK", "Bambino"),
        ("Weikfield Baking Powder 100g", "Instant & Packaged Foods", 35.0, 40.0, "PCS", "Weikfield"),
        ("Weikfield Custard Powder Vanilla 100g", "Instant & Packaged Foods", 45.0, 50.0, "PCS", "Weikfield"),
        ("Hershey's Chocolate Flavoured Syrup 623g", "Instant & Packaged Foods", 215.0, 240.0, "PCS", "Hershey's"),
        ("Knorr Masala No More Tears Cube 80g", "Instant & Packaged Foods", 45.0, 50.0, "PACK", "Knorr"),
        ("Patanjali Pure Honey 500g", "Instant & Packaged Foods", 185.0, 210.0, "PCS", "Patanjali"),

        # 8. Personal Care & Hygiene (25 items)
        ("Dettol Original Bathing Soap 125g (Pack of 4)", "Personal Care & Hygiene", 175.0, 198.0, "PACK", "Dettol"),
        ("Lifebuoy Total 10 Soap 125g (Pack of 4)", "Personal Care & Hygiene", 145.0, 165.0, "PACK", "Lifebuoy"),
        ("Dove Cream Beauty Bathing Bar 100g (Pack of 3)", "Personal Care & Hygiene", 195.0, 225.0, "PACK", "Dove"),
        ("Pears Pure & Gentle Bathing Bar 125g (Pack of 3)", "Personal Care & Hygiene", 185.0, 210.0, "PACK", "Pears"),
        ("Cinthol Original Soap 100g (Pack of 4)", "Personal Care & Hygiene", 150.0, 170.0, "PACK", "Cinthol"),
        ("Colgate Strong Teeth Dental Toothpaste 500g", "Personal Care & Hygiene", 220.0, 255.0, "PACK", "Colgate"),
        ("Colgate MaxFresh Peppermint Ice Gel 300g", "Personal Care & Hygiene", 180.0, 205.0, "PACK", "Colgate"),
        ("Close Up Everfresh Red Hot Gel 300g", "Personal Care & Hygiene", 175.0, 199.0, "PACK", "Close Up"),
        ("Sensodyne Fresh Gel Sensitive Teeth 150g", "Personal Care & Hygiene", 210.0, 235.0, "PACK", "Sensodyne"),
        ("Oral-B Shiny Clean Toothbrush (Buy 2 Get 1 Free)", "Personal Care & Hygiene", 60.0, 75.0, "PACK", "Oral-B"),
        ("Head & Shoulders Anti Dandruff Shampoo 650ml", "Personal Care & Hygiene", 520.0, 620.0, "PCS", "Head & Shoulders"),
        ("Dove Intense Repair Shampoo 650ml", "Personal Care & Hygiene", 495.0, 599.0, "PCS", "Dove"),
        ("Clinic Plus Strong & Long Shampoo 650ml", "Personal Care & Hygiene", 340.0, 399.0, "PCS", "Clinic Plus"),
        ("Pantene Pro-V Hair Fall Control Shampoo 650ml", "Personal Care & Hygiene", 480.0, 575.0, "PCS", "Pantene"),
        ("Parachute 100% Pure Coconut Hair Oil 500ml", "Personal Care & Hygiene", 195.0, 220.0, "PCS", "Parachute"),
        ("Bajaj Almond Drops Non-Sticky Hair Oil 300ml", "Personal Care & Hygiene", 210.0, 245.0, "PCS", "Bajaj"),
        ("Dabur Amla Hair Oil 450ml", "Personal Care & Hygiene", 175.0, 199.0, "PCS", "Dabur"),
        ("Nivea Soft Light Moisturizing Cream 200ml", "Personal Care & Hygiene", 260.0, 310.0, "PCS", "Nivea"),
        ("Vaseline Deep Moisture Body Lotion 400ml", "Personal Care & Hygiene", 295.0, 360.0, "PCS", "Vaseline"),
        ("Gillette Mach 3 Shaving Razor", "Personal Care & Hygiene", 290.0, 349.0, "PCS", "Gillette"),
        ("Gillette Series Sensitive Shaving Foam 418g", "Personal Care & Hygiene", 225.0, 260.0, "PCS", "Gillette"),
        ("Dettol Instant Liquid Handwash Refill 1.5L", "Personal Care & Hygiene", 199.0, 239.0, "PACK", "Dettol"),
        ("Lifebuoy Total 10 Handwash Pouch 1.5L", "Personal Care & Hygiene", 185.0, 215.0, "PACK", "Lifebuoy"),
        ("Stayfree Secure Cottony Soft Sanitary Pads (40 Pads)", "Personal Care & Hygiene", 260.0, 300.0, "PACK", "Stayfree"),
        ("Whisper Choice Ultra Sanitary Wings (36 Pads)", "Personal Care & Hygiene", 240.0, 275.0, "PACK", "Whisper"),

        # 9. Cleaning & Household Care (25 items)
        ("Surf Excel Easy Wash Detergent Powder 5kg", "Cleaning & Household", 590.0, 675.0, "KG", "Surf Excel"),
        ("Surf Excel Matic Front Load Liquid 2L", "Cleaning & Household", 420.0, 480.0, "LTR", "Surf Excel"),
        ("Ariel Complete Washing Powder 4kg", "Cleaning & Household", 510.0, 595.0, "KG", "Ariel"),
        ("Tide Plus Extra Power Detergent Powder 5kg", "Cleaning & Household", 485.0, 560.0, "KG", "Tide"),
        ("Rin Detergent Bar 250g (Pack of 4)", "Cleaning & Household", 85.0, 96.0, "PACK", "Rin"),
        ("Vim Dishwash Gel Lemon 750ml Bottle", "Cleaning & Household", 145.0, 165.0, "PCS", "Vim"),
        ("Vim Dishwash Bar 300g (Pack of 3)", "Cleaning & Household", 65.0, 75.0, "PACK", "Vim"),
        ("Pril Lime Dishwashing Liquid 750ml", "Cleaning & Household", 155.0, 175.0, "PCS", "Pril"),
        ("Scotch-Brite Heavy Duty Scrub Sponge (Pack of 3)", "Cleaning & Household", 75.0, 90.0, "PACK", "Scotch-Brite"),
        ("Harpic Power Plus Toilet Cleaner Liquid 1L", "Cleaning & Household", 185.0, 205.0, "LTR", "Harpic"),
        ("Harpic Bathroom Cleaner Floral 1L", "Cleaning & Household", 175.0, 195.0, "LTR", "Harpic"),
        ("Lizol Surface Disinfectant Cleaner Citrus 2L", "Cleaning & Household", 340.0, 395.0, "LTR", "Lizol"),
        ("Dettol Surface Disinfectant Liquid Lime 1L", "Cleaning & Household", 280.0, 320.0, "LTR", "Dettol"),
        ("Colin Glass & Household Cleaner Refill 1L", "Cleaning & Household", 160.0, 180.0, "LTR", "Colin"),
        ("Good Knight Gold Flash Liquid Mosquito Refill (Pack of 3)", "Cleaning & Household", 220.0, 255.0, "PACK", "Good Knight"),
        ("All Out Ultra Power+ Fan Mosquito Refill (Pack of 2)", "Cleaning & Household", 165.0, 190.0, "PACK", "All Out"),
        ("HIT Flying Insect Killer Black Spray 400ml", "Cleaning & Household", 215.0, 245.0, "PCS", "HIT"),
        ("Odonil Room Air Freshener Blocks 50g (Pack of 4)", "Cleaning & Household", 165.0, 195.0, "PACK", "Odonil"),
        ("Godrej aer Pocket Bathroom Fragrance Gel (Pack of 3)", "Cleaning & Household", 150.0, 175.0, "PACK", "Godrej"),
        ("Comfort After Wash Morning Fresh Fabric Conditioner 860ml", "Cleaning & Household", 215.0, 240.0, "PCS", "Comfort"),
        ("Origami So Soft 3-Ply Toilet Tissue Paper (Pack of 6)", "Cleaning & Household", 185.0, 220.0, "PACK", "Origami"),
        ("Origami Kitchen Towel Paper Roll (Pack of 2)", "Cleaning & Household", 120.0, 140.0, "PACK", "Origami"),
        ("Shalimar Garbage Trash Bags Medium (Pack of 30)", "Cleaning & Household", 95.0, 120.0, "PACK", "Shalimar"),
        ("Gala No Dust Floor Cleaning Broom", "Cleaning & Household", 155.0, 185.0, "PCS", "Gala"),
        ("Scotch-Brite Microfibre Floor Mop", "Cleaning & Household", 399.0, 499.0, "PCS", "Scotch-Brite"),

        # 10. Chocolates & Confectionery (20 items)
        ("Cadbury Dairy Milk Silk Chocolate 150g", "Chocolates & Sweets", 165.0, 175.0, "PCS", "Cadbury"),
        ("Cadbury Dairy Milk Fruit & Nut Silk 143g", "Chocolates & Sweets", 165.0, 175.0, "PCS", "Cadbury"),
        ("Cadbury Dairy Milk Roast Almond Silk 143g", "Chocolates & Sweets", 165.0, 175.0, "PCS", "Cadbury"),
        ("Cadbury Bournville 50% Dark Chocolate 80g", "Chocolates & Sweets", 95.0, 100.0, "PCS", "Cadbury"),
        ("Cadbury 5 Star Chocolate Bar 40g (Pack of 5)", "Chocolates & Sweets", 90.0, 100.0, "PACK", "Cadbury"),
        ("Nestle KitKat 4-Finger Wafer Bar 37.3g (Pack of 4)", "Chocolates & Sweets", 110.0, 120.0, "PACK", "Nestle"),
        ("Nestle Munch Crunchy Wafer Bar (Pack of 10)", "Chocolates & Sweets", 95.0, 100.0, "PACK", "Nestle"),
        ("Ferrero Rocher Premium Hazelnut Chocolates (16 Pieces)", "Chocolates & Sweets", 495.0, 575.0, "BOX", "Ferrero Rocher"),
        ("Snickers Peanut Filled Chocolate Bar 45g (Pack of 3)", "Chocolates & Sweets", 135.0, 150.0, "PACK", "Snickers"),
        ("Mars Caramel Nougat Chocolate Bar 51g", "Chocolates & Sweets", 55.0, 60.0, "PCS", "Mars"),
        ("Kinder Joy with Surprise Toy (Pack of 3)", "Chocolates & Sweets", 130.0, 140.0, "PACK", "Kinder"),
        ("Alpenliebe Juzt Jelly Strawberry 150g", "Chocolates & Sweets", 45.0, 50.0, "PACK", "Alpenliebe"),
        ("Center Fresh Spearmint Chewing Gum Stick (Pack of 20)", "Chocolates & Sweets", 80.0, 90.0, "PACK", "Center Fresh"),
        ("Happydent White Spearmint Chewing Gum 65g", "Chocolates & Sweets", 45.0, 50.0, "PCS", "Happydent"),
        ("Pulse Tangy Kachcha Aam Candy 180g Pouch", "Chocolates & Sweets", 48.0, 50.0, "PACK", "Pass Pass"),
        ("Chupa Chups Sour Bites Chewy Candy 54g", "Chocolates & Sweets", 35.0, 40.0, "PACK", "Chupa Chups"),
        ("Mentos Rainbow Rolls Chewy Dragees (Pack of 3)", "Chocolates & Sweets", 45.0, 50.0, "PACK", "Mentos"),
        ("Haldiram's Soan Papdi 500g Box", "Chocolates & Sweets", 135.0, 150.0, "BOX", "Haldiram's"),
        ("Haldiram's Rasgulla Tin 1kg", "Chocolates & Sweets", 210.0, 240.0, "PCS", "Haldiram's"),
        ("Haldiram's Gulab Jamun Tin 1kg", "Chocolates & Sweets", 220.0, 250.0, "PCS", "Haldiram's"),
    ]

    print(f"Loaded {len(catalog)} item definitions. Starting insertion...")

    category_cache = {}
    created_count = 0
    updated_count = 0

    base_barcode_prefix = 8901000000000

    for idx, (name, cat_name, price, mrp, unit, brand) in enumerate(catalog, start=1):
        if cat_name not in category_cache:
            cat_obj, _ = Category.objects.get_or_create(shop=shop, name=cat_name)
            category_cache[cat_name] = cat_obj
        category = category_cache[cat_name]

        # Generate consistent unique 13-digit EAN barcode
        # Format: 8901000000001, 8901000000002, ..., 8901000000200
        barcode_num = str(base_barcode_prefix + idx)
        sku = f"SKU-FMCG-{idx:04d}"

        product, created = Product.objects.get_or_create(
            shop=shop,
            sku=sku,
            defaults={
                'category': category,
                'name': name,
                'brand': brand,
                'selling_price': Decimal(str(price)),
                'mrp': Decimal(str(mrp)),
                'tax_rate': Decimal('5.00') if 'Grocery' in cat_name or 'Oils' in cat_name else Decimal('18.00'),
                'unit': unit,
                'min_stock_alert': 20
            }
        )

        if not created:
            product.name = name
            product.selling_price = Decimal(str(price))
            product.mrp = Decimal(str(mrp))
            product.category = category
            product.brand = brand
            product.save()

        # Unique Barcode Mapping
        barcode_obj, _ = ProductBarcode.objects.get_or_create(
            product=product,
            barcode=barcode_num,
            defaults={'format': 'EAN_13', 'is_primary': True}
        )

        # 500 Quantity Stock
        inventory, _ = Inventory.objects.get_or_create(
            shop=shop,
            product=product,
            defaults={'current_stock': Decimal('500.00'), 'reorder_level': 20}
        )
        inventory.current_stock = Decimal('500.00')
        inventory.save()

        if created:
            created_count += 1
            StockTransaction.objects.create(
                shop=shop,
                product=product,
                tx_type=StockTransaction.TxType.PURCHASE,
                quantity=Decimal('500.00'),
                balance_after=Decimal('500.00'),
                reference_id=f"INITIAL-STOCK-{sku}",
                notes="Seeded initial retail inventory of 500 units"
            )
        else:
            updated_count += 1

    total = Product.objects.filter(shop=shop).count()
    print(f"\n✓ Successfully seeded! Created: {created_count}, Updated: {updated_count}. Total store products: {total}.")
    print(f"✓ All products have exactly 500 units in stock.")
    print(f"✓ Barcodes range: 8901000000001 through 8901000000200.")

if __name__ == '__main__':
    seed_200_products()

