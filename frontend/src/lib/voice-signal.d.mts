export class ActivityDetector {
  constructor(settings?: { min_speech_seconds?: number; silence_seconds?: number; max_seconds?: number; auto_stop?: boolean });
  push(samples: Float32Array, rate: number): { active: boolean; rms: number; seconds: number; stop: boolean; hasSpeech: boolean };
}
export function encodeWav(chunks: Float32Array[], sourceRate: number, maxSeconds?: number): Blob;
export class CaptureLease {
  acquire(getStream: () => Promise<MediaStream>, isListening: () => boolean): Promise<MediaStream | undefined>;
  release(): void;
}
