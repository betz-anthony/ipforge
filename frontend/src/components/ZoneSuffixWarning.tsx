import { shortNameForZone } from '../utils/dnsNames'

interface Props {
  name: string
  zone: string
  allow: boolean
  onAllow: (allow: boolean) => void
  onUseShort: (short: string) => void
}

/** Warns when a record name repeats its zone; the server blocks it unless overridden. */
export default function ZoneSuffixWarning({ name, zone, allow, onAllow, onUseShort }: Props) {
  const short = shortNameForZone(name, zone)
  if (!short) return null
  return (
    <div className="form-field form-field-wide" role="alert">
      <span className="form-field-error-msg">
        "{name}" already ends in the zone "{zone}", so the DNS server would create
        "{name}.{zone}".
      </span>
      <span style={{ display: 'inline-flex', gap: '0.75rem', alignItems: 'center', marginTop: '0.25rem' }}>
        <button type="button" className="btn-ghost btn-sm" onClick={() => onUseShort(short)}>
          Use "{short}"
        </button>
        <label style={{ fontSize: '0.75rem', display: 'inline-flex', gap: '0.3rem', alignItems: 'center' }}>
          <input type="checkbox" checked={allow} onChange={e => onAllow(e.target.checked)} />
          Create it anyway
        </label>
      </span>
    </div>
  )
}
