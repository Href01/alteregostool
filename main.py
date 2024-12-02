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
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

app = Flask(__name__)

# Set up Cloudinary
cloudinary.config(
    cloud_name="ddtkjvcv3",  # Replace with your Cloudinary cloud name
    api_key="373545249941684",  # Replace with your Cloudinary API key
    api_secret="EEI0vX_rchzQpyeHqr_9k_fnlig"  # Replace with your Cloudinary API secret
)

# Set up gspread
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

# Load Google credentials from environment variable
google_credentials_json = os.environ.get('GOOGLE_CREDENTIALS')
if not google_credentials_json:
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

# Set up requests session with retries
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

BATCH_SIZE = 10  # Process 10 rows at a time

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
        response = session.get(image_url, timeout=10)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content)).convert("RGBA")
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Error downloading image for SKU {sku_code}: {e}")
        return None

    try:
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
    except Exception as e:
        app.logger.error(f"Error processing image for SKU {sku_code}: {e}")
        return None

def fetch_data_in_batches():
    """Fetches data from the input sheet in batches of 10 rows."""
    all_data = input_sheet.get_all_values()[1:]  # Skip the header row
    for i in range(0, len(all_data), BATCH_SIZE):
        yield all_data[i:i + BATCH_SIZE]

def update_sheet(data):
    """Updates the output sheet with data."""
    try:
        output_sheet.update('A1', [["SKU Code", "EAN Code", "Image Link"]])
        output_sheet.update('A2', data)
    except Exception as e:
        app.logger.error(f"Error updating output sheet: {e}")

@app.route('/process-data', methods=['POST'])
def process_data():
    """Endpoint to trigger the data processing."""
    input_data_batches = fetch_data_in_batches()
    output_data = []  # Initialize the output data list

    for batch in input_data_batches:
        for row in batch:
            if len(row) < 2:  # Skip rows with insufficient data
                continue
            sku_code, image_link = row
            ean_code = generate_ean()
            new_image_link = process_image(image_link, sku_code)
            if new_image_link:
                output_data.append([sku_code, ean_code, new_image_link])

        app.logger.info(f"Processed a batch of {len(batch)} rows.")

    if output_data:
        update_sheet(output_data)
    else:
        return jsonify({"status": "error", "message": "No valid data to process"}), 500

    return jsonify({"status": "success", "message": f"Processed {len(output_data)} rows successfully!"})

@app.route('/')
def home():
    return "Welcome to the Image Tagging API!"

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))  # Use PORT environment variable, default to 8080
    app.run(host='0.0.0.0', port=port)
