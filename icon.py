from PIL import Image

img = Image.open("generated_icon.jpeg")
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("app_icon.ico", format="ICO", sizes=icon_sizes)

# .icns for the macOS .app bundle (build.spec's BUNDLE(icon=...)). Pillow
# downsamples the full-res source to fill every size Apple expects, up to
# the 1024px (@2x) slot.
img.convert("RGBA").save("app_icon.icns", format="ICNS")
