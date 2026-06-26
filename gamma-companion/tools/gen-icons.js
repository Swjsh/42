"use strict";

// Generates public/icon-192.png and public/icon-512.png -- a branded maskable
// icon (green Gamma robot on the dark #0b1120 background). Zero dependencies:
// builds a valid PNG (RGBA, zlib-deflated IDAT) by hand using Node's zlib.
//
//   node gamma-companion/tools/gen-icons.js

const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const BG = [0x0b, 0x11, 0x20, 0xff]; // #0b1120
const ACCENT = [0x34, 0xe0, 0xa1, 0xff]; // #34e0a1
const DARK = [0x08, 0x23, 0x1c, 0xff]; // visor/inner dark
const EYE = [0x7a, 0xf7, 0xd0, 0xff]; // light mint
const YELLOW = [0xff, 0xd8, 0x6b, 0xff]; // antenna tip

function crc32(buf) {
  let c = ~0;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
  }
  return (~c) >>> 0;
}

function chunk(type, data) {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length, 0);
  const typeBuf = Buffer.from(type, "ascii");
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([typeBuf, data])), 0);
  // [length][type][data][crc] -- the data payload was missing before.
  return Buffer.concat([len, typeBuf, data, crc]);
}

// Draw a rounded-rect filled region onto the pixel buffer.
function fillRoundRect(px, W, x0, y0, w, h, r, color) {
  for (let y = y0; y < y0 + h; y++) {
    for (let x = x0; x < x0 + w; x++) {
      // rounded corners
      let cx = x, cy = y;
      let inside = true;
      const corners = [
        [x0 + r, y0 + r],
        [x0 + w - r - 1, y0 + r],
        [x0 + r, y0 + h - r - 1],
        [x0 + w - r - 1, y0 + h - r - 1],
      ];
      if (x < x0 + r && y < y0 + r) inside = dist(cx, cy, corners[0]) <= r;
      else if (x > x0 + w - r - 1 && y < y0 + r) inside = dist(cx, cy, corners[1]) <= r;
      else if (x < x0 + r && y > y0 + h - r - 1) inside = dist(cx, cy, corners[2]) <= r;
      else if (x > x0 + w - r - 1 && y > y0 + h - r - 1) inside = dist(cx, cy, corners[3]) <= r;
      if (inside) setPx(px, W, x, y, color);
    }
  }
}
function dist(x, y, c) {
  return Math.sqrt((x - c[0]) ** 2 + (y - c[1]) ** 2);
}
function fillCircle(px, W, cx, cy, r, color) {
  for (let y = Math.floor(cy - r); y <= Math.ceil(cy + r); y++) {
    for (let x = Math.floor(cx - r); x <= Math.ceil(cx + r); x++) {
      if ((x - cx) ** 2 + (y - cy) ** 2 <= r * r) setPx(px, W, x, y, color);
    }
  }
}
function setPx(px, W, x, y, color) {
  if (x < 0 || y < 0 || x >= W || y >= W) return;
  const i = (y * W + x) * 4;
  px[i] = color[0];
  px[i + 1] = color[1];
  px[i + 2] = color[2];
  px[i + 3] = color[3];
}

function buildIcon(size) {
  const W = size;
  const px = Buffer.alloc(W * W * 4);
  // fill background
  for (let i = 0; i < W * W; i++) {
    px[i * 4] = BG[0];
    px[i * 4 + 1] = BG[1];
    px[i * 4 + 2] = BG[2];
    px[i * 4 + 3] = BG[3];
  }
  // scale a 220x220 design into `size`. Maskable safe zone: keep art within ~80%.
  const s = size / 220;
  const S = (n) => Math.round(n * s);
  // antenna
  fillRoundRect(px, W, S(105), S(34), S(10), S(20), S(3), ACCENT);
  fillCircle(px, W, S(110), S(33), S(8) * 1.0, YELLOW);
  // head
  fillRoundRect(px, W, S(60), S(54), S(100), S(78), S(28), ACCENT);
  // visor
  fillRoundRect(px, W, S(74), S(68), S(72), S(50), S(20), DARK);
  // eyes
  fillCircle(px, W, S(99), S(92), S(9), EYE);
  fillCircle(px, W, S(121), S(92), S(9), EYE);
  // body
  fillRoundRect(px, W, S(68), S(132), S(84), S(64), S(24), ACCENT);
  // chest panel
  fillRoundRect(px, W, S(85), S(146), S(50), S(38), S(14), DARK);
  // chevron (two short bars approximated)
  fillRoundRect(px, W, S(96), S(160), S(14), S(6), S(3), EYE);
  fillRoundRect(px, W, S(110), S(160), S(14), S(6), S(3), EYE);

  // PNG encode: each row prefixed by filter byte 0
  const raw = Buffer.alloc((W * 4 + 1) * W);
  for (let y = 0; y < W; y++) {
    raw[y * (W * 4 + 1)] = 0;
    px.copy(raw, y * (W * 4 + 1) + 1, y * W * 4, (y + 1) * W * 4);
  }
  const idat = zlib.deflateSync(raw, { level: 9 });

  const sig = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(W, 0);
  ihdr.writeUInt32BE(W, 4);
  ihdr[8] = 8; // bit depth
  ihdr[9] = 6; // color type RGBA
  ihdr[10] = 0;
  ihdr[11] = 0;
  ihdr[12] = 0;
  return Buffer.concat([
    sig,
    chunk("IHDR", ihdr),
    chunk("IDAT", idat),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const out = path.join(__dirname, "..", "public");
for (const size of [192, 512]) {
  const png = buildIcon(size);
  const file = path.join(out, "icon-" + size + ".png");
  fs.writeFileSync(file, png);
  process.stdout.write("wrote " + file + " (" + png.length + " bytes)\n");
}
