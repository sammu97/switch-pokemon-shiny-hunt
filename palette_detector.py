import cv2
import numpy as np
from sklearn.cluster import KMeans
from pathlib import Path
import json
import argparse
from tqdm import tqdm
import re

# --- Config Loading ---
BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SPRITE_DIR = BASE_DIR / "firered-leafgreen"
DB_PATH = BASE_DIR / "palette_db.json"
SHINY_CHECK_CONFIG = CONFIG["shiny_check"]

# --- Core Image Processing Functions ---

def clean_sprite_from_frame(frame: np.ndarray, roi_key: str) -> np.ndarray | None:
    """
    Crops a frame to a specified ROI, flips if necessary, and removes the background
    by using OpenCV's FloodFill algorithm starting from the corners.
    Returns a clean sprite with an alpha channel.
    """
    roi = SHINY_CHECK_CONFIG[roi_key]

    if roi['y2'] > frame.shape[0] or roi['x2'] > frame.shape[1]:
        print(f"FATAL ERROR: ROI '{roi_key}' is outside the image bounds.")
        return None

    cropped_sprite = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]].copy()

    if cropped_sprite.size == 0:
        print(f"FATAL ERROR: ROI '{roi_key}' is empty. Check coordinates.")
        return None

    if roi.get("flip_horizontally", False):
        cropped_sprite = cv2.flip(cropped_sprite, 1)

    # 1. Setup for FloodFill
    h, w = cropped_sprite.shape[:2]

    # OpenCV's floodFill requires a mask that is exactly 2 pixels wider and taller than the image
    mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

    # Tolerance for background color variations (handles capture card noise/compression)
    tolerance = (15, 15, 15)

    # 2. FloodFill from all four corners
    # This ensures we catch the whole background even if a floating sprite particle blocks a path
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]

    for corner in corners:
        cv2.floodFill(
            image=cropped_sprite,
            mask=mask,
            seedPoint=corner,
            newVal=(0, 0, 0),  # Safely pass a dummy value to avoid Python TypeErrors
            loDiff=tolerance,
            upDiff=tolerance,
            # Flags:
            # 4 = check 4 neighboring pixels (up, down, left, right)
            # (255 << 8) = fill the mask with the value 255 (white)
            # cv2.FLOODFILL_MASK_ONLY = do not modify the original image, just update the mask
            flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY
        )

    # 3. Apply the mask to create transparency
    # The mask is 2 pixels larger, so we slice it [1:-1, 1:-1] to match the sprite's dimensions
    background_mask = mask[1:-1, 1:-1]

    # Convert to BGRA (adds the alpha channel)
    cleaned_sprite = cv2.cvtColor(cropped_sprite, cv2.COLOR_BGR2BGRA)

    # Wherever the floodfill mask is 255 (the background), set the BGRA values to transparent [0,0,0,0]
    cleaned_sprite[background_mask == 255] = [0, 0, 0, 0]

    return cleaned_sprite


def extract_palette(image: np.ndarray, n_colors: int = 4) -> list[tuple[float, float, float]] | None:
    # Safely handle images that don't have an alpha channel (like downloaded database sprites)
    if image.shape[2] == 4:
        bgr_channels = image[:, :, :3]
        alpha_channel = image[:, :, 3]
        opaque_mask = alpha_channel > 0
        
        if not np.any(opaque_mask):
            return None
            
        pixels_to_convert = bgr_channels[opaque_mask]
    else:
        pixels_to_convert = image.reshape(-1, 3)

    if len(pixels_to_convert) < n_colors:
        return None

    # Convert the 1D list of BGR pixels into a 2D format cvtColor expects (1, N, 3)
    pixels_2d = np.uint8([pixels_to_convert])
    
    # Convert BGR to LAB color space
    lab_pixels = cv2.cvtColor(pixels_2d, cv2.COLOR_BGR2LAB)[0]

    kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init='auto')
    kmeans.fit(lab_pixels)

    # Return the LAB palette centers as floats for JSON serialization
    palette_lab = kmeans.cluster_centers_
    return [tuple(float(c) for c in color) for color in palette_lab]

def palette_distance(palette1: list, palette2: list) -> float:
    """Calculates the 'distance' between two unordered palettes."""
    if not palette1 or not palette2: return float('inf')
    p1 = np.array(palette1)
    p2 = np.array(palette2)
    dist_1_to_2 = sum(min(np.linalg.norm(c1 - c2) for c2 in p2) for c1 in p1)
    dist_2_to_1 = sum(min(np.linalg.norm(c2 - c1) for c1 in p1) for c2 in p2)
    return dist_1_to_2 + dist_2_to_1

# --- Main Detector Function ---

