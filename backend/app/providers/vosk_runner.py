"""Private subprocess entry point, bounded by speech adapter timeout."""

import io
import json
import sys
import wave

from vosk import KaldiRecognizer, Model, SetLogLevel

SetLogLevel(-1)
model = Model(sys.argv[1])
with wave.open(io.BytesIO(sys.stdin.buffer.read(6 * 1024 * 1024))) as audio:
    recognizer = KaldiRecognizer(model, audio.getframerate())
    recognizer.SetWords(True)
    pieces, words = [], []
    while data := audio.readframes(4000):
        if recognizer.AcceptWaveform(data):
            item = json.loads(recognizer.Result())
            pieces.append(item.get("text", ""))
            words.extend(item.get("result", []))
    item = json.loads(recognizer.FinalResult())
    pieces.append(item.get("text", ""))
    words.extend(item.get("result", []))
print(json.dumps({"text": " ".join(x for x in pieces if x), "segments": words}))
