## Install

Download the latest release from
[Releases](https://github.com/Boffo90/cardwright/releases/latest). There are
two files, and either works:

- **`Cardwright_Setup-x.y.z.exe`** installs it per user. No administrator
  rights needed.
- **`Cardwright.exe`** is portable. Put it in its own folder: it keeps its
  settings, models and output beside itself.

Windows 10 or 11. If your antivirus flags the download, see
[Troubleshooting](Troubleshooting#my-antivirus-flags-it-as-a-trojan) before
deciding anything; there is a way to check the file yourself.

## First run

The first launch downloads the Real-ESRGAN AI engine and its models, about
110 MB, from their official sources, and checks your GPU. That happens once.
After it, upscaling runs entirely on your machine and needs no connection.
Card images are only ever fetched when you ask for a specific card.

No compatible GPU? It still works, falling back to high-quality resizing. You
get a correctly sized 1200 DPI file, just without the detail the AI adds.

## Your first sheet

1. **Get some cards in.** Type a card name in the search box and a gallery
   opens with every printing of it. Pick one. Or paste a Scryfall or Gatherer
   link, or use **Import list…** for a whole decklist. More in
   [Finding Cards](Finding-Cards).
2. **Press Upscale all.** Each card is upscaled to 2976×4160 px, which is
   exactly 63×88 mm at 1200 DPI.
3. **Press Export PDF…** and set up the sheet: page size, card grid, cut
   guides. The preview on the right is what prints, and you can drag cards
   around in it.
4. **Print at 100% scale**, with the printer's own colour correction off.
   "Fit to page" is the most common reason cards come out the wrong size.

## Dial in your printer once

Inkjets print darker and less saturated than a screen shows. Before your first
real sheet, open **Export > Tests > Calibration…**, print it, and compare the
nine numbered variants against a real card. Pick the closest number in
**Color profile**. The [Printing Guide](Printing-Guide) covers the rest.

## Where things are

- Finished cards go to the **output** folder. **Output folder…** in the footer
  opens it, or moves it to another drive. A card is about 29 MB.
- **Project…** saves the whole queue, quantities and chosen printings included,
  so a hand-built list survives closing the app.
- **Log**, in the header, opens a file with the full detail of any failure.
  Attach it to a bug report.
- **Help** has the in-app FAQ.

The app updates itself when a new version is out.
