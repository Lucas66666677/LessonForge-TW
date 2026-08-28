/**
 * Guards the upstream the Sites worker proxies `/api/*` to.
 *
 * `API_BASE_URL` is a deploy-time binding, not a value this repository holds, so a
 * regression to loopback or a private range never shows up in a diff or in CI. The
 * worker would keep answering: it would just forward the public site to an address
 * that is unreachable from the internet, or to whatever else happens to answer at
 * that address from inside the runtime's own network. Classifying the origin here
 * lets the worker refuse the misconfiguration instead of proxying to it.
 *
 * A hostname that merely *resolves* to a private address is not detectable without
 * DNS, which this deliberately does not do; the check is on the literal origin.
 */

/** Blocks that must never be the public API origin, as [network, prefix length]. */
const PRIVATE_IPV4_BLOCKS: ReadonlyArray<readonly [string, number]> = [
  ["0.0.0.0", 8], // "this network"
  ["10.0.0.0", 8], // RFC 1918 private
  ["100.64.0.0", 10], // RFC 6598 carrier-grade NAT
  ["127.0.0.0", 8], // loopback
  ["169.254.0.0", 16], // link-local, including cloud metadata
  ["172.16.0.0", 12], // RFC 1918 private
  ["192.168.0.0", 16], // RFC 1918 private
];

function toIpv4Number(host: string): number | null {
  const octets = host.split(".");
  if (octets.length !== 4) return null;
  let value = 0;
  for (const octet of octets) {
    if (!/^\d{1,3}$/.test(octet)) return null;
    const part = Number(octet);
    if (part > 255) return null;
    value = value * 256 + part;
  }
  return value;
}

function isPrivateIpv4(value: number): boolean {
  return PRIVATE_IPV4_BLOCKS.some(([network, prefix]) => {
    const base = toIpv4Number(network);
    const blockSize = 2 ** (32 - prefix);
    return base !== null && Math.floor(value / blockSize) === Math.floor(base / blockSize);
  });
}

/** Expands an IPv6 literal (already stripped of brackets) into its eight hextets. */
function toIpv6Hextets(host: string): number[] | null {
  const sides = host.split("::");
  if (sides.length > 2) return null;

  const parseSide = (side: string): number[] | null => {
    if (side === "") return [];
    const hextets: number[] = [];
    for (const group of side.split(":")) {
      if (group.includes(".")) {
        // A trailing dotted quad, as in `::ffff:127.0.0.1`, fills two hextets.
        const embedded = toIpv4Number(group);
        if (embedded === null) return null;
        hextets.push(Math.floor(embedded / 65536), embedded % 65536);
        continue;
      }
      if (!/^[0-9a-f]{1,4}$/.test(group)) return null;
      hextets.push(Number.parseInt(group, 16));
    }
    return hextets;
  };

  const head = parseSide(sides[0]);
  const tail = sides.length === 2 ? parseSide(sides[1]) : [];
  if (head === null || tail === null) return null;
  if (sides.length === 1) return head.length === 8 ? head : null;

  const elided = 8 - head.length - tail.length;
  if (elided < 1) return null;
  return [...head, ...(Array<number>(elided).fill(0)), ...tail];
}

function isPrivateIpv6(host: string): boolean {
  const hextets = toIpv6Hextets(host);
  if (hextets === null) return false;

  const zeroPrefix = hextets.slice(0, 5).every((hextet) => hextet === 0);
  // `::ffff:a.b.c.d` is an IPv4 address wearing an IPv6 spelling; judge it as IPv4.
  if (zeroPrefix && hextets[5] === 0xffff) {
    return isPrivateIpv4(hextets[6] * 65536 + hextets[7]);
  }
  if (zeroPrefix && hextets[5] === 0 && hextets[6] === 0) {
    return hextets[7] === 0 || hextets[7] === 1; // unspecified `::` and loopback `::1`
  }
  return (
    (hextets[0] >= 0xfc00 && hextets[0] <= 0xfdff) || // unique local
    (hextets[0] >= 0xfe80 && hextets[0] <= 0xfebf) // link local
  );
}

/**
 * Whether `apiBaseUrl` names an origin the public site may be proxied to. Anything
 * unparsable, non-HTTP, loopback, private IPv4, or private IPv6 is rejected.
 */
export function isPublicApiOrigin(apiBaseUrl: string): boolean {
  let parsed: URL;
  try {
    parsed = new URL(apiBaseUrl);
  } catch {
    return false;
  }
  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") return false;

  const host = parsed.hostname.toLowerCase();
  if (host === "") return false;
  if (host.startsWith("[") && host.endsWith("]")) return !isPrivateIpv6(host.slice(1, -1));
  // RFC 6761 reserves `localhost` and every name under it for the loopback host.
  if (host === "localhost" || host.endsWith(".localhost")) return false;

  const ipv4 = toIpv4Number(host);
  return ipv4 === null || !isPrivateIpv4(ipv4);
}

/**
 * The upstream URL for an incoming `/api/*` request, or `null` when `API_BASE_URL`
 * is unset or is not a public origin. A `null` is the worker's cue to answer
 * "not configured" rather than proxy.
 */
export function resolveApiUpstream(apiBaseUrl: string | undefined, requestUrl: URL): URL | null {
  const apiBase = apiBaseUrl?.replace(/\/$/, "");
  if (!apiBase || !isPublicApiOrigin(apiBase)) return null;
  return new URL(`${requestUrl.pathname}${requestUrl.search}`, apiBase);
}
