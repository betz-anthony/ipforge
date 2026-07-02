import type { CustomFieldDef } from '../api/client'

interface Props {
  defs: CustomFieldDef[]
  values: Record<string, string>
  tagsText: string
  onValueChange: (name: string, value: string) => void
  onTagsChange: (text: string) => void
}

export default function CustomFieldsEditor({ defs, values, tagsText, onValueChange, onTagsChange }: Props) {
  return (
    <>
      <div className="form-field" style={{ gridColumn: '1 / -1' }}>
        <label htmlFor="cf-tags">Tags</label>
        <input
          id="cf-tags"
          value={tagsText}
          onChange={e => onTagsChange(e.target.value)}
          placeholder="comma-separated, e.g. prod, critical"
        />
      </div>
      {defs.map(d => (
        <div className="form-field" key={d.id} style={{ gridColumn: '1 / -1' }}>
          <label htmlFor={`cf-${d.name}`}>{d.label}</label>
          {d.field_type === 'select' ? (
            <select id={`cf-${d.name}`} value={values[d.name] ?? ''} onChange={e => onValueChange(d.name, e.target.value)}>
              <option value="">— None —</option>
              {(d.options ?? []).map(o => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          ) : (
            <input
              id={`cf-${d.name}`}
              type={d.field_type === 'date' ? 'date' : 'text'}
              value={values[d.name] ?? ''}
              onChange={e => onValueChange(d.name, e.target.value)}
            />
          )}
        </div>
      ))}
    </>
  )
}

export function parseTags(text: string): string[] {
  return Array.from(new Set(text.split(',').map(t => t.trim()).filter(Boolean)))
}
