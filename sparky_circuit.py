from skidl import *

# Initialize project settings
set_default_tool(KICAD10)  # matches the installed KiCad 10.0

# Create Main Power Nets
vcc_5v = Net('5V')
vcc_3v3 = Net('3V3')
gnd = Net('GND')

# -----------------------------------------------------------------------------
# 1. ESP32 Dev Board
# -----------------------------------------------------------------------------
# Modeled as a generic connector representing the DEV BOARD's own broken-out
# header pins - NOT the bare RF_Module:ESP32-WROOM-32 KiCad symbol. That
# symbol represents the raw module (3.3V-only, no onboard regulator, no 5V
# pin - confirmed against the real KiCad library: pin 1 is GND, pin 2 is
# 3V3, nothing else in the power section). Our actual board is a full dev
# board with USB + an onboard regulator, which is why it exposes 5V/VIN at
# all. Treating it as a generic connector (like every other module below)
# sidesteps the mismatch entirely.
esp32 = Part(
    'Connector_Generic',
    'Conn_01x16',
    footprint='Connector_PinHeader_2.54mm:PinHeader_1x16_P2.54mm_Vertical',
    ref='U1'
)

net_5v_pin = esp32[1]
net_3v3_pin = esp32[2]
net_gnd_pin = esp32[3]
net_mic_sck = Net('MIC_SCK')
net_mic_ws = Net('MIC_WS')
net_mic_sd = Net('MIC_SD')
net_amp_bclk = Net('AMP_BCLK')
net_amp_lrc = Net('AMP_LRC')
net_amp_din = Net('AMP_DIN')
net_matrix_clk = Net('MATRIX_CLK')
net_matrix_din = Net('MATRIX_DIN')
net_matrix_cs = Net('MATRIX_CS')
net_led_cathode = Net('LED_CATHODE')
net_btn_ptt = Net('BTN_PTT')
net_touch_pad = Net('TOUCH_PAD')
# New: amp SD is now GPIO-controlled (mute), not hardwired to 3.3V - lets
# firmware mute the amp while the mic is recording, preventing the
# speaker's own output from bleeding into the mic. Idea borrowed from
# https://www.phippselectronics.com/i2s-audio-on-the-esp32-s3/ (their
# exact GPIO numbers are for an ESP32-S3 and don't apply to our
# ESP32-WROOM-32 board, but the mute technique itself is chip-agnostic).
net_amp_sd_mute = Net('AMP_SD_MUTE')

esp32[1] += vcc_5v          # 5V / VIN
esp32[2] += vcc_3v3         # 3V3
esp32[3] += gnd             # GND
esp32[4] += net_mic_sck     # GPIO32
esp32[5] += net_mic_ws      # GPIO25
esp32[6] += net_mic_sd      # GPIO33
esp32[7] += net_amp_bclk    # GPIO27
esp32[8] += net_amp_lrc     # GPIO26
esp32[9] += net_amp_din     # GPIO22
esp32[10] += net_matrix_clk # GPIO18
esp32[11] += net_matrix_din # GPIO23
esp32[12] += net_matrix_cs  # GPIO5
esp32[13] += net_led_cathode # GPIO4
esp32[14] += net_btn_ptt    # GPIO14
esp32[15] += net_touch_pad  # GPIO13
esp32[16] += net_amp_sd_mute # GPIO21 - amp mute control (was hardwired to 3.3V)

# -----------------------------------------------------------------------------
# 2. INMP441 I2S Microphone Module
# -----------------------------------------------------------------------------
# 6-pin module header: VDD, GND, L/R, SCK, WS, SD
mic = Part(
    'Connector_Generic',
    'Conn_01x06',
    footprint='Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical',
    ref='J_MIC'
)

mic[1] += vcc_3v3       # VDD (3.3V ONLY - 5V destroys chip)
mic[2] += gnd           # GND
mic[3] += gnd           # L/R (GND = Left/Mono channel)
mic[4] += net_mic_sck   # Bit Clock
mic[5] += net_mic_ws    # Word Select
mic[6] += net_mic_sd    # Serial Data Out

