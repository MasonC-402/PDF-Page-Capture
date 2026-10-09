# pdf_page_capture

Click through a PDF viewer page by page, screenshot each page, and optionally combine the screenshots into a new PDF.

It drives your real mouse and keyboard and captures the screen, so it works with almost any viewer: browser-embedded viewers, web document sites, Adobe Reader, Edge, and so on.

## Requirements

- Python 3.9+
- `pyautogui` and `pillow`

```
pip install pyautogui pillow
```

**macOS:** give your terminal app **Screen Recording** and **Accessibility** permissions (System Settings → Privacy & Security), or screenshots come out blank and clicks don't register.

**Windows:** if you use display scaling, run the script with the viewer on the same monitor so coordinates line up.

## Quick start

1. Open the document in your viewer and go to **page 1**.
2. Zoom so one full page fits in the window. Full screen (F11) helps keep the layout steady.
3. Run:

   ```
   python pdf_page_capture.py --make-pdf
   ```

4. Follow the prompts. For each one, press Enter in the terminal, then hover the mouse over the requested spot until the countdown finishes:
   - **Step 1:** the viewer's **Next page** button
   - **Step 2:** the **top-left** corner of the page area to capture
   - **Step 3:** the **bottom-right** corner of the page area to capture
5. Press Enter to start. Hands off the mouse and keyboard while it runs.

Screenshots are saved to `pdf_pages/page_0001.png`, `page_0002.png`, and so on. With `--make-pdf`, they're also combined into `pdf_pages/combined.pdf`.

## How it works

Each pass through the loop:

1. *(Optional, with `--reveal`)* Clicks the "Click here to display content" spot, then waits `--reveal-delay` seconds.
2. *(Optional, with `--park-mouse`)* Moves the cursor out of the way.
3. Takes a screenshot of the capture region.
4. Compares it with the previous screenshot. If it's new, it's saved. If it's identical, it counts as "unchanged."
5. Advances to the next page, by clicking Next or pressing `--key`, then waits `--delay` seconds.

It stops when the page hasn't changed for `--same-limit` passes in a row (the end of the document), when it hits `--max-pages`, or when you abort.

Page 1 is captured before the first advance, so always start on page 1.

## Viewers with a "Click here to display content" prompt

Some web viewers hide the page behind a click prompt shortly after it loads. Use `--reveal` and the script clicks that spot before every screenshot:

```
python pdf_page_capture.py --reveal --delay 2.5 --make-pdf
```

You'll get an extra setup step (**Step 1b**) to hover over the prompt. Make sure the prompt is visible in the browser before that step so you can see where to hover. If the prompt shows up where the Next button is, hover over that same spot again.

If the prompt reappears as soon as the mouse moves, add `--park-mouse`.

## Options

| Option | Default | Description |
|---|---|---|
| `--out DIR` | `pdf_pages` | Output folder |
| `--key KEY` | *(click mode)* | Advance with a key instead of clicking, e.g. `right`, `pagedown`, `space` |
| `--next-x N` `--next-y N` | *(prompt)* | Next-button coordinates; skips Step 1 |
| `--region L,T,W,H` | *(prompt)* | Capture region as left,top,width,height; skips Steps 2–3 |
| `--full-screen` | off | Capture the whole screen instead of a region |
| `--reveal` | off | Click a "display content" spot before each screenshot (prompts for it) |
| `--reveal-x N` `--reveal-y N` | *(prompt)* | Reveal-spot coordinates; skips Step 1b and turns on reveal |
| `--reveal-delay SEC` | `1.0` | Wait after the reveal click before the screenshot |
| `--delay SEC` | `1.5` | Wait after advancing for the next page to render |
| `--max-pages N` | `1000` | Safety cap on the number of pages |
| `--same-limit N` | `2` | Stop after this many unchanged pages in a row |
| `--tolerance N` | `10` | Pixel difference (0–255) ignored when comparing pages |
| `--hover-wait SEC` | `5` | Countdown length when recording a mouse position |
| `--park-mouse` | off | Move the cursor off-screen before each screenshot |
| `--make-pdf` | off | Combine all screenshots into `combined.pdf` at the end |

## Reusing your setup

During setup the script prints the coordinates it recorded, for example:

```
(Reuse next time with --region 412,88,1096,1412)
Next button: (reuse with --next-x 1820 --next-y 640)
Reveal spot: (reuse with --reveal-x 960 --reveal-y 700)
```

Pass those back in to skip the hover steps:

```
python pdf_page_capture.py --region 412,88,1096,1412 --next-x 1820 --next-y 640 \
    --reveal-x 960 --reveal-y 700 --delay 2.5 --make-pdf
```

Coordinates only stay valid if the browser window, zoom level, and screen layout are the same as last time.

## Stopping early

- Slam the mouse into any **screen corner** (pyautogui's failsafe), or
- Press **Ctrl+C** in the terminal.

Pages captured so far are kept. If you used `--make-pdf`, they're still combined.

## Combining existing screenshots later

If you ran without `--make-pdf`, you don't need to recapture:

```
python -c "from PIL import Image; from pathlib import Path; p=sorted(Path('pdf_pages').glob('page_*.png')); i=[Image.open(x).convert('RGB') for x in p]; i[0].save('pdf_pages/combined.pdf', save_all=True, append_images=i[1:])"
```

## Making the PDF searchable

The combined PDF is image-only. To add a selectable, searchable text layer, run it through OCR:

```
pip install ocrmypdf        # also needs Tesseract installed
ocrmypdf pdf_pages/combined.pdf pdf_pages/searchable.pdf
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Stops after page 1 or 2 | The page didn't finish loading. Raise `--delay`. If you're using `--key`, click inside the viewer first so it has focus. |
| Never stops at the end | Something in the capture region changes on every pass (page counter, spinner, ad). Tighten the region to just the page, or lower `--max-pages`. |
| Duplicate or skipped pages | Raise `--delay` so each page renders fully before the screenshot. |
| Half-loaded or blurry pages | Raise `--delay` and/or `--reveal-delay`. Zoom the viewer in further for sharper captures. |
| Mouse cursor in screenshots | Add `--park-mouse`. |
| Blank or black screenshots | On macOS, check Screen Recording permission. Otherwise the viewer may block screen capture. |
| Clicks land in the wrong place | The window moved or the zoom changed since setup. Rerun setup without the saved coordinates. |

## Notes

If you can download the original PDF, `pdftoppm -png file.pdf page` (from Poppler) gives you cleaner, full-resolution images in one command.

Check that the document's terms allow you to keep a copy before capturing licensed material.
