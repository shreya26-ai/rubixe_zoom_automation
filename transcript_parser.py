def parse_vtt(file_path):
    text_lines = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or "-->" in line or line.startswith("WEBVTT"):
                continue
            text_lines.append(line)

    return " ".join(text_lines)
