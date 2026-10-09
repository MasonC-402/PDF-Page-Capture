#!/usr/bin/env python3
"""
pdf_page_capture.py - Click "Next" through a PDF viewer and screenshot every page.

Works with any viewer (browser-embedded, Adobe, Edge, web document viewers, etc.)
because it drives the real mouse/keyboard and captures the screen.

Setup:
    pip install pyautogui pillow

Usage examples:
    # Interactive: hover over the Next button and the capture region when prompted
    python pdf_page_capture.py

    # Use the Right-arrow key instead of clicking a button
    python pdf_page_capture.py --key right

    # Cap at 200 pages, slower page loads, also bundle everything into one PDF
    python pdf_page_capture.py --max-pages 200 --delay 2.0 --make-pdf

Stop at any time by slamming the mouse into a screen corner (pyautogui failsafe)
or pressing Ctrl+C in the terminal.
"""

import argparse
import sys
import time
from pathlib import Path

try:
    import pyautogui
    from PIL import Image, ImageChops
except ImportError:
    sys.exit("Missing dependencies. Run: pip install pyautogui pillow")

pyautogui.FAILSAFE = True  # move mouse to a screen corner to abort


def countdown(seconds: int, msg: str) -> None:
    for s in range(seconds, 0, -1):
        print(f"\r{msg} in {s}...", end="", flush=True)
        time.sleep(1)
    print()


def capture_point(prompt: str, wait: int) -> tuple[int, int]:
    input(f"\n{prompt}\n  Press Enter here, then hover the mouse over that spot within {wait}s.")
    countdown(wait, "  Recording position")
    pos = pyautogui.position()
    print(f"  -> recorded ({pos.x}, {pos.y})")
    return pos.x, pos.y


def images_match(a: Image.Image, b: Image.Image, tolerance: int) -> bool:
    """True if two screenshots are effectively identical (no page change)."""
    if a.size != b.size:
        return False
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    # Ignore tiny pixel noise (cursor blink, anti-aliasing)
    bbox = diff.point(lambda p: 255 if p > tolerance else 0).getbbox()
    return bbox is None


