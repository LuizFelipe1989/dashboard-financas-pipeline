import os

BASE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(f"{BASE}/dashboard_template.html") as f:
        html = f.read()

    with open(f"{BASE}/dashboard_data.json") as f:
        data_json = f.read()

    with open(f"{BASE}/dashboard.js") as f:
        js = f.read()

    fonts = {}
    for key, fname in [
        ("__FONT_SERIF_600__", "source-serif-600"),
        ("__FONT_SANS_400__", "plex-sans-400"),
        ("__FONT_SANS_500__", "plex-sans-500"),
        ("__FONT_SANS_600__", "plex-sans-600"),
        ("__FONT_MONO_400__", "plex-mono-400"),
        ("__FONT_MONO_500__", "plex-mono-500"),
    ]:
        with open(f"{BASE}/fonts/{fname}.b64") as f:
            fonts[key] = f.read().strip()

    for k, v in fonts.items():
        html = html.replace(k, v)

    html = html.replace("__DASHBOARD_DATA_JSON__", data_json)
    html = html.replace("__DASHBOARD_JS__", js)

    out_path = f"{BASE}/dashboard.html"
    with open(out_path, "w") as f:
        f.write(html)

    print(f"Written: {out_path} ({len(html)} chars)")


if __name__ == "__main__":
    main()
