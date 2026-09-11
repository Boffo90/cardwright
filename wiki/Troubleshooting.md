## My antivirus flags it as a trojan

Windows Defender may report `Trojan:Win32/Wacatac.C!ml`. The `!ml` suffix means
a machine-learning guess about the file's shape, not a match against a known
virus, and Wacatac is Defender's catch-all for packed executables.

Cardwright is a packed executable that legitimately does three things malware
also does:

- it is one self-extracting file (PyInstaller)
- it downloads and runs another executable on first launch, the Real-ESRGAN
  AI engine
- it replaces its own `.exe` when you accept an update

All three are visible in the source, which is public.

**Check the file yourself rather than taking anyone's word for it.** Every
release lists the SHA-256 of both files. Run this where you downloaded it:

```
certutil -hashfile Cardwright.exe SHA256
```

If it matches the release page, you have exactly the file that was published.
Only the portable `.exe` tends to be flagged; the installer usually is not.

The real fix is a code-signing certificate, which is not in place yet. Until it
is, a report to Microsoft clears one build at a time, so each new version can be
flagged again.

## Windows says "unknown publisher"

That is SmartScreen reacting to any unsigned program, whatever it does, and it
has the same root cause as the above. The releases on GitHub are the only
official builds.

## The printer says "insufficient memory"

See [Printing Guide](Printing-Guide#insufficient-memory-or-an-error-page). In
short: let the PC rasterise with Adobe Reader's **Print as Image**, and set that
dialog's resolution to 600 or 1200.

## My disk is filling up

An upscaled card is about 29 MB, so a big project adds up fast.

- **Output folder… > Change** moves where new cards are saved, for instance to
  a second drive. If that drive is not connected when the app starts, cards go
  to the app's own folder instead and it tells you once. Reconnect and restart,
  and it goes back to your choice. Cards already made stay where they were.
- Working files are cleaned up automatically. Older versions never deleted
  them, and on one install they came to 6.6 GB; from v2.17.14 each card deletes
  its own as it finishes, and whatever an older version left behind is swept
  when the app starts.

## A card came out cropped, or kept a bleed edge

Bleed detection works by aspect ratio, which is a good guess but still a guess.
Set **MPC bleed** to *Assume none* for an image wrongly flagged, or *Assume
bleed* for one carrying bleed the proportions hide. It only ever runs on MPC
picks and your own files. Cards from Scryfall, Gatherer, Pokémon, Yu-Gi-Oh and
Riftbound are never touched.

## Some cards came back in English

Not every card was printed in every language. They are added in English and
listed after the import. See
[Finding Cards](Finding-Cards#languages).

## I can barely see the cut guides

They are probably too thin or the wrong colour for the card. See
[Cutting](Cutting#thickness).

## The two sides do not line up

See [Double-Sided Printing and Card Backs](Double-Sided-Printing-and-Card-Backs#getting-the-two-sides-to-line-up).

## Something else went wrong

The **Log** button in the header opens a file with the full detail of any
failure, including what was being fetched when it broke. It is capped at half a
megabyte, so it is safe to paste.

Report it on [Issues](https://github.com/Boffo90/cardwright/issues) and attach
the log: it is the difference between a guess and a fix. For something that is
not clearly a bug, [Discussions](https://github.com/Boffo90/cardwright/discussions)
is fine.

## Is printing proxies allowed?

Cardwright is an unofficial fan project. It ships no publisher artwork: card
images are fetched from public sources when you ask for them. Proxies are for
personal playtesting. Selling them, or passing them off as real cards, is not
what this tool is for, and what you do with the output is your responsibility.
