/** One camera lease and one sampled request at a time; never buffer a frame queue. */
export class CameraLease {
  constructor() { this.generation = 0; this.stream = null; this.pending = false; }
  async start(mediaDevices) {
    if (this.pending || this.stream) throw new Error("Camera is already starting or active.");
    this.pending = true;
    const generation = ++this.generation;
    try {
      const stream = await mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" }, audio: false });
      if (generation !== this.generation) { stream.getTracks().forEach(track => track.stop()); return null; }
      this.stream = stream;
      return stream;
    } finally { this.pending = false; }
  }
  stop() { ++this.generation; this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; }
}

export function cameraError(error) {
  return ({ NotAllowedError: "Camera access is blocked. Allow camera access in your browser’s site settings, then try again.", NotFoundError: "No camera was found. Connect a camera and try again.", NotReadableError: "The camera is unavailable or already in use. Close other camera apps and try again.", OverconstrainedError: "This camera does not support the requested capture settings." })[error?.name] || "Camera could not start. You can continue your interview and try again when ready.";
}

export class SampleGate {
  constructor() { this.busy = false; this.sequence = 0; }
  async run(sample) {
    if (this.busy) return false;
    this.busy = true;
    try { await sample(this.sequence++); return true; }
    finally { this.busy = false; }
  }
}
