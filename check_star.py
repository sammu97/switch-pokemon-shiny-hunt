import cv2
import numpy as np
import argparse
import time
from pathlib import Path
import sys

CAPTURE_INDEX = 0

# -----------------------------
# ROI for LIVE capture card / OBS virtual cam
# -----------------------------
LIVE_STAR_X1 = 815
LIVE_STAR_Y1 = 250
LIVE_STAR_X2 = 890
LIVE_STAR_Y2 = 325

# -----------------------------
# ROI for TEST images in Downloads
# -----------------------------
TEST_STAR_X1 = 1450
TEST_STAR_Y1 = 900
TEST_STAR_X2 = 1600
TEST_STAR_Y2 = 1020

YELLOW_THRESHOLD = 120
CONSECUTIVE_FRAMES_REQUIRED = 3


def has_shiny_star(frame: np.ndarray, roi) -> tuple[bool, int]:
    x1, y1, x2, y2 = roi
    region = frame[y1:y2, x1:x2]

    if region.size == 0:
        return False, 0

    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)

    lower_yellow = np.array([18, 80, 120])
    upper_yellow = np.array([40, 255, 255])

    mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    yellow_pixels = cv2.countNonZero(mask)

    return yellow_pixels > YELLOW_THRESHOLD, yellow_pixels


def draw_debug(frame, roi, shiny, yellow_pixels):
    x1, y1, x2, y2 = roi
    color = (0, 255, 0) if shiny else (0, 0, 255)
    label = f"{'SHINY STAR DETECTED' if shiny else 'No star'} | yellow={yellow_pixels}"

    preview = frame.copy()
    cv2.rectangle(preview, (x1, y1), (x2, y2), color, 2)
    cv2.putText(preview, label, (40, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)

    roi_img = preview[y1:y2, x1:x2]
    return preview, roi_img


def test_from_file(path, show_windows: bool):
    frame = cv2.imread(str(path))

    if frame is None:
        print("Could not load image:", path)
        return 2

    roi = (TEST_STAR_X1, TEST_STAR_Y1, TEST_STAR_X2, TEST_STAR_Y2)

    shiny, yellow_pixels = has_shiny_star(frame, roi)
    print(f"yellow_pixels={yellow_pixels}")

    print("STAR_DETECTED" if shiny else "NO_STAR")

    if show_windows:
        preview, roi_img = draw_debug(frame, roi, shiny, yellow_pixels)
        cv2.imshow("Image Test", preview)
        cv2.imshow("Star ROI", roi_img)
        print("Press ESC or q to close")

        while True:
            key = cv2.waitKey(20) & 0xFF
            if key == 27 or key == ord("q"):
                break

        cv2.destroyAllWindows()

    return 0 if shiny else 1


def watch_live(seconds: float, show_windows: bool):
    cap = cv2.VideoCapture(CAPTURE_INDEX, cv2.CAP_AVFOUNDATION)

    if not cap.isOpened():
        print("Could not open capture device")
        return 2

    roi = (LIVE_STAR_X1, LIVE_STAR_Y1, LIVE_STAR_X2, LIVE_STAR_Y2)

    start_time = time.time()
    consecutive_hits = 0

    while time.time() - start_time < seconds:
        ret, frame = cap.read()

        if not ret or frame is None:
            print("Failed to read frame")
            cap.release()
            cv2.destroyAllWindows()
            return 2

        shiny, yellow_pixels = has_shiny_star(frame, roi)

        if shiny:
            consecutive_hits += 1
        else:
            consecutive_hits = 0

        print(f"yellow_pixels={yellow_pixels} consecutive_hits={consecutive_hits}")

        if show_windows:
            preview, roi_img = draw_debug(frame, roi, shiny, yellow_pixels)
            cv2.imshow("Switch", preview)
            cv2.imshow("Star ROI", roi_img)

            key = cv2.waitKey(1) & 0xFF
            if key == 27 or key == ord("q"):
                cap.release()
                cv2.destroyAllWindows()
                return 130

        if consecutive_hits >= CONSECUTIVE_FRAMES_REQUIRED:
            cap.release()
            cv2.destroyAllWindows()
            print("STAR_DETECTED")
            return 0

    cap.release()
    cv2.destroyAllWindows()
    print("NO_STAR")
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", help="Test image from Downloads folder")
    parser.add_argument("--watch-seconds", type=float, help="Watch live feed for N seconds")
    parser.add_argument("--show", action="store_true", help="Show debug windows")
    args = parser.parse_args()

    if args.image:
        downloads = Path.home() / "Downloads"
        image_path = downloads / args.image
        print("Testing image:", image_path)
        sys.exit(test_from_file(image_path, args.show))

    if args.watch_seconds:
        sys.exit(watch_live(args.watch_seconds, args.show))

    sys.exit(watch_live(999999, True))


if __name__ == "__main__":
    main()