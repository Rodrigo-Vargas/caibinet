# Build Assets

This directory holds icons and signing assets required by electron-builder.
None of these binary files are committed to git (see `.gitignore`).

## Required icons

| File | Used for |
|---|---|
| `icon.icns` | macOS |
| `icon.ico` | Windows |
| `icons/` | Linux (PNG set) |

### Generating icons from a single source PNG (1024×1024)

```bash
# macOS icns (requires macOS)
mkdir icon.iconset
for size in 16 32 64 128 256 512; do
  sips -z $size $size source.png --out icon.iconset/icon_${size}x${size}.png
  sips -z $((size*2)) $((size*2)) source.png --out icon.iconset/icon_${size}x${size}@2x.png
done
iconutil -c icns icon.iconset

# Windows ico (requires ImageMagick)
convert source.png -define icon:auto-resize=256,128,64,48,32,16 icon.ico

# Linux PNGs (requires ImageMagick)
mkdir icons
for size in 16 24 32 48 64 96 128 256 512; do
  convert source.png -resize ${size}x${size} icons/${size}x${size}.png
done
```

## Required signing assets (not committed)

### Snap Store
- No local files needed — set `SNAPCRAFT_STORE_CREDENTIALS` repo secret.

### Microsoft Store
| Secret | How to obtain |
|---|---|
| `WIN_CSC_LINK` | Base64-encode your `.p12` EV certificate: `base64 cert.p12` |
| `WIN_CSC_KEY_PASSWORD` | Password for the certificate |
| `WIN_CERT_SUBJECT_NAME` | CN= subject from the cert (optional) |
| `APPX_PUBLISHER` | Publisher identity string from Microsoft Partner Center |
| `APPX_IDENTITY_NAME` | Package identity name from Partner Center |

### Mac App Store
| Secret | How to obtain |
|---|---|
| `APPLE_CERTS_P12` | Export "Mac App Distribution" + "Mac Installer Distribution" certs from Keychain as .p12, then `base64` encode |
| `APPLE_CERTS_PASSWORD` | Password set on the .p12 export |
| `APPLE_PROVISIONING_PROFILE` | Download `.provisionprofile` from developer.apple.com, then `base64` encode |
| `APPLE_ID` | Your Apple ID email |
| `APPLE_APP_SPECIFIC_PASSWORD` | Generate at appleid.apple.com |
| `APPLE_TEAM_ID` | Your 10-char team ID from developer.apple.com |
| `APP_STORE_CONNECT_API_KEY` | Key ID from App Store Connect → Users & Access → Keys |
| `APP_STORE_CONNECT_ISSUER_ID` | Issuer ID from same page |

Also set the **repository variable** `ENABLE_MAC_STORE=true` to activate the macOS job.
