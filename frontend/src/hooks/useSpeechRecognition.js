import { useEffect, useRef, useState } from "react";

const SpeechRecognition =
  typeof window !== "undefined"
    ? window.SpeechRecognition || window.webkitSpeechRecognition
    : null;

export const SPEECH_SUPPORTED = !!SpeechRecognition;

export function useSpeechRecognition({ onTranscript } = {}) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);

  useEffect(() => {
    if (!SPEECH_SUPPORTED) return undefined;
    const rec = new SpeechRecognition();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-US";

    rec.onresult = (event) => {
      let finalTranscript = "";
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcript = event.results[i][0].transcript;
        if (event.results[i].isFinal) finalTranscript += transcript;
        else interimTranscript += transcript;
      }
      if (onTranscript) {
        onTranscript({
          finalChunk: finalTranscript,
          interim: interimTranscript,
        });
      }
    };

    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);

    recognitionRef.current = rec;
    return () => {
      try { rec.stop(); } catch (_) { /* noop */ }
    };
  }, [onTranscript]);

  const start = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    try {
      rec.start();
      setListening(true);
    } catch (_) {
      // Already running — ignore.
    }
  };
  const stop = () => {
    const rec = recognitionRef.current;
    if (!rec) return;
    try { rec.stop(); } catch (_) { /* noop */ }
    setListening(false);
  };
  const toggle = () => (listening ? stop() : start());

  return { supported: SPEECH_SUPPORTED, listening, start, stop, toggle };
}
