import cv2
import numpy as np
from pathlib import Path
from tqdm import tqdm
import shutil

CHECKS_DIR = Path(__file__).resolve().parent / "shiny_checks"
ANOMALIES_DIR = Path(__file__).resolve().parent / "shiny_anomalies"

def main():
    attempt_files = sorted(list(CHECKS_DIR.glob("attempt_*.png")), key=lambda p: int(p.stem.split('_')[1]))
    if not attempt_files:
        print("No attempt images found in the 'shiny_checks' folder.")
        return

    # Use the first image found as the baseline
    baseline_path = attempt_files[0]
    baseline_img = cv2.imread(str(baseline_path))
    if baseline_img is None:
        print(f"Error: Could not read baseline image: {baseline_path.name}")
        return

    # Clear or create the anomalies directory
    if ANOMALIES_DIR.exists():
        print(f"Clearing existing '{ANOMALIES_DIR.name}' folder...")
        shutil.rmtree(ANOMALIES_DIR)
    ANOMALIES_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using baseline image: {baseline_path.name}")
    print(f"Found {len(attempt_files)} images to check. Scanning...")
    
    anomalies = []
    
    for file_path in tqdm(attempt_files[1:], desc="Comparing images"):
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
