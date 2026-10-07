import test from "node:test";
import assert from "node:assert/strict";
import { ActivityDetector, CaptureLease, encodeWav } from "../src/lib/voice-signal.mjs";

test("silence alone cannot complete a speech turn before its maximum", () => {
  const vad = new ActivityDetector();
  for (let i = 0; i < 100; i++) assert.equal(vad.push(new Float32Array(320), 16000).stop, false);
});

test("microphone lease forbids idle capture, duplicate start, and stops streams", async () => {
  let stops = 0; const stream = { getTracks: () => [{ stop: () => stops++ }] }; const capture = new CaptureLease();
  await assert.rejects(() => capture.acquire(async () => stream, () => false), /not listening/);
  assert.equal(await capture.acquire(async () => stream, () => true), stream);
  await assert.rejects(() => capture.acquire(async () => stream, () => true), /already started/);
  capture.release(); assert.equal(stops, 1); capture.release(); assert.equal(stops, 1);
});
test("permission denied and cancellation during permission cleanly release capture", async () => {
  const capture = new CaptureLease();
  await assert.rejects(() => capture.acquire(async () => { throw new Error("NotAllowedError"); }, () => true), /NotAllowedError/);
  let resolve; let stops = 0;
  const request = capture.acquire(() => new Promise(done => { resolve = done; }), () => true);
  capture.release(); resolve({ getTracks: () => [{ stop: () => stops++ }] });
  assert.equal(await request, undefined); assert.equal(stops, 1);
});
test("mock microphone signal flows through VAD into a bounded WAV upload", async () => {
  const capture = new CaptureLease(); let listening = true; let stopped = false;
  await capture.acquire(async () => ({ getTracks: () => [{ stop: () => { stopped = true; } }] }), () => listening);
  const vad = new ActivityDetector({ min_speech_seconds: .1, silence_seconds: .1 }); const frames = [];
  let value;
  for (let i = 0; i < 15; i++) { const frame = new Float32Array(320).fill(i < 8 ? .08 : 0); frames.push(frame); value = vad.push(frame, 16000); }
  assert.equal(value.stop, true); assert.equal(value.hasSpeech, true);
  const upload = encodeWav(frames, 16000); assert.equal(upload.type, "audio/wav");
  listening = false; capture.release(); assert.equal(stopped, true);
});
test("speech followed by configured silence ends the turn", () => {
  const vad = new ActivityDetector({ min_speech_seconds: .4, silence_seconds: .5 });
  for (let i = 0; i < 30; i++) assert.equal(vad.push(new Float32Array(320).fill(.1), 16000).stop, false);
  let value; for (let i = 0; i < 26; i++) value = vad.push(new Float32Array(320), 16000);
  assert.equal(value.stop, true); assert.equal(value.hasSpeech, true);
});
test("short noise does not end a turn and maximum duration bounds silence", () => {
  const vad = new ActivityDetector({ max_seconds: 1 });
  vad.push(new Float32Array(320).fill(.1), 16000);
  let value; for (let i = 0; i < 50; i++) value = vad.push(new Float32Array(320), 16000);
  assert.equal(value.stop, true); assert.equal(value.hasSpeech, false);
});
test("browser PCM transport is mono 16k WAV with preserved signal", async () => {
  const file = encodeWav([new Float32Array(4800).fill(.25)], 48000);
  const data = await file.arrayBuffer(); const view = new DataView(data);
  assert.equal(data.byteLength, 3244); assert.equal(view.getUint32(24, true), 16000);
  assert.equal(view.getUint16(22, true), 1); assert.equal(view.getInt16(44, true), 8191);
});

test("a worklet block crossing the maximum cannot exceed the audio upload duration", async () => {
  const file = encodeWav([new Float32Array(48000 + 128)], 48000, 1);
  const view = new DataView(await file.arrayBuffer());
  assert.equal(view.getUint32(40, true) / 2 / view.getUint32(24, true), 1);
});
