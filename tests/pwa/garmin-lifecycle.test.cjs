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
    listeners: {},
    append(...items) { this.children.push(...items); },
    replaceChildren(...items) { this.children = [...items]; },
    querySelector() { return null; },
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
    document: { querySelector: get, createElement: element },
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
  const ready = Promise.resolve().then(() => Promise.resolve());
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
    h.runTimer(delay => delay < 3500);
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
  assert.equal(h.run("state.csrf"), "synthetic-existing-session");
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
