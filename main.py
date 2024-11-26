from flask import Flask, request, jsonify
import os
import random
import requests
from PIL import Image
from io import BytesIO
import cloudinary
import cloudinary.uploader
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json

app = Flask(__name__)

# Set up Cloudinary
cloudinary.config(
    cloud_name="ddtkjvcv3",  # Replace with your Cloudinary cloud name
    api_key="373545249941684",  # Replace with your Cloudinary API key
    api_secret="EEI0vX_rchzQpyeHqr_9k_fnlig"  # Replace with your Cloudinary API secret
)

# Set up gspread
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Load Google credentials from environment variable (Render secret)
google_credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
if google_credentials_json is None:
    raise ValueError("Environment variable 'GOOGLE_CREDENTIALS' is missing.")

credentials_dict = json.loads(google_credentials_json)

credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, SCOPES)
gc = gspread.authorize(credentials)

# Access the Google Sheet
SPREADSHEET_ID = '13hOGcAON2smDiXzGuzmxQW9SLFS-wxJTPhJbkL2SWH0'  # Replace with your Google Sheet ID
sheet = gc.open_by_key(SPREADSHEET_ID)
input_sheet = sheet.worksheet("PASTE SKU")
output_sheet = sheet.worksheet("DATA GENERATION")

# Path to the .png tag image
TAG_IMAGE_PATH = "AG.png"  # Replace with the path to your tag image


def generate_ean():
    """Generates a valid EAN-13 code."""
    digits = [random.randint(0, 9) for _ in range(12)]
    odd_sum = sum(digits[-1::-2])
    even_sum = sum(digits[-2::-2])
    checksum = (10 - (odd_sum + 3 * even_sum) % 10) % 10
    return ''.join(map(str, digits)) + str(checksum)


def process_image(image_url, sku_code):
    """Processes an image: downloads, tags, and uploads to Cloudinary."""
    try:
        response = requests.get(image_url)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGBA")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading image for SKU {sku_code}: {e}")
        return None

    tag_img = Image.open(TAG_IMAGE_PATH).convert("RGBA")
    tag_size = int(min(img.width, img.height) * 0.2)
    tag_img = tag_img.resize((tag_size, tag_size), Image.Resampling.LANCZOS)

    padding = 10
    x_pos = img.width - tag_size - padding
    y_pos = padding

    img.paste(tag_img, (x_pos, y_pos), tag_img)
    output_path = f"{sku_code}.png"
    img.save(output_path, format="PNG")

    upload_response = cloudinary.uploader.upload(output_path, public_id=sku_code)
    os.remove(output_path)
    return upload_response['secure_url']


def fetch_data():
    """Fetches data from the input sheet."""
    return input_sheet.get_all_values()[1:]  # Skip the header row


def update_sheet(data):
    """Updates the output sheet with data."""
    output_sheet.update('A1', [["SKU Code", "EAN Code", "Image Link"]])
    output_sheet.update('A2', data)


@app.route('/process-data', methods=['POST'])
def process_data():
    """Endpoint to trigger the data processing."""
    input_data = fetch_data()
    output_data = []  # Initialize the output data list

    for row in input_data:
        if len(row) < 2:  # Skip rows with insufficient data
            continue
        sku_code, image_link = row
        ean_code = generate_ean()
        new_image_link = process_image(image_link, sku_code)
        if new_image_link:
            output_data.append([sku_code, ean_code, new_image_link])

    update_sheet(output_data)
    return jsonify({"status": "success", "message": "Data processed successfully!"})


@app.route('/')
def home():
    return "Welcome to the Image Tagging API!"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Use PORT environment variable, default to 8080
    app.run(host='0.0.0.0', port=port)
