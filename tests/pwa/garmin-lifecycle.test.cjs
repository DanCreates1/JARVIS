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
    children: [], textContent: "", disabled: false, value: "", dataset: {}, classList: { add() {}, remove() {} },
    attributes: {}, scrollTop: 0, scrollHeight: 0, clientHeight: 0, hidden: false,
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    focus() { this.focused = true; },
    contains(node) { return this.children.includes(node); },
    listeners: {},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    querySelector(selector) { const id = selector.match(/data-request="([^"]+)"/)?.[1]; return this.children.find(item => item.dataset.request === id) || null; },
    addEventListener(name, callback) { (this.listeners[name] ||= []).push(callback); },
  };
}

function harness() {
  const nodes = new Map(), requests = [], windowEvents = {}, timers = [], storage = new Map();
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
    AbortController, DOMException, TextEncoder, URLSearchParams, Date: FakeDate, Promise, CSS: { escape: value => value },
    crypto: { randomUUID: () => "synthetic-request" },
    document: { querySelector: get, createElement: element, addEventListener: (name, callback) => { windowEvents[name] = callback; } },
    window: { location: { origin: "https://synthetic.test" }, addEventListener: (name, callback) => { windowEvents[name] = callback; } },
    navigator: { onLine: true },
    indexedDB: { open: () => storageRequest(database) },
    sessionStorage: { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) },
    caches: { keys: async () => [] },
    setTimeout: (callback, delay) => { const timer = { callback, delay, active: true }; timers.push(timer); return timer; },
    clearTimeout: timer => { if (timer) timer.active = false; },
    fetch: (url, options) => {
      const pending = deferred();
      requests.push({ url, options, pending });
      // Deliberately ignore abort: transport/body work can complete after cancellation.
      return pending.promise;
    },
  });
  const run = (code) => vm.runInContext(code, context);
  const ready = (async () => { for (let turn = 0; turn < 20; turn++) await Promise.resolve(); })();
  const activate = (session = "synthetic-session") => run(`state.csrf=${JSON.stringify(session)};state.hasIdentity=true;state.healthAllowed=true;setConnected(true);`);
  const summary = (steps) => ({
    date: "2026-10-07", refreshed_at: "2026-10-07T12:00:00Z", steps,
    resting_heart_rate: null, sleep_minutes: null, stress: null, body_battery: null,
    activities: [{ name: "Activity", type: "walking", started: "2026-10-07T12:00:00" }],
  });
  const respond = (request, body, status = 200) => request.pending.resolve({ ok: status < 400, status, json: async () => body });
  vm.runInContext(script, context);
  const setIdentity = (value) => { identity = value; };
  const waitForRequests = async (count) => {
    for (let turn = 0; turn < 50 && requests.length < count; turn++) await Promise.resolve();
    assert.equal(requests.length, count);
  };
  const runTimer = (predicate) => {
    const timer = timers.find(item => item.active && predicate(item.delay));
    assert.ok(timer, "Expected active timer");
    timer.active = false;
    timer.callback();
  };
  const fakeEnrollmentCrypto = () => {
    context.window.indexedDB = context.indexedDB;
    context.btoa = text => Buffer.from(text, "binary").toString("base64");
    context.crypto.subtle = {
      generateKey: async () => ({ privateKey: "synthetic-private-key", publicKey: "synthetic-public-key" }),
      exportKey: async () => new Uint8Array(32),
      sign: async () => new Uint8Array(64),
    };
  };
  return { run, ready, activate, get, requests, summary, respond, windowEvents, context, clock, setIdentity, waitForRequests, runTimer, storage, fakeEnrollmentCrypto };
}

