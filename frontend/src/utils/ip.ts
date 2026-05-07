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