def main() -> None:
    ap = argparse.ArgumentParser(description="Screenshot every page of a PDF viewer.")
    ap.add_argument("--out", default="pdf_pages", help="Output folder (default: pdf_pages)")
    ap.add_argument("--key", help="Advance with this key instead of clicking (e.g. right, pagedown, space)")
    ap.add_argument("--next-x", type=int, help="X coordinate of the Next button (skip prompt)")
    ap.add_argument("--next-y", type=int, help="Y coordinate of the Next button (skip prompt)")
    ap.add_argument("--region", help="Capture region as left,top,width,height (skip prompt)")
    ap.add_argument("--full-screen", action="store_true", help="Capture the whole screen instead of a region")
    ap.add_argument("--delay", type=float, default=1.5, help="Seconds to wait for each page to render (default 1.5)")
    ap.add_argument("--max-pages", type=int, default=1000, help="Safety cap on pages (default 1000)")
    ap.add_argument("--same-limit", type=int, default=2,
                    help="Stop after this many consecutive unchanged pages (default 2)")
    ap.add_argument("--tolerance", type=int, default=10, help="Pixel diff tolerance 0-255 (default 10)")
    ap.add_argument("--hover-wait", type=int, default=5, help="Seconds to hover when recording positions")
    ap.add_argument("--park-mouse", action="store_true",
                    help="Move the mouse off the capture region before each screenshot")
    ap.add_argument("--reveal", action="store_true",
                    help="Click a 'display content' spot before each screenshot (prompts for the spot)")
    ap.add_argument("--reveal-x", type=int, help="X coordinate of the reveal spot (skip prompt; implies --reveal)")
    ap.add_argument("--reveal-y", type=int, help="Y coordinate of the reveal spot (skip prompt; implies --reveal)")
    ap.add_argument("--reveal-delay", type=float, default=1.0,
                    help="Seconds to wait after the reveal click before the screenshot (default 1.0)")
    ap.add_argument("--make-pdf", action="store_true", help="Combine screenshots into one PDF at the end")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # --- How to advance -----------------------------------------------------
    next_pos = None
    if not args.key:
        if args.next_x is not None and args.next_y is not None:
            next_pos = (args.next_x, args.next_y)
        else:
            next_pos = capture_point("Step 1: Locate the viewer's NEXT PAGE button.", args.hover_wait)

    # --- Optional "Click here to display content" spot ----------------------
    reveal_pos = None
    if args.reveal_x is not None and args.reveal_y is not None:
        reveal_pos = (args.reveal_x, args.reveal_y)
    elif args.reveal:
        print("\nTip: bring up the 'Click here to display content' prompt in the browser first,")
        print("     so you can see where to hover.")
        reveal_pos = capture_point("Step 1b: Locate the 'Click here to display content' spot.", args.hover_wait)

    # --- What to capture ----------------------------------------------------
    region = None
    if args.region:
        region = tuple(int(v) for v in args.region.split(","))
    elif not args.full_screen:
        tl = capture_point("Step 2: TOP-LEFT corner of the page area to capture.", args.hover_wait)
        br = capture_point("Step 3: BOTTOM-RIGHT corner of the page area to capture.", args.hover_wait)
        left, top = min(tl[0], br[0]), min(tl[1], br[1])
        region = (left, top, abs(br[0] - tl[0]), abs(br[1] - tl[1]))
    if region:
        print(f"\nCapture region: left={region[0]} top={region[1]} w={region[2]} h={region[3]}")
        print(f"(Reuse next time with --region {','.join(map(str, region))})")
    if next_pos:
        print(f"Next button: (reuse with --next-x {next_pos[0]} --next-y {next_pos[1]})")
    if reveal_pos:
        print(f"Reveal spot: (reuse with --reveal-x {reveal_pos[0]} --reveal-y {reveal_pos[1]})")

    input("\nMake sure the PDF is on PAGE 1 and the viewer window is visible. Press Enter to start.")
    countdown(3, "Starting")

    # Where to park the mouse so it doesn't appear in screenshots
    screen_w, screen_h = pyautogui.size()
    park = (screen_w - 5, screen_h // 2)

    saved: list[Path] = []
    prev = None
    same_count = 0

    try:
        for page in range(1, args.max_pages + 1):
            if reveal_pos:
                pyautogui.click(*reveal_pos)
                time.sleep(args.reveal_delay)
            if args.park_mouse:
                pyautogui.moveTo(*park)
            shot = pyautogui.screenshot(region=region)

            if prev is not None and images_match(prev, shot, args.tolerance):
                same_count += 1
                print(f"  page didn't change ({same_count}/{args.same_limit})")
                if same_count >= args.same_limit:
                    print("Reached the end of the document.")
                    break
            else:
                same_count = 0
                path = out / f"page_{len(saved) + 1:04d}.png"
                shot.save(path)
                saved.append(path)
                print(f"Saved {path}")

            prev = shot

            # Advance to the next page
            if args.key:
                pyautogui.press(args.key)
            else:
                pyautogui.click(*next_pos)
            time.sleep(args.delay)
        else:
            print(f"Hit --max-pages limit ({args.max_pages}).")
    except (KeyboardInterrupt, pyautogui.FailSafeException):
        print("\nStopped by user.")

    print(f"\nDone: {len(saved)} pages saved to {out.resolve()}")

    if args.make_pdf and saved:
        imgs = [Image.open(p).convert("RGB") for p in saved]
        pdf_path = out / "combined.pdf"
        imgs[0].save(pdf_path, save_all=True, append_images=imgs[1:])
        print(f"Combined PDF: {pdf_path.resolve()}")


if __name__ == "__main__":
    main()
