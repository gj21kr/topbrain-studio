import type { Structure } from './model';

/** The manifest's source group is authoritative even when its label is abbreviated. */
export function isArterialStructure(data: Pick<Structure, 'group' | 'name'>): boolean {
  if (/reference|skull|bone|parenchyma|^brain$/i.test(data.group) || /^(skull|brain|bone|cranium|cerebrum|cerebellum)\b/i.test(data.name)) return false;
  if (/^veins and sinuses$/i.test(data.group)) return false;
  if (/^arteries$/i.test(data.group)) return true;
  return /\b(artery|arteries|arterial|vessel|vascular|aorta|brachiocephalic|carotid|subclavian)\b/i.test(data.name)
    || /^(anterior circulation|posterior circulation|connections|aortic origin|neck arteries)$/i.test(data.group);
}
