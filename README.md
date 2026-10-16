# Calculator for Farm

A simple offline app for adding up farm weights (kg) per person. Type numbers under each name and the app totals each column and the whole page.

## Features

- Five name columns (add more with **+ Column**), with a total under each name and a grand total
- Big number keypad that stays at the bottom of the phone screen and can be dragged down to close
- **+** jumps to the next box, so you can type weights one after another
- **New page** button: saves the current page with its date and time, then starts a fresh one
- **History** (clock icon): every day of the last 30 days, plus each saved page. Press and hold for 3 seconds to delete.
- Full calculator with its own history tape, which can put its answer into the table
- Note box for each day
- Dates and times follow Cambodia time (UTC+7)
- Works offline, and saves everything on the phone

## Folders

| Folder | What it is |
|---|---|
| `app/` | The app itself (HTML, CSS and JavaScript in `index.html`), plus icons and offline files. Upload this folder to any web host, such as Netlify, to use it as a home-screen app. |
| `android/` | `build_apk.py`, which builds the Android APK from `app/` without Android Studio |
| `ios/` | Files for building the iPhone app in Xcode (see `docs/`) |
| `downloads/` | Ready-to-install Android APK |
| `docs/` | iPhone install guide (PDF) |

## Install

- **Android:** download `downloads/calculator-for-farm.apk` to the phone, open it and tap **Install**.
- **iPhone (with a Mac):** follow `docs/Calculator-for-Farm-iPhone-Guide.pdf`. Copy the files from `app/` into a folder called `web` and use it with the files in `ios/`.
- **iPhone or Android (no Mac):** upload the `app/` folder to [app.netlify.com/drop](https://app.netlify.com/drop), open the link on the phone, then choose **Add to Home Screen**.

## Building the Android APK

```bash
pip install cryptography
VERSION_CODE=31 VERSION_NAME=4.0 python3 android/build_apk.py app app/icon-192.png calculator-for-farm.apk ./signing
```

The signing key (`signing.key.pem` / `signing.cert.pem`) is **not** in this repository, on purpose. Keep it private. Phones can only update the app if every new APK is signed with the same key. The first build without a key creates a new one, and that build can't update an APK signed with the old key.
