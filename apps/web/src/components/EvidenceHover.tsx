import { useId, useState } from 'react'

export type Claim = { claim: string; label: string; score?: number; evidence_ids?: string[]; evidence_snippet?: string; fixed?: string | null }

const style: Record<string, string> = {
  supported: 'decoration-good bg-good-soft/60',
  partly_supported: 'decoration-warn bg-warn-soft',
  unsupported: 'decoration-bad bg-bad-soft line-through',
}

/** A claim in the draft; hover or focus shows the portfolio evidence behind it (keyboard accessible). */
export function EvidenceHover({ claim }: { claim: Claim }) {
  const [show, setShow] = useState(false)
  const id = useId()
  if (claim.label === 'not_a_claim') return <span>{claim.claim} </span>
  return (
    <span className="relative">
      <span tabIndex={0} aria-describedby={id} data-testid="claim" data-label={claim.label}
        onMouseEnter={() => setShow(true)} onMouseLeave={() => setShow(false)} onFocus={() => setShow(true)} onBlur={() => setShow(false)}
        className={`cursor-help rounded underline decoration-2 underline-offset-4 ${style[claim.label] ?? ''}`}>
        {claim.fixed ?? claim.claim}
      </span>{' '}
      {show && (
        <span id={id} role="tooltip" className="absolute left-0 top-full z-30 mt-1 block w-80 max-w-[85vw] rounded-lg border border-line bg-white p-3 text-xs shadow-lg">
          <span className="mb-1 block font-semibold capitalize">{claim.label.replace('_', ' ')} · score {claim.score?.toFixed(2)}</span>
          {claim.evidence_snippet ? <span className="block text-slate-700">“{claim.evidence_snippet}”</span> : <span className="block text-bad">No portfolio evidence; removed before review.</span>}
          {!!claim.evidence_ids?.length && <span className="mt-1 block font-mono text-[10px] text-muted">{claim.evidence_ids.join(' · ')}</span>}
        </span>
      )}
    </span>
  )
}
