import test from 'node:test';
import assert from 'node:assert/strict';
import { CameraLease, SampleGate, cameraError } from '../src/lib/vision-camera.mjs';

test('camera requests video only and releases every track', async () => {
  let stopped = 0, constraints;
  const stream = { getTracks: () => [{ stop: () => stopped++ }] };
  const lease = new CameraLease();
  assert.equal(await lease.start({ getUserMedia: async value => { constraints = value; return stream; } }), stream);
  assert.equal(constraints.audio, false);
  await assert.rejects(lease.start({}), /already/);
  lease.stop(); assert.equal(stopped, 1); assert.equal(lease.stream, null);
});

test('stop during pending permission releases late stream without starting capture', async () => {
  let resolve, stopped = 0;
  const lease = new CameraLease();
  const request = lease.start({ getUserMedia: () => new Promise(done => { resolve = done; }) });
  lease.stop(); resolve({ getTracks: () => [{ stop: () => stopped++ }] });
  assert.equal(await request, null); assert.equal(stopped, 1);
});

test('permission rejection clears pending lease and has clear optional fallback', async () => {
  const lease = new CameraLease();
  await assert.rejects(lease.start({ getUserMedia: async () => { throw { name: 'NotAllowedError' }; } }));
  assert.equal(lease.pending, false);
  assert.match(cameraError({ name: 'NotAllowedError' }), /denied or revoked/);
  assert.match(cameraError({ name: 'NotFoundError' }), /No camera/);
  assert.match(cameraError({ name: 'NotReadableError' }), /already in use/);
});

test('slow inference drops samples without building a backlog', async () => {
  const gate = new SampleGate(); let resolve, calls = 0;
  const first = gate.run(async sequence => { assert.equal(sequence, 0); calls++; await new Promise(done => { resolve = done; }); });
  for (let n = 0; n < 100; n++) assert.equal(await gate.run(async () => calls++), false);
  resolve(); assert.equal(await first, true); assert.equal(calls, 1);
  await gate.run(async sequence => assert.equal(sequence, 1));
});

test('failed sampling releases gate for a later attempt', async () => {
  const gate = new SampleGate();
  await assert.rejects(gate.run(async () => { throw new Error('network'); }));
  assert.equal(gate.busy, false); assert.equal(await gate.run(async () => {}), true);
});
