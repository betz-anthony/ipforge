type SkeletonProps = {
  width?: string
  height?: string
  radius?: string
  style?: React.CSSProperties
}

export function Skeleton({ width = '100%', height = '1rem', radius = '4px', style }: SkeletonProps) {
  return (
    <span
      className="skeleton"
      style={{
        display: 'inline-block',
        width,
        height,
        borderRadius: radius,
        ...style,
      }}
      aria-hidden="true"
    />
  )
}

type TableSkeletonProps = {
  rows?: number
  cols: number
}

export function TableSkeleton({ rows = 5, cols }: TableSkeletonProps) {
  return (
    <div className="table-wrap" aria-busy="true">
      <table>
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={r}>
              {Array.from({ length: cols }).map((_, c) => (
                <td key={c}><Skeleton width={c === cols - 1 ? '40%' : '70%'} height="0.85rem" /></td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
