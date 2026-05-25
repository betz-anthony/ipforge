export function isValidIPv4(ip: string): boolean {
  const parts = ip.split('.')
  if (parts.length !== 4) return false
  return parts.every(p => p !== '' && !isNaN(Number(p)) && Number(p) >= 0 && Number(p) <= 255 && String(Number(p)) === p)
}

export function isValidIPv6(ip: string): boolean {
  if (!ip || ip.length > 45) return false
  if ((ip.match(/::/g) ?? []).length > 1) return false
  const parts = ip.split(':')
  if (parts.length < 2 || parts.length > 8) return false
  return parts.every(p => p === '' || /^[0-9a-fA-F]{1,4}$/.test(p))
}

// IEEE 802-2014: EUI-48 — colon/hyphen-separated octets or Cisco dot-quad
export function isValidEUI48(mac: string): boolean {
  return /^([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}$/.test(mac) ||
         /^[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}\.[0-9a-fA-F]{4}$/.test(mac)
}

// IEEE 802c-2017: EUI-64 — colon/hyphen-separated octets
export function isValidEUI64(id: string): boolean {
  return /^([0-9a-fA-F]{2}[:-]){7}[0-9a-fA-F]{2}$/.test(id)
}

export function ipToNum(ip: string): number {
  return ip.split('.').reduce((acc, p) => (acc << 8) + parseInt(p, 10), 0) >>> 0
}

export function ipInCidr(ip: string, cidr: string): boolean {
  const [net, bits] = cidr.split('/')
  const shift = 32 - Number(bits)
  const mask = shift === 32 ? 0 : (~((1 << shift) - 1)) >>> 0
  return (ipToNum(ip) & mask) === (ipToNum(net) & mask)
}

export function rangeSize(start: string, end: string): number {
  const n = ipToNum(end) - ipToNum(start) + 1
  return n > 0 ? n : 0
}

// Expand IPv6 to 8 groups of 4 hex digits, returning BigInt
function ipv6ToBigInt(ip: string): bigint {
  const [head, tail] = ip.includes('::') ? ip.split('::') : [ip, '']
  const headParts = head ? head.split(':') : []
  const tailParts = tail ? tail.split(':') : []
  const fill = 8 - headParts.length - tailParts.length
  const parts = [...headParts, ...Array(fill).fill('0'), ...tailParts]
  let n = 0n
  for (const p of parts) n = (n << 16n) + BigInt(parseInt(p || '0', 16))
  return n
}

// Compare two IP strings numerically. Handles v4 and v6 (mixed: v4 < v6).
export function ipCompare(a: string, b: string): number {
  const av6 = a.includes(':')
  const bv6 = b.includes(':')
  if (av6 !== bv6) return av6 ? 1 : -1
  if (av6) {
    const an = ipv6ToBigInt(a), bn = ipv6ToBigInt(b)
    return an < bn ? -1 : an > bn ? 1 : 0
  }
  return ipToNum(a) - ipToNum(b)
}
