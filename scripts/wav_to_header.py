# wav_to_header.py
import sys

def wav_to_header(wav_path, header_path, var_name="TEST_AUDIO"):
    with open(wav_path, "rb") as f:
        data = f.read()

    with open(header_path, "w") as f:
        f.write(f"// Auto-generated from {wav_path}\n")
        f.write(f"const unsigned int {var_name}_LEN = {len(data)};\n")
        f.write(f"const unsigned char {var_name}[] = {{\n")
        for i in range(0, len(data), 16):
            chunk = data[i:i + 16]
            line = ", ".join(f"0x{b:02x}" for b in chunk)
            f.write(f"  {line},\n")
        f.write("};\n")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python wav_to_header.py input.wav output.h")
        sys.exit(1)
    wav_to_header(sys.argv[1], sys.argv[2])