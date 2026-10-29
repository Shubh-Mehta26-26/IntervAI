import test from "node:test";
import assert from "node:assert/strict";
import { AvatarAudio, mouthFromSamples, TranscriptCountdown } from "../src/lib/avatar-audio.mjs";

test("mouth follows sound energy and closes immediately during silence", () => {
  assert.equal(mouthFromSamples(new Float32Array(512), .8), 0);
  assert.equal(mouthFromSamples(new Float32Array(512).fill(.005)), 0);
  const soft = mouthFromSamples(new Float32Array(512).fill(.03));
  const loud = mouthFromSamples(new Float32Array(512).fill(.2));
  assert.ok(soft > 0 && loud > soft && loud <= 1);
  assert.equal(mouthFromSamples(new Float32Array()), 0);
});

test("playback analyser remains silent when stopped, muted, suspended, or buffering", async () => {
  const calls = [];
  class Context {
    state = "running";
    destination = {};
    createAnalyser() { return { fftSize: 512, connect: () => calls.push("output"), disconnect: () => calls.push("analyser disconnected"), getFloatTimeDomainData: buffer => buffer.fill(.1) }; }
    createMediaElementSource() { calls.push("source"); return { connect: () => calls.push("input"), disconnect: () => calls.push("source disconnected") }; }
    async resume() { this.state = "running"; }
    async close() { calls.push("closed"); this.state = "closed"; }
  }
  const element = { paused: false, ended: false, muted: false, volume: 1, readyState: 4, pause() { this.paused = true; } };
  const graph = new AvatarAudio(element, Context);
  assert.ok(graph.sample() > 0);
  for (const [key, value] of [["paused", true], ["ended", true], ["muted", true], ["volume", 0], ["readyState", 2]]) {
    const original = element[key]; element[key] = value;
    assert.equal(graph.sample(), 0, key); element[key] = original;
  }
  graph.context.state = "suspended";
  assert.equal(graph.sample(), 0);
  await graph.resume(); assert.ok(graph.sample() > 0);
  await graph.dispose(); assert.equal(element.paused, true);
  assert.deepEqual(calls, ["source", "input", "output", "source disconnected", "analyser disconnected", "closed"]);
});

function countdownHarness() {
  let callback, submitted = 0, allowed = true;
  const ticks = [];
  const countdown = new TranscriptCountdown({
    schedule: fn => { callback = fn; return 1; }, unschedule: () => {},
    tick: n => ticks.push(n), submit: () => submitted++, canSubmit: () => allowed,
  });
  return { countdown, ticks, advance: () => callback(), submitted: () => submitted, stop: () => { allowed = false; } };
}

test("hands-free submits exactly once after the full review window", () => {
  const session = countdownHarness();
  for (let i = 0; i < 3; i++) session.advance();
  assert.equal(session.submitted(), 0);
  session.advance(); session.advance();
  assert.equal(session.submitted(), 1);
  assert.deepEqual(session.ticks, [4, 3, 2, 1, 0]);
});

test("Stop, editing, unmount, and a late timer callback cannot submit a transcript", () => {
  for (const cancel of [s => s.countdown.cancel(), s => s.stop()]) {
    const session = countdownHarness(); session.advance(); cancel(session);
    for (let i = 0; i < 6; i++) session.advance();
    assert.equal(session.submitted(), 0);
  }
});