test("offline logout erases local identity and displayed data while remote DELETE remains pending", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.activate();
  h.run("state.subscription='synthetic-subscription';state.conversation='synthetic-conversation';state.cursor=4;renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  for (const selector of ["#device-status", "#tasks", "#log"]) h.get(selector).append(element());
  h.get("#message").value = "Synthetic draft";
  h.get("#ticket").value = "Synthetic ticket";
  const logout = h.run("logout()");
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(h.run("state.subscription"), null);
  assert.equal(h.run("state.conversation"), null);
  assert.equal(h.run("state.cursor"), 0);
  for (const selector of ["#device-status", "#tasks", "#log", "#garmin-metrics", "#garmin-activities"]) assert.equal(h.get(selector).children.length, 0);
  assert.equal(h.get("#message").value, "");
  assert.equal(h.get("#ticket").value, "");
  assert.equal(h.get("#logout").disabled, true);
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].url, "/api/v1/sessions/current");
  assert.equal(h.requests[0].options.method, "DELETE");
  assert.equal(h.requests[0].options.credentials, "include");
  assert.equal(h.requests[0].options.headers["X-Jarvis-CSRF"], "synthetic-session");
  await logout;
  assert.equal(await h.run("loadIdentity()"), undefined);
  assert.match(h.get("#connection").textContent, /Logged out/);
  // An old revocation response cannot expire a later valid connection.
  h.activate("synthetic-new-session");
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:84,activities:[]})");
  h.respond(h.requests[0], {}, 401);
  await Promise.resolve();
  assert.equal(h.run("state.online"), true);
  assert.equal(h.run("state.healthAllowed"), true);
  assert.equal(h.get("#garmin-metrics").children[0].children[1].textContent, "84");
});

test("late status and task JSON cannot restore private views after logout", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.activate();
  const status = h.run("refreshStatus()"), tasks = h.run("refreshTasks()");
  const bodies = [deferred(), deferred()], started = [deferred(), deferred()];
  for (let index = 0; index < 2; index++) h.requests[index].pending.resolve({ ok: true, status: 200, json: () => { started[index].resolve(); return bodies[index].promise; } });
  await Promise.all(started.map(item => item.promise));
  await h.run("logout()");
  bodies[0].resolve({ device: { display_name: "Synthetic name", state: "active", key_version: 1 }, session: { id: "synthetic-old-session" } });
  bodies[1].resolve([{ id: "synthetic-old-task", status: "complete" }]);
  await Promise.all([status, tasks]);
  assert.equal(h.get("#device-status").children.length, 0);
  assert.equal(h.get("#tasks").children.length, 0);
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(await h.run("loadIdentity()"), undefined);
  h.respond(h.requests[2], {});
});

test("logout rejects a late session bootstrap response or JSON body", async () => {
  for (const phase of ["response", "body"]) {
    const h = harness();
    await h.ready;
    h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
    h.run("signedHeaders=async()=>({})");
    const connect = h.run("connect()");
    await h.waitForRequests(1);
    assert.equal(h.requests[0].url, "/api/v1/browser/sessions");
    const body = deferred(), started = deferred();
    if (phase === "body") {
      h.requests[0].pending.resolve({ ok: true, status: 201, json: () => { started.resolve(); return body.promise; } });
      await started.promise;
    }
    await h.run("logout()");
    const credential = { csrf_token: "synthetic-late-session" };
    if (phase === "response") h.respond(h.requests[0], credential, 201);
    else body.resolve(credential);
    await connect;
    await h.waitForRequests(2);
    assert.equal(h.requests[0].options.signal.aborted, phase === "response");
    assert.equal(h.requests[1].url, "/api/v1/sessions/current");
    assert.equal(h.requests[1].options.headers["X-Jarvis-CSRF"], "synthetic-late-session");
    assert.equal(h.run("state.csrf"), null);
    assert.equal(h.run("state.hasIdentity"), false);
    assert.equal(h.run("state.healthAllowed"), false);
    assert.equal(h.run("state.online"), false);
    assert.equal(h.get("#device-status").children.length, 0);
    assert.equal(await h.run("loadIdentity()"), undefined);
    h.respond(h.requests[1], {});
    await h.run("state.logoutPending");
  }
});

test("late subscription bootstrap cannot restore a logged-out session", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  await h.waitForRequests(1);
  h.respond(h.requests[0], { csrf_token: "synthetic-session" }, 201);
  await h.waitForRequests(2);
  await h.run("logout()");
  h.respond(h.requests[1], { id: "synthetic-late-subscription", next_cursor: 8 });
  await connect;
  assert.equal(h.run("state.subscription"), null);
  assert.equal(h.run("state.cursor"), 0);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.requests.length, 3);
  h.respond(h.requests[2], {});
});

