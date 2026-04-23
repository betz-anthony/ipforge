import { useEffect, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { RefreshCw } from 'lucide-react'
import { syncApi } from '../api/client'

interface Props {
  type: 'dns' | 'dhcp'
}

function fmtAge(seconds: number | null): string {
  if (seconds === null) return '—'
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

export default function SyncBar({ type }: Props) {
  const qc = useQueryClient()
  const [fastPoll, setFastPoll] = useState(false)
  const prevStatus = useRef<string | null>(null)

  const { data } = useQuery({
    queryKey: ['sync-status'],
    queryFn: syncApi.status,
    refetchInterval: fastPoll ? 2000 : 15_000,
  })

  const info = data?.[type]

  useEffect(() => {
    if (!info) return
    const wasRunning = prevStatus.current === 'running'
    prevStatus.current = info.status
    if (wasRunning && info.status !== 'running') {
      setFastPoll(false)
      const key = type === 'dns' ? 'dns-zones' : 'dhcp-scopes'
      qc.invalidateQueries({ queryKey: [key] })
    }
  }, [info?.status, type, qc])

  const trigger = useMutation({
    mutationFn: () => syncApi.trigger(type),
    onSuccess: () => {
      setFastPoll(true)
      qc.invalidateQueries({ queryKey: ['sync-status'] })
    },
  })

  const isRunning = info?.status === 'running' || trigger.isPending

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '0.5rem',
      fontSize: '0.72rem', color: 'var(--text-muted)',
    }}>
      {info?.status === 'error' ? (
        <span style={{ color: 'var(--danger)' }} title={info.error ?? ''}>Sync error</span>
      ) : (
        <span>Synced {fmtAge(info?.age_seconds ?? null)}</span>
      )}
      <button
        className="btn-ghost btn-sm"
        onClick={() => trigger.mutate()}
        disabled={isRunning}
        title="Refresh data from provider"
        style={{ padding: '0.2rem 0.5rem', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}
      >
        <RefreshCw size={11} style={isRunning ? { animation: 'spin 1s linear infinite' } : undefined} />
        {isRunning ? 'Syncing…' : 'Refresh'}
      </button>
    </div>
  )
}
