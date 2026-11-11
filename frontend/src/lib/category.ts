import {
  Bot,
  Building2,
  Cpu,
  Gauge,
  Landmark,
  Leaf,
  MapPin,
  Network,
  Newspaper,
  Rocket,
  Scale,
  Server,
  ShieldCheck,
  Snowflake,
  Zap,
  type LucideIcon,
} from 'lucide-react'
import type { CSSProperties } from 'react'

/** Icon and hue (oklch) per category slug. Unknown slugs fall back to a neutral newspaper. */
const CATEGORY_LOOK: Record<string, [LucideIcon, number]> = {
  'dc-infrastructure': [Server, 250],
  'ai-compute-gpus': [Cpu, 290],
  'power-energy': [Zap, 70],
  cooling: [Snowflake, 215],
  sustainability: [Leaf, 150],
  'hyperscaler-investments': [Building2, 265],
  'economics-finance': [Landmark, 170],
  'site-selection': [MapPin, 25],
  networking: [Network, 235],
  optimization: [Gauge, 320],
  'ai-agentic': [Bot, 300],
  security: [ShieldCheck, 15],
  regulation: [Scale, 50],
  'emerging-tech': [Rocket, 340],
}
export function categoryLook(slug: string | null | undefined): { Icon: LucideIcon; style: CSSProperties } {
  const [Icon, h] = CATEGORY_LOOK[slug ?? ''] ?? [Newspaper, 260]
  return { Icon, style: { '--h': h } as CSSProperties }
}