test("startup identity lookup cannot restore identity after logout", async () => {
  const h = harness();
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  await h.run("logout()");
  await h.ready;
  assert.equal(h.run("state.hasIdentity"), false);
  assert.equal(h.get("#logout").disabled, true);
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("replacement enrollment waits for old remote logout response before creating a key", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  await h.run("logout()");
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-enrollment", challenge: "synthetic-challenge", approved_scopes: ["client.health.read"] });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  assert.equal(await h.run("loadIdentity()"), undefined);
  // Browser applies old Set-Cookie/Clear-Site-Data before replacement may begin.
  h.respond(h.requests[0], { revoked: true });
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/enrollments/complete");
  assert.equal(h.requests[0].options.signal.aborted, false);
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { id: "synthetic-new-device", key_version: 1 }, 201);
  await enroll;
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("remote logout aborts after five seconds and releases replacement bootstrap", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  await h.run("logout()");
  h.setIdentity({ deviceId: "synthetic-recovery", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  h.runTimer(delay => delay === 5000);
  assert.equal(h.requests[0].options.signal.aborted, true);
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/browser/sessions");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { csrf_token: "synthetic-recovery-session" }, 201);
  await connect;
  h.respond(h.requests[0], { revoked: true });
  assert.equal(h.run("state.csrf"), null);
});

test("replacement waits for stale bootstrap cookie cleanup as well as local logout", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-device", healthAllowed: true });
  h.run("signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  await h.waitForRequests(1);
  const body = deferred(), started = deferred();
  h.requests[0].pending.resolve({ ok: true, status: 201, json: () => { started.resolve(); return body.promise; } });
  await started.promise;
  await h.run("logout()");
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-recovery-enrollment", challenge: "synthetic-recovery-challenge" });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  body.resolve({ csrf_token: "synthetic-stale-bootstrap-session" });
  await connect;
  await h.waitForRequests(2);
  assert.equal(h.requests[1].options.headers["X-Jarvis-CSRF"], "synthetic-stale-bootstrap-session");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 2);
  h.respond(h.requests[1], { revoked: true });
  await h.waitForRequests(3);
  assert.equal(h.requests[2].url, "/api/v1/enrollments/complete");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[2], { id: "synthetic-recovery-device", key_version: 1 }, 201);
  await enroll;
  assert.equal(await h.run("loadIdentity()"), undefined);
});

test("replacement waits for local worker cleanup even when remote logout already succeeded", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const cleanup = deferred(), started = deferred();
  h.context.navigator.serviceWorker = { getRegistrations: async () => [{ active: { postMessage() {} }, unregister: () => { started.resolve(); return cleanup.promise; } }] };
  const logout = h.run("logout()");
  await started.promise;
  h.respond(h.requests[0], { revoked: true });
  h.fakeEnrollmentCrypto();
  h.get("#ticket").value = JSON.stringify({ id: "synthetic-enrollment", challenge: "synthetic-challenge" });
  const enroll = h.run("enroll()");
  for (let turn = 0; turn < 10; turn++) await Promise.resolve();
  assert.equal(h.requests.length, 1);
  cleanup.resolve(true);
  await logout;
  await h.waitForRequests(2);
  assert.equal(h.requests[1].url, "/api/v1/enrollments/complete");
  h.run("state.sessionGeneration+=1");
  h.respond(h.requests[1], { id: "synthetic-new-device", key_version: 1 }, 201);
  await enroll;
});

test("logout clears identity after an already-started local identity write settles", async () => {
  const h = harness();
  await h.ready;
  const write = deferred();
  h.context.syntheticWrite = write.promise;
  h.run("state.identityWrite=syntheticWrite");
  const logout = h.run("logout()");
  h.setIdentity({ deviceId: "synthetic-late-write", healthAllowed: true });
  write.resolve();
  await logout;
  assert.equal(await h.run("loadIdentity()"), undefined);
  assert.equal(h.run("state.hasIdentity"), false);
});

test("late chat response body or error cannot restore conversation after logout", async () => {
  for (const failure of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.run("state.subscription='synthetic-subscription'");
    h.get("#message").value = "Synthetic public prompt";
    const send = h.run("sendMessage({preventDefault(){}})");
    const body = deferred(), started = deferred();
    if (!failure) {
      h.requests[0].pending.resolve({ ok: true, status: 200, json: () => { started.resolve(); return body.promise; } });
      await started.promise;
    }
    await h.run("logout()");
    if (failure) h.requests[0].pending.reject(new Error("Synthetic delayed chat error"));
    else body.resolve({ conversation_id: "synthetic-late-conversation", reply: "Synthetic delayed reply" });
    await send;
    assert.equal(h.get("#log").children.length, 0);
    assert.equal(h.run("state.conversation"), null);
    h.respond(h.requests[1], { revoked: true });
  }
});

