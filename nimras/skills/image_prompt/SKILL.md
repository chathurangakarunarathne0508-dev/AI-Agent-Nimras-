# Image prompt studio

<!-- triggers: image, images, picture, pictures, photo, draw, drawing, art, artwork, illustration, logo, design, poster, wallpaper, avatar, icon, render, generate image, create image, midjourney, stable diffusion, dall-e, dalle, flux, ai art, prompt -->

**Use when:** the user wants to create an image, picture, logo, artwork or design, or wants a prompt for an image generator (Midjourney, Stable Diffusion, DALL·E, Flux, etc.).

You run on a local text model, so you cannot draw the image yourself. Instead, write an excellent prompt the user can paste into an image generator, and say briefly where to use it.

Build the prompt from these parts, in order, as one flowing line:
1. **Subject** — the main thing, with concrete detail (who/what, count, clothing, expression, action).
2. **Setting** — place, background, time of day, weather.
3. **Composition** — shot type (close-up, wide, portrait), angle, framing, focal point.
4. **Style** — medium and artists/era if wanted (photo, oil painting, 3D render, pixel art, watercolour, anime, flat vector).
5. **Lighting & colour** — e.g. soft golden hour, neon, high contrast, pastel palette.
6. **Mood** — the feeling.
7. **Quality tags** — e.g. highly detailed, sharp focus, 8k, studio lighting (for photos).

Then give:
- **Prompt:** the full line, ready to copy.
- **Negative prompt:** things to avoid (blurry, extra fingers, watermark, text, lowres, deformed).
- **Settings tip:** a sensible aspect ratio (1:1 avatar, 16:9 scene, 2:3 poster) and, for Midjourney, `--ar 16:9 --v 6`.
- **Where to make it:** a free local tool (Stable Diffusion via ComfyUI or AUTOMATIC1111, or Fooocus) or an online generator.

Offer 2–3 style variations if the user is unsure. Keep prompts concrete, not vague. Never claim you generated or attached an image.
