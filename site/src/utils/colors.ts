function clamp(value: number, min = 0, max = 1): number {
  return Math.min(max, Math.max(min, value));
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const cleaned = hex.replace('#', '');
  const normalized = cleaned.length === 3
    ? cleaned.split('').map((char) => `${char}${char}`).join('')
    : cleaned;
  const numeric = Number.parseInt(normalized, 16);
  return {
    r: (numeric >> 16) & 255,
    g: (numeric >> 8) & 255,
    b: numeric & 255,
  };
}

export function interpolateHex(startHex: string, endHex: string, ratio: number): string {
  const safeRatio = clamp(ratio);
  const start = hexToRgb(startHex);
  const end = hexToRgb(endHex);
  const channel = (from: number, to: number) => Math.round(from + (to - from) * safeRatio);
  const toHex = (value: number) => value.toString(16).padStart(2, '0');

  return `#${toHex(channel(start.r, end.r))}${toHex(channel(start.g, end.g))}${toHex(channel(start.b, end.b))}`;
}