test("late stream body cannot restore cursor, conversation or log after logout", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  h.run("state.subscription='synthetic-subscription'");
  const stream = h.run("streamLoop()"), body = deferred(), started = deferred();
  h.requests[0].pending.resolve({ ok: true, status: 200, text: () => { started.resolve(); return body.promise; } });
  await started.promise;
  await h.run("logout()");
  body.resolve('data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"synthetic-request","payload":{"content_delta":"Synthetic private reply"}}\n\ndata: {"cursor":2,"topic":"chat","event_type":"chat.completed","payload":{"conversation_id":"synthetic-old-conversation"}}\n\n');
  await stream;
  assert.equal(h.run("state.cursor"), 0);
  assert.equal(h.run("state.conversation"), null);
  assert.equal(h.get("#log").children.length, 0);
  assert.equal(h.run("state.online"), false);
  h.respond(h.requests[1], { revoked: true });
});

test("stream reconnect backoff cannot reconnect a logged-out or replaced session", async () => {
  for (const replacement of [false, true]) {
    const h = harness();
    await h.ready;
    h.activate();
    h.run("state.subscription='synthetic-subscription'");
    const stream = h.run("streamLoop()");
    h.requests[0].pending.reject(new Error("Synthetic network loss"));
    for (let turn = 0; turn < 10; turn++) await Promise.resolve();
    assert.equal(h.run("state.online"), false);
    await h.run("logout()");
    if (replacement) h.activate("synthetic-replacement-session");
    const label = h.get("#connection").textContent;
    // Logout cancels and wakes the backoff instead of waiting for its old timer.
    await stream;
    assert.equal(h.get("#connection").textContent, label);
    assert.equal(h.run("state.online"), replacement);
    assert.equal(h.get("#message").disabled, !replacement);
    assert.equal(h.requests.length, 2);
    h.respond(h.requests[1], { revoked: true });
  }
});

test("late notification permission cannot restore notification flag after logout", async () => {
  const h = harness();
  await h.ready;
  h.activate();
  const permission = deferred();
  h.context.Notification = h.context.window.Notification = { requestPermission: () => permission.promise };
  const notifications = h.run("enableNotifications()");
  await h.run("logout()");
  permission.resolve("granted");
  await notifications;
  assert.equal(h.storage.has("jarvis-notifications"), false);
  h.respond(h.requests[0], { revoked: true });
});

test("rejected enrollment preserves existing stream generation and connection", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-existing-device", healthAllowed: true });
  h.activate();
  const generation = h.run("state.sessionGeneration");
  await assert.rejects(h.run("enroll()"), /Log out and erase/);
  assert.equal(h.run("state.sessionGeneration"), generation);
  assert.equal(h.run("state.online"), true);
  assert.equal(h.run("state.healthAllowed"), true);
  assert.equal(h.requests.length, 0);
});

test("failed reconnect aborts old stream and remains offline with health cleared", async () => {
  const h = harness();
  await h.ready;
  h.setIdentity({ deviceId: "synthetic-existing-device", healthAllowed: true });
  h.activate("synthetic-existing-session");
  h.context.syntheticStreamController = new AbortController();
  h.run("state.streamAbort=syntheticStreamController;renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]});signedHeaders=async()=>({})");
  const connect = h.run("connect()");
  assert.equal(h.context.syntheticStreamController.signal.aborted, true);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.get("#connection").textContent, "Connecting");
  assert.equal(h.get("#garmin-metrics").children.length, 0);
  await h.waitForRequests(1);
  h.respond(h.requests[0], {}, 403);
  await assert.rejects(connect, /Session bootstrap rejected \(403\)/);
  assert.equal(h.run("state.csrf"), null);
  assert.equal(h.run("state.online"), false);
  assert.equal(h.run("state.healthAllowed"), false);
  assert.equal(h.get("#connection").textContent, "Connection failed");
  assert.equal(h.get("#refresh-garmin").disabled, true);
  assert.equal(h.get("#message").disabled, true);
});

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

async function flush() { for (let turn = 0; turn < 40; turn++) await Promise.resolve(); }
function streamSession(h) {
  h.activate();
  h.run("state.healthAllowed=false;state.subscription='synthetic-subscription';setConnected(false,'Checking live connection')");
}
function respondStream(h, request, text = ": keepalive\n\n") {
  request.pending.resolve({ ok: true, status: 200, text: async () => text });
}

