import cv2
import numpy as np
from pathlib import Path
import json
import argparse

# --- Config Loading ---
BASE_DIR = Path(__file__).resolve().parent
with open(BASE_DIR / "config.json", "r", encoding="utf-8") as f:
    CONFIG = json.load(f)

SHINY_CHECK_CONFIG = CONFIG["shiny_check"]


def is_shiny_from_frame(frame: np.ndarray, roi_key: str, debug_windows=False) -> bool:
    """
    Checks for a shiny by detecting the bright yellow Shiny Star
    in the top right quadrant of the summary box.
    """
    roi = SHINY_CHECK_CONFIG[roi_key]

    # 1. Crop to the summary box defined in config.json
    if roi['y2'] > frame.shape[0] or roi['x2'] > frame.shape[1]:
        print(f"FATAL ERROR: ROI '{roi_key}' is outside the image bounds.")
        return False

    box = frame[roi["y1"]:roi["y2"], roi["x1"]:roi["x2"]]

    if box.size == 0:
        print(f"FATAL ERROR: ROI '{roi_key}' is empty. Check coordinates.")
        return False

    # 2. Isolate the top right quadrant where the star spawns
    h, w = box.shape[:2]
    top_right_quadrant = box[0:int(h / 2), int(w / 2):w]

    # 3. Widen the HSV color bounds to handle JPEG/Capture card color compression
    hsv = cv2.cvtColor(top_right_quadrant, cv2.COLOR_BGR2HSV)
    lower_gold = np.array([15, 80, 150])
    upper_gold = np.array([45, 255, 255])

    mask = cv2.inRange(hsv, lower_gold, upper_gold)
    gold_pixel_count = cv2.countNonZero(mask)

    if debug_windows:
        debug_frame = frame.copy()
        # Draw a red rectangle showing the full ROI
        cv2.rectangle(debug_frame, (roi["x1"], roi["y1"]), (roi["x2"], roi["y2"]), (0, 0, 255), 2)

        cv2.imshow("1. Full ROI Box (Red Line)", debug_frame)
        cv2.imshow("2. Target Quadrant (Where it looks for star)", top_right_quadrant)
        cv2.imshow("3. Star Mask (White = Gold Found)", mask)
        print(f"Shiny Star Detection: Found {gold_pixel_count} gold pixels in ROI.")
        print(">>> Press any key while focused on a preview window to close them. <<<")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    return gold_pixel_count > 15


def identify_from_scene(scene_path: str):
    """Identifies if a shiny star exists in a given screenshot."""
    print(f"Identifying shiny star from scene: {scene_path}")
    try:
        scene_img = cv2.imread(scene_path)
        if scene_img is None:
            print("Error: Could not read scene file.")
            return
    except Exception as e:
        print(f"Error reading scene: {e}")
        return

    is_shiny = is_shiny_from_frame(scene_img, "summary_sprite_roi", debug_windows=True)
    print(f"\nFinal Result: The Pokémon is {'SHINY ✨' if is_shiny else 'NORMAL ❌'}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Pokémon Shiny Detector (Star Detection).")
    parser.add_argument("--test-scene", type=str, help="Path to a full game scene to identify.")
    args = parser.parse_args()

    if args.test_scene:
        identify_from_scene(args.test_scene)
    else:
        parser.print_help()