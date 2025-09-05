import os
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import piexif
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut
from datetime import datetime

# Configuration
INPUT_FOLDER = './content/photos'              # Set to your input folder path
OUTPUT_FOLDER = './content/outputs'       # Set to your output folder path
FONT_PATH = './content/fonts/LiberationSans-Regular.ttf'  # Path to your downloaded .ttf font file
FONT_SIZE = 40
TEXT_COLOR = (255, 255, 255)            # White text
SHADOW_COLOR = (0, 0, 0)                # Black shadow
MAX_WIDTH = 2048                         # Maximum width for images (optional)

# Supported image extensions
SUPPORTED_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.gif')

# Initialize geolocator
geolocator = Nominatim(user_agent="image_metadata_overlay")

# Determine the appropriate resampling filter
try:
    Resampling = Image.Resampling  # Pillow >= 10
    RESAMPLE_FILTER = Resampling.LANCZOS
except AttributeError:
    RESAMPLE_FILTER = Image.LANCZOS  # Pillow < 10

    
def get_exif_data(image_path):
    try:
        exif_dict = piexif.load(image_path)
        return exif_dict
    except Exception as e:
        print(f"Error reading EXIF data from {image_path}: {e}")
        return None

def get_date(exif_dict):
    for tag in ['DateTimeOriginal', 'DateTime', 'DateTimeDigitized']:
        tag_id = getattr(piexif.ExifIFD, tag, None)
        if tag_id:
            date_time = exif_dict['Exif'].get(tag_id)
            return date_time.decode('utf-8')
            # if date_time:
            #     try:
            #         # Parse the date string and format it to show only the date
            #         date_obj = datetime.strptime(date_time.decode('utf-8'), "%Y:%m:%d %H:%M:%S")
            #         return date_obj.strftime("%Y-%m-%d")
            #     except ValueError:
            #         # If parsing fails, return the date part as is
            #         return date_time.decode('utf-8').split()[0]
    return "Unknown Date"

def get_gps_coords(exif_dict):
    gps_info = exif_dict.get('GPS', {})
    if not gps_info:
        return None

    def _convert_to_degrees(value):
        d, m, s = value
        return d[0]/d[1] + (m[0]/m[1])/60 + (s[0]/s[1])/3600

    try:
        lat = _convert_to_degrees(gps_info[piexif.GPSIFD.GPSLatitude])
        if gps_info.get(piexif.GPSIFD.GPSLatitudeRef, b'N') != b'N':
            lat = -lat

        lon = _convert_to_degrees(gps_info[piexif.GPSIFD.GPSLongitude])
        if gps_info.get(piexif.GPSIFD.GPSLongitudeRef, b'E') != b'E':
            lon = -lon

        return (lat, lon)
    except KeyError as e:
        print(f"Missing GPS key: {e}")
        return None
    except Exception as e:
        print(f"Error converting GPS data: {e}")
        return None

def reverse_geocode(coords):
    try:
        location = geolocator.reverse(coords, timeout=10)
        if location:
            address = location.raw['address']
            # Create a detailed location string
            location_parts = []
            for part in ['road', 'suburb', 'city', 'state_district', 'state', 'country']:
                if part in address:
                    location_parts.append(address[part])
            return ', '.join(location_parts)
        else:
            return "Unknown Location"
    except GeocoderTimedOut:
        print("Geocoder service timed out.")
        return "Location Unavailable"
    except Exception as e:
        print(f"Geocoding error: {e}")
        return "Location Unavailable"


def add_overlay(image, text, font_path, font_size, text_color, shadow_color):
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype(font_path, font_size)
    except IOError:
        print(f"Font not found at {font_path}. Using default font.")
        font = ImageFont.load_default()

    text_lines = text.split('\n')
    padding = 10
    shadow_offset = 2

    # Calculate maximum width for text
    max_text_width = image.width - (padding * 4)  # Leave some padding on both sides

    # Function to get text size
    def get_text_size(text):
        bbox = font.getbbox(text)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Function to wrap text
    def wrap_text(text, max_width):
        words = text.split()
        lines = []
        current_line = []
        for word in words:
            test_line = ' '.join(current_line + [word])
            width, _ = get_text_size(test_line)
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        if current_line:
            lines.append(' '.join(current_line))
        return lines

    # Wrap location text if it's too long
    wrapped_lines = []
    for line in text_lines:
        if ':' in line:
            label, content = line.split(':', 1)
            label_width, _ = get_text_size(label + ': ')
            wrapped = wrap_text(content.strip(), max_text_width - label_width)
            wrapped_lines.extend([f"{label}:{wrapped[0]}"] + wrapped[1:])
        else:
            wrapped_lines.extend(wrap_text(line, max_text_width))

    # Calculate text dimensions
    total_text_height = sum(get_text_size(line)[1] for line in wrapped_lines)
    total_text_height += padding * (len(wrapped_lines) - 1)  # Add padding between lines

    # Position text at the bottom-right corner
    x = image.width - max_text_width - padding
    y = image.height - total_text_height - padding * 2

    # Draw each line of text with shadow
    for line in wrapped_lines:
        width, height = get_text_size(line)
        # Draw shadow
        draw.text((x + shadow_offset, y + shadow_offset), line, font=font, fill=shadow_color)
        # Draw text
        draw.text((x, y), line, font=font, fill=text_color)
        y += height + padding

def process_image(image_path, output_path):
    exif_data = get_exif_data(image_path)
    if not exif_data:
        print(f"No EXIF data for {image_path}. Skipping.")
        return

    date = get_date(exif_data)
    coords = get_gps_coords(exif_data)
    location = "Unknown Location"

    if coords:
        location = reverse_geocode(coords)

    text = f"Date and Time: {date}\nLattitude, Longitude: {coords}\nLocation: {location}"

    try:
        with Image.open(image_path) as img:
            # Optionally resize image if it's too large
            if img.width > MAX_WIDTH:
                ratio = MAX_WIDTH / float(img.width)
                new_height = int(float(img.height) * ratio)
                img = img.resize((MAX_WIDTH, new_height), RESAMPLE_FILTER)

            # Create a copy of the image to work with
            img_with_overlay = img.copy()

            add_overlay(img_with_overlay, text, FONT_PATH, FONT_SIZE, TEXT_COLOR, SHADOW_COLOR)

            # Ensure output directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # Preserve original EXIF data when saving
            if "exif" in img.info:
                img_with_overlay.save(output_path, exif=img.info["exif"])
            else:
                img_with_overlay.save(output_path)

            print(f"Processed and saved: {output_path}")
    except Exception as e:
        print(f"Error processing {image_path}: {e}")


def main():
    if not os.path.exists(INPUT_FOLDER):
        print(f"Input folder '{INPUT_FOLDER}' does not exist.")
        return

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for root, dirs, files in os.walk(INPUT_FOLDER):
        for file in files:
            if file.lower().endswith(SUPPORTED_EXTENSIONS):
                input_path = os.path.join(root, file)
                # Calculate the relative path, but don't include INPUT_FOLDER in the calculation
                relative_path = os.path.relpath(input_path, INPUT_FOLDER)
                # Combine OUTPUT_FOLDER with the relative path
                output_path = os.path.join(OUTPUT_FOLDER, relative_path)
                output_dir = os.path.dirname(output_path)
                os.makedirs(output_dir, exist_ok=True)

                process_image(input_path, output_path)

if __name__ == "__main__":
    main()