test("offline and repeated online events retain one owner and require a successful current poll", async () => {
  for (const outcome of ["success", "rejection", "stalled-body"]) {
    const h = harness(); await h.ready; streamSession(h);
    h.run("startStreamOwnership()"); await h.waitForRequests(1);
    const owner = h.run("state.streamOwner"), body = deferred();
    if (outcome === "stalled-body") h.requests[0].pending.resolve({ ok: true, status: 200, text: () => body.promise });
    await flush(); h.context.navigator.onLine = false; h.windowEvents.offline(); await flush();
    assert.equal(h.requests[0].options.signal.aborted, true);
    assert.equal(h.get("#send").disabled, true);
    if (outcome === "success") respondStream(h, h.requests[0]);
    if (outcome === "rejection") h.requests[0].pending.reject(new Error("Synthetic offline rejection"));
    if (outcome === "stalled-body") body.resolve('data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"old","payload":{"content_delta":"Old reply"}}\n\n');
    await flush(); assert.equal(h.run("state.cursor"), 0);
    h.context.navigator.onLine = true; h.windowEvents.online(); h.windowEvents.online();
    assert.equal(h.get("#send").disabled, true); assert.equal(h.run("state.streamOwner"), owner);
    await h.waitForRequests(2); assert.equal(h.get("#send").disabled, true);
    respondStream(h, h.requests[1], 'data: {"cursor":1,"topic":"chat","event_type":"chat.delta","request_id":"current","payload":{"content_delta":"Recovered reply"}}\n\n');
    await h.waitForRequests(3); assert.equal(h.run("state.online"), true);
    assert.equal(h.get("#send").disabled, false); assert.equal(h.run("state.cursor"), 1);
    assert.match(h.get("#log").children[0].textContent, /Recovered reply/);
    assert.equal(h.requests.filter(r => !r.options.signal.aborted && r === h.requests[2]).length, 1);
    h.run("stopStream()"); await flush();
  }
});

test("401 and stream 403 preserve key but online cannot reactivate rejected credentials", async () => {
  for (const status of [401, 403]) {
    const h = harness(); await h.ready; streamSession(h);
    h.setIdentity({ deviceId: "synthetic-device" }); h.run("startStreamOwnership()"); await h.waitForRequests(1);
    h.respond(h.requests[0], {}, status); await flush();
    assert.equal(h.run("state.csrf"), null); assert.equal(h.run("state.subscription"), null);
    assert.equal(h.run("state.hasIdentity"), true); assert.ok(await h.run("loadIdentity()"));
    h.context.navigator.onLine = false; h.windowEvents.offline(); h.context.navigator.onLine = true; h.windowEvents.online();
    await flush(); assert.equal(h.requests.length, 1); assert.equal(h.get("#send").disabled, true);
    assert.match(h.get("#access-status").textContent, /Connect existing device/);
  }
});

test("stream deadline and reconnect backoff keep Send disabled until Core responds", async () => {
  for (const phase of ["headers", "body"]) {
    const h = harness(); await h.ready; streamSession(h); h.run("startStreamOwnership()"); await h.waitForRequests(1);
    const body = deferred();
    if (phase === "body") { h.requests[0].pending.resolve({ ok: true, status: 200, text: () => body.promise }); await flush(); }
    h.runTimer(delay => delay === 30000); await flush();
    assert.equal(h.requests[0].options.signal.aborted, true); assert.equal(h.get("#send").disabled, true);
    h.runTimer(delay => delay >= 500 && delay < 3500); await h.waitForRequests(2);
    assert.equal(h.get("#send").disabled, true); respondStream(h, h.requests[1]); await h.waitForRequests(3);
    assert.equal(h.get("#send").disabled, false);
    if (phase === "body") body.resolve(": keepalive\n\n"); else respondStream(h, h.requests[0]);
    h.run("stopStream()"); await flush();
  }
});

test("Core subscription reset requires a new authenticated event poll", async () => {
  const h = harness(); await h.ready; streamSession(h); h.run("startStreamOwnership()"); await h.waitForRequests(1);
  h.respond(h.requests[0], {}, 404); await h.waitForRequests(2);
  assert.equal(h.requests[1].options.method, "DELETE"); h.respond(h.requests[1], {}); await h.waitForRequests(3);
  h.respond(h.requests[2], { id: "synthetic-restarted-subscription", next_cursor: 8 }); await h.waitForRequests(4);
  assert.equal(h.get("#send").disabled, true); assert.match(h.requests[3].url, /after=8/);
  respondStream(h, h.requests[3]); await h.waitForRequests(5); assert.equal(h.get("#send").disabled, false);
  h.run("stopStream()"); await flush();
});

