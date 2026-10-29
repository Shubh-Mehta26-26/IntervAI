// Mouth motion follows decoded playback samples, never a timer pretending to speak.
export function mouthFromSamples(samples, previous = 0) {
  if (!samples.length) return 0;
  const rms = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
  const target = Math.min(1, Math.max(0, (rms - 0.008) * 11));
  return target > previous ? previous + (target - previous) * 0.7 : target;
}

export class AvatarAudio {
  constructor(element, Context) {
    this.element = element;
    this.context = new Context();
    this.analyser = this.context.createAnalyser();
    this.analyser.fftSize = 512;
    this.source = this.context.createMediaElementSource(element);
    this.source.connect(this.analyser);
    this.analyser.connect(this.context.destination);
    this.samples = new Float32Array(this.analyser.fftSize);
    this.mouth = 0;
  }
  resume() { return this.context.resume(); }
  sample() {
    if (this.context.state !== "running" || this.element.paused || this.element.ended || this.element.muted || this.element.volume === 0 || this.element.readyState < 3) {
      this.mouth = 0;
    } else {
      this.analyser.getFloatTimeDomainData(this.samples);
      this.mouth = mouthFromSamples(this.samples, this.mouth);
    }
    return this.mouth;
  }
  dispose() {
    this.element.pause();
    this.source.disconnect();
    this.analyser.disconnect();
    this.mouth = 0;
    return this.context.close();
  }
}

// Cancellation also guards callbacks already queued by the event loop.
export class TranscriptCountdown {
  constructor({ tick, submit, canSubmit, schedule = setInterval, unschedule = clearInterval }) {
    this.active = true;
    this.remaining = 4;
    this.unschedule = unschedule;
    tick(this.remaining);
    this.timer = schedule(() => {
      if (!this.active || !canSubmit()) { this.cancel(); return; }
      this.remaining--;
      tick(this.remaining);
      if (this.remaining === 0) { this.cancel(); submit(); }
    }, 1000);
  }
  cancel() { this.active = false; this.unschedule(this.timer); }
}
