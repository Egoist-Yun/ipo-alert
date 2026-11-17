const pad = n => String(n).padStart(2, '0');

function bounds(year, month) {
  const last = new Date(Date.UTC(year, month, 0)).getUTCDate();
  return [`${year}-${pad(month)}-01`, `${year}-${pad(month)}-${pad(last)}`];
}

export function monthGrid(year, month) {
  const [first, last] = bounds(year, month);
  const lastDay = Number(last.slice(8));
  const offset = (new Date(Date.UTC(year, month - 1, 1)).getUTCDay() + 6) % 7; // Monday = 0
  const cells = [...Array(offset).fill('')];
  for (let d = 1; d <= lastDay; d++) cells.push(`${year}-${pad(month)}-${pad(d)}`);
  while (cells.length % 7) cells.push('');
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

function overlapping(ipos, year, month) {
  const [first, last] = bounds(year, month);
  return ipos.filter(i => i.sub_start && i.sub_end && i.sub_start <= last && i.sub_end >= first);
}

export function barsForMonth(ipos, year, month) {
  const [first, last] = bounds(year, month);
  return overlapping(ipos, year, month).map(i => ({
    no: i.no,
    name: i.name,
    start: i.sub_start < first ? first : i.sub_start,
    end: i.sub_end > last ? last : i.sub_end,
    flagCount: i.flag_count ?? 0,
    isSpac: !!i.is_spac,
    hasResult: i.inst_competition != null,
  }));
}

export function listForMonth(ipos, year, month) {
  return overlapping(ipos, year, month).sort((a, b) => a.sub_start.localeCompare(b.sub_start) || a.no - b.no);
}