test("queued Web Lock and repeated startup never create another active owner", async () => {
  const h = harness(); await h.ready; streamSession(h);
  const lock = deferred(); let callbacks = 0;
  h.context.navigator.locks = { request: async (name, options, callback) => { callbacks++; await lock.promise; return callback({ name }); } };
  h.run("startStreamOwnership();startStreamOwnership()"); assert.equal(callbacks, 1); assert.equal(h.requests.length, 0);
  assert.equal(h.get("#send").disabled, true); lock.resolve(); await h.waitForRequests(1);
  respondStream(h, h.requests[0]); await h.waitForRequests(2); assert.equal(h.get("#send").disabled, false);
  h.run("stopStream()"); await flush();
});

test("partial connect failure and body deadline release controls without false readiness", async () => {
  for (const phase of ["subscription", "status", "tasks", "stalled-body"]) {
    const h = harness(); await h.ready;
    h.setIdentity({ deviceId: "synthetic-device", healthAllowed: false }); h.run("signedHeaders=async()=>({})");
    const connection = h.run("connect()"), result = assert.rejects(connection);
    h.run("connect()"); await h.waitForRequests(1); assert.equal(h.get("#connect").disabled, true);
    h.respond(h.requests[0], { csrf_token: "synthetic-session" }, 201); await h.waitForRequests(2);
    if (phase === "subscription") h.respond(h.requests[1], {}, 503);
    else {
      h.respond(h.requests[1], { id: "synthetic-subscription", next_cursor: 0 }); await h.waitForRequests(3);
      if (phase === "status") h.respond(h.requests[2], {}, 503);
      else if (phase === "stalled-body") {
        h.requests[2].pending.resolve({ ok: true, status: 200, json: () => deferred().promise }); await flush(); h.runTimer(delay => delay === 10000);
      } else {
        h.respond(h.requests[2], { device: { display_name: "Synthetic", state: "active", key_version: 1 }, session: { id: "synthetic-session" } });
        await h.waitForRequests(4); h.respond(h.requests[3], {}, 503);
      }
    }
    await result; assert.equal(h.run("state.csrf"), null); assert.equal(h.get("#send").disabled, true);
    assert.equal(h.get("#connect").disabled, false); assert.equal(h.get("#enroll").disabled, true);
    assert.match(h.get("#access-status").textContent, /Retry Connect existing device/);
  }
});

test("history updates retain scroll position and selection until Jump to latest", async () => {
  const h = harness(); await h.ready; const log = h.get("#log");
  log.scrollHeight = 1000; log.clientHeight = 200; log.scrollTop = 120;
  h.run("row('jarvis','Synthetic delta','reply')"); assert.equal(log.scrollTop, 120); assert.equal(h.get("#jump-latest").hidden, false);
  log.scrollTop = 800;
  h.context.document.getSelection = () => ({ isCollapsed: false, anchorNode: log.children[0] });
  h.run("row('jarvis','Selected synthetic reply','reply')"); assert.equal(log.scrollTop, 800); assert.equal(h.get("#jump-latest").hidden, false);
  h.get("#jump-latest").listeners.click[0](); assert.equal(log.scrollTop, 1000); assert.equal(log.focused, true);
  assert.equal(h.get("#jump-latest").hidden, true);
});

test("completed answer announced once; delta, failed and cancelled behavior explicit", async () => {
  const h = harness(); await h.ready; let cursor = 0;
  const event = (type, payload = {}, id = "synthetic-reply") => h.run(`processEvent(${JSON.stringify({ cursor: ++cursor, topic: "chat", event_type: type, request_id: id, payload })})`);
  event("chat.started"); assert.equal(h.get("#chat").attributes["aria-busy"], "true");
  const start = h.get("#chat-status").textContent;
  event("chat.delta", { content_delta: "Synthetic " }); event("chat.frame", { type: "assistant_delta", content_delta: "answer" });
  assert.equal(h.get("#chat-status").textContent, start);
  event("chat.completed", { conversation_id: "synthetic-conversation" });
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Synthetic answer");
  assert.equal(h.get("#chat").attributes["aria-busy"], "false");
  h.get("#chat-status").textContent = "Sentinel"; event("chat.completed"); assert.equal(h.get("#chat-status").textContent, "Sentinel");
  event("chat.failed", {}, "failed-reply"); assert.equal(h.get("#chat-status").textContent, "Request failed safely.");
  event("chat.cancelled", {}, "cancelled-reply"); assert.equal(h.get("#chat-status").textContent, "Request cancelled.");
});

