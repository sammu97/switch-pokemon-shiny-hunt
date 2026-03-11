cmake_minimum_required(VERSION 3.13)

include(pico_sdk_import.cmake)

project(shinybot_pico_fw C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(shinybot_pico_fw
  src/main.c
  src/usb_descriptors.c
)

target_include_directories(shinybot_pico_fw PRIVATE src)

target_link_libraries(shinybot_pico_fw
  pico_stdlib
  pico_cyw43_arch_lwip_threadsafe_background
  tinyusb_device
  tinyusb_board
)

# IMPORTANT: don't fight TinyUSB by also using USB stdio
pico_enable_stdio_usb(shinybot_pico_fw 0)
pico_enable_stdio_uart(shinybot_pico_fw 0)

# --- Inject Wi-Fi creds from CMake vars into C macros ---
if (DEFINED WIFI_SSID)
  target_compile_definitions(shinybot_pico_fw PRIVATE WIFI_SSID=${WIFI_SSID})
endif()

if (DEFINED WIFI_PASSWORD)
  target_compile_definitions(shinybot_pico_fw PRIVATE WIFI_PASSWORD=${WIFI_PASSWORD})
endif()

pico_add_extra_outputs(shinybot_pico_fw)