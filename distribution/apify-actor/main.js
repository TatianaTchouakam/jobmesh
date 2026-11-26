// Jobmesh Apify actor: pages through the public /jobs API and stores the
// results in the actor's dataset. No key needed for public search.
import { Actor } from 'apify';

await Actor.init();
const input = (await Actor.getInput()) ?? {};
const base = 'https://jobmesh.world/jobs';
const pageSize = 50;               // free, keyless page size
const maxItems = input.maxItems ?? 500;

const params = (offset) => {
  const p = new URLSearchParams({ limit: String(pageSize), offset: String(offset) });
  if (input.q) p.set('q', input.q);
  if (input.country) p.set('country', input.country);
  if (input.workplace_type) p.set('workplace_type', input.workplace_type);
  return p.toString();
};

let offset = 0, stored = 0;
while (stored < maxItems) {
  const res = await fetch(`${base}?${params(offset)}`);
  if (!res.ok) break;
  const data = await res.json();
  const rows = data.results ?? [];
  if (rows.length === 0) break;
  const slice = rows.slice(0, maxItems - stored);
  await Actor.pushData(slice);
  stored += slice.length;
  if (rows.length < pageSize) break;
  offset += rows.length;
}
console.log(`Stored ${stored} jobs from Jobmesh.`);
await Actor.exit();