test("failed send keeps draft and repeated submit cannot duplicate in-flight request", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft";
  const send = h.run("sendMessage({preventDefault(){}})"); h.run("sendMessage({preventDefault(){}})");
  assert.equal(h.requests.length, 1); assert.equal(h.get("#send").disabled, true);
  h.requests[0].pending.reject(new Error("Synthetic failed send")); await send;
  assert.equal(h.get("#message").value, "Synthetic draft"); assert.equal(h.get("#send").disabled, false);
  assert.match(h.get("#chat-status").textContent, /outcome unconfirmed.*Draft kept/);
});

test("Garmin ages on screen and retains fetched-at context while loading without new reads", async () => {
  const h = harness(); await h.ready; h.activate();
  const initial = h.run("refreshGarmin(false)"); h.respond(h.requests[0], h.summary(42)); await initial;
  const refreshed = h.get("#garmin-state").textContent; h.clock.now += 299999; h.run("renderGarminStatus()");
  assert.equal(h.get("#garmin-state").textContent, refreshed); h.clock.now += 1; h.runTimer(delay => delay === 1);
  assert.match(h.get("#garmin-state").textContent, /Stale/); assert.equal(h.requests.length, 1);
  const loading = h.run("refreshGarmin(true)");
  assert.match(h.get("#garmin-state").textContent, /Checking Garmin.*last checked.*Stale/);
  assert.equal(h.get("#refresh-garmin").disabled, true); h.requests[1].pending.reject(new Error("Synthetic failure")); await loading;
  h.clock.now += 300000; h.windowEvents.visibilitychange(); assert.match(h.get("#garmin-state").textContent, /Stale/);
  await h.run("logout()"); h.windowEvents.pageshow(); h.windowEvents.visibilitychange();
  assert.equal(h.get("#garmin-state").textContent, EMPTY); assert.equal(h.run("state.healthSnapshot"), null);
  h.respond(h.requests[2], {});
});

test("logout focus and durable result distinguish remote success, failure and timeout", async () => {
  for (const result of [200, 503, "timeout"]) {
    const h = harness(); await h.ready; h.activate(); await h.run("logout()");
    assert.equal(h.get("#ticket").focused, true); assert.match(h.get("#access-status").textContent, /Server sign-out pending/);
    if (result === "timeout") h.runTimer(delay => delay === 5000); else h.respond(h.requests[0], {}, result);
    await flush(); assert.match(h.get("#access-status").textContent, result === 200 ? /Server sign-out confirmed/ : /Server sign-out unconfirmed/);
    assert.match(h.get("#access-status").textContent, /Device enrollment remains on Core/);
    assert.equal(h.get("#notice").textContent, h.get("#access-status").textContent);
  }
});

test("malformed ticket produces persistent associated recovery and no network call", async () => {
  const h = harness(); await h.ready; h.fakeEnrollmentCrypto(); h.get("#ticket").value = "{";
  await assert.rejects(h.run("enroll()"), /complete JSON/);
  assert.equal(h.requests.length, 0); assert.equal(h.get("#ticket").attributes["aria-invalid"], "true");
  assert.match(h.get("#ticket-error").textContent, /approved, unexpired, unused ticket/); assert.equal(h.get("#enroll").disabled, false);
});

test("completed HTTP reply survives later stream frames without duplicate speech", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic prompt"; const send = h.run("sendMessage({preventDefault(){}})");
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.started',request_id:'request:synthetic-request',payload:{}})");
  h.respond(h.requests[0], { reply: "Full synthetic answer", conversation_id: "synthetic-conversation" }); await send;
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Full synthetic answer");
  const announcement = h.get("#chat-status").textContent;
  h.run("processEvent({cursor:2,topic:'chat',event_type:'chat.started',request_id:'request:synthetic-request',payload:{}});processEvent({cursor:3,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Repeated answer'}});processEvent({cursor:4,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Full synthetic answer");
  assert.equal(h.get("#chat-status").textContent, announcement); assert.equal(h.run("state.cursor"), 4);
  assert.equal(h.get("#chat").attributes["aria-busy"], "false");
});

