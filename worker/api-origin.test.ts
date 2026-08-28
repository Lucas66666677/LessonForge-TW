import { describe, expect, it } from "vitest";

import { isPublicApiOrigin, resolveApiUpstream } from "./api-origin";

const REQUEST = new URL("https://lessonforge.example.tw/api/classes?page=2");

describe("isPublicApiOrigin", () => {
  it.each([
    "https://api.lessonforge.example.tw",
    "https://api.lessonforge.example.tw:8443",
    "http://api.lessonforge.example.tw",
    "https://203.0.113.10",
    "https://172.15.255.255", // just below the RFC 1918 172.16/12 block
    "https://172.32.0.1", // just above it
    "https://[2001:db8::1]",
  ])("accepts the public origin %s", (origin) => {
    expect(isPublicApiOrigin(origin)).toBe(true);
  });

  it.each([
    "http://localhost:8000",
    "http://api.localhost:8000",
    "http://LOCALHOST:8000",
    "http://127.0.0.1:8000",
    "http://127.9.9.9",
    "http://127.1", // shorthand the URL parser expands to 127.0.0.1
    "http://2130706433", // the same address as a bare integer
  ])("rejects the loopback origin %s", (origin) => {
    expect(isPublicApiOrigin(origin)).toBe(false);
  });

  it.each([
    "http://0.0.0.0:8000",
    "http://10.0.0.5:8000",
    "http://100.64.0.1",
    "http://169.254.169.254", // link-local, the cloud metadata address
    "http://172.16.0.1",
    "http://172.31.255.254",
    "http://192.168.1.10:8000",
  ])("rejects the private IPv4 origin %s", (origin) => {
    expect(isPublicApiOrigin(origin)).toBe(false);
  });

  it.each([
    "http://[::1]:8000",
    "http://[::]",
    "http://[fc00::1]",
    "http://[fd12:3456:789a::1]:8000",
    "http://[fe80::1]",
    "http://[::ffff:127.0.0.1]:8000", // IPv4-mapped loopback
    "http://[::ffff:192.168.1.10]", // IPv4-mapped RFC 1918
  ])("rejects the private IPv6 origin %s", (origin) => {
    expect(isPublicApiOrigin(origin)).toBe(false);
  });

  it.each([
    "",
    "api.lessonforge.example.tw", // no scheme, so not an absolute origin
    "ws://api.lessonforge.example.tw",
    "file:///etc/hosts",
  ])("rejects the unusable origin %s", (origin) => {
    expect(isPublicApiOrigin(origin)).toBe(false);
  });
});

describe("resolveApiUpstream", () => {
  it("forwards path and query to a public origin", () => {
    const upstream = resolveApiUpstream("https://api.lessonforge.example.tw", REQUEST);

    expect(upstream?.href).toBe("https://api.lessonforge.example.tw/api/classes?page=2");
  });

  it("tolerates a trailing slash on the configured origin", () => {
    const upstream = resolveApiUpstream("https://api.lessonforge.example.tw/", REQUEST);

    expect(upstream?.href).toBe("https://api.lessonforge.example.tw/api/classes?page=2");
  });

  it("refuses to resolve when the origin is unset", () => {
    expect(resolveApiUpstream(undefined, REQUEST)).toBeNull();
    expect(resolveApiUpstream("", REQUEST)).toBeNull();
  });

  it.each(["http://localhost:8000", "http://10.0.0.5:8000", "http://[::1]:8000"])(
    "refuses to resolve an upstream for %s",
    (origin) => {
      expect(resolveApiUpstream(origin, REQUEST)).toBeNull();
    },
  );
});
