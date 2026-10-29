// Signal-based VAD. No transcript or semantic inference is made from amplitude.
export class ActivityDetector {
  constructor({ min_speech_seconds = .4, silence_seconds = 3, max_seconds = 180, auto_stop = true } = {}) {
    this.min = min_speech_seconds; this.silence = silence_seconds; this.max = max_seconds;
    this.autoStop = auto_stop;
    this.total = 0; this.speech = 0; this.quiet = 0; this.noise = .003;
  }
  push(samples, rate) {
    const seconds = samples.length / rate;
    const rms = Math.sqrt(samples.reduce((sum, n) => sum + n * n, 0) / samples.length);
    const active = rms >= Math.max(.012, this.noise * 3);
    if (!active) this.noise = this.noise * .98 + rms * .02;
    this.total += seconds;
    if (active) { this.speech += seconds; this.quiet = 0; } else this.quiet += seconds;
    return { active, rms, seconds: this.total, stop: this.total >= this.max || (this.autoStop && this.speech >= this.min && this.quiet >= this.silence), hasSpeech: this.speech >= this.min };
  }
}

export function encodeWav(chunks, sourceRate, maxSeconds = 180) {
  const length = chunks.reduce((sum, part) => sum + part.length, 0);
  const samples = new Float32Array(length);
  let offset = 0;
  for (const part of chunks) { samples.set(part, offset); offset += part.length; }
  // A worklet block may cross the VAD deadline; never upload beyond the server limit.
  const count = Math.min(Math.floor(length * 16000 / sourceRate), Math.floor(maxSeconds * 16000));
  const bytes = new ArrayBuffer(44 + count * 2); const view = new DataView(bytes);
  const write = (at, text) => [...text].forEach((c, i) => view.setUint8(at + i, c.charCodeAt(0)));
  write(0, "RIFF"); view.setUint32(4, 36 + count * 2, true); write(8, "WAVEfmt ");
  view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, 16000, true); view.setUint32(28, 32000, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  write(36, "data"); view.setUint32(40, count * 2, true);
  for (let i = 0; i < count; i++) {
    // Average each source interval before downsampling; keeps transport portable.
    const start = Math.floor(i * sourceRate / 16000), end = Math.min(length, Math.max(start + 1, Math.floor((i + 1) * sourceRate / 16000)));
    let value = 0; for (let j = start; j < end; j++) value += samples[j]; value /= end - start;
    view.setInt16(44 + i * 2, Math.max(-1, Math.min(1, value)) * (value < 0 ? 32768 : 32767), true);
  }
  return new Blob([bytes], { type: "audio/wav" });
}

// Owns permission requests and streams, including cancellation while permission is pending.
export class CaptureLease {
  constructor() { this.epoch = 0; this.pending = false; this.stream = undefined; }
  async acquire(getStream, isListening) {
    if (this.pending || this.stream) throw new Error("Microphone capture already started.");
    if (!isListening()) throw new Error("The interview is not listening.");
    const epoch = this.epoch; this.pending = true;
    try {
      const stream = await getStream();
      if (epoch !== this.epoch || !isListening()) { stream.getTracks().forEach(track => track.stop()); return undefined; }
      this.stream = stream; return stream;
    } finally { this.pending = false; }
  }
  release() { this.epoch++; const stream = this.stream; this.stream = undefined; stream?.getTracks().forEach(track => track.stop()); }
}
