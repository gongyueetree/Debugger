cmake_minimum_required(VERSION 3.13)
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)
project(la_rp2040_adc12 C CXX ASM)
pico_sdk_init()
add_executable(la_rp2040_adc12 main.c)
target_link_libraries(la_rp2040_adc12 pico_stdlib hardware_adc hardware_dma hardware_clocks)
target_compile_definitions(la_rp2040_adc12 PRIVATE
    PICO_STDIO_USB_DEFAULT_CRLF=0
    PICO_STDIO_USB_ENABLE_RESET_VIA_BAUD_RATE=0
    USBD_PRODUCT="LA-RP2040 ADC12 v1")
pico_enable_stdio_usb(la_rp2040_adc12 1)
pico_enable_stdio_uart(la_rp2040_adc12 0)
pico_add_extra_outputs(la_rp2040_adc12)

set_target_properties(la_rp2040_adc12 PROPERTIES LINKER_LANGUAGE C)
