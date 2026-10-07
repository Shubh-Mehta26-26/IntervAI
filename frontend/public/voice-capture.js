/* Runs only while the interview is explicitly listening. */
class VoiceCapture extends AudioWorkletProcessor {
  process(inputs, outputs) {
    const samples = inputs[0]?.[0];
    if (samples) this.port.postMessage(samples.slice());
    // Output remains silent: microphone audio is never played back.
    for (const channel of outputs[0] || []) channel.fill(0);
    return true;
  }
}
registerProcessor("voice-capture", VoiceCapture);
