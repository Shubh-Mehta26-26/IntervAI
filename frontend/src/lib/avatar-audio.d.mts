export function mouthFromSamples(samples: Float32Array, previous?: number): number;
export class AvatarAudio {
  constructor(element: HTMLAudioElement, Context: typeof AudioContext);
  resume(): Promise<void>;
  sample(): number;
  dispose(): Promise<void>;
}
export class TranscriptCountdown {
  constructor(options: { tick: (remaining: number) => void; submit: () => void; canSubmit: () => boolean });
  cancel(): void;
}