# -----------------------------------------------------------------------------
# 3. MAX98357A I2S Audio Amplifier Module (+ speaker output, now connected)
# -----------------------------------------------------------------------------
# 9-pin module header: VIN, GND, SD, BCLK, LRC, DIN, SPK+, SPK-, GAIN
# NOTE: GAIN is only usable if your specific breakout board actually breaks
# out that pin on its header - not all cheap MAX98357A modules do. Verify
# on the physical board before wiring it; if there's no GAIN pad, skip that
# connection and the amp just runs at its default ~9dB gain.
amp = Part(
    'Connector_Generic',
    'Conn_01x09',
    footprint='Connector_PinHeader_2.54mm:PinHeader_1x09_P2.54mm_Vertical',
    ref='J_AMP'
)

amp[1] += vcc_5v            # VIN
amp[2] += gnd               # GND
amp[3] += net_amp_sd_mute   # SD - now GPIO-controlled mute, not hardwired 3.3V
amp[4] += net_amp_bclk      # Bit Clock
amp[5] += net_amp_lrc       # Left/Right Clock
amp[6] += net_amp_din       # Data Input
amp[9] += gnd               # GAIN tied to GND -> 12dB (louder than the ~9dB default)

# Speaker Connector (Off-breadboard screw terminal / JST)
spk_term = Part(
    'Connector_Generic',
    'Conn_01x02',
    footprint='TerminalBlock:TerminalBlock_MaiXu_MX126-5.0-02P_1x02_P5.00mm',
    ref='J_SPK'
)
amp[7] += spk_term[1]   # SPK+
amp[8] += spk_term[2]   # SPK-

# -----------------------------------------------------------------------------
# 4. MAX7219 Dot Matrix Display (32x8 Module Header)
# -----------------------------------------------------------------------------
# 5-pin module header: VCC, GND, DIN, CS, CLK
matrix = Part(
    'Connector_Generic',
    'Conn_01x05',
    footprint='Connector_PinHeader_2.54mm:PinHeader_1x05_P2.54mm_Vertical',
    ref='J_MATRIX'
)

matrix[1] += vcc_5v         # VCC (5V)
matrix[2] += gnd            # GND
matrix[3] += net_matrix_din # SPI MOSI
matrix[4] += net_matrix_cs  # SPI Chip Select
matrix[5] += net_matrix_clk # SPI Clock

# -----------------------------------------------------------------------------
# 5. Accent White LED (Low-side switched via GPIO 4)
# -----------------------------------------------------------------------------
led = Part(
    'Device',
    'LED',
    footprint='LED_THT:LED_D5.0mm',
    ref='D1'
)

r_led = Part(
    'Device',
    'R',
    value='220',
    footprint='Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal',
    ref='R1'
)

# 5V Rail -> Resistor -> LED Anode -> LED Cathode -> GPIO 4
vcc_5v += r_led[1]
r_led[2] += led['A']       # Anode (+)
led['K'] += net_led_cathode # Cathode (-) low-side switched

# -----------------------------------------------------------------------------
# 6. Push-to-Talk Button & Capacitive Touch Wire
# -----------------------------------------------------------------------------
btn = Part(
    'Switch',
    'SW_Push',
    footprint='Button_Switch_THT:SW_PUSH_6mm',
    ref='SW1'
)

# Internal pull-up configured in firmware on GPIO 14
btn[1] += net_btn_ptt
btn[2] += gnd

# Capacitive Touch Pad (Exposed Pad / Header Pin)
touch_pad = Part(
    'Connector_Generic',
    'Conn_01x01',
    footprint='Connector_PinHeader_2.54mm:PinHeader_1x01_P2.54mm_Vertical',
    ref='J_TOUCH'
)
touch_pad[1] += net_touch_pad

# -----------------------------------------------------------------------------
# Generate KiCad Netlist & ERC
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    ERC()
    generate_netlist(filename='sparky_build.net')
    print("Successfully generated 'sparky_build.net'!")
