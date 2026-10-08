"use strict";

const assert = require("node:assert/strict");
const { readFileSync } = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");
const vm = require("node:vm");

const script = readFileSync(path.join(__dirname, "../../src/jarvis/pwa/app.js"), "utf8");
const EMPTY = "Connect JARVIS to see Garmin data.";

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element() {
  return {
    children: [], textContent: "", disabled: false, value: "", classList: { add() {}, remove() {} },
    listeners: {},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); },
  };
}

function harness() {
  const nodes = new Map(), requests = [], windowEvents = {};
  const clock = { now: Date.parse("2026-10-07T12:00:00Z") };
  class FakeDate extends Date {
    static now() { return clock.now; }
  }
  const get = (selector) => {
    if (!nodes.has(selector)) nodes.set(selector, element());
    return nodes.get(selector);
  };
  let identity;
  const storageRequest = (result) => {
    const request = { result };
    queueMicrotask(() => request.onsuccess?.());
    return request;
  };
  const database = {
    close() {},
    transaction() {
      return { objectStore: () => ({
        get: () => storageRequest(identity),
        clear: () => { identity = undefined; return storageRequest(undefined); },
        put: (value) => { identity = value; return storageRequest(value); },
      }) };
    },
  };
  const context = vm.createContext({
    AbortController, DOMException, TextEncoder, URLSearchParams, Date: FakeDate, Promise,
    document: { querySelector: get, createElement: element },
    window: { location: { origin: "https://synthetic.test" }, addEventListener: (name, callback) => { windowEvents[name] = callback; } },
    navigator: { onLine: true },
    indexedDB: { open: () => storageRequest(database) },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    caches: { keys: async () => [] },
    setTimeout: () => 0,
    fetch: (url, options) => {
      const pending = deferred();
      requests.push({ url, options, pending });
      // Deliberately ignore abort: transport/body work can complete after cancellation.
      return pending.promise;
    },
  });
  const run = (code) => vm.runInContext(code, context);
  const ready = Promise.resolve().then(() => Promise.resolve());
  const activate = (session = "synthetic-session") => run(`state.csrf=${JSON.stringify(session)};state.hasIdentity=true;state.healthAllowed=true;setConnected(true);`);
  const summary = (steps) => ({
    date: "2026-10-07", refreshed_at: "2026-10-07T12:00:00Z", steps,
    resting_heart_rate: null, sleep_minutes: null, stress: null, body_battery: null,
    activities: [{ name: "Activity", type: "walking", started: "2026-10-07T12:00:00" }],
  });
  const respond = (request, body, status = 200) => request.pending.resolve({ ok: status < 400, status, json: async () => body });
  vm.runInContext(script, context);
  return { run, ready, activate, get, requests, summary, respond, windowEvents, context, clock };
}

test("logout clears health immediately and ignores delayed Garmin fetch even if revocation fails", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  const refresh = h.run("refreshGarmin(true)");
  const garmin = h.requests[0];
  const logout = h.run("logout()");
  assert.equal(garmin.options.signal.aborted, true);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-activities").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  assert.equal(h.get("#refresh-garmin").disabled, true);
  h.respond(garmin, h.summary(123));
  await refresh;
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  h.requests[1].pending.reject(new Error("Synthetic revocation failure"));
  await logout;
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
});

test("logout blocks delayed JSON body and late errors from changing cleared health view", async () => {
  for (const failure of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    const refresh = h.run("refreshGarmin(false)");
    const body = deferred();
    const bodyStarted = deferred();
    h.requests[0].pending.resolve({ ok: true, status: 200, json: () => { bodyStarted.resolve(); return body.promise; } });
    await bodyStarted.promise;
    const logout = h.run("logout()");
    if (failure) body.reject(new Error("Late synthetic parse failure"));
    else body.resolve(h.summary(234));
    await refresh;
    assert.equal(h.get("#garmin-metrics").children.length, 0);
    assert.equal(h.get("#garmin-state").textContent, EMPTY);
    h.respond(h.requests[1], {});
    await logout;
  }
});

