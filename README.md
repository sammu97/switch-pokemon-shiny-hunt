# Shiny Bot

Automated shiny hunting for **Pokémon FireRed / LeafGreen** on **Nintendo Switch** using a **Mac + Raspberry Pi Pico W**.

This project provides a framework for automating shiny hunting for the starter Pokémon in FireRed or LeafGreen. It is designed to be run on a Mac and interfaces with a Raspberry Pi Pico W to send button presses to a Nintendo Switch.

The bot:

1.  Resets the game via a command to the Pico.
2.  Executes a precise sequence of button presses to select the starter.
3.  Uses OpenCV to watch a specific region of the screen for the "shiny star" animation.
4.  When a shiny is detected, it stops automatically and sends a push notification to your phone.
5.  You can then **manually save the shiny Pokémon**.

## Legal

This project is for **educational and personal automation purposes only**. It is not affiliated with Nintendo, Game Freak, or The Pokémon Company. See the `LICENSE`, `NOTICE`, and `DISCLAIMER.md` files for more information.

---

## Hardware Required

-   Nintendo Switch + Dock
-   Raspberry Pi **Pico W**
-   HDMI Capture Card (e.g., Elgato Cam Link)
-   Mac
-   USB cable for Pico

---

## Setup

### 1. Mac Setup

Install the required dependencies using Homebrew and pip:

```sh
brew install cmake
pip3 install opencv-python numpy requests
```

You will also need:

-   Python 3
-   OBS Studio (for monitoring and getting the capture device index)
-   The Pico SDK

Clone the repository:

```sh
git clone <your-repo-url>
cd shiny-bot
```

### 2. Pico Firmware

The firmware for the Raspberry Pi Pico W is located in the `pico-fw` directory. You'll need to build and flash it once.

1.  **Set Pico SDK Path**:
    ```sh
    export PICO_SDK_PATH=~/pico-sdk
    ```

2.  **Configure and Build**:
    Navigate to the firmware directory and create a build folder.
    ```sh
    cd pico-fw
    mkdir build
    cd build
    ```
    Run cmake to configure the firmware with your WiFi credentials.
    ```sh
    cmake .. \
    -DPICO_BOARD=pico_w \
    -DWIFI_SSID='"YOUR_WIFI_NAME"' \
    -DWIFI_PASSWORD='"YOUR_WIFI_PASSWORD"'
    ```
    Build the firmware:
    ```sh
    cmake --build . -j
    ```

3.  **Flash Firmware**:
    Hold the **BOOTSEL** button on your Pico while plugging it into your Mac. It will appear as a disk drive named `RPI-RP2`. Copy the firmware file to it.
    ```sh
    cp shinybot_pico_fw.uf2 /Volumes/RPI-RP2/
    ```
    The Pico will reboot and connect to your WiFi network.

### 3. OBS Setup

1.  Connect your Switch Dock's HDMI output to your capture card.
2.  Connect the capture card to your Mac.
3.  Open OBS Studio and add a **Video Capture Device**, selecting your capture card.
4.  Confirm that you can see your Switch's screen in OBS. This is also how you can determine the `capture_index` for the config file (usually 0 or 1).

### 4. Configuration

All bot settings are managed in the `config.json` file.

1.  **Find Pico IP**: Find your Pico's IP address from your router's client list.
2.  **Edit `config.json`**:
    -   Set `pico_server.url` to your Pico's IP address (e.g., `http://192.168.1.95:8080`).
    -   Adjust `timing` variables if your game's pacing is different.
    -   Configure the `shiny_check.roi` (Region of Interest) to match the location of the shiny star on your screen. You can use the `--show` flag with `check_star.py` to help with this.
    -   Set `notifications.ntfy_topic` to a unique string for your push notifications.

### 5. Notification Setup (Optional)

The bot can send a push notification when a shiny is found using the free `ntfy.sh` service.

1.  Install the **ntfy** app on your iOS or Android device.
2.  Subscribe to the topic you defined in `config.json` (e.g., `jordan-shiny-bot-fr-lg`).

---

## Usage

### Testing Components

Before running the full loop, it's a good idea to test each part.

-   **Test Pico Connection**:
    ```sh
    # Check status
    curl http://<PICO_IP>:8080/status
    # Test a button press
    curl -X POST http://<PICO_IP>:8080/cmd -d "press A 120"
    ```

-   **Test Shiny Detection**:
    You can test the detection logic with a live feed. The `--show` flag is very useful for debugging the ROI.
    ```sh
    python3 check_star.py --watch-seconds 10 --show
    ```

-   **Test the Starter Sequence**:
    You can run the full starter sequence once to ensure the timing and button presses are correct.
    ```sh
    python3 switch_control.py
    ```

### Running the Bot

Once everything is configured and tested, you can start the main hunting loop.

```sh
python3 hunt_loop.py
```

To prevent your Mac from sleeping during a long hunt, it's recommended to use `caffeinate`:

```sh
caffeinate -i python3 hunt_loop.py
```

The bot will now run continuously until it finds a shiny or you stop it by pressing the **ESC** key.

---

## Project Structure

-   `hunt_loop.py`: The main entry point and orchestration script for the bot.
-   `switch_control.py`: Handles all communication with the Pico to press buttons and reset the game. Contains the starter sequence logic.
-   `check_star.py`: Uses OpenCV to analyze the video feed and detect the shiny star.
-   `config.json`: Central configuration file for all bot settings.
-   `pico-fw/`: Contains the source code and build system for the Raspberry Pi Pico W firmware.
-   `*.txt` / `*.json`: Runtime files for state management and OBS overlays (`hunt_state.json`, `encounter_count.txt`, etc.).
