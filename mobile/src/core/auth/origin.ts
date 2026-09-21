const dnsLabel = /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/;

export function normalizeServerOrigin(
  value: string,
  options: Readonly<{ allowInsecureLoopback?: boolean }> = {},
): string {
  if (value !== value.trim() || value.length === 0 || value.length > 255) {
    throw new Error("server origin must be trimmed and at most 255 characters");
  }
  if (!/^[\x00-\x7f]+$/.test(value)) {
    throw new Error("server origin must contain only ASCII characters");
  }
  let url: URL;
  try {
    url = new URL(value);
  } catch {
    throw new Error("server origin is invalid");
  }
  if (url.username || url.password || url.pathname !== "/" || url.search || url.hash) {
    throw new Error("server origin cannot contain credentials, path, query, or fragment");
  }
  const hostname = url.hostname.toLowerCase();
  if (!hostname || hostname.endsWith(".")) {
    throw new Error("server origin contains an invalid host");
  }
  const ipv6 = hostname.startsWith("[") && hostname.endsWith("]");
  const ipv4 = /^\d{1,3}(?:\.\d{1,3}){3}$/.test(hostname);
  if (
    (!ipv6 && !ipv4 && hostname.split(".").some((label) => !dnsLabel.test(label))) ||
    (ipv6 && !/^\[[0-9a-f:]+\]$/.test(hostname))
  ) {
    throw new Error("server origin contains an invalid host");
  }
  if (ipv4 && hostname.split(".").some((part) => Number(part) > 255)) {
    throw new Error("server origin contains an invalid host");
  }
  if (url.port === "0") {
    throw new Error("server origin contains an invalid port");
  }
  const loopback = hostname === "localhost" || hostname.startsWith("127.") || hostname === "[::1]";
  if (
    url.protocol !== "https:" &&
    !(url.protocol === "http:" && options.allowInsecureLoopback === true && loopback)
  ) {
    throw new Error("server origin must use HTTPS");
  }
  return `${url.protocol}//${url.host.toLowerCase()}`;
}