test("new connect clears old health and ignores old response before identity lookup finishes", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const refresh = h.run("refreshGarmin(false)");
  const connect = h.run("connect()");
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
  assert.equal(h.run("state.healthAllowed"), false);
  h.respond(h.requests[0], h.summary(345));
  await refresh;
  await assert.rejects(connect, /No enrolled device key/);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
});

test("older refresh cannot replace latest result or its status", async () => {
  for (const failure of ["none", "transport", "expired-session"]) {
    const h = harness();
    await h.ready;
    h.activate();
    const older = h.run("refreshGarmin(false)");
    const latest = h.run("refreshGarmin(true)");
    assert.equal(h.requests[0].options.signal.aborted, true);
    h.respond(h.requests[1], h.summary(456));
    await latest;
    const label = h.get("#garmin-state").textContent;
    if (failure === "transport") h.requests[0].pending.reject(new Error("Late older failure"));
    else if (failure === "expired-session") h.respond(h.requests[0], {}, 401);
    else h.respond(h.requests[0], h.summary(999));
    await older;
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "456");
    assert.equal(h.get("#garmin-state").textContent, label);
    assert.equal(h.run("state.online"), true);
  }
});

test("active session rejection clears health rather than retaining stale private values", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  const refresh = h.run("refreshGarmin(true)");
  h.respond(h.requests[0], {}, 401);
  await refresh;
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  assert.equal(h.get("#garmin-state").textContent, EMPTY);
});

test("offline cancels pending refresh and keeps stale presentation; new session rejects old response", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const offlineRefresh = h.run("refreshGarmin(true)");
  h.context.navigator.onLine = false;
  h.windowEvents.offline();
  const stale = h.get("#garmin-state").textContent;
  h.respond(h.requests[0], h.summary(567));
  await offlineRefresh;
  assert.equal(h.get("#garmin-state").textContent, stale);
  assert.match(stale, /stale/);
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  h.context.navigator.onLine = true;
  h.activate("session:old");
  const old = h.run("refreshGarmin(false)");
  h.activate("session:new");
  h.respond(h.requests[1], h.summary(678));
  await old;
  assert.equal(h.get("#garmin-metrics").children.length, 0);
});

test("Garmin response is explicitly stale at five minutes and for invalid or future timestamps", async () => {
  for (const [age, timestamp, expectedStale] of [
    [299999, "2026-10-07T12:00:00Z", false],
    [300000, "2026-10-07T12:00:00Z", true],
    [600000, "2026-10-07T12:00:00Z", true],
    [0, "2026-10-07T12:00:01Z", true],
    [0, "invalid timestamp", true],
  ]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.clock.now += age;
    const refresh = h.run("refreshGarmin(true)");
    const summary = { ...h.summary(789), refreshed_at: timestamp };
    h.respond(h.requests[0], summary);
    await refresh;
    const label = h.get("#garmin-state").textContent;
    assert.equal(label.includes("Stale. Refresh Garmin"), expectedStale);
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "789");
    if (timestamp === "invalid timestamp") assert.match(label, /last checked Unknown/);
  }
});

test("failed Garmin refresh retains prior metrics with explicit stale warning", async () => {
  for (const failure of ["transport", "unavailable"]) {
    const h = harness();
    await h.ready;
    h.activate();
    const initial = h.run("refreshGarmin(false)");
    h.respond(h.requests[0], h.summary(890));
    await initial;
    assert.doesNotMatch(h.get("#garmin-state").textContent, /stale/i);
    const refresh = h.run("refreshGarmin(true)");
    if (failure === "transport") h.requests[1].pending.reject(new Error("Synthetic network failure"));
    else h.respond(h.requests[1], {}, 503);
    await refresh;
    assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "890");
    assert.match(h.get("#garmin-state").textContent, /Shown Garmin data may be stale\./);
    assert.equal(h.get("#garmin-activities").children.length, 1);
  }
});
