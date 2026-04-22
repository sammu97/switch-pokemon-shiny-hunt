import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import shutil
import re

# Local imports
from star_detector import is_shiny_from_frame

CHECKS_DIR = Path(__file__).resolve().parent / "shiny_checks"
ANOMALIES_DIR = Path(__file__).resolve().parent / "shiny_anomalies"


def main():
    if ANOMALIES_DIR.exists():
        print(f"Clearing existing '{ANOMALIES_DIR.name}' folder...")
        shutil.rmtree(ANOMALIES_DIR)
    ANOMALIES_DIR.mkdir(parents=True, exist_ok=True)

    # Grab all full frames
    attempt_files = sorted(
        [p for p in CHECKS_DIR.glob("attempt_*_full.png")],
        key=lambda p: int(re.search(r'(\d+)', p.name).group(1)) if re.search(r'(\d+)', p.name) else 0
    )

    if not attempt_files:
        print("No '_full.png' images found to check.")
        return

    print(f"Found {len(attempt_files)} frames to check. Scanning for stars...")

    anomalies = []

    for file_path in tqdm(attempt_files, desc="Scanning images for Star"):
        img = cv2.imread(str(file_path))
        if img is None:
            print(f"Warning: Could not read {file_path.name}")
            continue

        if is_shiny_from_frame(img, "summary_sprite_roi"):
            anomalies.append(file_path.name)
            shutil.copy(str(file_path), str(ANOMALIES_DIR / file_path.name))

    if not anomalies:
        print("\nNo shiny stars were found in the folder.")
    else:
        print(f"\nFound {len(anomalies)} images containing a Shiny Star!")
        for name in anomalies:
            print(f" - {name}")
        print(f"\nCopies of these shiny images have been saved to the '{ANOMALIES_DIR.name}' folder!")


if __name__ == "__main__":
    main()