def is_shiny_from_frame(frame: np.ndarray, db: dict, target_pokemon_id: str, roi_key: str, debug_windows=False) -> bool:
    """The main detection function for the hunting loop."""
    cleaned_sprite = clean_sprite_from_frame(frame, roi_key)
    if cleaned_sprite is None:
        return False

    live_palette = extract_palette(cleaned_sprite)
    if not live_palette:
        return False

    # Try to load the user's baseline palette for comparison
    baseline_path = BASE_DIR / "shiny_checks" / "baseline_palette.json"
    if baseline_path.exists():
        with open(baseline_path, "r") as f:
            baseline_palette = json.load(f)
        
        dist_to_baseline = palette_distance(live_palette, baseline_palette)
        print(f"Dist to Baseline Normal: {dist_to_baseline:.2f}")

        # It's a shiny if it is significantly different from the live baseline.
        is_shiny = dist_to_baseline > 150.0
    else:
        print("Warning: No baseline found. Falling back to DB comparison.")
        target_palettes = db.get(target_pokemon_id)
        if not target_palettes:
            print(f"Warning: Target Pokémon '{target_pokemon_id}' not in database.")
            return False

        dist_normal = palette_distance(live_palette, target_palettes["normal"])
        dist_shiny = palette_distance(live_palette, target_palettes["shiny"])
        
        is_shiny = (dist_shiny < dist_normal * 0.85) and (dist_shiny < 1000)
        print(f"Match for {target_pokemon_id}: Normal Dist: {dist_normal:.2f}, Shiny Dist: {dist_shiny:.2f} -> Shiny? {is_shiny}")


    if debug_windows:
        cv2.imshow("Cleaned Sprite", cleaned_sprite)
        print("Press any key in a preview window to close.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return is_shiny

# --- CLI Tool Functions ---

def build_palette_database():
    """Analyzes all sprites and saves their palettes to a JSON file."""
    print("Building palette database...")
    database = {}
    sprite_files = list(SPRITE_DIR.glob("*.png"))

    for normal_path in tqdm(sprite_files, desc="Analyzing Sprites"):
        match = re.match(r"(\d+)", normal_path.name)
        if not match: continue
        
        pokedex_id = match.group(1)
        shiny_files = list((SPRITE_DIR / "shiny").glob(f"{pokedex_id}*.png"))
        if not shiny_files: continue
        
        shiny_path = shiny_files[0]
        db_key = normal_path.stem

        normal_img = cv2.imread(str(normal_path), cv2.IMREAD_UNCHANGED)
        shiny_img = cv2.imread(str(shiny_path), cv2.IMREAD_UNCHANGED)

        if normal_img is None or shiny_img is None: continue

        normal_palette = extract_palette(normal_img)
        shiny_palette = extract_palette(shiny_img)

        if normal_palette and shiny_palette:
            database[db_key] = {"normal": normal_palette, "shiny": shiny_palette}
    
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(database, f, indent=2)
        
    print(f"\nDatabase built successfully with {len(database)} entries.")

def identify_from_scene(scene_path: str, db: dict):
    """Identifies a Pokémon from a full game scene for testing."""
    print(f"Identifying Pokémon from scene: {scene_path}")
    
    try:
        scene_img = cv2.imread(scene_path)
        if scene_img is None:
            print("Error: Could not read scene file.")
            return
    except Exception as e:
        print(f"Error reading scene: {e}")
        return

    cleaned_sprite = clean_sprite_from_frame(scene_img, "summary_sprite_roi")
    if cleaned_sprite is None:
        print("Warning: Could not create a clean sprite for analysis.")
        return

    live_palette = extract_palette(cleaned_sprite)
    if not live_palette:
        print("Warning: Could not extract a palette from the cleaned sprite.")
        return

    # Try to load the user's baseline palette for comparison
    baseline_path = BASE_DIR / "shiny_checks" / "baseline_palette.json"
    if baseline_path.exists():
        with open(baseline_path, "r") as f:
            baseline_palette = json.load(f)
        
        dist_to_baseline = palette_distance(live_palette, baseline_palette)
        
        print("\n--- Baseline Comparison Result ---")
        print(f"Distance to your normal baseline: {dist_to_baseline:.2f}")
        
        shiny_found = dist_to_baseline > 150.0
        print(f"Is it considered Shiny (>150 distance)? {shiny_found}")
        
        print("---------------------------------------")
    else:
        print("\nNote: 'shiny_checks/baseline_palette.json' not found.")
        print("Run 'python3 hunt_loop.py' at least once to create a baseline.")

        target_pokemon_id = SHINY_CHECK_CONFIG["target_pokemon"]
        target_palettes = db.get(target_pokemon_id)
        if target_palettes:
            dist_to_shiny_db = palette_distance(live_palette, target_palettes["shiny"])
            print(f"For reference, distance to perfect Shiny {target_pokemon_id} in DB: {dist_to_shiny_db:.2f}")

    cv2.imshow("Cleaned Sprite", cleaned_sprite)
    print("Press any key to close the preview window.")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Pokémon Shiny Detector using Palette Analysis.")
    parser.add_argument("--build-db", action="store_true", help="Build the palette database.")
    parser.add_argument("--test-scene", type=str, help="Path to a full game scene to identify.")
    
    args = parser.parse_args()

    if args.build_db:
        build_palette_database()
    elif args.test_scene:
        if not DB_PATH.exists():
            print("Error: Palette database not found. Please run with --build-db first.")
        else:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                db = json.load(f)
            identify_from_scene(args.test_scene, db)
    else:
        parser.print_help()
