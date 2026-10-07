export class CameraLease { stream: MediaStream | null; pending: boolean; start(mediaDevices: MediaDevices): Promise<MediaStream | null>; stop(): void; }
export function cameraError(error: { name?: string }): string;
export class SampleGate { busy: boolean; sequence: number; run(sample: (sequence: number) => Promise<void>): Promise<boolean>; }
