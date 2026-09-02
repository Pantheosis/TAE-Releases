from PIL import Image

img = Image.open("generated_icon.jpeg")
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save("app_icon.ico", format="ICO", sizes=icon_sizes)

# .icns for the macOS .app bundle (build.spec's BUNDLE(icon=...)). Pillow
# upsamples the 256px source to fill the 512/1024 (@2x) slots Apple expects,
# so those largest sizes will look soft next to a hand-authored hi-res icon
# -- acceptable here since 256px is the largest source we have.
img.convert("RGBA").save("app_icon.icns", format="ICNS")
