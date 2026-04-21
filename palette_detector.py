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
    by using the colors of the outer boundary pixels as a mask.
    Returns a clean sprite with an alpha channel.
    """
    roi = SHINY_CHECK_CONFIG[roi_key]
    
    if roi['y2'] > frame.shape[0] or roi['x2'] > frame.shape[1]:
        print(f"FATAL ERROR: ROI '{roi_key}' is outside the image bounds.")
        return None
        
    cropped_sprite = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]
    
    if cropped_sprite.size == 0:
        print(f"FATAL ERROR: ROI '{roi_key}' is empty. Check coordinates.")
        return None

    if roi.get("flip_horizontally", False):
        cropped_sprite = cv2.flip(cropped_sprite, 1)

    border_pixels = np.concatenate([
        cropped_sprite[0, :], cropped_sprite[-1, :],
        cropped_sprite[:, 0], cropped_sprite[:, -1],
    ])
    unique_border_colors = set(tuple(color) for color in border_pixels)
    
    combined_mask = np.zeros(cropped_sprite.shape[:2], dtype=np.uint8)
    tolerance = 15
    for color in unique_border_colors:
        lower_bound = tuple(max(0, int(c) - tolerance) for c in color)
        upper_bound = tuple(min(255, int(c) + tolerance) for c in color)
        mask = cv2.inRange(cropped_sprite, np.array(lower_bound), np.array(upper_bound))
        combined_mask = cv2.bitwise_or(combined_mask, mask)

    cleaned_sprite = cv2.cvtColor(cropped_sprite, cv2.COLOR_BGR2BGRA)
    cleaned_sprite[combined_mask == 255] = [0, 0, 0, 0]
    
    return cleaned_sprite

def extract_palette(image: np.ndarray, n_colors: int = 4) -> list[tuple[int, int, int]] | None:
    """Extracts the 'n' most dominant colors from an image with transparency."""
    if image.shape[2] != 4:
        print("Error: extract_palette requires an image with an alpha channel.")
        return None
        
    bgr_channels = image[:, :, :3]
    alpha_channel = image[:, :, 3]
    opaque_mask = alpha_channel > 0
    pixels = bgr_channels[opaque_mask]

    if len(pixels) < n_colors:
        return None

    kmeans = KMeans(n_clusters=n_colors, random_state=42, n_init='auto')
    kmeans.fit(pixels)
    
    palette_bgr = kmeans.cluster_centers_
    palette_rgb = [tuple(int(c) for c in color) for color in palette_bgr[:, ::-1]]
    palette_rgb.sort(key=lambda c: sum(c))
    
    return palette_rgb

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

    is_shiny = is_shiny_from_frame(scene_img, db, SHINY_CHECK_CONFIG["target_pokemon"], "summary_sprite_roi", debug_windows=True)
    
    if is_shiny is not None:
        print(f"\nFinal Result: The Pokémon is likely {'SHINY' if is_shiny else 'NORMAL'}")


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
