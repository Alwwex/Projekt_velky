// Jednotky a formátování délek. Interně vše v milimetrech.

export const UNITS = {
  m: { label: 'm', name: 'metry' },
  cm: { label: 'cm', name: 'centimetry' },
  mm: { label: 'mm', name: 'milimetry' },
  ft: { label: 'ft-in', name: 'stopy a palce' },
};

const nf = (digits) => new Intl.NumberFormat('cs-CZ', {
  minimumFractionDigits: digits, maximumFractionDigits: digits,
});
const NF = { 0: nf(0), 1: nf(1), 2: nf(2), 3: nf(3) };

/** Formátuje délku v mm podle zvolených jednotek. */
export function formatLength(mm, unit = 'm', { short = false } = {}) {
  if (mm == null || !Number.isFinite(mm)) return '—';
  switch (unit) {
    case 'mm': return `${NF[0].format(mm)} mm`;
    case 'cm': return `${NF[1].format(mm / 10)} cm`;
    case 'ft': return formatFeetInches(mm);
    default: return short ? `${NF[2].format(mm / 1000)} m` : `${NF[3].format(mm / 1000)} m`;
  }
}

export function formatArea(mm2, unit = 'm') {
  if (unit === 'ft') return `${NF[1].format(mm2 / (304.8 * 304.8))} ft²`;
  return `${NF[2].format(mm2 / 1e6)} m²`;
}

export function formatFeetInches(mm) {
  let sixteenths = Math.round((mm / 25.4) * 16);
  const neg = sixteenths < 0;
  sixteenths = Math.abs(sixteenths);
  const ft = Math.floor(sixteenths / 192);
  sixteenths -= ft * 192;
  const inch = Math.floor(sixteenths / 16);
  let num = sixteenths % 16;
  let den = 16;
  while (num && num % 2 === 0) { num /= 2; den /= 2; }
  const frac = num ? ` ${num}/${den}` : '';
  return `${neg ? '-' : ''}${ft}' ${inch}${frac}"`;
}

/**
 * Převede text zadaný uživatelem na mm.
 * Podporuje: "3,452"  "3.452 m"  "345 cm"  "3452mm"  "11' 4 3/8\""  "136.5in"
 * Číslo bez jednotky se bere v jednotkách `unit`.
 */
export function parseLength(text, unit = 'm') {
  if (text == null) return NaN;
  let s = String(text).trim().toLowerCase().replace(/,/g, '.').replace(/\s+/g, ' ');
  if (!s) return NaN;
  // stopy/palce
  const fi = s.match(/^(-?\d+(?:\.\d+)?)\s*(?:'|ft)\s*(?:(\d+(?:\.\d+)?)?\s*(?:(\d+)\/(\d+))?\s*(?:"|in)?)?$/);
  if (fi) {
    const ft = parseFloat(fi[1]);
    const inch = fi[2] ? parseFloat(fi[2]) : 0;
    const frac = fi[3] ? parseInt(fi[3], 10) / parseInt(fi[4], 10) : 0;
    return (ft * 12 + inch + frac) * 25.4;
  }
  const inches = s.match(/^(-?\d+(?:\.\d+)?)\s*(?:"|in)$/);
  if (inches) return parseFloat(inches[1]) * 25.4;
  const m = s.match(/^(-?\d+(?:\.\d+)?)\s*(mm|cm|m)?$/);
  if (!m) return NaN;
  const v = parseFloat(m[1]);
  const u = m[2] || (unit === 'ft' ? 'in' : unit);
  switch (u) {
    case 'mm': return v;
    case 'cm': return v * 10;
    case 'in': return v * 25.4;
    default: return v * 1000;
  }
}
