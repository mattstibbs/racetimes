// Makes the service's landing page images (slice 19) in static/img/landing/.
//
//   PHOTO=/path/to/cowes-week-2019.jpg \
//     NODE_PATH="$(npm root -g)" node scripts/landing_images/make.js
//
// PHOTO is the hero photo: "Cowes Week 2019" by Peter Trimming, CC BY-SA 2.0,
// https://commons.wikimedia.org/wiki/File:Cowes_Week_2019_-_geograph.org.uk_-_6240990.jpg
// (download any size of 1600 pixels wide or more). It's resized to two widths,
// as WebP and a JPEG fallback. Being a resized copy, it keeps the same licence;
// the page credits it (templates/clubs/service_home.html).
//
// The screenshots are the tops of three of the user manual's own
// (manual/images/), so run this again after scripts/manual_screenshots/run.sh
// changes them.
//
// Chromium does the resizing and encoding, so this needs only Node.js and
// Playwright, as the manual's screenshots do; nothing is added to Python.
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const OUT = path.join(ROOT, 'static', 'img', 'landing');
const MANUAL = path.join(ROOT, 'manual', 'images');

// [output name, source, crop height in source pixels (the top of it), output width]
const SCREENSHOTS = [
  ['results-phone.png', 'results-home.png', 600, 375],
  ['race-day.png', 'race-day-finishing.png', 640, 768],
  ['race-office.png', 'race-office.png', 600, 960],
];
const PHOTO_WIDTHS = [800, 1600];

// Draws the image, cropped to its top `cropHeight` pixels (all of it if not
// given) and scaled to `width`, and returns it encoded as `type`.
async function encode(page, file, { width, cropHeight, type, quality }) {
  const data = fs.readFileSync(file).toString('base64');
  const mime = file.endsWith('.png') ? 'image/png' : 'image/jpeg';
  const dataUrl = await page.evaluate(
    async ({ src, width, cropHeight, type, quality }) => {
      const img = new Image();
      img.src = src;
      await img.decode();
      const sourceHeight = cropHeight || img.naturalHeight;
      const height = Math.round((sourceHeight * width) / img.naturalWidth);
      const canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      const context = canvas.getContext('2d');
      context.imageSmoothingQuality = 'high';
      context.drawImage(img, 0, 0, img.naturalWidth, sourceHeight, 0, 0, width, height);
      return canvas.toDataURL(type, quality);
    },
    { src: `data:${mime};base64,${data}`, width, cropHeight, type, quality },
  );
  return Buffer.from(dataUrl.split(',')[1], 'base64');
}

(async () => {
  const photo = process.env.PHOTO;
  if (!photo) throw new Error('Set PHOTO to the hero photo file (see the top of this script).');
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || undefined });
  const page = await browser.newPage();
  const write = (name, bytes) => {
    fs.writeFileSync(path.join(OUT, name), bytes);
    console.log(`${name}: ${Math.round(bytes.length / 1024)} KB`);
  };
  for (const width of PHOTO_WIDTHS) {
    write(`cowes-${width}.webp`, await encode(page, photo, { width, type: 'image/webp', quality: 0.78 }));
    write(`cowes-${width}.jpg`, await encode(page, photo, { width, type: 'image/jpeg', quality: 0.8 }));
  }
  for (const [name, source, cropHeight, width] of SCREENSHOTS) {
    write(name, await encode(page, path.join(MANUAL, source), { width, cropHeight, type: 'image/png' }));
  }
  await browser.close();
})();
