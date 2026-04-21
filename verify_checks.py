import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import shutil
import re

CHECKS_DIR = Path(__file__).resolve().parent / "shiny_checks"
ANOMALIES_DIR = Path(__file__).resolve().parent / "shiny_anomalies"
BASELINE_IMG_NAME = "attempt_0_baseline.png"
BASELINE_IMG_PATH = CHECKS_DIR / BASELINE_IMG_NAME

def main():
    if not BASELINE_IMG_PATH.exists():
        print(f"Error: Baseline image {BASELINE_IMG_PATH} not found.")
        return

    baseline_img = cv2.imread(str(BASELINE_IMG_PATH))
    if baseline_img is None:
        print("Error: Could not read baseline image.")
        return

    # Clear or create the anomalies directory
    if ANOMALIES_DIR.exists():
        print(f"Clearing existing '{ANOMALIES_DIR.name}' folder...")
        shutil.rmtree(ANOMALIES_DIR)
    ANOMALIES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using baseline image: {BASELINE_IMG_NAME}")
    
    # Get only the cleaned sprites for comparison
    attempt_files = sorted(
        [p for p in CHECKS_DIR.glob("attempt_*_cleaned.png")],
        key=lambda p: int(re.search(r'(\d+)', p.name).group(1))
    )
    
    if not attempt_files:
        print("No '_cleaned.png' images found to check.")
        return
        
    print(f"Found {len(attempt_files)} cleaned sprites to check. Scanning...")
    
    anomalies = []
    
    for file_path in tqdm(attempt_files, desc="Comparing images"):
        img = cv2.imread(str(file_path))
        if img is None:
            print(f"Warning: Could not read {file_path.name}")
            continue
            
        if img.shape != baseline_img.shape:
            anomalies.append((file_path.name, "Different image dimensions"))
            shutil.copy(str(file_path), str(ANOMALIES_DIR / file_path.name))
            continue
            
        diff = cv2.absdiff(img, baseline_img)
        mean_diff = np.mean(diff)
        
        if mean_diff > 10.0:
            anomalies.append((file_path.name, f"Significant difference detected (Score: {mean_diff:.2f})"))
            shutil.copy(str(file_path), str(ANOMALIES_DIR / file_path.name))

    if not anomalies:
        print("\nAll images matched the baseline. No shinies were found in the folder.")
    else:
        print(f"\nFound {len(anomalies)} anomalous images that differ significantly from the baseline:")
        for name, reason in anomalies:
            print(f" - {name}: {reason}")
        print(f"\nCopies of these anomalous images have been saved to the '{ANOMALIES_DIR.name}' folder for easy manual review!")

if __name__ == "__main__":
    main()
