import {
  type KeyboardEvent,
  type PointerEvent,
  type ReactNode,
  type RefObject,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'

import { DAY, type Frame, fmtDay, type Margin, startOfDay } from './scale'

// Kézzel rajzolt SVG-grafikonok (felületterv, 2026-10-30): egy tengely, halk
// folytonos rács, a határ szaggatott vonal a státusz színében. Recharts helyett
// saját rajz, mert a terv pontosan ezt írja elő, és így nincs új függőség.

/** Dátumfeliratok: legalább ~58 px közöttük, hogy keskeny grafikonon se fedjék egymást. */
export function XAxis({ f, h, now }: { f: Frame; h: number; now: Date }) {
  const min = Math.ceil(58 / f.dw)
  const step = [1, 2, 7, 14, 21, 28, 35, 42].find((s) => s >= min) ?? 45
  const labels: ReactNode[] = []
  for (let k = 0; k < f.n; k += step) {
    const d = new Date(startOfDay(now) - k * DAY + DAY / 2)
    labels.push(
      <text
        key={k}
        className="xt"
        x={(f.x0 + (f.n - k - (k === 0 ? 0 : 0.5)) * f.dw).toFixed(1)}
        y={h - 6}
        // A mai (jobb szélső) felirat a sávhoz jobbra igazodik, hogy ne lógjon ki.
        textAnchor={k === 0 ? 'end' : 'middle'}
      >
        {fmtDay(d)}
      </text>,
    )
  }
  return <>{labels}</>
}

export function YGrid({
  ticks,
  y,
  f,
  fmt = String,
}: {
  ticks: number[]
  y: (v: number) => number
  f: Frame
  fmt?: (v: number) => string
}) {
  return (
    <>
      {ticks.map((v) => (
        <g key={v}>
          <line className="gl" x1={f.x0} x2={f.x1} y1={y(v).toFixed(1)} y2={y(v).toFixed(1)} />
          <text className="yt" x={f.x0 - 8} y={(y(v) + 3.8).toFixed(1)} textAnchor="end">
            {fmt(v)}
          </text>
        </g>
      ))}
    </>
  )
}

/** Szaggatott határvonal a státusz színében, a jobb szélén az értékkel. */
export function ThresholdLines({
  thresholds,
  y,
  f,
}: {
  thresholds: { value: number; kind: 'mod' | 'sev'; label: string }[]
  y: (v: number) => number
  f: Frame
}) {
  return (
    <>
      {thresholds.map((th) => {
        const yy = y(th.value).toFixed(1)
        return (
          <g key={`${th.kind}-${th.value}`}>
            <line className={`thr thr-${th.kind}`} x1={f.x0} x2={f.x1} y1={yy} y2={yy} />
            <text className="thl" x={f.x1 + 6} y={(Number(yy) + 3.8).toFixed(1)}>
              {th.label}
            </text>
          </g>
        )
      })}
    </>
  )
}

function useWidth(ref: RefObject<HTMLDivElement | null>) {
  const [width, setWidth] = useState(0)
  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => setWidth(Math.max(220, Math.floor(el.getBoundingClientRect().width)))
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [ref])
  return width
}

/** Amit egy grafikon kirajzol: rács, jelek (a kiemelt pont indexével), a pontok
 * helye a tooltiphez, és a tooltip tartalma. */
export type Drawn = {
  grid: ReactNode
  marks: (hot: number | null) => ReactNode
  xs: number[]
  ys: number[]
  tip: (i: number) => ReactNode
}

/** A grafikon kerete: méri a szélességet, kezeli az egeret és a billentyűzetet
 * (←/→ lépked a pontok között, Esc elrejti), és megjeleníti a tooltipet. */
export function ChartShell({
  height,
  label,
  margin,
  draw,
}: {
  height: number
  label: string
  margin: Margin
  draw: (w: number) => Drawn
}) {
  const ref = useRef<HTMLDivElement>(null)
  const w = useWidth(ref)
  const [hot, setHot] = useState<number | null>(null)
  const d = w ? draw(w) : null
  const n = d?.xs.length ?? 0
  const cur = hot !== null && hot < n ? hot : null

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    if (!d || !n) return
    const r = e.currentTarget.getBoundingClientRect()
    const px = (e.clientX - r.left) * (w / r.width)
    let best = 0
    d.xs.forEach((x, i) => {
      if (Math.abs(x - px) < Math.abs(d.xs[best] - px)) best = i
    })
    setHot(best)
  }
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (!n) return
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault()
      const step = e.key === 'ArrowRight' ? 1 : -1
      setHot(cur === null ? n - 1 : Math.min(n - 1, Math.max(0, cur + step)))
    } else if (e.key === 'Escape') setHot(null)
  }

  return (
    <div className="pd-chart" ref={ref} style={{ height }}>
      {d && (
        <svg
          viewBox={`0 0 ${w} ${height}`}
          width={w}
          height={height}
          role="img"
          tabIndex={0}
          aria-label={label}
          onPointerMove={onMove}
          onPointerLeave={() => setHot(null)}
          onFocus={() => n && setHot(n - 1)}
          onBlur={() => setHot(null)}
          onKeyDown={onKey}
        >
          {d.grid}
          {cur !== null && (
            <line
              className="xh"
              x1={d.xs[cur]}
              x2={d.xs[cur]}
              y1={margin.t}
              y2={height - margin.b}
            />
          )}
          {d.marks(cur)}
        </svg>
      )}
      {d && cur !== null && (
        <div
          className={d.xs[cur] > w - 170 ? 'pd-tip flip' : 'pd-tip'}
          style={{ left: d.xs[cur], top: d.ys[cur] }}
          aria-hidden="true"
        >
          {d.tip(cur)}
        </div>
      )}
    </div>
  )
}