test("logout cancels a queued owner; later lock grant cannot start a stale poll", async () => {
  const h = harness(); await h.ready; streamSession(h); const lock = deferred(); let signal;
  h.context.navigator.locks = { request: async (name, options, callback) => { signal = options.signal; await lock.promise; return callback({ name }); } };
  h.run("startStreamOwnership()"); await h.run("logout()"); assert.equal(signal.aborted, true);
  lock.resolve(); await flush(); assert.equal(h.requests.length, 1); assert.equal(h.run("state.online"), false);
  h.respond(h.requests[0], {});
});

test("browser resume marks old health stale without another Garmin request", async () => {
  const h = harness(); await h.ready; h.activate();
  h.run("renderGarmin({date:'2026-10-07',refreshed_at:'2026-10-07T12:00:00Z',steps:42,activities:[]})");
  h.clock.now += 300001; h.windowEvents.pageshow(); h.windowEvents.visibilitychange();
  assert.match(h.get("#garmin-state").textContent, /Stale/); assert.equal(h.requests.length, 0);
});

test("unconfirmed POST outcome cannot suppress later authoritative streamed reply", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft"; const send = h.run("sendMessage({preventDefault(){}})");
  h.requests[0].pending.reject(new Error("Synthetic response loss")); await send;
  assert.equal(h.run("state.chatAnnounced.has('request:synthetic-request')"), false);
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Recovered authoritative answer'}});processEvent({cursor:2,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  assert.equal(h.get("#log").children[1].textContent, "JARVIS: Recovered authoritative answer");
  assert.equal(h.get("#log").children[1].className, "entry jarvis");
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Recovered authoritative answer");
  assert.equal(h.get("#message").value, "");
});

test("lost POST response after streamed completion preserves known answer and clears submitted draft", async () => {
  const h = harness(); await h.ready; h.activate(); h.run("state.subscription='synthetic-subscription'");
  h.get("#message").value = "Synthetic draft"; const send = h.run("sendMessage({preventDefault(){}})");
  h.run("processEvent({cursor:1,topic:'chat',event_type:'chat.delta',request_id:'request:synthetic-request',payload:{content_delta:'Known answer'}});processEvent({cursor:2,topic:'chat',event_type:'chat.completed',request_id:'request:synthetic-request',payload:{}})");
  h.requests[0].pending.reject(new Error("Synthetic lost acknowledgement")); await send;
  assert.equal(h.get("#message").value, ""); assert.equal(h.get("#log").children[1].textContent, "JARVIS: Known answer");
  assert.equal(h.get("#chat-status").textContent, "Reply complete. JARVIS: Known answer");
});

test("Garmin deadline bounds stalled headers/body and releases accessible loading state", async () => {
  for (const phase of ["headers", "body"]) {
    const h = harness(); await h.ready; h.activate(); const refresh = h.run("refreshGarmin(true)");
    if (phase === "body") { h.requests[0].pending.resolve({ ok: true, status: 200, json: () => deferred().promise }); await flush(); }
    assert.equal(h.get("#garmin").attributes["aria-busy"], "true"); assert.equal(h.get("#refresh-garmin").disabled, true);
    h.runTimer(delay => delay === 95000); await refresh;
    assert.equal(h.requests[0].options.signal.aborted, true); assert.equal(h.get("#refresh-garmin").disabled, false);
    assert.equal(h.get("#garmin").attributes["aria-busy"], "false"); assert.match(h.get("#garmin-state").textContent, /Garmin check failed/);
  }
});

test("steady keepalive polls do not repeatedly mutate polite connection statuses", async () => {
  const h = harness(); await h.ready; streamSession(h); const writes = new Map();
  for (const selector of ["#connection", "#access-status"]) {
    const node = h.get(selector); let value = node.textContent; writes.set(selector, 0);
    Object.defineProperty(node, "textContent", { get: () => value, set: next => { value = next; writes.set(selector, writes.get(selector) + 1); } });
  }
  h.run("startStreamOwnership()"); await h.waitForRequests(1); respondStream(h, h.requests[0]); await h.waitForRequests(2);
  respondStream(h, h.requests[1]); await h.waitForRequests(3); respondStream(h, h.requests[2]); await h.waitForRequests(4);
  assert.equal(writes.get("#connection"), 1); assert.equal(writes.get("#access-status"), 1);
  h.run("stopStream()"); await flush();
});
